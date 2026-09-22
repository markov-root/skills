"""Advisory task-size gate (ADR 0025 §4).

This gate warns on oversize *smells* and prompts vertical-slice decomposition. It is **advisory
only and never blocks** — the red team rejected a hard size gate by default (blocker B3).

The genuinely decidable structural invariants ADR §4 lists as hard-blocks are already enforced
elsewhere and are deliberately NOT re-implemented here:

- missing completion evidence on a ``done`` task -> the ``done_task_evidence`` currency policy
  (``policy/manifest.py`` / ``documents/currency.py``);
- a dependency cycle -> ``engineering task graph`` cycle detection (``documents/graph.py``);
- an acceptance criterion with no expressible check -> document validation's task-criteria checks
  (``documents/validation.py``: ``criteria-mismatch`` / ``criterion-id-missing``).

So this gate adds no new blocker. A complete ``atomic_large`` exception (rationale + rollback/verify
plan + checkpoints) suppresses the oversize smells for legitimately atomic large work; an incomplete
exception is itself surfaced as an advisory warning. All thresholds are per-project-tunable warnings
(ADR §10), never universal hard gates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_ACCEPTANCE_CRITERIA = 7
DEFAULT_MAX_TOUCHED_DIRS = 4
_ATOMIC_LARGE_FIELDS = ("rationale", "rollback", "checkpoints")


@dataclass(frozen=True)
class SizeFinding:
    """One advisory size-gate finding. ``ci_blocking`` is always ``False`` for this gate."""

    code: str
    severity: str
    message: str
    rationale: str
    repair: str
    ci_blocking: bool = False


def _details(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    details = metadata.get("details")
    return details if isinstance(details, Mapping) else {}


def _atomic_large_state(details: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Return (present, missing_fields) for an ``atomic_large`` exception.

    ``present`` is True when the key exists at all; ``missing_fields`` lists required subfields that
    are absent or empty. A complete exception has ``present`` True and no missing fields.
    """
    atomic = details.get("atomic_large")
    if atomic is None:
        return False, ()
    if not isinstance(atomic, Mapping):
        return True, _ATOMIC_LARGE_FIELDS
    missing = tuple(field for field in _ATOMIC_LARGE_FIELDS if not atomic.get(field))
    return True, missing


def _top_level_dirs(touches: Sequence[Any]) -> set[str]:
    """First non-glob path segment of each ``touches`` glob, used only to count breadth."""
    tops: set[str] = set()
    for entry in touches:
        if not isinstance(entry, str):
            continue
        head = entry.strip().lstrip("/").split("/", 1)[0].strip()
        if head and head not in {"*", "**"}:
            tops.add(head)
    return tops


def evaluate_task_sizing(
    metadata: Mapping[str, Any],
    *,
    max_acceptance_criteria: int = DEFAULT_MAX_ACCEPTANCE_CRITERIA,
    max_touched_dirs: int = DEFAULT_MAX_TOUCHED_DIRS,
) -> tuple[SizeFinding, ...]:
    """Advisory oversize-smell evaluation for one task record's metadata.

    Returns advisory findings only (``ci_blocking=False``). A complete ``atomic_large`` exception
    suppresses the oversize smells; an incomplete one is reported. Non-task or absent-detail records
    yield no findings.
    """
    if str(metadata.get("role", "")) != "task":
        return ()
    details = _details(metadata)
    present, missing = _atomic_large_state(details)
    exception_complete = present and not missing

    findings: list[SizeFinding] = []
    if present and missing:
        findings.append(
            SizeFinding(
                "record.size.atomic-large-incomplete",
                "warning",
                f"atomic_large exception is missing required field(s): {', '.join(missing)}",
                "an atomic_large exception must justify the size with a rationale, a rollback/verify "
                "plan, and checkpoints before it can suppress the decomposition prompt",
                "complete atomic_large.rationale, atomic_large.rollback, and atomic_large.checkpoints",
            )
        )

    smells: list[SizeFinding] = []
    criteria = details.get("criteria")
    criteria_count = (
        len(criteria) if isinstance(criteria, Sequence) and not isinstance(criteria, str) else 0
    )
    if criteria_count > max_acceptance_criteria:
        smells.append(
            SizeFinding(
                "record.size.acceptance-criteria",
                "warning",
                f"task declares {criteria_count} acceptance criteria (> {max_acceptance_criteria})",
                "many independent acceptance criteria are a smell that a task should be split into a "
                "parent epic with vertical-slice children",
                "split into a parent epic with smaller child tasks, or justify with an atomic_large "
                "exception",
            )
        )
    touches = details.get("touches")
    tops = (
        _top_level_dirs(touches)
        if isinstance(touches, Sequence) and not isinstance(touches, str)
        else set()
    )
    if len(tops) > max_touched_dirs:
        smells.append(
            SizeFinding(
                "record.size.touched-dirs",
                "warning",
                f"task touches {len(tops)} top-level directories (> {max_touched_dirs}): "
                f"{', '.join(sorted(tops))}",
                "a task spanning many unrelated top-level directories is a smell that the work is not "
                "a single vertical slice",
                "narrow the slice, or justify the breadth with an atomic_large exception",
            )
        )

    if not exception_complete:
        findings.extend(smells)
    return tuple(findings)
