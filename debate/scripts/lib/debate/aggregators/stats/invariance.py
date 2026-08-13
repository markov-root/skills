"""Decomposition-invariance check (the "#13 internal consistency" component).

Our central methodology claim: the **clause** is the scoring unit, so "indicator
count stops mattering for the score" — splitting or merging indicators must not move a measure's
headline. This module *tests* that claim by scoring a measure under alternative clause→indicator
partitions and reporting the deviation.

It also exposes the subtlety: with **equal per-indicator weight**, the claim is FALSE when
indicators hold unequal clause counts (a 1-clause indicator then counts as much as a 5-clause
one). Invariance holds iff each indicator's weight equals the sum of its clause weights
(`weight_mode="clause_mass"`), which reduces the measure to a flat weighted clause mean. Run
both modes to see the gap — this is a methodology finding, not just a test helper.

**Node-type awareness.** Once a node can be `any_of` (MAX) instead of `all_of`
(weighted mean), invariance is redefined from "invariant under any re-grouping" to "invariant
under **structure-preserving** re-grouping" — regrouping that keeps each node's type. Two locked
facts replace the single claim: (1) within `all_of`, clause-mass regrouping is invariant (above);
(2) an `any_of` node equals the **MAX** of its members (`any_of_equals_max`). Flipping a node's
type `all_of`↔`any_of` is a **semantic change** (a different, quote-licensed reading of the source
text) and is *allowed* to move the score — `type_flip_delta` reports that move as a finding, not a
bug.
"""

from __future__ import annotations

from debate.aggregators.stats.model import (
    VALUE_SCORE,
    Clause,
    Commitment,
    Indicator,
    Measure,
    Provider,
)
from debate.aggregators.stats.tree import score_tree


def _measure_headline(
    clauses_by_id: dict[str, Clause], groups: list[list[str]], weight_mode: str
) -> float | None:
    indicators = [
        Indicator(id=f"i{k}", clauses=[clauses_by_id[i] for i in ids])
        for k, ids in enumerate(groups)
    ]
    # clause_mass = the default (no scheme); equal = force every indicator to weight 1 via a scheme.
    scheme = {} if weight_mode == "clause_mass" else {ind.id: 1.0 for ind in indicators}
    tree = score_tree(Provider("X", [Commitment("c", [Measure("m", indicators)])]), scheme)
    return tree["children"][0]["children"][0]["score"]  # the measure node


def _single_indicator_headline(clauses: list[Clause], satisfy: str) -> float | None:
    """Score one measure holding a single indicator (all clauses) under a given `satisfy`."""
    ind = Indicator(id="i0", clauses=clauses, satisfy=satisfy)
    tree = score_tree(Provider("X", [Commitment("c", [Measure("m", [ind])])]))
    return tree["children"][0]["children"][0]["score"]


def decomposition_invariance(
    clauses: list[Clause], partitions: dict[str, list[list[str]]], *, weight_mode: str = "equal"
) -> dict:
    """Score one measure under several clause→indicator partitions; report whether the headline
    is invariant. `partitions` maps a label to a grouping of clause ids into indicators."""
    by_id = {c.id: c for c in clauses}
    scores = {
        name: _measure_headline(by_id, groups, weight_mode) for name, groups in partitions.items()
    }
    vals = [s for s in scores.values() if s is not None]
    deviation = (max(vals) - min(vals)) if len(vals) >= 2 else 0.0
    return {
        "weight_mode": weight_mode,
        "scores": scores,
        "max_deviation": round(deviation, 6),
        "invariant": deviation < 1e-9,
    }


def any_of_equals_max(clauses: list[Clause]) -> dict:
    """Locked invariant: an `any_of` node scores the MAX of its members' (applicable,
    headline) clause values. `headline` rolls them up through the real tree; `expected_max` is the
    direct MAX over the same clauses — they must coincide (MAX is weight-free and idempotent, so
    regrouping the members cannot move it)."""
    headline = _single_indicator_headline(clauses, "any_of")
    applicable = [
        c for c in clauses if c.active and c.value != "n/a" and c.verifiability == "public"
    ]
    expected = max((VALUE_SCORE[c.value] for c in applicable), default=None)
    holds = (headline is None and expected is None) or (
        headline is not None and expected is not None and abs(headline - expected) < 1e-9
    )
    return {"headline": headline, "expected_max": expected, "holds": holds}


def type_flip_delta(clauses: list[Clause]) -> dict:
    """Report the score move when one node flips `all_of`↔`any_of` on the SAME clauses.

    This is the demonstration that a type flip is a *semantic change*, not a regrouping: MAX ≥ the
    weighted mean, so `any_of - all_of` is ≥ 0 and is the (defensible, quote-licensed) over-credit
    a flat mean would have withheld. Logged as a finding; never asserted to be zero."""
    all_of = _single_indicator_headline(clauses, "all_of")
    any_of = _single_indicator_headline(clauses, "any_of")
    delta = (any_of - all_of) if (all_of is not None and any_of is not None) else None
    return {
        "all_of": all_of,
        "any_of": any_of,
        "delta": round(delta, 6) if delta is not None else None,
        "semantic_change": bool(delta is not None and abs(delta) > 1e-9),
    }
