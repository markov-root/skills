"""vote — fixed-ballot tally (ADR-0013). Plurality over a CLOSED option slate.

REJECTED for generation (ADR-0014: never vote a divergent/steelman field into a consensus — a
majority can be confidently wrong the same way, and voting discards the minority argument that is
often the point). `accepts()` therefore refuses any task whose `ballot_kind` isn't `fixed`, so a
`--aggregator vote` on a Delphi/steelman task fails fast at load, not silently mid-run.
"""

from __future__ import annotations

from collections import Counter

from debate.aggregators.base import AggregationResult


class Vote:
    id = "vote"

    def accepts(self, task) -> bool:
        return getattr(task, "ballot_kind", "open") == "fixed"

    def reduce(
        self,
        field_blinded: dict[str, dict],
        *,
        schema: dict | None = None,
        ballots: dict | None = None,
        roles: dict | None = None,
        context: dict | None = None,
    ) -> AggregationResult:
        # ballots = {voice_id: option_id} over a closed slate; else read each voice's `vote` field.
        casts = ballots or {v: s.get("vote") for v, s in field_blinded.items() if s.get("vote")}
        if not casts:
            raise ValueError("vote aggregator needs fixed ballots ({voice: option_id})")
        tally = Counter(casts.values())
        # Deterministic tie-break: highest count, then lexical option id (no RNG — resume-stable).
        winner = min(tally.items(), key=lambda kv: (-kv[1], str(kv[0])))[0]
        return AggregationResult(
            result={"winner": winner, "tally": dict(tally), "n_ballots": len(casts)},
            aggregator=self.id,
            meta={"rule": "plurality"},
        )
