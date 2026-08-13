"""The debate loop: independent -> cross-critique(steelman) -> revise -> task.aggregate().

Task-agnostic. Owns round sequencing, peer blinding, per-round validation, artifacts and
resume. WHAT each round means is the task's (prompts, schema, context); the final aggregate
step is the task's too (LLM merge for generation, Beta/MC math for scoring).
"""

from __future__ import annotations

import hashlib
import logging
import random
import string
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from debate.aggregators import select_aggregator
from debate.backends import Debater, QuotaExceeded, voice_descriptor
from debate.config import get_settings
from debate.engine import escalation as _esc
from debate.engine import plan as _plan
from debate.engine import trace as _trace
from debate.engine.artifacts import RunStore
from debate.engine.call import produce
from debate.engine.prompting import blocks as _blocks
from debate.engine.prompting import json_block as _json_block
from debate.engine.validate import validate_output
from debate.logging import run_logger
from debate.metrics import summarize
from debate.referees.base import referee_report
from debate.tasks.base import DebateTask

_log = logging.getLogger("debate.engine.loop")


def _live_output_tokens(metrics: list[dict]) -> int:
    """Output tokens spent by LIVE (non-cached) calls so far — the token-budget guard's meter.

    Counts reasoning tokens for backends that report them SEPARATELY from completion (codex): the
    OpenAI/OpenRouter schema folds reasoning INTO `completion_tokens`, and Claude Code reports none,
    but codex's `reasoning_output_tokens` is disjoint from its `output_tokens` — so ignoring it lets
    a reasoning-heavy voice systematically overshoot the ceiling (audit E-2)."""
    total = 0
    for m in metrics:
        if m.get("cached"):
            continue
        total += int(m.get("output_tokens") or 0)
        if m.get("backend") == "codex_cli":
            total += int(m.get("reasoning_tokens") or 0)
    return total


def _assess_atom_field(task: DebateTask, coverage, merge, sets: dict[str, dict]) -> dict | None:
    """ADR-0011 marginal-value assessment of the current field, or None if the task does
    not implement `extract_atoms` (then the engine uses the `search_signature` fallback instead).

    Classifies each item's requirement-atoms against the covered set (orthogonal / decomposes /
    refinement / redundant / contradicts), attaches redundant/refinement items to a canonical
    in the reversible merge forest, flags low-discrimination atoms via the archetype
    panel (RANK/FLAG ONLY — never gates), commits the atoms, and returns the pass-level coverage
    signal. Discrimination is structurally excluded from the productivity/stop logic.
    """
    atoms_by_ind = task.extract_atoms(sets)
    if atoms_by_ind is None:
        return None
    lookup = task.items(sets)
    classifications: list[dict] = []
    flags: list[dict] = []
    for iid, atoms in atoms_by_ind.items():
        keys = [a["key"] for a in atoms]
        novel = [k for k in keys if k not in coverage.covered]
        relation = None
        if not novel and keys:  # collision — ask the task's verb hook (default None → redundant)
            owner = coverage.covered.get(keys[0])
            relation = task.arbitrate_collision(lookup.get(iid, {}), lookup.get(owner, {}))
        c = coverage.classify(iid, atoms, contradicts=(relation == "contradicts"))
        if relation == "refines" and c["class"] == _esc.CLS_REDUNDANT:
            c["class"] = _esc.CLS_REFINEMENT
        classifications.append(c)
        # discrimination prior on NEW atoms — rank/flag only (variance across archetypes)
        for a in atoms:
            if a["key"] in novel:
                vec = task.archetype_panel(a["key"], a.get("span"))
                if vec:
                    mean = sum(vec) / len(vec)
                    var = sum((v - mean) ** 2 for v in vec) / len(vec)
                    if (
                        var < 0.04
                    ):  # low spread → everyone passes/fails alike (or gaming-susceptible)
                        flags.append(
                            {
                                "item": iid,
                                "atom": a["key"],
                                "pass_variance": round(var, 4),
                                "flag": "low_discrimination",
                            }
                        )
        coverage.commit(iid, atoms)
        if c["class"] in (_esc.CLS_REDUNDANT, _esc.CLS_REFINEMENT) and keys:
            owner = coverage.covered.get(keys[0])
            if owner and owner != iid:
                merge.attach(iid, owner, relation or "duplicates")
    pa = coverage.assess_pass(classifications)
    pa["low_discrimination_flags"] = flags
    return pa


# Quorum for tolerate-a-failing-voice (task-0011): a debate may lose voices to hard errors/refusals
# and still run, but a multi-voice panel that collapses to one voice is no longer a debate. The
# effective quorum is min(_QUORUM_MIN, configured voices), so a deliberately-single-voice panel
# (the `consultancy` baseline) still runs while a 3-voice panel must keep >=2.
_QUORUM_MIN = 2


def _union_findings(all_findings: list[dict | None]) -> dict | None:
    """Union of every pass's red-team findings for the arbitrator (D-1; ADR-0014 union-then-
    arbitrate). A single set passes through UNCHANGED (byte-identical to the pre-union loop); many
    passes concatenate their `findings` and keep each full pass dict under `passes`, so a finding
    raised in the standard pass or an earlier escalation — and a pass's `new_option` — stays visible
    to the arbitrator (the pre-D-1 loop passed only the LATEST pass's findings)."""
    fds = [f for f in all_findings if f]
    if not fds:
        return None
    if len(fds) == 1:
        return fds[0]
    merged = [f for fd in fds for f in (fd.get("findings") or [])]
    return {"findings": merged, "passes": fds}


