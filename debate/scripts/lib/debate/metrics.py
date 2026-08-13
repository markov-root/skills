"""Per-run timing / cost / token metrics for a debate (OBSERVABILITY.md).

The backends already RECEIVE duration, cost and token usage from every model call
(`claude -p --output-format json` returns `duration_ms`/`total_cost_usd`/`usage`; OpenRouter
returns `usage`) — they were being discarded. The debate loop additionally times each call's
wall-clock and collects these into a per-run `metrics.json` beside the run artifacts. No extra
model calls, no new dependency; this is free instrumentation of an otherwise opaque ~hour-long run.

`cached` calls (skipped on resume) carry no timing and are excluded from the rollup.

COST is split by backend: `cost_usd` is REAL cash (billed backends — OpenRouter), while
`notional_cost_usd` is the subscription-equivalent for `claude_code` (Max plan = $0 marginal, but
`claude -p` still reports a `total_cost_usd`). Conflating them inflated the headline ~4× (the claude
notional was ~77% of the blend), so `cost_usd` now means what actually leaves the wallet.
"""

from __future__ import annotations

# Backends billed per-token (real cash). Everything else (claude_code on a Max plan) is a flat
# subscription — its reported per-call cost is NOTIONAL, not money spent. codex_cli joins here or
# notional per the access model when wired (ADR-0004).
_BILLED_BACKENDS = {"openrouter"}

_SUM_KEYS = (
    "wall_s",
    "cost_usd",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)


def summarize(calls: list[dict]) -> dict:
    """Roll up the per-call records into run totals + a per-round breakdown."""
    live = [c for c in calls if not c.get("cached")]

    def _sum(key: str) -> float:
        return sum(c[key] for c in live if isinstance(c.get(key), (int, float)))

    def _billed(c: dict) -> bool:
        # Default unknown/missing backend to billed — never UNDER-report real spend.
        return c.get("backend", "openrouter") in _BILLED_BACKENDS

    def _cost_sum(billed: bool) -> float:
        return sum(
            c["cost_usd"]
            for c in live
            if isinstance(c.get("cost_usd"), (int, float)) and _billed(c) == billed
        )

    by_round: dict[str, dict] = {}
    for c in live:
        r = by_round.setdefault(
            c["round"], {"calls": 0, "wall_s": 0.0, "cost_usd": 0.0, "output_tokens": 0}
        )
        r["calls"] += 1
        r["wall_s"] = round(r["wall_s"] + (c.get("wall_s") or 0), 2)
        if _billed(c):  # by_round cost is real cash too (notional rolled up at the top level)
            r["cost_usd"] = round(r["cost_usd"] + (c.get("cost_usd") or 0), 6)
        r["output_tokens"] += c.get("output_tokens") or 0

    return {
        "n_calls": len(live),
        "n_cached": len(calls) - len(live),
        "wall_s": round(_sum("wall_s"), 2),
        "cost_usd": round(_cost_sum(billed=True), 6),  # REAL cash (OpenRouter); honest headline
        "notional_cost_usd": round(_cost_sum(billed=False), 6),  # claude_code Max = $0 marginal
        "input_tokens": int(_sum("input_tokens")),
        "output_tokens": int(_sum("output_tokens")),
        "cached_tokens": int(_sum("cached_tokens")),
        "cache_write_tokens": int(_sum("cache_write_tokens")),
        "reasoning_tokens": int(_sum("reasoning_tokens")),
        "by_round": by_round,
    }
