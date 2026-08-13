"""Adopted start/finish workflow orchestration independent of CLI presentation."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from ..documents.validation import expand_markdown_paths, validate_documents
from ..policy.manifest import Check, Manifest, ReviewerDeclaration
from ..project.classifier import Change, classify_changes, git_changes, git_commit
from ..project.context import load_adopted_project
from ..project.discovery import discover_instructions, discover_project
from ..reviewers.semantic import build_review_packet, run_review
from ..verification.checks import CheckResult, inspect_check_executable, run_check
from ..verification.fitness import Selection, select_affected, validate_fitness
from ..verification.fitness import from_manifest as fitness_from_manifest
from ..verification.generated import from_manifest as generated_from_manifest
from ..verification.generated import run_generator, verify_generated
from .baseline import (
    BaselineIdentity,
    BaselineRecord,
    CheckRecord,
    ToolIdentity,
    fingerprint_paths,
    incompatibilities,
    manifest_digest,
    read_baseline,
    record_digest,
    tool_identities_digest,
)
from .evidence import compare
from .evidence import to_json as evidence_json
from .lifecycle import (
    AuthorityRecord,
    ChangeFact,
    CheckPlan,
    ClassificationFact,
    EvidenceFact,
    FinishRecord,
    FitnessPlan,
    LifecycleError,
    ReviewPlan,
    StartRecord,
    ValidationFact,
    read_start,
    start_digest,
    write_finish,
    write_start_bundle,
)
from .rendering import render_finish, render_start


@dataclass(frozen=True)
class WorkflowResult:
    status: str
    root: Path
    data: dict[str, Any]
    human: str | None = None


def _result_status(results: Sequence[CheckResult]) -> str:
    statuses = {result.status for result in results}
    if statuses & {"failed", "timed_out"}:
        return "failed"
    if "unavailable" in statuses:
        return "unavailable"
    return "passed"


def _check_records(results: Sequence[CheckResult]) -> tuple[CheckRecord, ...]:
    return tuple(
        CheckRecord(
            result.name,
            result.status,
            result.exit_code,
            round(result.duration_seconds * 1000),
            result.stdout + result.stderr,
        )
        for result in results
    )


def _identity(
    root: Path,
    manifest: Manifest,
    profile: str,
    tools: Sequence[ToolIdentity],
    *,
    repository_state: tuple[str | None, str] | None = None,
) -> BaselineIdentity:
    commit, dirty_fingerprint = repository_state or _repository_state(root)
    return BaselineIdentity(
        str(root.resolve()),
        commit,
        dirty_fingerprint,
        manifest_digest(manifest.raw),
        profile,
        "engineering/0.1.0",
        tool_identities_digest(tools),
    )


def _repository_state(root: Path) -> tuple[str | None, str]:
    try:
        paths = [
            change.path
            for change in git_changes(root)
            if change.path != ".engineering" and not change.path.startswith(".engineering/")
        ]
    except (OSError, RuntimeError, subprocess.SubprocessError):
        paths = []
    return git_commit(root), fingerprint_paths(root, paths)


def _tool_identities_for_checks(checks: Sequence[Check], root: Path) -> tuple[ToolIdentity, ...]:
    tools: list[ToolIdentity] = []
    for check in checks:
        identity = inspect_check_executable(check, root)
        tools.append(
            ToolIdentity(
                check=check.name,
                executable=identity.executable,
                resolved_executable=identity.resolved_executable,
                executable_sha256=identity.executable_sha256,
                version_command=identity.version_command,
                version_status=identity.version_status,
                version_output=identity.version_output,
            )
        )
    return tuple(tools)


def _validate_requested_paths(paths: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in paths:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or "\x00" in value
            or any(character in value for character in "*?[")
        ):
            raise ValueError(f"invalid repository-relative requested path: {value!r}")
        normalized.append(path.as_posix())
    return tuple(dict.fromkeys(normalized))


def _recovery_code(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9._-]{0,79}", value):
        raise ValueError(
            f"invalid manual recovery code {value!r}; use a non-sensitive lowercase identifier"
        )
    return value


def _authority(
    project_root: Path,
    manifest_path: Path,
    start_path: str | Path,
    global_agents: str | Path | None,
    *,
    refuse_drift: bool = True,
) -> tuple[AuthorityRecord, ...]:
    project = discover_project(start_path)
    instructions = discover_instructions(project, start_path, global_agents=global_agents)
    if refuse_drift and any(item.drift for item in instructions):
        raise ValueError("instruction drift must be resolved before starting a run")
    authority = [
        AuthorityRecord(
            item.kind,
            (
                item.path.relative_to(project_root).as_posix()
                if item.path.is_relative_to(project_root)
                else str(item.path)
            ),
            item.sha256,
            item.precedence,
            item.drift,
        )
        for item in instructions
    ]
    authority.append(
        AuthorityRecord(
            "manifest",
            manifest_path.relative_to(project_root).as_posix(),
            hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            len(authority),
        )
    )
    return tuple(authority)


def _project_changes(root: Path) -> tuple[Change, ...]:
    return tuple(
        item
        for item in git_changes(root)
        if item.path != ".engineering" and not item.path.startswith(".engineering/")
    )


def _selection_plan(
    manifest: Manifest,
    root: Path,
    paths: Sequence[str],
    *,
    full: bool = False,
) -> tuple[dict[str, Selection], tuple[FitnessPlan, ...]]:
    check_selections = {
        item.check: item
        for item in select_affected(
            paths,
            {name: check.applies_to for name, check in manifest.checks.items()},
            full=full,
        )
    }
    issues_by_name: dict[str, list[str]] = {}
    for issue in validate_fitness(root, fitness_from_manifest(manifest)):
        issues_by_name.setdefault(issue.fitness, []).append(issue.code)
    fitness_selections = {
        item.check: item
        for item in select_affected(
            paths,
            {declaration.name: declaration.applies_to for declaration in manifest.fitness},
            full=full,
        )
    }
    fitness_plans: list[FitnessPlan] = []
    for declaration in manifest.fitness:
        selection = fitness_selections[declaration.name]
        fitness_plans.append(
            FitnessPlan(
                declaration.name,
                declaration.check,
                selection.selected,
                selection.reason,
                declaration.references,
                tuple(issues_by_name.get(declaration.name, ())),
            )
        )
        if selection.selected and not check_selections[declaration.check].selected:
            check_selections[declaration.check] = Selection(
                declaration.check,
                True,
                f"required by applicable fitness function {declaration.name!r}",
            )
    return check_selections, tuple(fitness_plans)


def start_run(
    start: str | Path,
    *,
    intent: str,
    paths: Sequence[str] = (),
    run_id: str | None = None,
    global_agents: str | Path | None = None,
) -> WorkflowResult:
    if not intent.strip():
        raise ValueError("intent must not be empty")
    adopted = load_adopted_project(start)
    root, manifest, project = adopted.root, adopted.manifest, adopted.discovery
    requested_paths = _validate_requested_paths(paths)
    authority = _authority(root, manifest.path, start, global_agents)
    try:
        preexisting = _project_changes(root) if project.git_root is not None else ()
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return WorkflowResult("unavailable", root, {"reason": str(exc)})
    known_paths = {item.path for item in preexisting}
    prospective = tuple(
        Change(path, "intent") for path in requested_paths if path not in known_paths
    )
    classifications = classify_changes(
        (*preexisting, *prospective),
        manifest.classifiers,
        manifest.approval_required,
    )
    approvals = tuple(
        dict.fromkeys(item.category for item in classifications if item.approval_required)
    )
    affected_paths = requested_paths or tuple(item.path for item in preexisting)
    check_selections, fitness_plans = _selection_plan(manifest, root, affected_paths)
    selected_checks = tuple(
        manifest.checks[name] for name in manifest.checks if check_selections[name].selected
    )
    repository_state = _repository_state(root)
    tools = _tool_identities_for_checks(selected_checks, root)
    identity = _identity(root, manifest, "start", tools, repository_state=repository_state)
    results = tuple(run_check(check, root) for check in selected_checks)
    result_by_name = {result.name: result for result in results}
    baseline_checks: list[CheckRecord] = []
    check_plans: list[CheckPlan] = []
    for name in manifest.checks:
        selection = check_selections[name]
        record = (
            _check_records((result_by_name[name],))[0]
            if selection.selected
            else CheckRecord(name, "not_applicable", None, 0, "")
        )
        baseline_checks.append(record)
        check_plans.append(CheckPlan(name, selection.selected, selection.reason, record.status))
    baseline = BaselineRecord(identity, tuple(baseline_checks), tools)
    selected_run_id = run_id or hashlib.sha256(os.urandom(32)).hexdigest()[:16]
    start_record = StartRecord(
        run_id=selected_run_id,
        intent=intent.strip(),
        requested_paths=requested_paths,
        authority=authority,
        baseline_digest=record_digest(baseline),
        preexisting_changes=tuple(
            ChangeFact(item.path, item.status, item.old_path) for item in preexisting
        ),
        classifications=tuple(
            ClassificationFact(
                item.category,
                item.path,
                item.rule,
                item.evidence,
                item.approval_required,
            )
            for item in classifications
        ),
        approvals_required=approvals,
        checks=tuple(check_plans),
        fitness=fitness_plans,
        next_command=f"engineering finish {selected_run_id}",
    )
    baseline_path, start_path = write_start_bundle(root, selected_run_id, baseline, start_record)
    status = "approval_required" if approvals else _result_status(results)
    return WorkflowResult(
        status,
        root,
        {
            "run_id": selected_run_id,
            "baseline": baseline_path.relative_to(root).as_posix(),
            "start": start_path.relative_to(root).as_posix(),
            "record": asdict(start_record),
            "results": [result.to_dict() for result in results],
        },
        render_start(start_record),
    )


def _authority_changes(
    before: Sequence[AuthorityRecord], after: Sequence[AuthorityRecord]
) -> tuple[str, ...]:
    old = {(item.kind, item.path): (item.sha256, item.precedence, item.drift) for item in before}
    new = {(item.kind, item.path): (item.sha256, item.precedence, item.drift) for item in after}
    changes: list[str] = []
    for key in sorted(old.keys() | new.keys()):
        if key not in old:
            changes.append(f"added:{key[0]}:{key[1]}")
        elif key not in new:
            changes.append(f"removed:{key[0]}:{key[1]}")
        elif old[key] != new[key]:
            changes.append(f"changed:{key[0]}:{key[1]}")
    return tuple(changes)


def _within_declared_scope(path: str, requested: Sequence[str]) -> bool:
    return any(path == item or path.startswith(f"{item.rstrip('/')}/") for item in requested)


def _finish_validations(
    root: Path,
    manifest: Manifest,
    actual_paths: Sequence[str],
    *,
    full: bool,
) -> tuple[ValidationFact, ...]:
    facts: list[ValidationFact] = []
    docs_selection = select_affected(
        actual_paths,
        {"docs": manifest.docs.include or ("**/*.md",)},
        full=full,
    )[0]
    if docs_selection.selected:
        paths = expand_markdown_paths(root, manifest.docs.include or ("**/*.md",))
        for item in validate_documents(root, manifest.docs, paths):
            facts.append(
                ValidationFact("docs", item.code, f"{item.path}:{item.line}", item.message)
            )
    generated = generated_from_manifest(manifest)
    generated_selections = {
        item.check: item
        for item in select_affected(
            actual_paths,
            {item.name: (*item.sources, *item.outputs) for item in generated},
            full=full,
        )
    }
    for item in generated:
        if not generated_selections[item.name].selected:
            continue
        for finding in verify_generated(root, item, run_generator):
            facts.append(
                ValidationFact(
                    f"generated:{item.name}",
                    finding.code,
                    finding.path or "",
                    finding.message,
                )
            )
    return tuple(facts)


def _reviewer_blocking(declaration: ReviewerDeclaration) -> tuple[bool, str]:
    if not declaration.blocking:
        return False, "advisory project policy"
    if declaration.exception_expires is not None:
        expires = date.fromisoformat(declaration.exception_expires)
        if expires >= datetime.now(UTC).date():
            return False, (
                f"blocking exception through {expires.isoformat()}: {declaration.exception_reason}"
            )
    return True, f"blocking project policy owned by {declaration.owner}"


def finish_run(
    start: str | Path,
    run_id: str,
    *,
    full: bool = False,
    global_agents: str | Path | None = None,
    manual_recovery: Sequence[str] = (),
) -> WorkflowResult:
    if (
        not run_id
        or run_id in {".", ".."}
        or any(character in run_id for character in ("/", "\\", "\x00"))
    ):
        raise LifecycleError("invalid run id")
    adopted = load_adopted_project(start)
    root, manifest, project = adopted.root, adopted.manifest, adopted.discovery
    run_directory = root / ".engineering" / "runs" / run_id
    baseline = read_baseline(run_directory / "baseline.json")
    start_record = read_start(run_directory / "start.json")
    if start_record.run_id != run_id:
        raise LifecycleError("start record run id does not match target")
    if start_record.baseline_digest != record_digest(baseline):
        raise LifecycleError("start record does not bind the stored baseline")
    sealed_global = next(
        (item.path for item in start_record.authority if item.kind == "global"),
        None,
    )
    current_authority = _authority(
        root,
        manifest.path,
        start,
        global_agents or sealed_global,
        refuse_drift=False,
    )
    authority_changes = _authority_changes(start_record.authority, current_authority)
    if authority_changes:
        return WorkflowResult(
            "incompatible",
            root,
            {
                "run_id": run_id,
                "incompatible_fields": ["authority"],
                "authority_changes": list(authority_changes),
            },
        )
    try:
        actual_changes = _project_changes(root) if project.git_root is not None else ()
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return WorkflowResult("unavailable", root, {"reason": str(exc)})
    actual_paths = tuple(item.path for item in actual_changes)
    check_selections, fitness_plans = _selection_plan(manifest, root, actual_paths, full=full)
    reviewer_declarations = tuple(manifest.reviewers.values())
    for plan in start_record.checks:
        if plan.selected and not check_selections[plan.name].selected:
            check_selections[plan.name] = Selection(
                plan.name,
                True,
                "selected by the immutable start contract",
            )
    selected_checks = tuple(
        manifest.checks[name] for name in manifest.checks if check_selections[name].selected
    )
    repository_state = _repository_state(root)
    tools = _tool_identities_for_checks(selected_checks, root)
    baseline_tool_names = {item.check for item in baseline.tools}
    compatibility_tools = tuple(item for item in tools if item.check in baseline_tool_names)
    compatibility_identity = _identity(
        root,
        manifest,
        baseline.identity.profile,
        compatibility_tools,
        repository_state=repository_state,
    )
    incompatible = incompatibilities(baseline.identity, compatibility_identity)
    if incompatible:
        return WorkflowResult(
            "incompatible",
            root,
            {"run_id": run_id, "incompatible_fields": list(incompatible)},
        )
    results = tuple(run_check(check, root) for check in selected_checks)
    result_by_name = {item.name: item for item in results}
    final_checks: list[CheckRecord] = []
    check_plans: list[CheckPlan] = []
    for name in manifest.checks:
        selection = check_selections[name]
        check_record = (
            _check_records((result_by_name[name],))[0]
            if selection.selected
            else CheckRecord(name, "not_applicable", None, 0, "")
        )
        final_checks.append(check_record)
        check_plans.append(
            CheckPlan(name, selection.selected, selection.reason, check_record.status)
        )
    try:
        final_changes = _project_changes(root) if project.git_root is not None else ()
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return WorkflowResult("unavailable", root, {"reason": str(exc)})
    final_paths = tuple(item.path for item in final_changes)
    final_selections, final_fitness_plans = _selection_plan(manifest, root, final_paths, full=full)
    late_applicable: list[str] = []
    for index, plan in enumerate(check_plans):
        if not plan.selected and final_selections[plan.name].selected:
            late_applicable.append(plan.name)
            final_checks[index] = CheckRecord(plan.name, "skipped", None, 0, "")
            check_plans[index] = CheckPlan(
                plan.name,
                False,
                "became applicable after verification subprocesses ran",
                "skipped",
            )
    fitness_plans = tuple(
        final_plan if final_plan.selected and not initial_plan.selected else initial_plan
        for initial_plan, final_plan in zip(fitness_plans, final_fitness_plans, strict=True)
    )
    classifications = classify_changes(
        final_changes,
        manifest.classifiers,
        manifest.approval_required,
    )
    approvals = tuple(
        dict.fromkeys(item.category for item in classifications if item.approval_required)
    )
    validations = _finish_validations(root, manifest, final_paths, full=full)
    final_identity = _identity(root, manifest, "start", tools)
    evidence_items = compare(baseline.checks, final_checks)
    evidence_facts = tuple(
        EvidenceFact(
            item.name,
            item.classification,
            item.baseline.status if item.baseline else None,
            item.final.status if item.final else None,
        )
        for item in evidence_items
    )
    preexisting_paths = {item.path for item in start_record.preexisting_changes}
    unexpected_paths = tuple(
        sorted(
            item.path
            for item in final_changes
            if item.path not in preexisting_paths
            and not _within_declared_scope(item.path, start_record.requested_paths)
        )
    )
    start_classifications = {(item.category, item.path) for item in start_record.classifications}
    scope_expansions = tuple(
        sorted(
            f"{item.category}:{item.path}"
            for item in classifications
            if (item.category, item.path) not in start_classifications
        )
    )
    preexisting_failures = tuple(
        item.name
        for item in baseline.checks
        if item.status in {"failed", "timed_out", "unavailable"}
    )
    checks_not_run = tuple(
        f"{item.name}: {item.reason}" for item in check_plans if not item.selected
    )
    passed = sum(item.status == "passed" for item in final_checks)
    claims = (
        f"Executed {len(results)} selected declared checks; {passed} passed.",
        f"Compared {len(evidence_facts)} declared check states with the immutable baseline.",
        "Validated only the declared deterministic surfaces recorded in this artifact.",
    )
    assumptions = (
        (
            "Requested paths define intended scope; pre-existing changes are preserved separately."
            if start_record.requested_paths
            else (
                "No requested paths were declared; every non-pre-existing changed path is treated "
                "as unexpected."
            )
        ),
    )
    manual_recovery_steps = tuple(dict.fromkeys(_recovery_code(value) for value in manual_recovery))
    reviewer_selections = {
        item.check: item
        for item in select_affected(
            final_paths,
            {item.name: item.applies_to for item in reviewer_declarations},
            full=full,
        )
    }
    review_results = []
    review_plans: list[ReviewPlan] = []
    review_evidence = {
        "checks": [asdict(item) for item in final_checks],
        "fitness": [asdict(item) for item in fitness_plans],
        "comparisons": [asdict(item) for item in evidence_facts],
        "validations": [asdict(item) for item in validations],
        "claims": list(claims),
        "assumptions": list(assumptions),
    }
    included_review_evidence = (
        "stated intent and requested paths",
        "final changed paths and deterministic classifications",
        "declared check, fitness, and validation evidence",
        "candidate completion claims and assumptions",
        "repository files available in an isolated copy except declared exclusions",
    )
    omitted_review_evidence = (
        "hidden reasoning traces",
        "production runtime state and traces not present in the repository",
        "credentials and paths declared sensitive or forbidden by project policy",
    )
    excluded_review_paths = tuple(
        dict.fromkeys((*manifest.paths.sensitive, *manifest.paths.forbidden))
    )
    for declaration in reviewer_declarations:
        selection = reviewer_selections[declaration.name]
        effective_blocking, policy_reason = _reviewer_blocking(declaration)
        for profile in declaration.profiles:
            if not selection.selected:
                review_plans.append(
                    ReviewPlan(
                        declaration.name,
                        profile,
                        False,
                        selection.reason,
                        "not_applicable",
                        effective_blocking,
                        declaration.owner,
                    )
                )
                continue
            packet = build_review_packet(
                profile,
                intent=start_record.intent,
                requested_paths=start_record.requested_paths,
                actual_changes=tuple(asdict(item) for item in final_changes),
                classifications=tuple(asdict(item) for item in classifications),
                evidence=review_evidence,
                included_evidence=included_review_evidence,
                omitted_evidence=omitted_review_evidence,
            )
            result = run_review(
                declaration,
                root,
                profile,
                packet,
                excluded_patterns=excluded_review_paths,
            )
            review_results.append(result)
            outcome = (
                f"{result.status}; verdict={result.verdict}; {policy_reason}"
                if result.verdict is not None
                else f"{result.status}; {result.reason}; {policy_reason}"
            )
            review_plans.append(
                ReviewPlan(
                    declaration.name,
                    profile,
                    True,
                    outcome,
                    result.status,
                    effective_blocking,
                    declaration.owner,
                )
            )
    residual_risks: list[str] = [
        "Deterministic checks do not establish semantic or system-level correctness."
    ]
    if unexpected_paths:
        residual_risks.append(
            f"Unexpected changed paths require review: {', '.join(unexpected_paths)}"
        )
    if scope_expansions:
        residual_risks.append(f"Change classifications expanded: {', '.join(scope_expansions)}")
    if approvals:
        residual_risks.append(f"Outstanding approvals: {', '.join(approvals)}")
    if validations:
        residual_risks.append(f"Documentation/generated validation findings: {len(validations)}")
    if late_applicable:
        residual_risks.append(
            "Checks became applicable after verification and were not run: "
            f"{', '.join(late_applicable)}"
        )
    unhealthy_reviews = tuple(
        f"{item.reviewer}/{item.profile}"
        for item in review_results
        if item.status != "completed" or item.verdict in {"concern", "incomplete"} or item.findings
    )
    if unhealthy_reviews:
        residual_risks.append(
            "Semantic review findings or unknowns require human review: "
            f"{', '.join(unhealthy_reviews)}"
        )
    if review_results:
        residual_risks.append(
            "Semantic review records examined evidence and unknowns; a no-finding verdict does not "
            "prove correctness."
        )
    failed_states = tuple(
        item.name for item in final_checks if item.status in {"failed", "timed_out", "unavailable"}
    )
    if failed_states:
        residual_risks.append(f"Checks not passing: {', '.join(failed_states)}")
    finish_record = FinishRecord(
        run_id=run_id,
        baseline_digest=record_digest(baseline),
        start_digest=start_digest(start_record),
        identity=final_identity,
        checks=tuple(final_checks),
        tools=tools,
        authority=current_authority,
        authority_changes=authority_changes,
        actual_changes=tuple(
            ChangeFact(item.path, item.status, item.old_path) for item in final_changes
        ),
        classifications=tuple(
            ClassificationFact(
                item.category,
                item.path,
                item.rule,
                item.evidence,
                item.approval_required,
            )
            for item in classifications
        ),
        approvals_required=approvals,
        unexpected_paths=unexpected_paths,
        scope_expansions=scope_expansions,
        check_plans=tuple(check_plans),
        fitness=fitness_plans,
        evidence=evidence_facts,
        validations=validations,
        capability_plans=(),
        capabilities=(),
        review_plans=tuple(review_plans),
        reviews=tuple(review_results),
        claims=claims,
        checks_not_run=checks_not_run,
        preexisting_failures=preexisting_failures,
        manual_recovery_steps=manual_recovery_steps,
        assumptions=assumptions,
        residual_risks=tuple(residual_risks),
    )
    final_path = write_finish(root, run_id, finish_record)
    result_status = _result_status(results)
    blocking_review_failure = any(
        plan.blocking
        and plan.selected
        and (
            plan.status != "completed"
            or next(
                item.verdict
                for item in review_results
                if item.reviewer == plan.reviewer and item.profile == plan.profile
            )
            != "pass"
        )
        for plan in review_plans
    )
    if approvals:
        status = "approval_required"
    elif (
        result_status == "failed"
        or validations
        or unexpected_paths
        or scope_expansions
        or late_applicable
        or blocking_review_failure
    ):
        status = "failed"
    elif result_status == "unavailable":
        status = "unavailable"
    elif unhealthy_reviews:
        status = "passed_with_advisories"
    else:
        status = "passed"
    return WorkflowResult(
        status,
        root,
        {
            "run_id": run_id,
            "final": final_path.relative_to(root).as_posix(),
            "record": asdict(finish_record),
            "summary": evidence_json(evidence_items)["summary"],
        },
        render_finish(finish_record),
    )
