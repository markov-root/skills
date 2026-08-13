"""Monte-Carlo *propagation* — NOT MCMC.

We have direct three-point estimates per indicator (IDEA) and a deterministic mean tree, so
we forward-propagate known uncertainty through a known function: plain MC sampling.

1. **Linear opinion pool.** Each rater's `(low, best, high, confidence)` is fit to a modified-
   PERT (see `distributions.fit_rater`) and the pooled density is sampled by picking a rater
   uniformly, then drawing from its fit — this *mixes* the densities, preserving between-rater
   disagreement (a bimodal panel stays bimodal). We do NOT average Beta parameters into one Beta
   (that discards disagreement).
2. **Propagate.** For each of N draws, sample every indicator, then recompute the whole
   weighted-mean tree; the per-node sample sets give percentile bands.

The fit itself (5/95-quantile matching, modified-PERT γ, confidence rescaling) lives in
`distributions`; the analytic LinOP-vs-LogOP *diagnostic* attached to each indicator lives in
`pooling` — this module only samples and rolls up. Independence is a documented FLOOR: sampling
indicators independently lets errors cancel (~1/√n), so the band is deceptively tight. Real
errors are correlated; the one-factor common-cause copula (ρ) restores that, and
`dependence.effective_raters` reports N_eff. The orchestrator publishes the *wider* of this band
and the methodological-ensemble band.
"""

from __future__ import annotations

import math
import random

from debate.aggregators.stats.distributions import DEFAULT_GAMMA, fit_rater, fit_sample
from debate.aggregators.stats.model import HEADLINE_VERIFIABILITY, Provider, RaterEstimate
from debate.aggregators.stats.pooling import pooling_diagnostic
from debate.aggregators.stats.tree import (
    WeightScheme,
    effective_indicator_weight,
    indicator_score,
    node_weight,
)

_SQRT2 = math.sqrt(2.0)


def _pooled_samples(
    rng: random.Random, estimates: list[RaterEstimate], n: int, fallback: float, gamma: float
) -> list[float]:
    """N draws from the linear opinion pool of the raters' fitted PERTs.

    Each rater is fit ONCE (quantile-matching runs two Beta inversions — too costly to redo per
    draw); we then mix by picking a rater uniformly each draw and sampling its fit. A degenerate
    (zero-width) rater is a point mass at its clamped `best`. With no estimates we emit the
    deterministic point score as a degenerate sample so the indicator still propagates.
    """
    if not estimates:
        return [fallback] * n
    fits = [fit_rater(e.low, e.best, e.high, e.confidence, gamma) for e in estimates]
    bests = [min(1.0, max(0.0, e.best)) for e in estimates]
    out = []
    for _ in range(n):
        i = rng.randrange(len(estimates))
        fit = fits[i]
        x = bests[i] if fit is None else fit_sample(fit, rng)
        out.append(min(1.0, max(0.0, x)))
    return out


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0,1]) of an already-sorted list."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    if lo + 1 >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[lo + 1] - sorted_vals[lo])


def _band(samples: list[float]) -> dict | None:
    if not samples:
        return None
    s = sorted(samples)
    return {
        "median": _percentile(s, 0.5),
        "p5": _percentile(s, 0.05),
        "p95": _percentile(s, 0.95),
    }


def _mean_over_samples(children: list[tuple[list[float], float]], n: int) -> list[float]:
    """Per-draw weighted mean across children that have samples. (samples, weight) pairs."""
    den = sum(w for _, w in children)
    if not children or den == 0:
        return []
    return [sum(s[i] * w for s, w in children) / den for i in range(n)]


