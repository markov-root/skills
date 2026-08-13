"""statistical — the numeric reducer (ADR-0013), the FIRST and ONLY caller of the dormant
`aggregators/stats/` math (PERT + linear opinion pool + Monte-Carlo; IDEA default, task-0021).

Reduces a panel of three-point (min/mode/max) estimates per item into a point + 90% CI. Each rater's
estimate is fitted to a modified-PERT Beta (`fit_rater`); the panel is mixed by a LINEAR OPINION
POOL (pick a rater per draw, sample its fit — preserves disagreement/bimodality rather than
averaging it away), and the point/CI are read off the pooled sample. Extremizing is OFF and no
Cooke weighting is
applied without seed questions (ADR-0013 defaults). Pure-stdlib; keeps stats/ a clean leaf.
"""

from __future__ import annotations

import random
import statistics

from debate.aggregators.base import AggregationResult
from debate.aggregators.stats.distributions import (
    CREDIBLE_LEVEL,
    DEFAULT_GAMMA,
    fit_rater,
    fit_sample,
)

_SEED = 12345  # fixed → the reduction is reproducible/resume-stable (ADR-0005)
_N_SAMPLES = 4000


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def pool_three_point(
    estimates: list[dict], *, seed: int = _SEED, n_samples: int = _N_SAMPLES
) -> dict:
    """A list of `{min, mode, max, confidence?}` (aliases low/best/high accepted) → `{point, ci_low,
    ci_high, n_estimates, n_samples}`. The core numeric routine, testable on canned vectors."""
    rng = random.Random(seed)
    fits = []
    for e in estimates:
        lo = float(e.get("min", e.get("low")))
        mo = float(e.get("mode", e.get("best")))
        hi = float(e.get("max", e.get("high")))
        conf = float(e.get("confidence", CREDIBLE_LEVEL))
        f = fit_rater(lo, mo, hi, conf, gamma=DEFAULT_GAMMA)
        if f is not None:
            fits.append(f)
    if not fits:
        raise ValueError("no valid three-point estimates to pool")
    samples = sorted(fit_sample(rng.choice(fits), rng) for _ in range(n_samples))
    return {
        "point": round(statistics.fmean(samples), 6),
        "ci_low": round(_percentile(samples, 0.05), 6),
        "ci_high": round(_percentile(samples, 0.95), 6),
        "n_estimates": len(fits),
        "n_samples": n_samples,
    }


class Statistical:
    id = "statistical"

    def accepts(self, task) -> bool:
        return getattr(task, "ballot_kind", "open") in ("fixed", "three_point")

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
        items = ballots
        if items is None:
            task = ctx.get("task")
            items = task.ballots(field_blinded) if task is not None else None
        if not items:
            raise ValueError(
                "statistical aggregator needs three-point ballots (per-item estimates)"
            )
        result = {iid: pool_three_point(ests) for iid, ests in items.items()}
        return AggregationResult(result={"items": result}, aggregator=self.id, meta={})
