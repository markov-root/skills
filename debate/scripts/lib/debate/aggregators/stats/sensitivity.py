"""Sensitivity analysis + rank-stability (the "#14 value-of-information" component).

Two defensible, cheap diagnostics on top of the aggregation tree:

* **Variance sensitivity** — which indicators drive a measure's confidence band? For a weighted
  mean `M = Σ wᵢXᵢ / Σwᵢ` with independent draws, `Var(M) = Σ (wᵢ/W)² Var(Xᵢ)`, so each
  indicator's *share* of the measure's variance is analytic — no extra propagation, just the
  per-indicator sample variance (from its pooled three-point) and its weight. Tells us where
  scoring scrutiny and weight choices matter most (and where they don't).

* **Rank-stability** — does the provider ordering survive every weight scheme? If the ranking
  is invariant we can state it strongly; if a pair flips, that is itself a finding (and a single
  headline number would have been a lie). This is the media-defensible robustness claim.

Same independence caveat as the MC band: the variance shares are a first-order,
independent-sampling view; correlated errors (the false-zero) are not captured here.
"""

from __future__ import annotations

import random
import statistics

from debate.aggregators.stats.model import HEADLINE_VERIFIABILITY, Provider
from debate.aggregators.stats.montecarlo import DEFAULT_GAMMA, _pooled_samples
from debate.aggregators.stats.tree import WeightScheme, effective_indicator_weight, indicator_score


def variance_sensitivity(
    provider: Provider,
    scheme: WeightScheme | None = None,
    *,
    n_samples: int = 10_000,
    seed: int = 12345,
    gamma: float = DEFAULT_GAMMA,
) -> dict:
    """Per measure, rank the contributing indicators by their share of the measure's CI variance
    and by point leverage (wᵢ/W — how far a unit change in this indicator moves the measure)."""
    scheme = scheme or {}
    rng = random.Random(seed)
    measures: list[dict] = []
    for com in provider.commitments:
        for m in com.measures:
            parts: list[dict] = []
            for ind in m.indicators:
                point = indicator_score(ind, HEADLINE_VERIFIABILITY, scheme)
                if point is None:  # no headline-scorable clause -> not in the measure mean
                    continue
                w = effective_indicator_weight(ind, HEADLINE_VERIFIABILITY, scheme)
                samples = _pooled_samples(rng, ind.estimates, n_samples, point, gamma)
                var = statistics.pvariance(samples) if len(samples) > 1 else 0.0
                parts.append(
                    {"indicator": ind.id, "weight": w, "point": round(point, 4), "var": var}
                )
            total_w = sum(p["weight"] for p in parts) or 1.0
            contribs = {p["indicator"]: (p["weight"] / total_w) ** 2 * p["var"] for p in parts}
            total_c = sum(contribs.values())
            for p in parts:
                p["point_leverage"] = round(p["weight"] / total_w, 4)
                p["variance_share"] = (
                    round(contribs[p["indicator"]] / total_c, 4) if total_c > 0 else None
                )
                p.pop("var")
            parts.sort(key=lambda p: (p["variance_share"] or 0, p["point_leverage"]), reverse=True)
            measures.append({"measure": m.id, "indicators": parts})
    return {"provider": provider.name, "model": provider.model, "measures": measures}


def rank_stability(scores_by_scheme: dict[str, dict[str, float | None]]) -> dict:
    """Given {scheme_name: {provider: overall_score}}, report the ranking under each scheme,
    whether it is invariant, and any provider pair whose order flips across schemes."""
    orderings = {
        scheme: sorted(scores, key=lambda p: (scores[p] is not None, scores[p]), reverse=True)
        for scheme, scores in scores_by_scheme.items()
    }
    stable = len({tuple(o) for o in orderings.values()}) == 1
    schemes = list(orderings)
    providers = list(orderings[schemes[0]]) if schemes else []
    flips: list[dict] = []
    for i in range(len(providers)):
        for j in range(i + 1, len(providers)):
            a, b = providers[i], providers[j]
            relations = {orderings[s].index(a) < orderings[s].index(b) for s in schemes}
            if len(relations) > 1:
                flips.append({"pair": [a, b], "note": "order flips across weight schemes"})
    return {"orderings": orderings, "stable": stable, "flips": flips}