def _blind_label(n: int) -> str:
    """Bijective base-26 label: 0→A … 25→Z, 26→AA, 27→AB … — so blinding survives a panel of >26
    voices (audit E-3). Identical to `ascii_uppercase[n]` for n<26, so ≤26-voice runs are unchanged.
    """
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = string.ascii_uppercase[r] + s
    return s


def _blind_labels(debaters: list[Debater], debate_name: str) -> dict[str, str]:
    """Assign blind labels (A/B/C…) under a per-run permutation seeded by the debate name.

    Blinding hides model identity, but a FIXED label order (config index) would still present the
    same model first to the arbitrator on every run/measure — a position/primacy bias confounded
    with model identity (ADR-0020). Permuting the label→model map per debate (deterministically, so
    resume is stable) decorrelates presentation order from identity across the dataset.
    """
    seed = int.from_bytes(hashlib.sha256(debate_name.encode()).digest()[:8], "big")
    order = list(range(len(debaters)))
    random.Random(seed).shuffle(order)
    return {d.id: _blind_label(order[i]) for i, d in enumerate(debaters)}


def run_debate(
    task: DebateTask,
    debaters: list[Debater],
    arbitrator: Debater,
    *,
    debate_name: str,
    resume: bool = True,
    redteam: Debater | None = None,
    max_rounds: int | None = None,
    token_budget: int | None = None,
    run_dir: str | None = None,
    plan: _plan.Plan | None = None,
    aggregator: str | None = None,
    max_concurrency: int | None = None,
) -> dict:
    """Run the debate, parking (not crashing) on a subscription-quota hit (ADR-0016).

    The deliberation itself lives in `_drive_debate`; this wrapper owns the run store and the park
    boundary. A `QuotaExceeded` from any voice is caught, recorded as a resumable `STOP_LIMIT`
    marker, and re-raised — so a re-run of the same debate resumes from cache without re-charging.
    """
    store = RunStore(task.name, task.subject_id, debate_name, run_dir=run_dir)
    log = run_logger("debate.engine.loop", run_id=debate_name, log_file=store.log_file)
    metrics: list[dict] = []  # per-call timing/cost/tokens, rolled up into metrics.json
    run_t0 = time.perf_counter()
    try:
        return _drive_debate(
            task,
            debaters,
            arbitrator,
            store,
            log,
            metrics,
            run_t0,
            debate_name=debate_name,
            resume=resume,
            redteam=redteam,
            max_rounds=max_rounds,
            token_budget=token_budget,
            plan=plan,
            aggregator=aggregator,
            max_concurrency=max_concurrency,
        )
    except QuotaExceeded as e:
        # Park, don't crash (ADR-0016): a subscription/plan limit is resumable, not a failure. Write
        # a STOP_LIMIT marker (sibling of STOP_BUDGET) with the tokens spent so far, then re-raise
        # so the CLI can print the resume command. A re-run skips cached calls (no re-charge).
        prior = store.read("round_status") if store.has("round_status") else {}
        spent = int(prior.get("tokens_spent", 0)) + _live_output_tokens(metrics)
        store.write(
            "round_status",
            None,
            {
                "stop_reason": _esc.STOP_LIMIT,
                "complete": False,
                "detail": str(e)[:300],
                "tokens_spent": spent,
            },
        )
        log.warning(
            "PARKED on usage limit — re-run the same debate to resume from cache: %s", str(e)[:200]
        )
        raise


