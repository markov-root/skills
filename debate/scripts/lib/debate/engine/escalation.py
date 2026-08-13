"""Dynamic debate rounds (ADR-0011) — floor + cap + exhausted-search stop.

The engine always runs a FLOOR (propose → critique → revise) so a single pass never ships, and,
when a red-team is configured, a standard adversarial pass (redteam → respond). Beyond that it may
run ESCALATION passes — a red-team **licensed to propose a new option** → respond — focused on the
task-reported contested subset, until the **search is exhausted**: a full pass that adds no new
option, no new evidence citation, no clause-value change and no new finding. It explicitly does
**not** stop on agreement / low variance: agreement also occurs when the whole panel is wrong the
*same* way (correlated error), so an agreement-stop ships confident error and violates ADR-0014
(no forced convergence; spread is a diagnostic).

Three composable reasons rounds go dynamic (do not conflate them — ADR-0011):
  (I)   depth-on-demand        — stop early on EXHAUSTED search (efficiency).      → `progressed()`
  (II)  escalation-on-disagree — focus extra passes on the CONTESTED subset.       → task focus hook
  (III) breadth-on-stagnation  — the late round may PROPOSE, widening the options. → escalate prompt

`max_rounds` is the hard CAP on total phases (propose/critique/revise = 3; each adversarial pass
= 2). It defaults to 5 — exactly today's full config (floor + one standard red-team pass) — so the
engine's behaviour is unchanged until the cap is raised, at which point escalation passes run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# The floor: always run, so a single-pass answer never ships (ADR-0011).
FLOOR_ROUNDS = ("propose", "critique", "revise")
FLOOR_PHASES = len(FLOOR_ROUNDS)

# Stop reasons. Every reason is a COMPLETE (legitimately finished) debate except a budget hit,
# which is an interrupted, resumable `ongoing-incomplete` (ADR-0011).
STOP_FLOOR = "floor_only"  # no red-team configured (lean config) — no adversary to escalate with
STOP_STANDARD = "standard_pass"  # ran the standard red-team pass; cap leaves no room to escalate
STOP_NO_FOCUS = "no_focus"  # task does not support escalation (focus hook returns None)
STOP_NO_CONTESTED = "no_contested"  # focus is empty — nothing contested to deepen
STOP_EXHAUSTED = "exhausted_search"  # a full pass added no new search information (the (I) stop)
STOP_NOVELTY = "no_new_option"  # a pass minted no genuinely-new unique option — novelty gate (0015)
STOP_CAP = "cap_reached"  # hit `max_rounds` — escalation bounded so it can't run away
STOP_BUDGET = "budget_exhausted"  # token ceiling hit — a non-complete (resumable) stop
STOP_LIMIT = "usage_limit"  # subscription/plan quota hit — resumable park (ADR-0016), NOT complete

# Non-complete (resumable) stops: STOP_BUDGET (token ceiling) and STOP_LIMIT (quota park). A re-run
# resumes from cache and finishes the debate — neither is a legitimately-finished result.
_COMPLETE = frozenset(
    {
        STOP_FLOOR,
        STOP_STANDARD,
        STOP_NO_FOCUS,
        STOP_NO_CONTESTED,
        STOP_EXHAUSTED,
        STOP_NOVELTY,
        STOP_CAP,
    }
)

_SUFFIX = re.compile(r"-\d+$")  # "respond-2" -> stage "respond"; "escalate-1" -> "escalate"


def is_complete(reason: str) -> bool:
    """True unless the stop was a budget interruption (which is resumable, not finished)."""
    return reason in _COMPLETE


def stage_of(round_name: str) -> str:
    """The semantic STAGE a (possibly numbered) round maps to, for prompt/schema lookup.

    Storage keys rounds uniquely ("escalate-1", "respond-2") so resume is unambiguous; the task's
    `system_prompt`/`output_schema` key on the stage ("escalate", "respond")."""
    return _SUFFIX.sub("", round_name)


def progressed(seen: set, new: set) -> bool:
    """Did a round add new search information? True iff it contributed a token not already SEEN.

    Compared against the CUMULATIVE union of all prior rounds (not just the previous one), so an
    A→B→A oscillation reads as exhausted, not as endless progress. This is the (I) depth-on-demand
    stop — a pure function of the search signature, with NO dependence on inter-rater agreement."""
    return not new.issubset(seen)


@dataclass
class RoundLedger:
    """Per-item round bookkeeping (ADR-0011).

    The floor + standard pass touch every item; escalation passes touch only the focused
    (contested) subset. Recording round-count + final-round PER ITEM keeps the ADR-0014
    pre/post inflation & conformity diagnostics comparable across lean vs escalated items —
    otherwise the "post-debate" condition silently differs without being recorded."""

    rounds: dict[str, int] = field(default_factory=dict)
    final_round: dict[str, str] = field(default_factory=dict)

    def record(self, round_name: str, item_ids) -> None:
        for iid in item_ids:
            self.rounds[iid] = self.rounds.get(iid, 0) + 1
            self.final_round[iid] = round_name

    def dump(self) -> dict[str, dict]:
        return {
            iid: {"rounds": n, "final_round": self.final_round.get(iid)}
            for iid, n in sorted(self.rounds.items())
        }


@dataclass
class StopLedger:
    """Persisted escalation stop state (audit B-1) — written to `round_status.json` under
    `stop_ledger` so a RESUMED run reconstructs the stop decision FROM DISK instead of re-deriving
    it by re-calling the task's stop/focus hooks (escalation_focus / extract_atoms /
    search_signature / arbitrate_collision) over the cached field.

    Why it matters: those hooks are only guaranteed to resume deterministically if they are PURE
    functions of the field (a contract now stated in `DebateTask`). A hook that touches `random`,
    the clock, or the network would make a re-run stop at a different pass than the original — a
    silent divergence in "the one thing that must work perfectly" (resume). Persisting each pass's
    focus + terminal decision closes that gap: on resume of a COMPLETE escalation the loop replays
    exactly these passes (every model call is cached, so no re-charge) and adopts the recorded
    `stop_reason`, never re-consulting the hooks. An INCOMPLETE (parked / budget) escalation has no
    complete ledger, so the loop falls back to live derivation and continues where it left off (the
    per-pass coverage/signature accumulator is not persisted — a documented carry-forward).

    Pure bookkeeping: this changes no stop MATH; it records the decisions the loop already makes.
    """

    passes: list[dict] = field(
        default_factory=list
    )  # per-pass: {pass, focus, stop, stop_reason, …}
    stop_reason: str | None = None
    complete: bool = False

    def record(self, k: int, focus, *, stop: bool, stop_reason: str | None, spent: int, **extra):
        """Append one escalation pass's decision. `extra` carries diagnostics (missing_mass,
        signature, …) — informational only; replay keys solely on `focus`/`stop`/`stop_reason`."""
        self.passes.append(
            {
                "pass": k,
                "focus": list(focus),
                "stop": bool(stop),
                "stop_reason": stop_reason,
                "spent": int(spent),
                **extra,
            }
        )

    def finalize(self, stop_reason: str | None, complete: bool) -> StopLedger:
        """Stamp the terminal reason once the loop ends (a top-of-loop cap/no-contested break
        records no pass, so the terminal reason lives here, not on a pass entry)."""
        self.stop_reason = stop_reason
        self.complete = bool(complete)
        return self

    @property
    def n_passes(self) -> int:
        return len(self.passes)

    def decision_for(self, k: int) -> dict | None:
        """The recorded entry for escalation pass `k`, or None if that pass was never recorded."""
        for p in self.passes:
            if p.get("pass") == k:
                return p
        return None

    def escalation_complete(self) -> bool:
        """True iff a prior run recorded a COMPLETE escalation (≥1 pass, a terminal complete stop).
        Only then is a hook-free replay sound; a budget/park stop returns False → live fallback."""
        return self.n_passes > 0 and self.stop_reason is not None and is_complete(self.stop_reason)

    def serialize(self) -> dict:
        return {"passes": self.passes, "stop_reason": self.stop_reason, "complete": self.complete}

    @classmethod
    def load(cls, status: dict | None) -> StopLedger:
        """Reconstruct from a prior `round_status.json` dict (empty if it carries no ledger — e.g.
        an old run or a bare quota-park marker, both of which then take the live path)."""
        raw = (status or {}).get("stop_ledger") or {}
        led = cls(passes=[dict(p) for p in (raw.get("passes") or [])])
        led.stop_reason = raw.get("stop_reason")
        led.complete = bool(raw.get("complete"))
        return led


# ---------------------------------------------------------------------------
# Marginal information value (ADR-0011)
#
# The exhausted-search stop above keys on a task `search_signature` that, for
# generation, partly hashed CLAUSE TEXT — so a reworded clause read as "new" (a
# ~9x productivity overcount on the ss-7.4 run) and a genuinely-new-but-redundant
# item counted as progress. The fix moves the unit from surface text to the
# REQUIREMENT-ATOM (one testable obligation, anchored to a verbatim sub-span) and
# gates escalation on MARGINAL COVERAGE of atoms, never on agreement.
#
# This module owns only the DETERMINISTIC, task-agnostic, hand-recomputable core:
# the atom ledger, the five-class marginal-value classification, the Good-Turing
# exhausted-search estimate, and a reversible merge forest. The LLM-asserted parts
# (extracting atoms from a span, the collision verb, the archetype discrimination
# panel) are task hooks (DebateTask) with safe offline fallbacks. Discrimination
# only RANKS/FLAGS — it is structurally excluded from the stop, so no predicted
# quantity can ever halt the loop (the red-team's catch).
# ---------------------------------------------------------------------------

# Marginal-value classes (ADR-0011). Order = descending value.
CLS_ORTHOGONAL = "orthogonal-new-coverage"  # ≥1 atom no existing item tests
CLS_DECOMPOSES = "decomposes"  # new atom INSIDE an already-cited span (same span, new duty)
CLS_CONTRADICTS = (
    "contradicts"  # same atom, opposing reading — a PRESERVED FINDING (keeps loop alive)
)
CLS_REFINEMENT = "refinement"  # no new atom, but sharper wording — lower-but-real value, kept
CLS_REDUNDANT = "redundant"  # all atoms already covered, no sharpening — merge candidate

# Classes that count as PRODUCTIVE for the escalation gate: a new atom, or a
# preserved disagreement. Refinements and redundants do NOT keep the loop alive
# (they are kept and ranked, but they are not "new search").
_PRODUCTIVE = frozenset({CLS_ORTHOGONAL, CLS_DECOMPOSES, CLS_CONTRADICTS})

# Exhausted-search stop parameter (ADR-0011). Hand-set, versioned here, not learned.
# K_UNPRODUCTIVE=1 → stop the first pass that adds no new atom and no contradiction (the clean
# "no new signal" reading). Reads ONLY coverage productivity — never discrimination.
UNPRODUCTIVE_STOP_K = 1


def is_productive(cls: str) -> bool:
    return cls in _PRODUCTIVE


def good_turing_missing_mass(observation_counts: dict) -> float:
    """Good–Turing estimate of the probability the NEXT observation is a new type.

    `observation_counts` maps atom-key -> how many items have asserted it so far.
    missing_mass = N1 / N where N1 = #atom-keys seen exactly once, N = total observations.
    High while the search keeps minting singletons (new atoms); falls as passes start
    repeating known atoms. This is the principled reading of "exhausted search" — and it
    reads ONLY coverage observations, never any rater-agreement or discrimination signal.
    """
    total = sum(observation_counts.values())
    if total == 0:
        return 1.0
    singletons = sum(1 for c in observation_counts.values() if c == 1)
    return singletons / total


class CoverageLedger:
    """Tracks the requirement-atoms the debate has covered, classifies each pass's field
    against them, and reports the exhausted-search stop on MARGINAL COVERAGE.

    Atoms are opaque dicts the task supplies: {"key", "item", "salience"?, "span"?}.
    `key` is the dedup unit (a normalized obligation, NOT clause text). Everything here is
    deterministic given the atoms — the subjectivity lives entirely in how the task
    extracts atoms, which is auditable (each atom anchors to a verbatim sub-span).
    """

    def __init__(self):
        self.covered: dict[str, str] = {}  # atom-key -> first item id that introduced it
        self.spans: dict[str, set] = {}  # item id -> set of atom-keys (for decomposes/merge)
        self.counts: dict[str, int] = {}  # atom-key -> #items asserting it (Good-Turing)
        self.unproductive_streak = 0

    def classify(self, item_id: str, atoms: list, *, contradicts: bool = False) -> dict:
        """Classify one item's atoms against what's covered. `contradicts` is supplied by
        the task's collision-arbitration hook (default False) — the only non-deterministic input,
        and the only route to CLS_CONTRADICTS."""
        keys = [a["key"] for a in atoms]
        novel = [k for k in keys if k not in self.covered]
        salience = {a["key"]: float(a.get("salience", 1.0)) for a in atoms}
        if novel:
            # new atom that lands inside a span already cited by an existing item = decomposes
            shares = any(k in self.spans.get(item_id, set()) for k in keys) or any(
                set(keys) & ks for iid, ks in self.spans.items() if iid != item_id
            )
            cls = CLS_DECOMPOSES if (shares and len(novel) < len(keys)) else CLS_ORTHOGONAL
        elif contradicts:
            cls = CLS_CONTRADICTS
        else:
            cls = CLS_REDUNDANT  # the engine cannot see "sharper wording"; the task may upgrade
        return {
            "item": item_id,
            "class": cls,
            "novel_atoms": novel,
            "coverage_gain": round(sum(salience[k] for k in novel), 4),
            "productive": is_productive(cls) or contradicts,
        }

    def commit(self, item_id: str, atoms: list) -> None:
        """Fold an item's atoms into the covered set + observation counts."""
        self.spans.setdefault(item_id, set())
        for a in atoms:
            k = a["key"]
            self.covered.setdefault(k, item_id)
            self.spans[item_id].add(k)
            self.counts[k] = self.counts.get(k, 0) + 1

    def assess_pass(self, classifications: list) -> dict:
        """Roll a pass's per-item classifications into the pass-level coverage signal."""
        productive = sum(1 for c in classifications if c["productive"])
        self.unproductive_streak = 0 if productive else self.unproductive_streak + 1
        from collections import Counter

        return {
            "productive_items": productive,
            "coverage_gain": round(sum(c["coverage_gain"] for c in classifications), 4),
            "classes": dict(Counter(c["class"] for c in classifications)),
            "missing_mass": round(good_turing_missing_mass(self.counts), 4),
            "unproductive_streak": self.unproductive_streak,
        }

    def exhausted(self, *, k_unproductive: int) -> bool:
        """Exhausted-search stop: `k_unproductive` consecutive passes added no PRODUCTIVE coverage
        (no new atom and no `contradicts`). This is the discrete form of "the search is mined out."

        Reads ONLY the productivity streak — never agreement, never discrimination (the
        no-guessed-quantity-stops rule). The Good-Turing `missing_mass` is reported per pass as a
        continuous diagnostic of the same exhaustion, but is deliberately NOT an independent stop:
        a productive-but-no-new-atom pass (a `contradicts`/preserved finding) drives missing_mass
        toward 0 yet must keep the loop alive, so productivity — not raw atom mass — is the gate."""
        return self.unproductive_streak >= k_unproductive


