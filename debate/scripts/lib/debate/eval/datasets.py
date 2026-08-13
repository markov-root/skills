"""Ground-truth datasets for the harness (task-0026) — the ONLY thing the harness scores against.

A dataset is verifiable known-answer items. `novel` marks a post-training-cutoff / unpublished item
so the harness can split novel-vs-published and rule out contamination (Ashokkumar et al.): a debate
"win" that evaporates on novel items is memorization, not reasoning. A tiny built-in arithmetic set
ships for the smoke path + tests; real sets (a TESS-style effects archive, a QuALITY-style
reading-comprehension set with information asymmetry) load from JSON — those are the agent+human
ingestion work, deferred, kept out of the repo (data, not code).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Item:
    id: str
    question: str
    answer: object  # the ground truth (categorical label or numeric value)
    novel: bool = False  # True = post-cutoff / unpublished → the contamination-control split
    meta: dict = field(default_factory=dict)


@dataclass
class Dataset:
    name: str
    items: list[Item]

    def truth(self) -> dict:
        return {it.id: it.answer for it in self.items}

    def novel_ids(self) -> set[str]:
        return {it.id for it in self.items if it.novel}


def load_dataset(path: str | Path) -> Dataset:
    """Load from JSON: `{"name": ..., "items": [{id, question, answer, novel?, meta?}, …]}`."""
    doc = json.loads(Path(path).read_text())
    items = [
        Item(
            id=str(it["id"]),
            question=it["question"],
            answer=it["answer"],
            novel=bool(it.get("novel", False)),
            meta=it.get("meta", {}),
        )
        for it in doc["items"]
    ]
    return Dataset(name=doc.get("name", Path(path).stem), items=items)


def builtin_arithmetic() -> Dataset:
    """A minimal verifiable set (numeric ground truth) for the smoke path + tests — half marked
    novel so the contamination split has both strata. Not a benchmark; a wiring fixture."""
    rows = [
        ("a1", "2 + 2", 4, False),
        ("a2", "3 * 7", 21, False),
        ("a3", "10 - 6", 4, True),
        ("a4", "12 / 4", 3, True),
    ]
    return Dataset(
        name="builtin-arithmetic",
        items=[Item(id=i, question=q, answer=a, novel=n) for i, q, a, n in rows],
    )
