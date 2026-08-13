"""Read-only aggregation of diagnostics produced by other components."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from ..documents.validation import expand_markdown_paths, validate_documents
from ..policy.manifest import Manifest
from ..project.discovery import discover_instructions, discover_project
from ..project.health import (
    inspect_ci_coverage,
    inspect_command_availability,
    inspect_path_policy,
    inspect_project_templates,
    inspect_reviewer_health,
)
from .fitness import from_manifest as fitness_from_manifest
from .fitness import validate_fitness
from .generated import from_manifest as generated_from_manifest
from .generated import inspect_generated


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    evidence: str
    rationale: str
    repair: str
    ci_blocking: bool = False


@dataclass(frozen=True)
class DoctorReport:
    status: str
    findings: tuple[Finding, ...]
    ci_blocking_findings: int


def diagnose(root: Path, manifest: Manifest, start: str | Path, *, ci: bool) -> DoctorReport:
    """Aggregate every adopted read-only health population without running project checks."""

    project = discover_project(start)
    groups: dict[str, list[Finding]] = {
        name: []
        for name in (
            "instructions",
            "commands",
            "reviewers",
            "ci",
            "paths",
            "fitness",
            "generated",
            "docs",
            "templates",
            "policy",
        )
    }
    for item in discover_instructions(project, start):
        if item.drift:
            groups["instructions"].append(
                Finding(
                    "instructions.drift",
                    "error",
                    f"{item.path}: {item.drift}",
                    "conflicting agent instructions create ambiguous policy",
                    "make CLAUDE.md a symlink to AGENTS.md",
                    True,
                )
            )
    for name, inspector in (
        ("commands", inspect_command_availability),
        ("reviewers", inspect_reviewer_health),
        ("ci", inspect_ci_coverage),
        ("paths", inspect_path_policy),
        ("templates", inspect_project_templates),
    ):
        groups[name].extend(Finding(**asdict(item)) for item in inspector(root, manifest))
    for issue in validate_fitness(root, fitness_from_manifest(manifest)):
        groups["fitness"].append(
            Finding(
                f"fitness.{issue.code}",
                "error" if issue.code.startswith("missing") else "warning",
                f"{issue.fitness}: {issue.message}",
                "declared architectural policy must remain traceable and current",
                "repair the declaration or its referenced ADR",
                True,
            )
        )
    for declaration in generated_from_manifest(manifest):
        for issue in inspect_generated(root, declaration):
            severe = issue.code.startswith(("unsafe", "invalid"))
            groups["generated"].append(
                Finding(
                    f"generated.{issue.code}",
                    "error" if severe else "warning",
                    f"{issue.declaration}: {issue.path or '-'}: {issue.message}",
                    "declared generated relationships must be safe and currently resolvable",
                    "repair the declaration or regenerate the expected output",
                    True,
                )
            )
    doc_paths = expand_markdown_paths(root, manifest.docs.include or ("**/*.md",))
    if manifest.docs.include and not doc_paths:
        groups["docs"].append(
            Finding(
                "docs.no-files",
                "warning",
                f"docs.include matched no files: {list(manifest.docs.include)!r}",
                "documentation policy cannot validate an empty accidental selection",
                "correct docs.include or remove the declaration if not applicable",
                True,
            )
        )
    for issue in validate_documents(root, manifest.docs, doc_paths):
        severe = issue.code in {"unsafe-link", "forbidden-syntax"}
        groups["docs"].append(
            Finding(
                f"docs.{issue.code}",
                getattr(issue, "severity", "error" if severe else "warning"),
                f"{issue.path}:{issue.line}: {issue.message}",
                getattr(
                    issue,
                    "rationale",
                    "declared documentation must remain navigable and structurally current",
                ),
                getattr(issue, "repair", "repair the referenced documentation finding"),
                getattr(issue, "ci_blocking", True),
            )
        )
    if not manifest.checks:
        groups["policy"].append(
            Finding(
                "policy.no-checks",
                "warning",
                "checks is empty",
                "no verification commands are declared",
                "declare at least one project check",
                True,
            )
        )
    findings = aggregate(groups)
    return DoctorReport(
        status(findings, ci=ci), findings, sum(item.ci_blocking for item in findings)
    )


def aggregate(groups: Mapping[str, Iterable[Finding]]) -> tuple[Finding, ...]:
    """Deduplicate component findings without reproducing component logic."""
    unique: dict[tuple[str, str], Finding] = {}
    for component in sorted(groups):
        for finding in groups[component]:
            key = (finding.id, finding.evidence)
            existing = unique.get(key)
            if existing is None or _rank(finding.severity) > _rank(existing.severity):
                unique[key] = finding
    return tuple(
        sorted(unique.values(), key=lambda item: (-_rank(item.severity), item.id, item.evidence))
    )


def _rank(severity: str) -> int:
    return {"info": 0, "warning": 1, "error": 2}.get(severity, 0)


def status(findings: Sequence[Finding], *, ci: bool = False) -> str:
    failed = any(item.severity == "error" or (ci and item.ci_blocking) for item in findings)
    return "failed" if failed else "passed"
