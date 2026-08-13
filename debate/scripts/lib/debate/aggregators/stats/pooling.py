"""Opinion-pool divergence diagnostic (ADR-0013 decision 5) — analytic, not Monte-Carlo.

The headline band uses the **linear opinion pool** (LinOP — mix the raters' densities), which
preserves disagreement. The **log opinion pool** (LogOP — geometric mean of densities) is
*zero-forcing*: one overconfident rater assigning ~0 density anywhere vetoes the truth there. We
never use LogOP for the published number, but where LinOP and LogOP disagree sharply the
indicator's score is **sensitive to the pooling choice** — worth flagging for a human.

This is computed on a fixed grid straight from the fitted densities — deterministic, no
sampling — so it belongs here, beside the sampler in `montecarlo`, not inside it.
"""

from __future__ import annotations

import math

from debate.aggregators.stats.distributions import DEFAULT_GAMMA, fit_pdf, fit_rater
from debate.aggregators.stats.model import RaterEstimate

# Resolution of the analytic grid the LinOP/LogOP bands are read off of.
_GRID_N = 512
# Pooling-sensitivity thresholds: flag an indicator if the linear and log pools disagree on the
# centre by more than this, or on width by more than this ratio.
_POOL_MEDIAN_TOL = 0.10
_POOL_WIDTH_RATIO = 1.5


def _grid_band(dens: list[float]) -> dict | None:
    """Read p5/median/p95 off an (unnormalised) density sampled at grid midpoints."""
    total = sum(dens)
    if total <= 0.0:
        return None
    step = 1.0 / _GRID_N
    cum = 0.0
    qs: dict[float, float | None] = {0.05: None, 0.5: None, 0.95: None}
    for j, d in enumerate(dens):
        cum += d / total
        x = (j + 0.5) * step
        for q in qs:
            if qs[q] is None and cum >= q:
                qs[q] = x
    return {"p5": qs[0.05], "median": qs[0.5], "p95": qs[0.95]}


def pooling_diagnostic(estimates: list[RaterEstimate], gamma: float = DEFAULT_GAMMA) -> dict | None:
    """Compare the linear (mixture) and log (geometric-mean) opinion pools analytically.

    Returns {linop, logop, pooling_sensitive, reason} or None when fewer than two raters have
    positive width (the comparison is ill-posed). Where raters' supports barely overlap the log
    pool collapses, which is exactly the signal we want to surface.
    """
    fits = [fit_rater(e.low, e.best, e.high, e.confidence, gamma) for e in estimates]
    usable = [f for f in fits if f is not None]
    if len(usable) < 2:
        return None
    step = 1.0 / _GRID_N
    lin = [0.0] * _GRID_N
    log = [0.0] * _GRID_N  # exp(mean log density); 0 wherever any rater has 0 density
    for j in range(_GRID_N):
        x = (j + 0.5) * step
        log_sum = 0.0
        ok = True
        for fit in usable:
            d = fit_pdf(fit, x)
            lin[j] += d / len(usable)
            if d > 0.0:
                log_sum += math.log(d)
            else:
                ok = False
        log[j] = math.exp(log_sum / len(usable)) if ok else 0.0

    linop = _grid_band(lin)
    logop = _grid_band(log)
    if linop is None:
        return None
    if logop is None:  # disjoint supports — maximal pooling sensitivity
        return {
            "linop": linop,
            "logop": None,
            "pooling_sensitive": True,
            "reason": "logop_degenerate",
        }

    median_gap = abs(linop["median"] - logop["median"])
    lin_w = linop["p95"] - linop["p5"]
    log_w = logop["p95"] - logop["p5"]
    width_ratio = lin_w / log_w if log_w > 1e-9 else float("inf")
    reason = None
    if median_gap > _POOL_MEDIAN_TOL:
        reason = "median_divergence"
    elif width_ratio > _POOL_WIDTH_RATIO:
        reason = "width_divergence"
    return {
        "linop": linop,
        "logop": logop,
        "pooling_sensitive": reason is not None,
        "reason": reason,
    }