def _sample_arrays(
    rng: random.Random,
    provider: Provider,
    scheme: WeightScheme,
    n: int,
    common_cause: float,
    gamma: float,
) -> dict[str, list[float]]:
    """Per-participating-indicator sample arrays for the headline tree.

    `common_cause` ρ ∈ [0,1] injects a single shared latent factor (a one-factor Gaussian
    copula) so a fraction of every indicator's deviation moves together — the honest model of
    correlated error (a vague provider is vague everywhere; one retrieval miss depresses several
    indicators). ρ=0 reproduces the independent floor EXACTLY (same draws, same order); ρ→1
    makes errors stop cancelling, widening the aggregate band. Marginals are preserved (we
    reorder each indicator's own pooled samples), so only the dependence changes, not the
    per-indicator distribution.
    """
    # Tree-order list of (indicator, point) that have a headline score.
    participating = [
        (ind, point)
        for com in provider.commitments
        for m in com.measures
        for ind in m.indicators
        if (point := indicator_score(ind, HEADLINE_VERIFIABILITY, scheme)) is not None
    ]
    if common_cause <= 0:
        return {
            ind.id: _pooled_samples(rng, ind.estimates, n, p, gamma) for ind, p in participating
        }

    shared = [rng.gauss(0.0, 1.0) for _ in range(n)]
    r, r2 = math.sqrt(common_cause), math.sqrt(1.0 - common_cause)
    arrays: dict[str, list[float]] = {}
    for ind, point in participating:
        marg = sorted(_pooled_samples(rng, ind.estimates, n, point, gamma))
        col = []
        for s in range(n):
            z = r * shared[s] + r2 * rng.gauss(0.0, 1.0)  # correlation ρ between indicators
            u = 0.5 * (1.0 + math.erf(z / _SQRT2))  # -> uniform via the normal CDF
            col.append(marg[min(n - 1, max(0, int(u * n)))])
        arrays[ind.id] = col
    return arrays


def propagate(
    provider: Provider,
    scheme: WeightScheme | None = None,
    *,
    n_samples: int = 10_000,
    seed: int = 12345,
    common_cause: float = 0.0,
    gamma: float = DEFAULT_GAMMA,
) -> dict:
    """Forward-propagate per-indicator three-point estimates up the headline (public) tree.

    Returns a nested dict mirroring `tree.score_tree`, each node carrying a `ci`
    {median, p5, p95} or None; indicator nodes also carry a `pooling` diagnostic (LinOP vs
    LogOP, ADR-0013) or None. Seeded for reproducible bands. `common_cause` ρ models correlated
    error: 0 = the independent floor, higher = the honest wider band. `gamma` is the
    modified-PERT concentration.
    """
    scheme = scheme or {}
    rng = random.Random(seed)
    n = n_samples
    arrays = _sample_arrays(rng, provider, scheme, n, common_cause, gamma)

    commitments: list[dict] = []
    com_samples: list[tuple[list[float], float]] = []
    for com in provider.commitments:
        measures: list[dict] = []
        meas_samples: list[tuple[list[float], float]] = []
        for m in com.measures:
            ind_nodes: list[dict] = []
            ind_samples: list[tuple[list[float], float]] = []
            for ind in m.indicators:
                samples = arrays.get(ind.id)
                if samples is None:  # no headline-scorable clause -> excluded from the band too
                    ind_nodes.append(
                        {"id": ind.id, "level": "indicator", "ci": None, "pooling": None}
                    )
                    continue
                w = effective_indicator_weight(ind, HEADLINE_VERIFIABILITY, scheme)
                ind_nodes.append(
                    {
                        "id": ind.id,
                        "level": "indicator",
                        "ci": _band(samples),
                        "pooling": pooling_diagnostic(ind.estimates, gamma),
                    }
                )
                ind_samples.append((samples, w))
            m_samples = _mean_over_samples(ind_samples, n)
            measures.append(
                {"id": m.id, "level": "measure", "ci": _band(m_samples), "children": ind_nodes}
            )
            if m_samples:
                meas_samples.append((m_samples, node_weight(scheme, m.id, m.weight)))
        c_samples = _mean_over_samples(meas_samples, n)
        commitments.append(
            {"id": com.id, "level": "commitment", "ci": _band(c_samples), "children": measures}
        )
        if c_samples:
            com_samples.append((c_samples, node_weight(scheme, com.id, com.weight)))

    overall_samples = _mean_over_samples(com_samples, n)
    return {
        "id": provider.name,
        "level": "overall",
        "ci": _band(overall_samples),
        "children": commitments,
    }
