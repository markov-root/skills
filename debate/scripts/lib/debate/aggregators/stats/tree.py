"""The deterministic weighted-mean tree — the headline machinery.

clause score -> indicator -> measure -> commitment -> overall, each a weighted mean of the
level below. Three things ride alongside every score:

  * the **headline** uses `public` clauses only, re-normalised over public-clause weights;
  * a **with-request** score adds `request` clauses (drilldown; never headlined);
  * **% publicly verifiable** — the share of *applicable* clause weight tagged `public`.

`regulator_only` clauses are never scored (not testable from public evidence). `n/a` clauses
are excluded from the denominator (not scored 0). Aggregation is **weight-parameterised**: a
`WeightScheme` overrides indicator/measure/commitment weights by id (clause weights are
intrinsic to the clause and never overridden); v1 passes none → uniform.
"""

from __future__ import annotations

from collections.abc import Iterable

from debate.aggregators.stats.model import (
    HEADLINE_VERIFIABILITY,
    VALUE_SCORE,
    WITH_REQUEST_VERIFIABILITY,
    Clause,
    Commitment,
    Indicator,
    Measure,
    Provider,
)

# A weight scheme overrides a node's weight by id; missing id -> the node's own default.
WeightScheme = dict[str, float]


def _applicable(c: Clause) -> bool:
    """A clause counts toward scores iff it is **active** (its codebook activation condition holds)
    and carries a fulfilment value — inactive clauses are the principled `n/a`, excluded from the
    denominator rather than scored 0 (ADR-0017). Legacy `value == "n/a"` is treated the same."""
    return c.active and c.value != "n/a"


def node_weight(scheme: WeightScheme, node_id: str, default: float) -> float:
    return scheme.get(node_id, default)


def _weighted_mean(pairs: Iterable[tuple[float | None, float]]) -> float | None:
    """Weighted mean over (value, weight), skipping None values. None if nothing contributes."""
    kept = [(v, w) for v, w in pairs if v is not None]
    den = sum(w for _, w in kept)
    if not kept or den == 0:
        return None
    return sum(v * w for v, w in kept) / den


def indicator_score(
    ind: Indicator, verif_set: frozenset[str], scheme: WeightScheme
) -> float | None:
    """Indicator score over the applicable clauses whose verifiability is in `verif_set`.

    `all_of` (default) → the clause-mass weighted mean. `any_of` → **MAX** over the
    applicable clauses (the Zadeh t-conorm): a quote-licensed disjunction where either route
    satisfies the measure, so a fully-met route is not penalised for an un-attempted alternative.
    MAX is weight-free (idempotent) — clause weights set the parent mean, not the OR.

    None when no clause qualifies (e.g. a `request`/`regulator_only`-only indicator has no
    headline score — it then drops out of its parent's mean rather than scoring 0).
    """
    applicable = [c for c in ind.clauses if _applicable(c) and c.verifiability in verif_set]
    if not applicable:
        return None
    if ind.satisfy == "any_of":
        return max(VALUE_SCORE[c.value] for c in applicable)
    return _weighted_mean((VALUE_SCORE[c.value], c.weight) for c in applicable)


def effective_indicator_weight(
    ind: Indicator, verif_set: frozenset[str], scheme: WeightScheme
) -> float:
    """An indicator's weight in its measure's mean.

    Default = its **clause mass** on this basis (Σ weights of its applicable clauses whose
    verifiability is in `verif_set`). This makes the measure a flat weighted *clause* mean, so
    the headline is invariant to how clauses are grouped into indicators — the clause is the
    unit. A scheme override (e.g. Stage-2 importance weights) takes precedence and
    deliberately departs from invariance; that shows up as ensemble spread, not a silent change.
    """
    if ind.id in scheme:
        return scheme[ind.id]
    return sum(c.weight for c in ind.clauses if _applicable(c) and c.verifiability in verif_set)


def _pct_public(clauses: list[Clause]) -> float | None:
    """Share of applicable clause weight tagged `public`. A pure coverage statistic —
    independent of the weight scheme and of whether clauses are met."""
    applicable = [c for c in clauses if _applicable(c)]
    total = sum(c.weight for c in applicable)
    if not applicable or total == 0:
        return None
    public = sum(c.weight for c in applicable if c.verifiability == "public")
    return public / total


def _clauses_under(node: Indicator | Measure | Commitment | Provider) -> list[Clause]:
    if isinstance(node, Indicator):
        return list(node.clauses)
    children = (
        node.indicators
        if isinstance(node, Measure)
        else node.measures
        if isinstance(node, Commitment)
        else node.commitments
    )
    return [c for child in children for c in _clauses_under(child)]


def _indicator_node(ind: Indicator, scheme: WeightScheme) -> dict:
    return {
        "id": ind.id,
        "level": "indicator",
        "score": indicator_score(ind, HEADLINE_VERIFIABILITY, scheme),
        "score_with_request": indicator_score(ind, WITH_REQUEST_VERIFIABILITY, scheme),
        "pct_public": _pct_public(ind.clauses),
    }


def _roll_up(
    node_id: str,
    level: str,
    children: list[dict],
    weights: dict[str, float],
    descendants: list[Clause],
) -> dict:
    return {
        "id": node_id,
        "level": level,
        "score": _weighted_mean((c["score"], weights[c["id"]]) for c in children),
        "score_with_request": _weighted_mean(
            (c["score_with_request"], weights[c["id"]]) for c in children
        ),
        "pct_public": _pct_public(descendants),
        "children": children,
    }


def _measure_node(m: Measure, scheme: WeightScheme) -> dict:
    """Roll indicators up to a measure with BASIS-SPECIFIC clause-mass weights: the headline
    weights by public-clause mass, the drilldown by public+request mass. Both reduce to a flat
    weighted clause mean (decomposition-invariant)."""
    ind_nodes = [_indicator_node(ind, scheme) for ind in m.indicators]

    def mean(verif_set: frozenset[str], key: str) -> float | None:
        return _weighted_mean(
            (node[key], effective_indicator_weight(ind, verif_set, scheme))
            for ind, node in zip(m.indicators, ind_nodes, strict=True)
        )

    return {
        "id": m.id,
        "level": "measure",
        "score": mean(HEADLINE_VERIFIABILITY, "score"),
        "score_with_request": mean(WITH_REQUEST_VERIFIABILITY, "score_with_request"),
        "pct_public": _pct_public(_clauses_under(m)),
        "children": ind_nodes,
    }


def score_tree(provider: Provider, scheme: WeightScheme | None = None) -> dict:
    """Compute the full deterministic score tree for one provider×model under a weight scheme."""
    scheme = scheme or {}
    commitments: list[dict] = []
    for com in provider.commitments:
        measures: list[dict] = []
        for m in com.measures:
            measures.append(_measure_node(m, scheme))
        meas_w = {m.id: node_weight(scheme, m.id, m.weight) for m in com.measures}
        commitments.append(_roll_up(com.id, "commitment", measures, meas_w, _clauses_under(com)))
    com_w = {com.id: node_weight(scheme, com.id, com.weight) for com in provider.commitments}
    return _roll_up(provider.name, "overall", commitments, com_w, _clauses_under(provider))