class MergeForest:
    """Reversible union-find over item ids for consolidation (ADR-0011).

    Redundant/duplicate items re-parent under a canonical one; refinements attach as
    first-class variants (kept, ranked, never deleted). `unmerge` splits a link when later
    evidence (differing pass-vectors) shows two merged atoms actually discriminate apart.
    Records metadata only — the arbitrator does any physical merge; the score is already
    redundancy-proof (clause-mass weighting), so this is parsimony/interpretability, not score.
    """

    def __init__(self):
        self.canonical: dict[str, str] = {}  # item -> its canonical (self if a canonical)
        self.variants: dict[str, list] = {}  # canonical -> [(item, relation)]

    def attach(self, item: str, canonical: str, relation: str) -> None:
        self.canonical[item] = canonical
        self.canonical.setdefault(canonical, canonical)
        self.variants.setdefault(canonical, []).append({"item": item, "relation": relation})

    def unmerge(self, item: str) -> None:
        c = self.canonical.get(item)
        if c and c != item:
            self.variants[c] = [v for v in self.variants.get(c, []) if v["item"] != item]
            self.canonical[item] = item

    def dump(self) -> dict:
        clusters = {c: v for c, v in self.variants.items() if v}
        return {"clusters": clusters, "n_merged": sum(len(v) for v in clusters.values())}
