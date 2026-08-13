"""The debate PLAN — the config-driven round pipeline as data (ADR-0011/0012; task-0017 Phase B).

The engine's round sequence is a `Plan`: an ordered list of `PhaseSpec`s the stage-runner executes
(Phase C). Today's hardcoded propose→critique→revise→(redteam→respond)→escalate→aggregate is just
`default_plan(...)` — so making a debate a different shape is a config edit, not a code edit.

This module is **engine-owned and task-agnostic** (ADR-0002): it imports nothing from
`debate.tasks`.
It owns the plan model, pass-expansion, load-time validation against the `docs/round-types.md`
catalog,
the role-**pools** normalization (ADR-0017/0018), and a stable `plan_hash`. It does NOT execute
anything (that is the runner, Phase C) — so importing it has no runtime effect on a debate.

Vocabulary (ADR-0012): a **phase** is one atomic model call step (propose/critique/…); a
**plan** is the ordered phases = the protocol. A **pass** (`floor`/`adversarial`/`escalation`)
is a shorthand that
expands to its phases (`docs/round-types.md` §3).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# --- the phase catalog (docs/round-types.md §1) ---------------------------------------------
# Each stage binds to a role POOL with a SHAPE, and declares its aggregation KIND. `precondition` is
# the stage that must appear earlier for this one to be legal (validated at load). `escalate` is the
# only inherently dynamic phase (it may repeat on the contested subset until a stop rule fires).

PROPOSE, CRITIQUE, REVISE = "propose", "critique", "revise"
REDTEAM, RESPOND, ESCALATE, AGGREGATE = "redteam", "respond", "escalate", "aggregate"

# stage -> (role_pool, shape, kind, precondition-stage or None)
_CATALOG: dict[str, tuple[str, str, str, str | None]] = {
    PROPOSE: ("proposers", "fan-out", "generate", None),
    CRITIQUE: ("reviewers", "fan-out", "generate", PROPOSE),
    REVISE: ("proposers", "fan-out", "generate", CRITIQUE),
    REDTEAM: ("adversaries", "single", "generate", REVISE),
    RESPOND: ("proposers", "fan-out", "generate", None),  # attacker precondition checked specially
    ESCALATE: ("adversaries", "single", "generate", RESPOND),
    AGGREGATE: ("aggregators", "single", "reduce", None),  # closer, appended automatically
}

# Passes expand to phases (docs/round-types.md §3). The engine enables/disables the pass,
# not halves.
_PASSES: dict[str, list[str]] = {
    "floor": [PROPOSE, CRITIQUE, REVISE],
    "adversarial": [REDTEAM, RESPOND],
    "escalation": [ESCALATE, RESPOND],  # dynamic; repeats until a stop rule fires
}

FLOOR_MIN = 3  # propose+critique+revise — the cheapest complete debate (never ship a single pass)
_ATTACKERS = frozenset({REDTEAM, ESCALATE})
# The only keys a `rounds:` block may carry, and the only referee injection points the engine
# calls (loop.py runs `before_revise` after critique, `before_respond` after the red-team). Unknown
# entries in either are rejected at load — silently ignoring a mis-typed `before_critique:` would
# drop the user's checks and fall back to defaults with no error (the trap this closes).
_ROUNDS_KEYS = frozenset({"min", "max", "plan", "token_budget", "referees"})
_REFEREE_POINTS = frozenset({"before_revise", "before_respond"})
# The role pools a phase may bind to (ADR-0017/0018). Kept here so validation is one
# source of truth.
POOLS = ("proposers", "reviewers", "adversaries", "aggregators")


class PlanError(ValueError):
    """A round plan is malformed — raised at load, fail-fast, with the offending phase named."""


@dataclass(frozen=True)
class PhaseSpec:
    """One phase in the plan: a stage bound to a role pool with a shape (ADR-0017 wide contract)."""

    stage: str  # prompt/schema key (propose/critique/revise/redteam/respond/escalate/aggregate)
    role_pool: str  # proposers | reviewers | adversaries | aggregators
    shape: str  # single | fan-out | sample-k
    kind: str  # generate | elicit | reduce  (elicit→reduce is the ADR-0017 ballot pair)
    k: int | None = None  # sample-k size, when shape == sample-k
    referees: tuple[str, ...] = ()  # deterministic checks injected before this phase (task-0013)
    dynamic: bool = False  # may repeat (escalate) until repeat_until fires
    repeat_until: str | None = None  # names the task stop-predicate the runner evaluates (Phase C)

    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "role_pool": self.role_pool,
            "shape": self.shape,
            "kind": self.kind,
            "k": self.k,
            "referees": list(self.referees),
            "dynamic": self.dynamic,
            "repeat_until": self.repeat_until,
        }


def _phase(
    stage: str, *, referees=(), dynamic=False, repeat_until=None, shape=None, k=None
) -> PhaseSpec:
    role_pool, default_shape, kind, _pre = _CATALOG[stage]
    return PhaseSpec(
        stage=stage,
        role_pool=role_pool,
        shape=shape or default_shape,
        kind=kind,
        k=k,
        referees=tuple(referees),
        dynamic=dynamic,
        repeat_until=repeat_until,
    )


@dataclass
class Plan:
    """An ordered list of phases + the caps that bound a run. `max` caps total runtime phases
    (floor=3, each adversarial/escalation pass=2); `token_budget` is the graceful escalation
    ceiling (ADR-0011). Both are PER-DEBATE here (audit F-1), snapshotted with
    the run in Phase C."""

    phases: list[PhaseSpec]
    min: int = FLOOR_MIN
    max: int = 5
    token_budget: int | None = None
    referees: dict = field(default_factory=dict)  # before_<stage> / gates lists (task-0013)

    @property
    def stages(self) -> list[str]:
        return [p.stage for p in self.phases]

    @property
    def has_adversary(self) -> bool:
        return any(p.stage in _ATTACKERS for p in self.phases)

    @property
    def is_dynamic(self) -> bool:
        return any(p.dynamic for p in self.phases)

    def as_dict(self) -> dict:
        return {
            "phases": [p.as_dict() for p in self.phases],
            "min": self.min,
            "max": self.max,
            "token_budget": self.token_budget,
            "referees": self.referees,
            "plan_hash": self.plan_hash,
        }

    @property
    def plan_hash(self) -> str:
        """Stable hash of the plan's STRUCTURE (phases + min/max). Excludes token_budget (a
        resource ceiling, not shape). Used to key the aggregate cache (audit D-2) and stamp
        the trace (ADR-0020) so an edited plan re-fires the reduce instead of silently reusing
        a stale result."""
        payload = json.dumps(
            {"phases": [p.as_dict() for p in self.phases], "min": self.min, "max": self.max},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# --- the default plan = today's hardcoded sequence, expressed as data -----------------------


def default_plan(
    *, has_redteam: bool, dynamic: bool = True, max_rounds: int = 5, token_budget: int | None = None
) -> Plan:
    """The plan the engine runs today (byte-behavior target for the Phase C regression gate).

    floor (propose·critique·revise) + — when a red-team is configured — one standard
    `adversarial` pass (redteam·respond) + a `dynamic` `escalation` pass
    (escalate·respond, repeats on the contested subset). `aggregate` is appended as the
    closer. With `max_rounds=5` (the default) the escalation pass is present but never
    reached (floor 3 + adversarial 2 = 5 = cap), exactly like `loop.py` today —
    escalation only fires when the cap is raised. So this reproduces current behavior for
    both the lean (no red-team) and full configs."""
    phases: list[PhaseSpec] = [_phase(PROPOSE), _phase(CRITIQUE), _phase(REVISE)]
    if has_redteam:
        phases += [_phase(REDTEAM), _phase(RESPOND)]
        if dynamic:
            phases += [
                _phase(ESCALATE, dynamic=True, repeat_until="escalation_stop"),
                _phase(RESPOND, dynamic=True),
            ]
    phases.append(_phase(AGGREGATE))
    return Plan(phases=phases, min=FLOOR_MIN, max=max_rounds, token_budget=token_budget)


# --- loading a plan from config (docs/round-types.md §3 list form) --------------------------


def expand_passes(items: list) -> list[str]:
    """Expand a `plan:` list of stage-names and `{pass: <name>, dynamic?: bool}` shorthands
    into a flat stage list. A bare string is a stage; a mapping is a pass. `aggregate` is
    NOT added here (the loader appends it as the closer). Unknown stage/pass names fail fast."""
    out: list[str] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            if item not in _CATALOG:
                raise PlanError(f"unknown stage {item!r} (known: {sorted(_CATALOG)})")
            if item == ESCALATE:
                raise PlanError(
                    f"plan item {index}: bare 'escalate' cannot run safely; use "
                    "{pass: escalation, dynamic: true}"
                )
            out.append(item)
        elif isinstance(item, dict) and "pass" in item:
            unknown = sorted(str(k) for k in item if k not in {"pass", "dynamic"})
            if unknown:
                raise PlanError(
                    f"plan item {index}: unknown pass key(s) {unknown} — "
                    "allowed: ['dynamic', 'pass']"
                )
            name = item["pass"]
            if name not in _PASSES:
                raise PlanError(f"unknown pass {name!r} (known: {sorted(_PASSES)})")
            if "dynamic" in item and type(item["dynamic"]) is not bool:
                raise PlanError(f"plan item {index}: `dynamic` must be true or false")
            if name == "escalation" and item.get("dynamic") is not True:
                raise PlanError(f"plan item {index}: escalation must declare `dynamic: true`")
            out.extend(_PASSES[name])
        else:
            raise PlanError(f"plan item must be a stage name or {{pass: ...}}, got {item!r}")
    return out


def _validate_ordering(stages: list[str]) -> None:
    """Enforce the dependency graph (docs/round-types.md §2) on a flat stage list
    (pre-aggregate)."""
    if not stages:
        raise PlanError("empty plan")
    if stages[0] != PROPOSE:
        raise PlanError(f"plan must open with 'propose' (index 0), got {stages[0]!r}")
    if AGGREGATE in stages[: -0 or len(stages)]:
        # aggregate is appended by the loader; a user-supplied aggregate mid-plan is illegal
        if AGGREGATE in stages:
            raise PlanError("'aggregate' is the implicit closer — do not list it in the plan")
    seen: set[str] = set()
    attacker_since_respond = False
    for i, st in enumerate(stages):
        pre = _CATALOG[st][3]
        if pre is not None and pre not in seen:
            raise PlanError(f"phase {i} {st!r} requires a preceding {pre!r}")
        if st in _ATTACKERS:
            if attacker_since_respond:
                raise PlanError(
                    f"phase {i} {st!r} starts before the preceding attack received a 'respond'"
                )
            attacker_since_respond = True
        if st == RESPOND:
            if not attacker_since_respond:
                raise PlanError(f"phase {i} 'respond' has no preceding attacker (redteam/escalate)")
            attacker_since_respond = False
        seen.add(st)
    if attacker_since_respond:
        raise PlanError("plan ends with an attack that has no following 'respond'")


def resolve_pools(cast: dict) -> dict[str, list]:
    """Normalize a cast dict into the four role POOLS (ADR-0017/0018), preserving back-compat
    with the singular `redteam`/`arbitrator` shape (project.load_cast). Explicit
    `reviewers`/`adversaries`/`aggregators` lists in cast.yaml win; otherwise: reviewers
    default to the proposers (peer review), adversaries to `[redteam]` (or empty),
    aggregators to `[arbitrator]`."""
    proposers = list(cast.get("proposers") or cast.get("debaters") or [])
    reviewers = list(cast.get("reviewers") or proposers)
    adversaries = cast.get("adversaries")
    if adversaries is None:
        rt = cast.get("redteam")
        adversaries = [rt] if rt else []
    aggregators = cast.get("aggregators")
    if aggregators is None:
        arb = cast.get("arbitrator")
        aggregators = [arb] if arb else []
    return {
        "proposers": proposers,
        "reviewers": reviewers,
        "adversaries": list(adversaries),
        "aggregators": list(aggregators),
    }


def _validate_pools(plan: Plan, pools: dict[str, list]) -> None:
    """Every phase must bind to a NON-EMPTY pool; escalate/dynamic needs an adversary
    (round-types §2)."""
    for i, p in enumerate(plan.phases):
        if p.role_pool not in POOLS:
            raise PlanError(f"phase {i} {p.stage!r}: unknown role pool {p.role_pool!r}")
        if not pools.get(p.role_pool):
            raise PlanError(
                f"phase {i} {p.stage!r} binds to empty pool {p.role_pool!r} — "
                f"add {p.role_pool} to the cast (or drop the phase)"
            )
        if p.shape == "sample-k" and (not p.k or p.k < 1):
            raise PlanError(f"phase {i} {p.stage!r}: shape 'sample-k' needs k>=1")


def validate(plan: Plan, pools: dict[str, list] | None = None) -> Plan:
    """Full load-time validation (docs/round-types.md §5). Ordering + caps always;
    pool-binding when a cast is supplied. Returns the plan so callers can write
    `plan = validate(load_plan(...), pools)`."""
    pre_aggregate = [p.stage for p in plan.phases if p.stage != AGGREGATE]
    _validate_ordering(pre_aggregate)
    # `max` caps runtime phases; a plan whose non-dynamic phases already exceed the cap can
    # never run.
    static = sum(1 for p in plan.phases if p.stage != AGGREGATE and not p.dynamic)
    if plan.min < FLOOR_MIN:
        raise PlanError(f"min {plan.min} < floor {FLOOR_MIN} — the floor always runs")
    if plan.max < static:
        raise PlanError(f"max {plan.max} < the {static} non-dynamic phase(s) — plan can never run")
    if plan.min > plan.max:
        raise PlanError(f"min {plan.min} > max {plan.max}")
    if pools is not None:
        _validate_pools(plan, pools)
    return plan


def validate_referee_names(plan: Plan, known: tuple[str, ...] | list[str]) -> Plan:
    """Validate task-owned checker names after the task is known.

    Injection-point shape belongs to the task-agnostic plan loader; checker implementations belong
    to the task. Keeping this second validation step explicit preserves that boundary while ensuring
    a typo never degrades into an empty referee selection.
    """
    allowed = set(known)
    for point, names in plan.referees.items():
        unknown = sorted(name for name in names if name not in allowed)
        if unknown:
            raise PlanError(
                f"unknown referee checker(s) at {point!r}: {unknown} — "
                f"known for this task: {sorted(allowed)}"
            )
    return plan


def _integer_setting(rounds: dict, key: str, default: int) -> int:
    value = rounds.get(key, default)
    if type(value) is not int:
        raise PlanError(f"`rounds.{key}` must be an integer, got {value!r}")
    return value


def load_plan(debate_cfg: dict, cast: dict, settings) -> Plan:
    """Build the `Plan` for a debate. Reads a `rounds:` block from debate.yaml if present,
    else falls back to `default_plan(...)` (today's behavior). Per-debate
    `max`/`min`/`token_budget` default to the process settings but a `rounds:` block
    overrides them (audit F-1). Validated before return.

    A `rounds:` block (docs/round-types.md §3):
        rounds:
          min: 3
          max: 7
          plan: [propose, critique, revise, {pass: adversarial}, {pass: escalation, dynamic: true}]
          token_budget: 200000
          referees: {before_revise: [near_duplicate, ...], before_respond: [..., overreach]}
    Referee points are `before_revise` (after critique) and `before_respond` (after the red-team);
    each value NAMES the checkers to run there (task-owned; see `DelphiTask.available_referees`).
    Omit the block for the task's defaults; an empty list disables referees at that point.
    """
    pools = resolve_pools(cast)
    has_redteam = bool(pools["adversaries"])
    rounds = (debate_cfg or {}).get("rounds")
    default_max = getattr(settings, "max_debate_rounds", 5)
    default_budget = getattr(settings, "debate_token_budget", None)
    if rounds is None:
        plan = default_plan(
            has_redteam=has_redteam,
            dynamic=True,
            max_rounds=default_max,
            token_budget=default_budget,
        )
        return validate(plan, pools)
    if not isinstance(rounds, dict):
        raise PlanError("`rounds:` must be a mapping (min/max/plan/referees/token_budget)")
    unknown = sorted(
        (k for k in rounds if not isinstance(k, str) or k not in _ROUNDS_KEYS), key=str
    )
    if unknown:
        raise PlanError(
            f"unknown key(s) in `rounds:`: {unknown} — allowed: {sorted(_ROUNDS_KEYS)}. "
            "(the nested `unit`/`review`/`adversary`/`stop` shape is an unbuilt design; "
            "see docs/round-types.md §3 for the list form)"
        )
    ref = rounds.get("referees")
    if ref is not None:
        if not isinstance(ref, dict):
            raise PlanError("`rounds.referees` must be a mapping of injection-point -> [checks]")
        bad_points = sorted(
            (k for k in ref if not isinstance(k, str) or k not in _REFEREE_POINTS), key=str
        )
        if bad_points:
            raise PlanError(
                f"unknown referee injection point(s): {bad_points} — the engine calls only "
                f"{sorted(_REFEREE_POINTS)} (before_revise = after critique, before_respond = "
                "after the red-team)"
            )
        for point, names in ref.items():
            if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                raise PlanError(
                    f"`rounds.referees.{point}` must be a list of checker names (strings)"
                )
    raw = rounds.get("plan")
    if raw is None:
        # rounds block with only caps → keep the default shape, apply the caps
        plan = default_plan(has_redteam=has_redteam, dynamic=True)
    else:
        if not isinstance(raw, list):
            raise PlanError("`rounds.plan` must be a list of stages/passes")
        # a {pass: escalation, dynamic: true} entry marks the escalation pass dynamic
        dynamic_escalation = any(
            isinstance(it, dict) and it.get("pass") == "escalation" and it.get("dynamic")
            for it in raw
        )
        stages = expand_passes(raw)
        phases = [
            _phase(
                st,
                dynamic=(
                    st in (ESCALATE, RESPOND) and dynamic_escalation and _after_escalate(stages, i)
                ),
                repeat_until="escalation_stop" if (st == ESCALATE and dynamic_escalation) else None,
            )
            for i, st in enumerate(stages)
        ]
        phases.append(_phase(AGGREGATE))
        plan = Plan(phases=phases)
    plan.min = _integer_setting(rounds, "min", plan.min)
    plan.max = _integer_setting(rounds, "max", default_max)
    plan.token_budget = rounds.get("token_budget", default_budget)
    if plan.token_budget is not None and (
        type(plan.token_budget) is not int or plan.token_budget < 1
    ):
        raise PlanError(
            f"`rounds.token_budget` must be a positive integer or null, got {plan.token_budget!r}"
        )
    plan.referees = rounds.get("referees", {}) or {}
    return validate(plan, pools)


def _after_escalate(stages: list[str], idx: int) -> bool:
    """True if stage `idx` is an escalate, or a respond whose nearest preceding attacker is
    an escalate — so only the escalation-pass respond is marked dynamic, not the
    standard-pass respond."""
    if stages[idx] == ESCALATE:
        return True
    for j in range(idx - 1, -1, -1):
        if stages[j] in _ATTACKERS:
            return stages[j] == ESCALATE
    return False
