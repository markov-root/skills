"""Adapter for engineering record lint (structure and quality-review modes)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..documents.lint import lint_project
from ..policy.document_paths import DocumentContainment
from ..policy.manifest import Manifest, ManifestV2, load_manifest
from ..policy.project_root import (
    ExplicitProjectRoot,
    load_explicit_manifest,
    resolve_explicit_project_root,
)
from .contracts import (
    EXIT_CHECK_FAILED,
    EXIT_OK,
    CommandResult,
    CommandSpec,
    explanation,
)

_MODE_CHOICES = ("structure", "quality-review")
_STRUCTURAL = "structure"


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=("lint",))
    parser.add_argument(
        "--mode",
        choices=_MODE_CHOICES,
        default=_STRUCTURAL,
        help="structure blocks only under the agent_scheduling profile; quality-review is advisory",
    )


def _public_finding(item: Any, *, project: str | None = None) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "id": item.code,
        "severity": item.severity,
        "message": item.message,
        "provenance": {"path": item.path, "line": item.line},
        "rationale": item.rationale,
        "repair": item.repair,
        "ci_blocking": item.ci_blocking,
    }
    if project is not None:
        finding["project"] = project
    return finding


def _render(
    findings: Sequence[dict[str, Any]],
    *,
    mode: str,
    profile: bool,
) -> str:
    lines = ["# Engineering record lint", ""]
    if mode == _STRUCTURAL:
        gate = (
            "blocking under the agent_scheduling profile"
            if profile
            else "advisory (no agent_scheduling profile)"
        )
        lines.append(f"- Mode: structure ({gate})")
    else:
        lines.append("- Mode: quality-review (advisory, never blocks)")
    if not findings:
        lines.append("- Findings: none")
        return "\n".join((*lines, ""))
    lines.append(f"- Findings: {len(findings)}")
    lines.append("")
    for item in findings:
        provenance = item["provenance"]
        suffix = f" [{item['project']}]" if item.get("project") else ""
        lines.append(
            f"- `{item['id']}` at `{provenance['path']}:{provenance['line']}`{suffix}: {item['message']}"
        )
        lines.append(f"  Why: {item['rationale']}")
        lines.append(f"  Repair: {item['repair']}")
    return "\n".join((*lines, ""))


def _effective_manifest(
    resolution: ExplicitProjectRoot,
) -> tuple[Path, Manifest | ManifestV2 | None, bool]:
    """Resolve the adopted manifest and the agent_scheduling profile flag."""
    root = resolution.root
    exact = root / "engineering.yaml"
    if exact.is_file():
        manifest = load_explicit_manifest(resolution, required=True)
        return (
            root,
            manifest,
            isinstance(manifest, ManifestV2) and manifest.agent_scheduling,
        )
    for directory in root.parents:
        candidate = directory / "engineering.yaml"
        if not candidate.is_file():
            continue
        manifest = load_manifest(candidate)
        if isinstance(manifest, ManifestV2):
            return directory, manifest, manifest.agent_scheduling
        return root, None, False
    return root, None, False


def handle(args: argparse.Namespace) -> CommandResult:
    if args.action != "lint":
        raise ValueError("record supports only the 'lint' action")
    quality_review = args.mode != _STRUCTURAL
    resolution = resolve_explicit_project_root(args.project_root)
    root, manifest, profile = _effective_manifest(resolution)
    # The advisory size gate runs only under the agent_scheduling profile (structure mode only).
    size_gate = manifest.size_gate if (profile and isinstance(manifest, ManifestV2)) else None

    findings: list[dict[str, Any]] = []
    projects: list[str] = []
    if isinstance(manifest, ManifestV2):
        for scope in manifest.document_projects.projects:
            projects.append(scope.id)
            containment = DocumentContainment.for_scope(root, scope)
            findings.extend(
                _public_finding(item, project=scope.id)
                for item in lint_project(
                    root,
                    scope.currency,
                    containment=containment,
                    quality_review=quality_review,
                    size_gate=size_gate,
                )
            )
    elif manifest is not None and manifest.docs.currency is not None:
        findings.extend(
            _public_finding(item)
            for item in lint_project(
                root,
                manifest.docs.currency,
                quality_review=quality_review,
            )
        )

    if quality_review:
        status = "passed"
        exit_code = EXIT_OK
    elif profile:
        # Only ci_blocking findings (decidable structural invariants) fail the gate; advisory
        # size-gate warnings surface but never block (ADR 0025 §4 — advisory by default).
        blocking = [item for item in findings if item.get("ci_blocking")]
        if blocking:
            status, exit_code = "failed", EXIT_CHECK_FAILED
        elif findings:
            status, exit_code = "partial", EXIT_OK
        else:
            status, exit_code = "passed", EXIT_OK
    else:
        status = "partial" if findings else "passed"
        exit_code = EXIT_OK

    data: dict[str, Any] = {
        "action": "lint",
        "mode": args.mode,
        "agent_scheduling": profile,
        "root_resolution": resolution.to_dict(),
        "projects": projects,
        "count": len(findings),
        "findings": findings,
        "limitations": [
            "Structural lint proves recorded section/provenance shape only, never content correctness.",
            "Quality-review prompts are judgment guidance and can never block.",
            (
                "The task-size gate is advisory and never blocks; the decidable size invariants it "
                "references (done-without-evidence, dependency cycle, acceptance-criterion-without-check) "
                "are enforced by the done-evidence policy, task graph, and document validation."
            ),
        ],
    }
    return CommandResult(
        status,
        root,
        data,
        exit_code,
        _render(findings, mode=args.mode, profile=profile),
    )


SPEC = CommandSpec(
    "record",
    "lint engineering records structurally or with advisory quality-review prompts",
    configure,
    handle,
    explanation(
        "record",
        "Engineering record lint",
        "Generalize done-evidence gating into a per-role structural lint and an advisory quality-review mode.",
        (
            "a record's required sections or provenance must be checked before continuation",
            "structural invariants decidable by inspection must be enforced under agent scheduling",
            "the judgment properties of a good record must be surfaced as review prompts",
        ),
        (
            "grading content correctness",
            "grading prose truth or product authority",
        ),
        prerequisites=("an adopted engineering.yaml docs.currency role contract",),
        evidence=(
            "per-role required-section and provenance findings with stable identifiers",
            "an agent_scheduling flag that controls whether structure may block",
            "advisory quality-review prompts that never block",
        ),
        limitations=(
            "record lint proves recorded shape, not content, approval, or evidence quality",
            "the task-size gate warns advisorily and never blocks; decidable size invariants are enforced elsewhere",
        ),
        next_commands=(
            "engineering record lint --mode structure --json",
            "engineering record lint --mode quality-review --json",
            "engineering document validate --json",
        ),
        references=(
            "docs/adr/0025-ratify-the-agent-scale-ticketing-and-records-design-v2.md",
            "docs/context/document-contracts.md",
        ),
    ),
)
