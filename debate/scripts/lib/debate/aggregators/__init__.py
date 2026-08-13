"""The aggregator axis (ADR-0013): the final reduction of the blinded field, selectable
independently of the protocol and the task.

- `base.py` — the `Aggregator` protocol + `AggregationResult` (the seam, ADR-0017).
- `arbitrator_select.py` — the default LLM merge (union-then-arbitrate); open or fixed field.
- `statistical.py` — PERT + opinion-pool + Monte-Carlo over three-point ballots; the only importer
  of `stats/` (IDEA default, task-0021).
- `vote.py` — fixed-ballot plurality; refused on a generative (open-ballot) task.
- `stats/` — pure-stdlib numeric math, a leaf reached only through `statistical.py`.

`select_aggregator(name, task)` builds the reducer and validates it against the task's field type at
load (fail fast) — e.g. `vote` on a generative task raises here, not mid-run (ADR-0014).
"""

from __future__ import annotations

from debate.aggregators.arbitrator_select import ArbitratorSelect
from debate.aggregators.base import AggregationResult, Aggregator
from debate.aggregators.statistical import Statistical
from debate.aggregators.vote import Vote

__all__ = [
    "Aggregator",
    "AggregationResult",
    "ArbitratorSelect",
    "Statistical",
    "Vote",
    "build_aggregator",
    "select_aggregator",
]

_REGISTRY = {a.id: a for a in (ArbitratorSelect, Statistical, Vote)}


def build_aggregator(name: str) -> Aggregator:
    """Instantiate a reducer by id, or raise with the known set (fail fast at config load)."""
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(
            f"unknown aggregator {name!r} — known: {', '.join(sorted(_REGISTRY))}"
        ) from None


def select_aggregator(name: str, task) -> Aggregator:
    """Build `name` and validate it against the task's field type (ADR-0013). Refuses an
    incompatible pairing at load — e.g. `vote` on an open-ballot (generative) task."""
    agg = build_aggregator(name)
    if not agg.accepts(task):
        raise ValueError(
            f"aggregator {name!r} is incompatible with task {getattr(task, 'name', '?')!r} "
            f"(ballot_kind={getattr(task, 'ballot_kind', 'open')!r}) — it needs a fixed ballot"
        )
    return agg
