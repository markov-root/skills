"""arbitrator_select — the default reducer (ADR-0013/0014/0017): union-then-arbitrate.

For now it ADAPTS to the task's own `aggregate()` (an LLM arbitrator merge), so the default
artifacts are byte-identical to the pre-seam loop; the standalone union + `arbitrator_invention`
gate logic that makes this a first-class reducer independent of any task is task-0025. It reads the
arbitrator voice, the task hook, and the (already-unioned) red-team findings from `context` — it
imports nothing from `debate.tasks` (the task arrives duck-typed via context), keeping the
aggregator axis a leaf that never depends on a task (ADR-0002 boundary).
"""

from __future__ import annotations

from debate.aggregators.base import AggregationResult


class ArbitratorSelect:
    id = "arbitrator_select"

    def accepts(self, task) -> bool:
        return True  # an LLM merge works for any field shape (open or fixed)

    def reduce(
        self,
        field_blinded: dict[str, dict],
        *,
        schema: dict | None = None,
        ballots: dict | None = None,
        roles: dict | None = None,
        context: dict | None = None,
    ) -> AggregationResult:
        ctx = context or {}
        task = ctx["task"]
        arbitrator = ctx["arbitrator"]
        result = task.aggregate(field_blinded, arbitrator, redteam=ctx.get("redteam"))
        return AggregationResult(result=result, aggregator=self.id, meta={})
