"""Internal aggregation data model — the input the MC/tree engine consumes.

Deliberately decoupled from the wire contract (`schemas/scores.schema.json`): this model
works in [0,1] floats over dataclasses (what the math wants), while the wire schema is the
0–100 JSON distribution artifact (what readers want). Both now speak the same methodology
(per-clause verifiability + IDEA three-point); a thin adapter maps between them.

The scoring unit is the clause. Verifiability and n/a handling live there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from debate.aggregators.stats.distributions import CREDIBLE_LEVEL

ClauseValue = Literal["met", "partial", "not_met", "n/a"]
Verifiability = Literal["public", "request", "regulator_only"]

# Clause value -> score on [0,1]. "n/a" is absent here on purpose: it is *excluded* from
# the denominator (not scored 0), so it never maps to a number.
VALUE_SCORE: dict[str, float] = {"met": 1.0, "partial": 0.5, "not_met": 0.0}

# Verifiability sets per reporting basis:
#   headline      = public clauses only (the defensible cross-provider number)
#   with_request  = public + request (drilldown; Article-91 candidates, scored not headlined)
#   regulator_only is never in either set — not testable from public evidence.
HEADLINE_VERIFIABILITY: frozenset[str] = frozenset({"public"})
WITH_REQUEST_VERIFIABILITY: frozenset[str] = frozenset({"public", "request"})


@dataclass(frozen=True)
class Clause:
    """One objective near-binary check, split into two axes (ADR-0017):

    * **activation** — `active`: does this clause apply to this provider/model? Decided
      structurally from the codebook's checkable activation condition, NOT a per-rater vote. An
      inactive clause is excluded from the denominator (the principled `n/a`).
    * **fulfilment** — `value` (met/partial/not_met): the scorer's judgment, meaningful only for
      an *active* clause. An active clause unmet by evidence is `not_met` — never silently dropped.
    """

    id: str
    value: ClauseValue
    verifiability: Verifiability
    weight: float = 1.0
    active: bool = True


@dataclass(frozen=True)
class RaterEstimate:
    """One rater's IDEA three-point estimate of an indicator's score, on [0,1].

    `confidence` is the rater's stated probability that the truth lies within [low, high]; it
    rescales the interval to the common credible level before pooling (a low confidence widens
    the band — ADR-0013). The default is `CREDIBLE_LEVEL`, i.e. "interval as stated / no rescale":
    a missing confidence must NOT be read as full certainty (which would wrongly narrow the band).
    """

    low: float
    best: float
    high: float
    confidence: float = CREDIBLE_LEVEL


SatisfyOp = Literal["all_of", "any_of"]


@dataclass
class Indicator:
    """A scorable atom: a clause checklist plus (optionally) per-rater three-point estimates.

    `estimates` drives the Monte-Carlo band. An indicator with no estimates still produces a
    deterministic point score and propagates as a degenerate (point-mass) sample.

    `satisfy` is the operator combining this indicator's clauses:

    * **`all_of`** (default) — the clause-mass weighted mean: every clause contributes additively
      (implicitly conjunctive; failing one is partly compensated by passing others).
    * **`any_of`** — **MAX** over the applicable clauses (the Zadeh t-conorm / fuzzy OR), used
      ONLY where the source text itself offers alternative routes to satisfaction ("…through X *or*
      through Y"). Licensed at generation time by a verbatim disjunctive `cop_quote` + the
      anti-squishiness gate — never a per-rater scoring vote. MAX is monotone,
      idempotent, and honest about `partial` (a 0.5 on the single attempted route scores 0.5).
    """

    id: str
    clauses: list[Clause]
    estimates: list[RaterEstimate] = field(default_factory=list)
    weight: float = 1.0
    satisfy: SatisfyOp = "all_of"


@dataclass
class Measure:
    id: str
    indicators: list[Indicator]
    weight: float = 1.0


@dataclass
class Commitment:
    id: str
    measures: list[Measure]
    weight: float = 1.0


@dataclass
class Provider:
    """One provider × model assessment tree. `model` is None for lab-level (firm-wide) scope."""

    name: str
    commitments: list[Commitment]
    model: str | None = None
