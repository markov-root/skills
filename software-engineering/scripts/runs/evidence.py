"""Truthful comparison and rendering of structured check records."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .baseline import CheckRecord


@dataclass(frozen=True)
class EvidenceItem:
    name: str
    classification: str
    baseline: CheckRecord | None
    final: CheckRecord | None


def _bad(status: str) -> bool:
    return status in {"failed", "timed_out"}


def compare(
    baseline: Iterable[CheckRecord], final: Iterable[CheckRecord]
) -> tuple[EvidenceItem, ...]:
    before = {item.name: item for item in baseline}
    after = {item.name: item for item in final}
    result: list[EvidenceItem] = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if new is None or new.status == "skipped":
            kind = "skipped"
        elif new.status == "not_applicable":
            kind = "not_applicable"
        elif new.status == "unavailable":
            kind = "unavailable"
        elif old is None or old.status in {"skipped", "unavailable", "not_applicable"}:
            kind = "newly_applicable"
        elif not _bad(old.status) and _bad(new.status):
            kind = "new"
        elif _bad(old.status) and not _bad(new.status):
            kind = "resolved"
        else:
            kind = "unchanged"
        result.append(EvidenceItem(name, kind, old, new))
    return tuple(result)


def to_json(items: Iterable[EvidenceItem]) -> dict[str, object]:
    rows = list(items)
    counts = Counter(item.classification for item in rows)
    return {
        "schema_version": 1,
        "summary": dict(sorted(counts.items())),
        "checks": [asdict(item) for item in rows],
    }


def to_markdown(items: Iterable[EvidenceItem]) -> str:
    rows = list(items)
    table = [
        ("Check", "Result", "Baseline", "Final"),
        *[
            (
                item.name,
                item.classification,
                item.baseline.status if item.baseline else "not run",
                item.final.status if item.final else "not run",
            )
            for item in rows
        ],
    ]
    widths = [max(len(row[index]) for row in table) for index in range(4)]

    def render(row: tuple[str, ...]) -> str:
        return (
            "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
        )

    lines = [
        "# Engineering evidence",
        "",
        render(table[0]),
        render(tuple("-" * width for width in widths)),
        *(render(row) for row in table[1:]),
    ]
    lines.extend(["", f"Checks represented: {len(rows)}.", ""])
    return "\n".join(lines)
