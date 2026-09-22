"""Standalone engineering record lint: structural (decidable) and quality-review (advisory).

The structural mode generalizes the ``done_task_evidence`` gate into a per-role check driven by
``ROLE_CONTRACTS[role].required_sections`` plus provenance and current-handoff cardinality that are
decidable by inspection. The quality-review mode emits advisory review prompts for the semantic
"properties of a good X" a linter cannot decide. Only the structural mode may block, and only when a
project opts into the ``agent_scheduling`` profile.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..policy.document_paths import DocumentContainment
from ..policy.manifest import DocsCurrencyPolicy, SizeGateThresholds
from .contracts import ROLE_CONTRACTS
from .size_gate import evaluate_task_sizing
from .validation import scan_typed_documents

MAX_DOCUMENT_BYTES = 1_000_000
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_CURRENT_STATE = "current"

# Role judgment prompts for properties a structural linter cannot decide. These surface the
# template quality bars (slice 0094) as review questions rather than gates.
QUALITY_PROMPTS: dict[str, str] = {
    "task": "Are the acceptance criteria actually satisfied, with concrete and reproducible completion evidence?",
    "adr": "Is the decision still current, are alternatives fairly compared, and are consequences honestly scoped?",
    "audit": "Is the method sound and the scope correct, and does the disposition follow from the findings?",
    "research": "Is the method rigorous, are sources credible and typed, and is uncertainty honestly bounded?",
    "lesson": "Is the inference durable and transferable, and is its boundary proportional to the evidence?",
    "handoff": "Is the resume context complete and accurate enough for the next agent to continue?",
    "plan": "Is the objective unambiguous, the approach principled, and the progress log truthful?",
}


@dataclass(frozen=True)
class RecordLint:
    code: str
    severity: str
    path: str
    line: int
    message: str
    rationale: str
    repair: str
    ci_blocking: bool = True


def extract_headings(text: str) -> tuple[str, ...]:
    """Return lowercased heading texts in document order for the given Markdown text."""
    return tuple(match.group(2).strip().casefold() for match in _HEADING.finditer(text))


def lint_structure(
    *,
    role: str,
    source: str,
    body: str,
    metadata: Mapping[str, Any],
    body_line: int = 1,
) -> tuple[RecordLint, ...]:
    """Structural, decidable-by-inspection checks for one record.

    Driven by ``ROLE_CONTRACTS[role].required_sections`` plus provenance (dated and attributable).
    """
    findings: list[RecordLint] = []
    present = set(extract_headings(body))
    for section in ROLE_CONTRACTS[role].required_sections:
        if section.casefold() not in present:
            findings.append(
                _finding(
                    "record.structure.section-missing",
                    "error",
                    source,
                    body_line,
                    f"{role} record lacks required section {section!r}",
                    "role templates fix the required sections that make a record decidable by inspection",
                    f"add the required section {section!r} with reviewed content",
                )
            )
    authority = metadata.get("authority")
    owner = authority.get("owner") if isinstance(authority, dict) else metadata.get("owner")
    if not metadata.get("created") or not metadata.get("updated") or not owner:
        findings.append(
            _finding(
                "record.structure.provenance-missing",
                "error",
                source,
                body_line,
                f"{role} record must be dated and attributable (created, updated, owner)",
                "provenance decidable by inspection requires a realised date and an attributable owner",
                "set created/updated and an attributable owner on the record",
            )
        )
    return tuple(findings)


def _lint_handoff_cardinality(records: Sequence[Any]) -> tuple[RecordLint, ...]:
    current = [
        record
        for record in records
        if str(record.metadata.get("role")) == "handoff"
        and str(record.metadata.get("state")) == _CURRENT_STATE
    ]
    if len(current) < 2:
        return ()
    paths = ", ".join(record.source for record in current)
    return (
        _finding(
            "record.structure.handoff-ambiguous",
            "error",
            current[1].source,
            1,
            f"{len(current)} current handoffs make continuation authority ambiguous: {paths}",
            "one-current-handoff cardinality keeps continuation authority decidable by inspection",
            "retain one current handoff and mark the others superseded",
        ),
    )


def lint_project(
    root: Path,
    policy: DocsCurrencyPolicy,
    *,
    containment: DocumentContainment | None = None,
    quality_review: bool = False,
    size_gate: SizeGateThresholds | None = None,
) -> tuple[RecordLint, ...]:
    """Lint every adopted typed record in one project under the requested mode.

    When ``size_gate`` thresholds are supplied (only under the agent_scheduling profile), structure
    mode also emits the advisory task-size gate findings. Those findings never block.
    """
    if policy is None:
        return ()
    scan = scan_typed_documents(root, policy, containment=containment)
    findings: list[RecordLint] = []
    for record in scan.records:
        role = str(record.metadata.get("role", ""))
        source = record.source
        body = _read_body(root, source)
        if quality_review:
            prompt = QUALITY_PROMPTS.get(role)
            if not prompt:
                continue
            findings.append(
                _finding(
                    "record.quality-review.prompt",
                    "info",
                    source,
                    1,
                    f"{role} record review: {prompt}",
                    "semantic quality is not decidable by inspection",
                    "ask a reviewer to judge this record against the role quality bar",
                    ci_blocking=False,
                )
            )
            continue
        findings.extend(
            lint_structure(
                role=role,
                source=source,
                body=body,
                metadata=record.metadata,
            )
        )
        if size_gate is not None and role == "task":
            findings.extend(
                _finding(
                    item.code,
                    item.severity,
                    source,
                    1,
                    item.message,
                    item.rationale,
                    item.repair,
                    ci_blocking=item.ci_blocking,
                )
                for item in evaluate_task_sizing(
                    record.metadata,
                    max_acceptance_criteria=size_gate.max_acceptance_criteria,
                    max_touched_dirs=size_gate.max_touched_dirs,
                )
            )
    if not quality_review:
        findings.extend(_lint_handoff_cardinality(scan.records))
    return tuple(sorted(findings, key=lambda item: (item.path, item.code)))


def _read_body(root: Path, source: str) -> str:
    data = (root / source).read_bytes()
    if len(data) > MAX_DOCUMENT_BYTES:
        data = data[:MAX_DOCUMENT_BYTES]
    return data.decode("utf-8", errors="replace")


def _finding(
    code: str,
    severity: str,
    path: str,
    line: int,
    message: str,
    rationale: str,
    repair: str,
    *,
    ci_blocking: bool = True,
) -> RecordLint:
    return RecordLint(
        code,
        severity,
        path,
        line,
        message,
        rationale,
        repair,
        ci_blocking,
    )