def _drive_debate(
    task: DebateTask,
    debaters: list[Debater],
    arbitrator: Debater,
    store: RunStore,
    log: logging.Logger,
    metrics: list[dict],
    run_t0: float,
    *,
    debate_name: str,
    resume: bool,
    redteam: Debater | None,
    max_rounds: int | None,
    token_budget: int | None,
    plan: _plan.Plan | None = None,
    aggregator: str | None = None,
    max_concurrency: int | None = None,
) -> dict:
    settings = get_settings() if plan is None or max_concurrency is None else None
    # Select the reducer NOW (fail fast before any spend): the task's default aggregator unless the
    # caller overrides, validated against the task's field type — e.g. `vote` on a generative task
    # raises here, not after an hour of debate (ADR-0013; task-0025).
    reducer = select_aggregator(aggregator or task.default_aggregator, task)
    # CAP on total phases (ADR-0011): floor=3; each adversarial pass=2. Default 5 = exactly today's
    # full config (floor + one standard red-team pass), so behaviour is unchanged until raised.
    if max_rounds is None:
        max_rounds = settings.max_debate_rounds if settings is not None else plan.max
    if token_budget is None:
        token_budget = settings.debate_token_budget if settings is not None else plan.token_budget
    blind = _blind_labels(debaters, debate_name)
    store.write_meta("blinding.json", blind)
    if not resume:
        log.info("resume disabled — completed steps will be recomputed if re-run")

    # Independent within-round calls fan out concurrently (they depend only on PRIOR rounds, never
    # on each other — that independence is the anti-anchoring guarantee). Bounded by concurrency.
    concurrency = max(
        1,
        max_concurrency
        if max_concurrency is not None
        else settings.max_concurrency,
    )
    # Tolerate a failing/refusing voice (task-0011): a voice that errors after bounded retries (a
    # hard error, a timeout, or an AUP refusal that never validates) is DROPPED from that round with
    # a recorded note and the debate continues — as long as a quorum survives. A QuotaExceeded is
    # NOT a per-voice drop: it is a run-level park (ADR-0016), so it propagates untouched.
    active = list(debaters)  # survivors; shrinks after propose to the voices that produced a set
    dropped: list[dict] = []  # {debater, round, error} — surfaced in result.json/metrics.json

    def _run_one(d: Debater, round_name: str, build_user, stage):
        # build_user() is called INSIDE the guard so a voice whose prior-round output is missing
        # (it was dropped earlier) fails cleanly into a drop rather than KeyError-ing the round.
        try:
            return d.id, produce(task, d, round_name, build_user(d), store, metrics, stage=stage)
        except QuotaExceeded:
            raise  # a subscription-quota hit parks the whole run — never a single-voice drop
        except Exception as e:  # noqa: BLE001 — degrade gracefully; the surviving voices carry on
            note = f"{type(e).__name__}: {str(e)[:200]}"
            log.warning(
                "voice %s failed %s — dropping it from this round: %s", d.id, round_name, note
            )
            dropped.append({"debater": d.id, "round": round_name, "error": note})
            metrics.append({"round": round_name, "debater": d.id, "dropped": True, "error": note})
            return d.id, None

    def fan_out(
        round_name: str, build_user: Callable[[Debater], str], *, stage: str | None = None
    ) -> dict[str, dict]:
        panel = active  # read at call time — shrinks to the propose survivors after round 1
        if concurrency == 1 or len(panel) == 1:
            pairs = [_run_one(d, round_name, build_user, stage) for d in panel]
        else:
            with ThreadPoolExecutor(max_workers=min(concurrency, len(panel))) as ex:
                futs = [ex.submit(_run_one, d, round_name, build_user, stage) for d in panel]
                pairs = [f.result() for f in futs]  # QuotaExceeded (park) re-raises here
        return {did: out for did, out in pairs if out is not None}

    shared, context = task.shared_context(), task.context_text()
    log.info(
        "debate '%s' task=%s subject=%s debaters=%s", debate_name, task.name, task.subject_id, blind
    )

    # The round PLAN (task-0017): today's fixed sequence expressed as data, so a debate's SHAPE is
    # config, not control flow. `default_plan` reproduces the historical sequence (floor + optional
    # standard adversarial pass + a dynamic escalation pass). The runner below iterates the plan's
    # NON-DYNAMIC phases (floor + standard pass); the dynamic escalation pass, if any, is driven by
    # the loop further down (it repeats until a stop rule); `aggregate` is the finalization step.
    if plan is None:
        plan = _plan.default_plan(
            has_redteam=redteam is not None,
            dynamic=True,
            max_rounds=max_rounds,
            token_budget=token_budget,
        )
    # The plan loader validates injection-point shape without importing a concrete task. Checker
    # names become knowable only here; validate them before the first model call so a typo cannot
    # silently disable an intended safeguard. Older/custom tasks without a named registry retain
    # their existing behavior rather than acquiring an undocumented new seam requirement.
    referee_registry = getattr(task, "available_referees", None)
    if referee_registry is not None:
        _plan.validate_referee_names(plan, referee_registry())
    # A caller-supplied plan owns the caps; otherwise the settings/args do (used by the escalation
    # loop and round_status below). A plan without an `escalate` phase never escalates, even with a
    # red-team voice present — the plan, not the voice, decides the shape (task-0017).
    max_rounds = plan.max
    token_budget = plan.token_budget
    plan_has_escalation = any(p.stage == _plan.ESCALATE for p in plan.phases)
    store.write_meta("plan.json", plan.as_dict())

    # Deliberation state threaded across phases: `field` is the current per-voice set (proposals →
    # revised → responded); `reviews` are the critique outputs (the DISCUSSION block); `phase`
    # counts model phases run (floor=3, +2 per adversarial pass) for the round_status bookkeeping.
    proposals: dict[str, dict] = {}
    field: dict[str, dict] = {}
    reviews: list[dict] = []
    redteam_findings: dict | None = None
    all_findings: list[dict | None] = []  # every pass's findings, for the D-1 arbitrator union
    flags: list[dict] = []  # all referee findings (injected + recorded) → flags.json (task-0013)
    scrutiny_block = ""  # task-0014: blinded critique of newly-proposed options, awaiting respond
    pending_flags = ""  # the rendered FLAGS block awaiting injection into the next proposer round
    ledger = _esc.RoundLedger()
    phase = 0
    stop_reason = _esc.STOP_FLOOR

    # Block builders read the live state at call time (behaviour identical to the prior linear
    # code): blinded peers for `critique`, the DISCUSSION block for `revise`, the blinded field for
    # the adversary. build_user() is invoked inside fan_out's per-voice guard, so a dropped voice
    # degrades cleanly rather than KeyError-ing the round (task-0011).
    def _peers(d: Debater) -> str:
        peers = _blocks(
            *(_json_block(f"PEER {blind[o.id]}", proposals[o.id]) for o in active if o.id != d.id)
        )
        return _blocks(shared, context, peers)

    def _discussion() -> str:
        return _blocks(*(_json_block(f"DISCUSSION {i + 1}", c) for i, c in enumerate(reviews)))

    def _field_block(label: str) -> str:
        return _blocks(
            *(_json_block(f"{label} {blind[d.id]}", field[d.id]) for d in active if d.id in field)
        )

    def _scrutinize_new(new_opts: list[dict], rname: str) -> str:
        """task-0014: give genuinely-new adversary-proposed options the SAME blinded peer
        critique a floor proposal gets, BEFORE they can reach aggregation — closing the asymmetric-
        scrutiny gap (a late addition otherwise gets only a `respond`, never independent vetting).
        Runs one interleaved critique fan-out (reusing the critique prompt) over the new options
        shown blinded; returns the critiques as a block to feed into the following respond. No-op
        unless a pass proposed a new option, so a run with no new option is byte-identical."""
        proposed = _blocks(
            *(_json_block(f"PROPOSED OPTION P{i + 1}", o) for i, o in enumerate(new_opts))
        )
        note = (
            "SCRUTINY: these options were newly proposed mid-debate and have NOT yet been "
            "peer-reviewed. Critique each on the merits (blinded — you do not know who proposed "
            "it): steelman it first, then give your sharpest, most specific objection."
        )
        crit = fan_out(
            rname,
            lambda d, proposed=proposed, note=note: _blocks(shared, context, proposed, note),
            stage="critique",
        )
        scrutinies = [crit[d.id] for d in active if d.id in crit]
        log.info("scrutiny of %d new option(s): %d critiques", len(new_opts), len(scrutinies))
        return _blocks(
            *(_json_block(f"NEW-OPTION SCRUTINY {i + 1}", c) for i, c in enumerate(scrutinies))
        )

    quorum = min(_QUORUM_MIN, len(debaters))

    def _assert_quorum(survivors: dict, after: str) -> None:
        """C-1 (audit): re-assert quorum after EVERY field-producing fan-out, not just propose.

        `active` freezes to the propose survivors, but a later round can still drop voices to hard
        errors — and if the field collapses below quorum the run must fail LOUDLY, never silently
        aggregate an empty/degenerate field (`aggregate({})`). Raising here is resume-safe: nothing
        downstream of the failing round was written, so a re-run resumes from the cached good calls.
        """
        if len(survivors) < quorum:
            raise RuntimeError(
                f"below quorum after {after}: {len(survivors)}/{len(debaters)} voices survived "
                f"(need >= {quorum}) — not a debate. dropped: {dropped}"
            )

    def _referee(point: str, rt: dict | None = None) -> str:
        """Run the task's deterministic referees at `point`, record every finding to `flags.json`,
        and return the FLAGS block to inject into the next proposer round (task-0013). No model
        call; default (a task with no referees) returns '' and records nothing — runs unaffected.
        """
        # The plan's `referees:` block may NAME which checkers run at this point (config-selectable,
        # task-0013 follow-up); absent → the task's default set for the point. Boundary stays clean:
        # the engine passes names, the task owns which checkers those names mean.
        select = plan.referees.get(point) if plan.referees else None
        found = task.referees(point, field, redteam=rt, select=select)
        if not found:
            return ""
        flags.extend({**f.to_dict(), "point": point} for f in found)
        log.info("referees @%s: %d finding(s)", point, len(found))
        return referee_report(found)

    seen: dict[str, int] = {}  # per-stage occurrence count → unique storage key for repeated phases
    for ph in plan.phases:
        if ph.dynamic or ph.stage == _plan.AGGREGATE:
            continue  # escalation is driven below; aggregate is the finalization step
        st = ph.stage
        # Unique storage key per phase instance ("revise", then "revise-2", …) so a repeated stage
        # doesn't collide on one dir; `stage=st` keeps prompt/schema keyed on the semantics (F-2).
        seen[st] = seen.get(st, 0) + 1
        rname = st if seen[st] == 1 else f"{st}-{seen[st]}"
        if st == _plan.PROPOSE:
            # propose — independent; no peeking (anti-sycophancy). Quorum must survive (task-0011).
            proposals = fan_out(rname, lambda d: _blocks(shared, context), stage=st)
            active = [d for d in debaters if d.id in proposals]
            if len(active) < quorum:
                raise RuntimeError(
                    f"below quorum: {len(active)}/{len(debaters)} voices produced a valid proposal "
                    f"(need >= {quorum}) — not a debate. dropped: {dropped}"
                )
            field = dict(proposals)
            ledger.record(rname, task.item_ids(field))
            phase += 1
            log.info(
                "propose: %d/%d proposals (%d dropped)",
                len(active),
                len(debaters),
                len(debaters) - len(active),
            )
        elif st == _plan.CRITIQUE:
            # critique — each voice sees peers, blinded (steelman the strongest disagreement).
            crit_by_id = fan_out(rname, _peers, stage=st)
            reviews = [crit_by_id[d.id] for d in active if d.id in crit_by_id]
            ledger.record(rname, task.item_ids(field))
            phase += 1
            log.info("critique: %d critiques", len(reviews))
            # Referee injection point 1 (task-0013): deterministic checks on the proposals, flagged
            # into the revise prompt so the panel fixes them without spending reasoning re-deriving.
            pending_flags = _referee("before_revise")
        elif st == _plan.REVISE:
            # revise — each voice refines its OWN current set given the full discussion + any FLAGS.
            disc = _discussion()
            field = fan_out(
                rname,
                # bind `field` (the pre-revise set) as a default — fan_out invokes this
                # synchronously before the reassignment below; binding is explicit + silences B023.
                lambda d, disc=disc, field=field, fl=pending_flags: _blocks(
                    shared, context, _json_block("YOUR PROPOSAL", field[d.id]), disc, fl
                ),
                stage=st,
            )
            pending_flags = ""  # consumed
            _assert_quorum(field, rname)  # C-1: the field must survive a revise collapse
            ledger.record(rname, task.item_ids(field))
            phase += 1
            log.info("revise: %d revised", len(field))
        elif st == _plan.REDTEAM:
            # standard red-team — the adversary attacks the near-final field (single voice).
            redteam_findings = produce(
                task,
                redteam,
                rname,
                _blocks(shared, context, _field_block("REVISED")),
                store,
                metrics,
                stage=st,
            )
            all_findings.append(redteam_findings)  # D-1: accumulate for the arbitrator union
            ledger.record(rname, task.item_ids(field))
            phase += 1
            log.info("red-team: %d findings", len(redteam_findings.get("findings", [])))
            # Referee injection point 2 (task-0013): checks on the revised field WITH the red-team
            # findings in hand (so `unaddressed` can fire), flagged into the respond prompt.
            pending_flags = _referee("before_respond", rt=redteam_findings)
            # Symmetric scrutiny (task-0014): if the red-team PROPOSED a genuinely new option, give
            # it one blinded peer critique before it reaches aggregation. No new option → no step.
            new_opts = task.new_options(redteam_findings, field)
            if new_opts:
                scrutiny_name = "scrutinize" if seen[st] == 1 else f"scrutinize-{seen[st]}"
                scrutiny_block = _scrutinize_new(new_opts, scrutiny_name)
                phase += 1
        elif st == _plan.RESPOND:
            # respond — the panel concedes/defends; an in-loop grounding referee (ADR-0011) is fed
            # back like a finding so raters fix drifted quotes before the gate, plus any FLAGS.
            rt_block = _json_block("RED-TEAM FINDINGS", redteam_findings)
            grounding = task.grounding_referee(field)
            gnd_block = _json_block("GROUNDING REFEREE", grounding) if grounding else ""
            if grounding:
                log.info("grounding referee: %d quote(s) flagged", len(grounding["findings"]))

            def _respond_user(
                d, rt=rt_block, gnd=gnd_block, field=field, fl=pending_flags, sc=scrutiny_block
            ):
                return _blocks(
                    shared, context, _json_block("YOUR REVISED SET", field[d.id]), rt, gnd, sc, fl
                )

            field = fan_out(
                rname,
                _respond_user,
                stage=st,
            )
            pending_flags = ""  # consumed
            scrutiny_block = ""  # consumed (task-0014)
            _assert_quorum(field, rname)  # C-1: the field must survive a respond collapse
            stop_reason = _esc.STOP_STANDARD
            ledger.record(rname, task.item_ids(field))
            phase += 1
            log.info("respond: %d responses", len(field))

    final_sets = field

    # ESCALATION (ADR-0011): beyond the standard pass, run extra adversarial passes on the CONTESTED
    # subset — a red-team LICENSED TO PROPOSE a new option (the breadth mechanism that produced Θ),
    # then respond — stopping on EXHAUSTED SEARCH (a pass adds no new option/evidence/value/find),
    # never on agreement (ADR-0014). Bounded by the round cap and a graceful token-budget guard.
    # Only reachable when a red-team is configured, the plan has an `escalate` phase, and the task
    # opts in (focus is not None) — so the default (max_rounds=5) path above is unchanged.
    def _escalation_pass(k: int, pass_focus: list[str], current_field: dict) -> tuple[dict, dict]:
        """Run ONE escalation pass (adversary licensed to propose → panel responds) on a snapshot of
        the current field. Storage keys `escalate-{k}`/`respond-{k+1}`; the `escalate`/`respond`
        stages drive prompt+schema. Reused verbatim by the live loop AND the B-1 ledger replay, so a
        resumed run rebuilds the exact same (cached) calls."""
        esc_name, resp_name = f"escalate-{k}", f"respond-{k + 1}"
        esc_field = _blocks(
            *(
                _json_block(f"CURRENT {blind[d.id]}", current_field[d.id])
                for d in active
                if d.id in current_field
            )
        )
        focus_block = (
            "ESCALATION FOCUS — concentrate on these contested items, and you MAY PROPOSE A "
            "NEW OPTION (a new item / clause / value / interpretation), not merely attack the "
            "existing set: " + ", ".join(pass_focus)
        )
        findings = produce(
            task,
            redteam,
            esc_name,
            _blocks(shared, context, esc_field, focus_block),
            store,
            metrics,
            stage="escalate",
        )
        esc_block = _json_block("RED-TEAM FINDINGS", findings)
        grounding = task.grounding_referee(current_field)  # in-loop verbatim referee (ADR-0011)
        gnd_block = _json_block("GROUNDING REFEREE", grounding) if grounding else ""
        # Symmetric scrutiny (task-0014): a new option minted by THIS pass gets one blinded peer
        # critique (storage `scrutinize-{k}`) before the panel responds. No-op unless one was made.
        new_opts = task.new_options(findings, current_field)
        sc_block = _scrutinize_new(new_opts, f"scrutinize-{k}") if new_opts else ""
        responded = fan_out(
            resp_name,
            # bind loop vars as defaults (the lambda is invoked synchronously inside fan_out, but
            # this keeps each pass's field/findings explicit and silences the closure lint).
            lambda d, current=current_field, esc=esc_block, gnd=gnd_block, sc=sc_block: _blocks(
                shared, context, _json_block("YOUR CURRENT SET", current[d.id]), esc, gnd, sc
            ),
            stage="respond",
        )
        return responded, findings

    prior = store.read("round_status") if store.has("round_status") else {}
    spent = int(prior.get("tokens_spent", 0))  # cumulative across resumes (the budget is a ceiling)
    prior_ledger = _esc.StopLedger.load(prior)  # B-1: the persisted per-pass stop decisions, if any
    escalates = redteam is not None and plan_has_escalation
    # B-1 (audit): if a prior run recorded a COMPLETE escalation, REPLAY its recorded passes from
    # the ledger (every call is cached — no re-charge) and adopt the recorded stop_reason, rather
    # than RE-DERIVING the stop by re-calling the task's escalation_focus/extract_atoms/
    # search_signature hooks over the cached field. This makes resume deterministic even if a hook
    # is impure. An INCOMPLETE (parked/budget) escalation has no complete ledger, so it goes live
    # and continues where it left off (the accumulator state is not persisted — a carry-forward).
    replaying = escalates and prior_ledger.escalation_complete()

    focus: list[str] | None = None
    if replaying:
        focus = ["<replay>"]  # non-None sentinel to enter the loop; per-pass focus comes from disk
    elif escalates:
        focus = task.escalation_focus(final_sets)
        if focus is None:
            stop_reason = _esc.STOP_NO_FOCUS
    # Exhausted-search instrument: the MARGINAL-VALUE atom path (ADR-0011) when the task implements
    # `extract_atoms`, else the `search_signature` fallback. The atom ledger is seeded with the
    # standard field as baseline coverage, so escalation passes are scored on what they ADD (rebuilt
    # on replay for the recorded marginal_value, but never gating there). Both read only coverage.
    coverage = _esc.CoverageLedger()
    merge = _esc.MergeForest()
    marginal_passes: list[dict] = []
    # task-0015: the NOVELTY regime (opt-in) takes precedence — the loop continues only while a pass
    # mints a genuinely-new unique option, so it supersedes both the atom and signature instruments.
    novelty_regime = escalates and task.escalation_stop_regime() == "novelty"
    atom_path = (
        not novelty_regime
        and redteam is not None
        and focus is not None
        and task.extract_atoms(final_sets) is not None
    )
    if atom_path:
        _assess_atom_field(task, coverage, merge, final_sets)  # commit baseline coverage
    seen_sig = (
        task.search_signature(final_sets, redteam_findings)
        if (
            not replaying
            and not novelty_regime
            and redteam is not None
            and focus is not None
            and not atom_path
        )
        else set()
    )
    stop_ledger = _esc.StopLedger()
    escalation_passes = 0
    complete = True
    while redteam is not None and focus is not None:
        k = escalation_passes + 1
        rec = prior_ledger.decision_for(k) if replaying else None
        if replaying:
            if rec is None:  # every recorded pass replayed → adopt the recorded terminal stop
                stop_reason = prior_ledger.stop_reason
                break
            pass_focus = rec["focus"]
        else:
            if phase + 2 > max_rounds:  # CAP — escalation can't run away
                # Cap with zero escalation passes just means the default config had no room to
                # escalate (the standard pass WAS the whole debate); reserve CAP for a real cut-off.
                stop_reason = _esc.STOP_CAP if escalation_passes else _esc.STOP_STANDARD
                break
            focus = task.escalation_focus(final_sets)
            if (
                not focus
            ):  # nothing contested left to deepen (NOT an agreement-stop — the floor ran)
                stop_reason = _esc.STOP_NO_CONTESTED
                break
            spent_now = spent + _live_output_tokens(metrics)
            if token_budget is not None and spent_now >= token_budget:
                # Graceful stop at the ceiling: mark ongoing-incomplete + resumable, re-pay nothing.
                stop_reason = _esc.STOP_BUDGET
                complete = False
                log.warning(
                    "token budget %d reached (spent ~%d) — stopping escalation, resumable",
                    token_budget,
                    spent_now,
                )
                break
            pass_focus = focus
        escalation_passes = k
        current = dict(final_sets)  # snapshot: final_sets is rebound to `responded` below
        log.info("escalation pass %d on %d contested item(s): %s", k, len(pass_focus), pass_focus)
        final_sets, esc_findings = _escalation_pass(k, pass_focus, current)
        _assert_quorum(final_sets, f"escalate-{k}")  # C-1: never collapse the field mid-escalation
        all_findings.append(esc_findings)  # D-1: accumulate for the arbitrator union
        redteam_findings = esc_findings  # the LATEST findings (with any new option) → arbitration
        phase += 2
        ledger.record(f"escalate-{k}", pass_focus)
        ledger.record(f"respond-{k + 1}", pass_focus)
        # Stop diagnostics — deterministic; rebuilt on replay for the record but never gating there
        # (the ledger's recorded decision wins on replay; live passes compute + record it).
        stopped = False
        stop_extra: dict = {}
        pass_stop_reason = _esc.STOP_EXHAUSTED  # the reason recorded when THIS regime says stop
        if novelty_regime:
            # NOVELTY gate (task-0015; ADR-0014 §6): continue only while the pass minted a
            # genuinely-new unique option (reuses `new_options` → the `near_duplicate` primitive).
            # A pass that adds none stops the loop — the owner's legible steelman rule.
            minted = task.new_options(esc_findings, current)
            stopped = not minted
            pass_stop_reason = _esc.STOP_NOVELTY
            stop_extra = {"new_options": [o.get("id") for o in minted], "novel": bool(minted)}
            log.info("escalation pass %d: %d new-unique option(s)", k, len(minted))
        elif atom_path:
            # MARGINAL-VALUE gate (ADR-0011): classify the pass's atoms, gate on coverage.
            pa = _assess_atom_field(task, coverage, merge, final_sets)
            marginal_passes.append({"pass": k, **pa})
            log.info(
                "escalation pass %d: %d productive, coverage_gain=%.2f, missing_mass=%.2f",
                k,
                pa["productive_items"],
                pa["coverage_gain"],
                pa["missing_mass"],
            )
            stopped = coverage.exhausted(k_unproductive=_esc.UNPRODUCTIVE_STOP_K)
            stop_extra = {
                "missing_mass": pa["missing_mass"],
                "unproductive_streak": pa["unproductive_streak"],
            }
        elif not replaying:  # signature fallback — skipped on replay (not needed for the record)
            new_sig = task.search_signature(final_sets, esc_findings)
            stopped = not _esc.progressed(seen_sig, new_sig)  # the SEARCH is mined out → stop (I)
            stop_extra = {"signature": sorted(str(s) for s in new_sig)}
            if not stopped:
                seen_sig |= new_sig
        if replaying:
            if rec["stop"]:  # the recorded terminal pass
                stop_reason = rec["stop_reason"]
                break
            continue  # a recorded non-terminal pass → replay the next one
        stop_ledger.record(
            k,
            pass_focus,
            stop=stopped,
            stop_reason=pass_stop_reason if stopped else None,
            spent=spent + _live_output_tokens(metrics),
            **stop_extra,
        )
        if stopped:
            stop_reason = pass_stop_reason  # no new option (novelty) / no new search (exhausted)
            break

    if replaying:
        stop_ledger = prior_ledger  # persist the disk ledger unchanged (its decisions were adopted)
    else:
        stop_ledger.finalize(stop_reason, complete and _esc.is_complete(stop_reason))

    _assert_quorum(final_sets, "final")  # C-1: never aggregate an empty/degenerate field
    spent += _live_output_tokens(metrics)
    dynamic_status = {
        "stop_reason": stop_reason,
        "complete": complete and _esc.is_complete(stop_reason),
        "floor": list(_esc.FLOOR_ROUNDS),
        "cap_rounds": max_rounds,
        "phases_run": phase,
        "escalation_passes": escalation_passes,
        "token_budget": token_budget,
        "tokens_spent": spent,
        "per_item_rounds": ledger.dump(),
    }
    if redteam is not None:  # B-1: persist the escalation stop ledger (empty if no pass ran) so a
        dynamic_status["stop_ledger"] = stop_ledger.serialize()  # resume replays it, not the hooks
    if atom_path:  # ADR-0011: marginal-value instrumentation + reversible merge clusters
        dynamic_status["marginal_value"] = {
            "gate": "atom_coverage",
            "passes": marginal_passes,
            "covered_atoms": len(coverage.covered),
            "merge": merge.dump(),
        }
    store.write("round_status", None, dynamic_status)
    log.info(
        "rounds: %d phase(s), %d escalation pass(es), stop=%s, complete=%s",
        phase,
        escalation_passes,
        stop_reason,
        dynamic_status["complete"],
    )

    # Aggregate (ADR-0013/0017): route the blinded final field through the SELECTED Aggregator's
    # reduce() (`reducer`, chosen + validated at the top). The default `arbitrator_select` adapts to
    # the task's own aggregate() so the artifact is byte-identical to the pre-seam loop.
    final_blinded = {blind[d.id]: final_sets[d.id] for d in active if d.id in final_sets}
    # D-1 (audit): the arbitrator sees the UNION of every pass's red-team findings, not just the
    # latest — a single-pass run unions to that one dict (byte-identical); see `_union_findings`.
    redteam_union = _union_findings(all_findings)
    # D-2 (audit): key the aggregate cache on (plan_hash, aggregator, arbitrator) — NOT bare
    # existence — so an edited plan / swapped arbitrator RE-FIRES the reduce instead of silently
    # reusing a stale result. A pre-D-2 run (no meta sidecar) is reused as-is: never re-charge a
    # completed run merely because it lacks the new key.
    agg_key = {
        "plan_hash": plan.plan_hash,
        "aggregator": reducer.id,
        "arbitrator": voice_descriptor(arbitrator),
    }
    cache_ok = store.has("aggregate") and (
        not store.has("aggregate.meta") or store.read("aggregate.meta") == agg_key
    )
    if cache_ok:
        final = store.read("aggregate")
        metrics.append({"round": "aggregate", "debater": arbitrator.id, "cached": True})
        log.info("aggregate: loaded cached result")
    else:
        t0 = time.perf_counter()
        agg = reducer.reduce(
            final_blinded,
            schema=task.output_schema("aggregate"),
            ballots=task.ballots(final_blinded),
            context={"task": task, "arbitrator": arbitrator, "redteam": redteam_union},
        )
        final = agg.result
        metrics.append(
            {
                "round": "aggregate",
                "debater": arbitrator.id,
                "backend": getattr(arbitrator, "backend", None),  # split real vs notional cost
                "wall_s": round(time.perf_counter() - t0, 2),
                **(getattr(arbitrator, "last_meta", {}) or {}),
            }
        )
        if schema := task.output_schema("aggregate"):
            validate_output(
                final,
                schema,
                context="aggregate",
                dump_to=store.dir / "_invalid" / "aggregate.json",
            )
        store.write("aggregate", None, final)
        store.write_meta("aggregate.meta.json", agg_key)  # D-2: what plan/aggregator/arbitrator ran
    log.info("aggregate complete")

    # Deterministic gate (task-defined): grounding + exclusivity for generation. Recorded and
    # surfaced loudly; high-severity issues set gate.ok=False but do not discard the run (the
    # human review is the backstop — crashing would throw away an expensive near-complete debate).
    gate = task.verify_final(final)
    # arbitrator_invention gate (ADR-0014 §7; task-0025): fold in any merged item traceable to no
    # proposal. Run here (not in the reducer) so it is deterministic + resume-stable even when the
    # aggregate is cache-loaded; a HIGH invention finding fails the gate.
    invention = task.invention_gate(final, final_blinded)
    if invention:
        gate = {
            "ok": gate["ok"] and not any(f.get("severity") == "high" for f in invention),
            "issues": [*gate.get("issues", []), *invention],
        }
    store.write("gate", None, gate)
    if not gate["ok"]:
        highs = [i for i in gate["issues"] if i.get("severity") == "high"]
        log.warning("GATE FAILED — %d high-severity issue(s): %s", len(highs), highs)
    elif gate["issues"]:
        log.info("gate passed with %d low/medium note(s)", len(gate["issues"]))

    summary = summarize(metrics)
    # Real elapsed wall-clock for the whole run. With concurrency it is LESS than summary.wall_s
    # (the sum of per-call latencies), so both are reported: elapsed = what you waited, wall_s =
    # cumulative model time.
    summary["elapsed_s"] = round(time.perf_counter() - run_t0, 2)
    # Per-run reliability/bias dashboard (ADR-0012/0014), computed by the task from the recorded
    # pre-debate (propose) and post-debate (final) per-rater sets. The engine stays task-agnostic:
    # it supplies the rounds + rater models and stores whatever opaque dict the task returns.
    raters_meta = [{"id": d.id, "model": getattr(d, "model", None)} for d in debaters]
    diagnostics = task.panel_diagnostics({"propose": proposals, "final": final_sets}, raters_meta)
    # Panel roster (ADR-0004 provenance): every voice + its backend/model/vendor, plus a
    # `monovendor` flag, so the generated set records WHICH models deliberated. Promoted into the
    # codebook by `registry.promote_codebook`, so a CC-only run is distinguishable from a
    # cross-vendor panel by reading the item file alone. De-blind per-item support via
    # `result.blinding` (id→label) against each item's `support` to see who proposed what.
    proposer_descriptors = [voice_descriptor(d) for d in debaters]
    proposer_vendors = sorted({p["vendor"] for p in proposer_descriptors})
    panel = {
        "proposers": proposer_descriptors,
        "redteam": voice_descriptor(redteam) if redteam is not None else None,
        "arbitrator": voice_descriptor(arbitrator),
        "vendors": proposer_vendors,
        "monovendor": len(proposer_vendors) == 1,
        # Voices dropped mid-run (task-0011): a degraded run is VISIBLY degraded, never silent. The
        # per-round detail (which round, why) is in metrics.json `calls` (dropped=True entries).
        "dropped": sorted({r["debater"] for r in dropped}),
    }
    metrics_doc = {
        "task": task.name,
        "subject": task.subject_id,
        "debate": debate_name,
        "panel": panel,
        "summary": summary,
        "calls": metrics,
    }
    if diagnostics is not None:
        metrics_doc["panel_diagnostics"] = diagnostics
    metrics_doc["dynamic_rounds"] = dynamic_status  # ADR-0011: stop reason + per-item rounds
    store.write_meta("metrics.json", metrics_doc)
    # L0 trace (ADR-0019/0020): fold every per-call CallRecord sidecar into one `calls.jsonl`. Built
    # by globbing the durable sidecars, so it is resume-stable — metrics.json is an L2/L3 rollup
    # VIEW over these rows. (The task-defined aggregate call doesn't flow through `produce`, so it
    # is not an L0 row yet — captured when the aggregator seam lands, Phase E / task-0031.)
    store.write_call_log()
    # L1 (ADR-0020/task-0031): a role + capability-class (G/D/C) VIEW over the L0 stream — no new
    # model calls, so it never perturbs L0 or resume. L3: the run-level facts + an optional-typed
    # ground-truth slot (label-free runs stay valid + analyzable; the harness fills GT via the L4
    # label store, task-0026). Labels live in a SEPARATE append-only store, never mutating these.
    store.write_jsonl("roleoutputs.jsonl", _trace.build_role_outputs(store.collect_call_records()))
    store.write_meta("flags.json", {"findings": flags})  # task-0013: all referee findings for audit
    _task_spec = getattr(task, "spec", None)
    store.write_meta(
        "run.json",
        {
            "schema_version": _trace.TRACE_SCHEMA_VERSION,
            "task": task.name,
            "subject_id": task.subject_id,
            "debate": debate_name,
            "plan_hash": plan.plan_hash,
            "aggregator": reducer.id,
            "cast_pools": {
                "proposers": [d.id for d in debaters],
                "adversaries": [redteam.id] if redteam is not None else [],
                "aggregators": [arbitrator.id],
            },
            "materials_mode": (
                _task_spec.get("materials_mode") if isinstance(_task_spec, dict) else None
            ),
            # task-0027: the frozen evidence-universe id — the artifact states which corpus it used.
            "corpus_version": (
                _task_spec.get("corpus_version") if isinstance(_task_spec, dict) else None
            ),
            "seeds": {"blinding": debate_name},  # the blinding permutation is seeded by the name
            "ground_truth": {
                "provenance": "none"
            },  # optional-typed slot; labels are L4 (task-0026)
        },
    )
    log.info(
        "metrics: %d live calls (%d cached), %.0fs wall, $%.4f real (+$%.4f notional), "
        "%d->%d tok in/out",
        summary["n_calls"],
        summary["n_cached"],
        summary["wall_s"],
        summary["cost_usd"],
        summary["notional_cost_usd"],
        summary["input_tokens"],
        summary["output_tokens"],
    )

    result = {
        "task": task.name,
        "subject_id": task.subject_id,
        "debate": debate_name,
        "panel": panel,
        "blinding": blind,
        "gate": gate,
        "dynamic_rounds": dynamic_status,
        **final,
    }
    store.write("result", None, result)
    log.info("done -> %s/result.json", store.rel())
    return result
