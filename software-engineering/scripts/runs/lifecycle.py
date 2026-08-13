"""Immutable aggregate lifecycle records."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..reviewers.semantic import (
    ReviewCitation,
    ReviewDismissal,
    ReviewerIdentity,
    ReviewFinding,
    ReviewResult,
)
from .baseline import (
    BaselineIdentity,
    BaselineRecord,
    CheckRecord,
    ToolIdentity,
    record_digest,
)

SCHEMA_VERSION = 1
CHECK_STATES = {
    "passed",
    "failed",
    "unavailable",
    "timed_out",
    "skipped",
    "not_applicable",
}


class LifecycleError(ValueError):
    """A lifecycle run is invalid, incomplete, or immutable."""


@dataclass(frozen=True)
class AuthorityRecord:
    kind: str
    path: str
    sha256: str
    precedence: int
    drift: str | None = None


@dataclass(frozen=True)
class ChangeFact:
    path: str
    status: str
    old_path: str | None = None


@dataclass(frozen=True)
class ClassificationFact:
    category: str
    path: str
    rule: str
    evidence: str
    approval_required: bool


@dataclass(frozen=True)
class CheckPlan:
    name: str
    selected: bool
    reason: str
    baseline_status: str


@dataclass(frozen=True)
class FitnessPlan:
    name: str
    check: str
    selected: bool
    reason: str
    references: tuple[str, ...]
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StartRecord:
    run_id: str
    intent: str
    requested_paths: tuple[str, ...]
    authority: tuple[AuthorityRecord, ...]
    baseline_digest: str
    preexisting_changes: tuple[ChangeFact, ...]
    classifications: tuple[ClassificationFact, ...]
    approvals_required: tuple[str, ...]
    checks: tuple[CheckPlan, ...]
    fitness: tuple[FitnessPlan, ...]
    next_command: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class EvidenceFact:
    name: str
    classification: str
    baseline_status: str | None
    final_status: str | None


@dataclass(frozen=True)
class ValidationFact:
    source: str
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class CapabilityPlan:
    name: str
    selected: bool
    reason: str
    status: str
    blocking: bool


@dataclass(frozen=True)
class ReviewPlan:
    reviewer: str
    profile: str
    selected: bool
    reason: str
    status: str
    blocking: bool
    owner: str | None


@dataclass(frozen=True)
class FinishRecord:
    run_id: str
    baseline_digest: str
    start_digest: str
    identity: BaselineIdentity
    checks: tuple[CheckRecord, ...]
    tools: tuple[ToolIdentity, ...]
    authority: tuple[AuthorityRecord, ...]
    authority_changes: tuple[str, ...]
    actual_changes: tuple[ChangeFact, ...]
    classifications: tuple[ClassificationFact, ...]
    approvals_required: tuple[str, ...]
    unexpected_paths: tuple[str, ...]
    scope_expansions: tuple[str, ...]
    check_plans: tuple[CheckPlan, ...]
    fitness: tuple[FitnessPlan, ...]
    evidence: tuple[EvidenceFact, ...]
    validations: tuple[ValidationFact, ...]
    capability_plans: tuple[CapabilityPlan, ...]
    capabilities: tuple[dict[str, Any], ...]
    review_plans: tuple[ReviewPlan, ...]
    reviews: tuple[ReviewResult, ...]
    claims: tuple[str, ...]
    checks_not_run: tuple[str, ...]
    preexisting_failures: tuple[str, ...]
    manual_recovery_steps: tuple[str, ...]
    assumptions: tuple[str, ...]
    residual_risks: tuple[str, ...]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = SCHEMA_VERSION


def write_start_bundle(
    root: Path,
    run_id: str,
    baseline: BaselineRecord,
    start: StartRecord,
) -> tuple[Path, Path]:
    """Atomically publish baseline and start records as one immutable run."""
    _validate_run_id(run_id)
    if start.run_id != run_id:
        raise LifecycleError("start record run id does not match target")
    if start.baseline_digest != record_digest(baseline):
        raise LifecycleError("start record baseline digest does not match baseline")
    root = root.resolve()
    runs = root / ".engineering" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    target = runs / run_id
    if target.exists():
        raise LifecycleError(f"run already exists: {run_id}")
    staging = Path(tempfile.mkdtemp(prefix=".start-", dir=runs))
    try:
        _write_sealed(staging / "baseline.json", asdict(baseline))
        _write_sealed(staging / "start.json", asdict(start))
        directory_fd = os.open(staging, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.rename(staging, target)
        runs_fd = os.open(runs, os.O_RDONLY)
        try:
            os.fsync(runs_fd)
        finally:
            os.close(runs_fd)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return target / "baseline.json", target / "start.json"


def read_start(path: Path) -> StartRecord:
    payload = _read_sealed(path)
    try:
        if payload["schema_version"] != SCHEMA_VERSION:
            raise LifecycleError("unsupported start schema version")
        checks = tuple(CheckPlan(**item) for item in payload["checks"])
        if any(item.baseline_status not in CHECK_STATES for item in checks):
            raise LifecycleError("start record contains unknown check state")
        return StartRecord(
            run_id=payload["run_id"],
            intent=payload["intent"],
            requested_paths=tuple(payload["requested_paths"]),
            authority=tuple(AuthorityRecord(**item) for item in payload["authority"]),
            baseline_digest=payload["baseline_digest"],
            preexisting_changes=tuple(
                ChangeFact(**item) for item in payload["preexisting_changes"]
            ),
            classifications=tuple(
                ClassificationFact(**item) for item in payload["classifications"]
            ),
            approvals_required=tuple(payload["approvals_required"]),
            checks=checks,
            fitness=tuple(
                FitnessPlan(
                    **{
                        **item,
                        "references": tuple(item["references"]),
                        "findings": tuple(item.get("findings", ())),
                    }
                )
                for item in payload["fitness"]
            ),
            next_command=payload["next_command"],
            created_at=payload["created_at"],
            schema_version=payload["schema_version"],
        )
    except LifecycleError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise LifecycleError("malformed start record") from exc


def start_digest(record: StartRecord) -> str:
    return _seal(asdict(record))


def write_finish(root: Path, run_id: str, record: FinishRecord) -> Path:
    """Atomically add an immutable aggregate final record to a started run."""
    _validate_run_id(run_id)
    if record.run_id != run_id:
        raise LifecycleError("finish record run id does not match target")
    directory = root.resolve() / ".engineering" / "runs" / run_id
    if not directory.is_dir():
        raise LifecycleError(f"start run does not exist: {run_id}")
    target = directory / "final.json"
    if target.exists():
        raise LifecycleError(f"final record already exists: {run_id}")
    fd, temporary = tempfile.mkstemp(prefix=".final-", dir=directory)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            _dump_sealed(handle, asdict(record))
        temporary_path.chmod(0o444)
        os.replace(temporary_path, target)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return target


def read_finish(path: Path) -> FinishRecord:
    payload = _read_sealed(path)
    try:
        if payload["schema_version"] != SCHEMA_VERSION:
            raise LifecycleError("unsupported finish schema version")
        checks = tuple(CheckRecord(**item) for item in payload["checks"])
        if any(item.status not in CHECK_STATES for item in checks):
            raise LifecycleError("finish record contains unknown check state")
        return FinishRecord(
            run_id=payload["run_id"],
            baseline_digest=payload["baseline_digest"],
            start_digest=payload["start_digest"],
            identity=BaselineIdentity(**payload["identity"]),
            checks=checks,
            tools=tuple(
                ToolIdentity(
                    **{
                        **item,
                        "version_command": (
                            tuple(item["version_command"])
                            if item.get("version_command") is not None
                            else None
                        ),
                    }
                )
                for item in payload["tools"]
            ),
            authority=tuple(AuthorityRecord(**item) for item in payload["authority"]),
            authority_changes=tuple(payload["authority_changes"]),
            actual_changes=tuple(ChangeFact(**item) for item in payload["actual_changes"]),
            classifications=tuple(
                ClassificationFact(**item) for item in payload["classifications"]
            ),
            approvals_required=tuple(payload["approvals_required"]),
            unexpected_paths=tuple(payload["unexpected_paths"]),
            scope_expansions=tuple(payload["scope_expansions"]),
            check_plans=tuple(CheckPlan(**item) for item in payload["check_plans"]),
            fitness=tuple(
                FitnessPlan(
                    **{
                        **item,
                        "references": tuple(item["references"]),
                        "findings": tuple(item.get("findings", ())),
                    }
                )
                for item in payload["fitness"]
            ),
            evidence=tuple(EvidenceFact(**item) for item in payload["evidence"]),
            validations=tuple(ValidationFact(**item) for item in payload["validations"]),
            capability_plans=tuple(CapabilityPlan(**item) for item in payload["capability_plans"]),
            capabilities=tuple(payload.get("capabilities", ())),
            review_plans=tuple(ReviewPlan(**item) for item in payload["review_plans"]),
            reviews=tuple(_review_result(item) for item in payload["reviews"]),
            claims=tuple(payload["claims"]),
            checks_not_run=tuple(payload["checks_not_run"]),
            preexisting_failures=tuple(payload["preexisting_failures"]),
            manual_recovery_steps=tuple(payload.get("manual_recovery_steps", ())),
            assumptions=tuple(payload["assumptions"]),
            residual_risks=tuple(payload["residual_risks"]),
            created_at=payload["created_at"],
            schema_version=payload["schema_version"],
        )
    except LifecycleError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise LifecycleError("malformed finish record") from exc


def _review_result(item: dict[str, Any]) -> ReviewResult:
    raw_identity = item["identity"]
    version_command = (
        tuple(raw_identity["version_command"])
        if raw_identity.get("version_command") is not None
        else None
    )
    if "reviewer" in raw_identity:
        identity = {**raw_identity, "version_command": version_command}
    else:
        # Read pre-migration semantic-review records without retaining the generic
        # adapter runtime that originally produced them.
        identity = {
            "reviewer": raw_identity["capability"],
            "adapter": raw_identity["adapter"],
            "executable": raw_identity["invoke_executable"],
            "resolved_executable": raw_identity["resolved_invoke_executable"],
            "executable_sha256": raw_identity["invoke_executable_sha256"],
            "version_command": version_command,
            "version_status": raw_identity["version_status"],
            "version_output": raw_identity["version_output"],
            "network": raw_identity["network"],
        }
    return ReviewResult(
        reviewer=item["reviewer"],
        profile=item["profile"],
        status=item["status"],
        verdict=item["verdict"],
        confidence=item["confidence"],
        provider=item["provider"],
        model=item["model"],
        findings=tuple(
            ReviewFinding(
                id=finding["id"],
                severity=finding["severity"],
                basis=finding["basis"],
                observation=finding["observation"],
                recommendation=finding["recommendation"],
                evidence=tuple(ReviewCitation(**citation) for citation in finding["evidence"]),
                causal_link=finding.get("causal_link"),
            )
            for finding in item["findings"]
        ),
        dismissed_findings=tuple(
            ReviewDismissal(
                id=dismissal["id"],
                reason=dismissal["reason"],
                evidence=tuple(ReviewCitation(**citation) for citation in dismissal["evidence"]),
            )
            for dismissal in item["dismissed_findings"]
        ),
        examined=tuple(item["examined"]),
        omitted=tuple(item["omitted"]),
        causal_links_examined=tuple(item["causal_links_examined"]),
        interaction_classes_examined=tuple(item["interaction_classes_examined"]),
        unknown_causal_links=tuple(item["unknown_causal_links"]),
        identity=ReviewerIdentity(**identity),
        profile_digest=item["profile_digest"],
        input_digest=item["input_digest"],
        output_digest=item["output_digest"],
        duration_ms=item["duration_ms"],
        output_truncated=item["output_truncated"],
        mutation_paths=tuple(item["mutation_paths"]),
        reason=item.get("reason", ""),
        schema_version=item["schema_version"],
    )


def _validate_run_id(run_id: str) -> None:
    if (
        not run_id
        or run_id in {".", ".."}
        or any(character in run_id for character in ("/", "\\", "\x00"))
    ):
        raise LifecycleError("invalid run id")


def _write_sealed(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        _dump_sealed(handle, payload)
    path.chmod(0o444)


def _dump_sealed(handle, payload: dict[str, Any]) -> None:
    envelope = {"record": payload, "integrity": {"sha256": _seal(payload)}}
    json.dump(envelope, handle, sort_keys=True, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())


def _read_sealed(path: Path) -> dict[str, Any]:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope["record"]
        if envelope["integrity"]["sha256"] != _seal(payload):
            raise LifecycleError("start integrity check failed")
        return payload
    except LifecycleError:
        raise
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LifecycleError("malformed start record") from exc


def _seal(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
