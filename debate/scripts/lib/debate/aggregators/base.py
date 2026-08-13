"""The `Aggregator` seam (ADR-0013) — reduce the blinded final field to a result dict, chosen
independently of protocol and task.

`engine/loop.py` will call `aggregator.reduce(...)` instead of a task-specific merge (task-0025),
so "same protocol, different reducer" becomes a config choice, not a rewrite. This module defines
only the protocol; the concrete reducers land in task-0025:

- `arbitrator_select` — union-then-arbitrate (steelman default; ADR-0014 §7), guarded by the
  deterministic `arbitrator_invention` gate.
- `statistical` — wraps `aggregators/stats/` (numeric, IDEA default).
- `vote` — fixed-ballot only (rejected for generation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AggregationResult:
    """The output of a reduce (ADR-0017): the result dict plus provenance for the trace.

    `result` is the aggregated payload the loop writes as `aggregate.json` and spreads into
    `result.json` — so a reducer that wraps today's arbitrator merge stays byte-identical.
    `aggregator` names the reducer that produced it; `meta` carries reducer-specific provenance
    (ballots, pool composition, the invention-gate outcome) for the record — additive, never part
    of the result payload.
    """

    result: dict
    aggregator: str
    meta: dict = field(default_factory=dict)


class Aggregator(Protocol):
    """Reduce a blinded final field (label -> set) to an `AggregationResult`, chosen independently
    of protocol and task (ADR-0013). ADR-0017 widens the seam so a reducer can carry ballots and
    role pools and delegate to sub-aggregators; compatibility with the field shape is validated at
    load and fails fast.

    `context` is an opaque bag the loop fills with what a reducer needs without the engine reaching
    into the task (ADR-0002): today `{task, arbitrator, redteam}` for the default adapter; richer
    reducers (statistical, vote) read `ballots`/`roles` — all task-0025.
    """

    id: str

    def reduce(
        self,
        field_blinded: dict[str, dict],
        *,
        schema: dict | None = None,
        ballots: dict | None = None,
        roles: dict | None = None,
        context: dict | None = None,
    ) -> AggregationResult: ...
