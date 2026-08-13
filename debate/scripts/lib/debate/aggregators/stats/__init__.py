"""Aggregation + confidence engine.

`aggregate()` is the one public entry point. It computes the deterministic score tree (the
headline + with-request + %-public numbers) under a *primary* weight scheme, the Monte-Carlo
band under that scheme, and a methodological-ensemble band across ALL supplied schemes — then
publishes, per node, the **wider** of the MC band and the ensemble band (the ensemble
width is the more truthful number; the independent-MC band is a floor).

Scores are on [0,1] (display ×100). Built and fixture-tested independently of the scoring
task; the moment the scoring debate emits real clause judgments + three-point estimates, this
engine turns them into the published numbers.
"""

from __future__ import annotations

from debate.aggregators.stats.dependence import effective_raters, mean_pairwise_rho
from debate.aggregators.stats.distributions import DEFAULT_GAMMA
from debate.aggregators.stats.invariance import decomposition_invariance
from debate.aggregators.stats.model import (
    Clause,
    Commitment,
    Indicator,
    Measure,
    Provider,
    RaterEstimate,
)
from debate.aggregators.stats.montecarlo import propagate
from debate.aggregators.stats.pooling import pooling_diagnostic
from debate.aggregators.stats.sensitivity import rank_stability, variance_sensitivity
from debate.aggregators.stats.tree import WeightScheme, score_tree

__all__ = [
    "Clause",
    "Commitment",
    "Indicator",
    "Measure",
    "Provider",
    "RaterEstimate",
    "aggregate",
    "decomposition_invariance",
    "effective_raters",
    "pooling_diagnostic",
    "rank_stability",
    "variance_sensitivity",
]


def _flatten(tree_node: dict, into: dict[str, dict]) -> dict[str, dict]:
    into[tree_node["id"]] = tree_node
    for child in tree_node.get("children", []):
        _flatten(child, into)
    return into


def _published_band(ensemble: dict | None) -> dict | None:
    """The published bracket is the methodological-ensemble band (the headline recomputed across
    weight schemes) — coherent BY CONSTRUCTION: it is the point itself under alternate weights, so
    it always brackets the point. The Monte-Carlo PANEL band is deliberately NOT used as the
    headline CI: it pools the raters' own three-point uncertainty over a *different*
    quantity and can exclude the point. The panel band is still emitted as `ci_montecarlo`, a
    labelled diagnostic, alongside a `point_outside_panel` flag. When no ensemble band exists (a
    single weight scheme) there is no coherent indicator-level bracket -> None; we never fall back
    to the panel band as a fake CI."""
    if not ensemble:
        return None
    return {"low": ensemble["min"], "high": ensemble["max"], "basis": "ensemble"}


def _panel_divergence(score: float | None, mc: dict | None) -> dict | None:
    """Flag + signed distance for the arbitrated point lying outside the panel's [p5,p95] band
    Surfaces the arbitrator-vs-panel divergence the published bracket no longer hides;
    fires often by design (a quantized point vs an honestly-uncertain panel)."""
    if score is None or not mc:
        return None
    lo, hi = mc["p5"], mc["p95"]
    dist = round(lo - score, 6) if score < lo else round(score - hi, 6) if score > hi else 0.0
    return {"outside": dist > 0.0, "distance": max(dist, 0.0)}


def _merge(score_node: dict, mc_node: dict, ensemble_by_id: dict[str, dict]) -> dict:
    nid = score_node["id"]
    ens = ensemble_by_id.get(nid)
    mc_ci = mc_node.get("ci")
    merged = {
        "id": nid,
        "level": score_node["level"],
        "score": score_node["score"],
        "score_with_request": score_node["score_with_request"],
        "pct_public": score_node["pct_public"],
        "ci_montecarlo": mc_ci,
        "ci_ensemble": ens,
        "ci_published": _published_band(ens),
        "point_outside_panel": _panel_divergence(score_node["score"], mc_ci),
    }
    if "pooling" in mc_node:  # indicator-level LinOP-vs-LogOP diagnostic (ADR-0013)
        merged["pooling"] = mc_node["pooling"]
    score_kids = score_node.get("children", [])
    mc_kids = {k["id"]: k for k in mc_node.get("children", [])}
    if score_kids:
        merged["children"] = [
            _merge(sk, mc_kids.get(sk["id"], {}), ensemble_by_id) for sk in score_kids
        ]
    return merged


def aggregate(
    provider: Provider,
    *,
    weight_schemes: dict[str, WeightScheme] | None = None,
    n_samples: int = 10_000,
    seed: int = 12345,
    common_cause: float = 0.0,
    gamma: float = DEFAULT_GAMMA,
    rater_families: list[str] | None = None,
) -> dict:
    """Aggregate one provider×model into a published score tree with confidence bands.

    `weight_schemes` maps a scheme name to its id->weight overrides; the FIRST is primary
    (drives the headline score + MC band). v1 passes none -> a single uniform scheme. Supply
    2-3 schemes (e.g. uniform + Stage-2 Delphi weights) to get a real ensemble band and a
    rank-stability signal.

    `gamma` is the modified-PERT concentration (ADR-0013). `rater_families` — the vendor family
    per panel rater — adds an N_eff dependence diagnostic (effective number of independent
    raters) to the result.
    """
    schemes = weight_schemes or {"uniform": {}}
    names = list(schemes)
    primary = schemes[names[0]]

    # Per-scheme headline scores -> ensemble band per node (min/max across schemes).
    per_scheme_flat = {name: _flatten(score_tree(provider, schemes[name]), {}) for name in names}
    ensemble_by_id: dict[str, dict] = {}
    for nid in per_scheme_flat[names[0]]:
        vals = [
            per_scheme_flat[name][nid]["score"]
            for name in names
            if per_scheme_flat[name][nid]["score"] is not None
        ]
        if len(vals) >= 2 and (max(vals) > min(vals)):
            ensemble_by_id[nid] = {
                "min": min(vals),
                "max": max(vals),
                "by_scheme": {name: per_scheme_flat[name][nid]["score"] for name in names},
            }

    score = score_tree(provider, primary)
    mc = propagate(
        provider, primary, n_samples=n_samples, seed=seed, common_cause=common_cause, gamma=gamma
    )
    tree = _merge(score, mc, ensemble_by_id)
    result = {
        "provider": provider.name,
        "model": provider.model,
        "weight_schemes": names,
        "primary_scheme": names[0],
        "n_samples": n_samples,
        "seed": seed,
        "gamma": gamma,
        "tree": tree,
    }
    if rater_families:
        result["dependence"] = {
            "n_raters": len(rater_families),
            "rho_bar": mean_pairwise_rho(rater_families),
            "n_eff": effective_raters(rater_families),
        }
    return result
