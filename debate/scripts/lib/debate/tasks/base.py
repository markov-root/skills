"""DebateTask — the interface the engine drives.

The engine runs three generic rounds — independent -> cross-critique(steelman) -> revise —
then calls the task's `aggregate()`. A task supplies:

  - context_text():    the input bundle (generation: the item + appendices;
                        scoring: item + evidence dossier)
  - shared_context():  text appended to every round's user message (e.g. the criteria block)
  - system_prompt(r):  the prompt for round r, from prompts/<name>/<r>.md
  - output_schema(r):  JSON Schema to validate round r's output, or None to skip
  - aggregate(...):    the final step. Generation merges via an LLM arbitrator; scoring runs
                       Beta/Monte-Carlo math. This is the one step that genuinely differs, so
                       it is a task method, not engine logic.

Protocol is therefore a property of the task, not a global IDEA-vs-Delphi choice: scoring's
independent round elicits three-point estimates (IDEA); generation's proposes a set (Delphi).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from debate._resources import resource_path
from debate.backends import Debater

# The three generic, engine-driven rounds. The 4th step is the task's aggregate().
ROUNDS = ("propose", "critique", "revise")


@cache
def _voice() -> str:
    """The distilled house writing voice (ADR-0007), appended to EVERY system prompt so all
    generated prose (items, clauses, rationales, summaries, the final writeup) avoids
    AI-tell language and never uses em dashes. The full guide is `prompts/voice-full.md`; the
    dedicated writeup pass loads that in full."""
    path = resource_path("prompts", "_voice.md")
    return path.read_text() if path.exists() else ""


class DebateTask:
    name: str = "base"

    # Which Aggregator reduces this task's field by default (ADR-0013; task-0025). A generative task
    # (open ballot) merges via `arbitrator_select`; a numeric task (IDEA) uses `statistical`. A
    # config override is allowed where the field type permits — validated at load (fail fast).
    default_aggregator: str = "arbitrator_select"
    # The ballot kind gates aggregator compatibility: `open` = free-form proposals (no fixed option
    # set) → `vote` is refused (ADR-0014: never vote for a divergent/steelman field); `fixed` = a
    # closed slate every voice scores → `vote`/`statistical` permitted.
    ballot_kind: str = "open"

    def __init__(
        self,
        subject_id: str,
        prompts_dir: Path | str | None = None,
        *,
        resolved_prompts: dict[str, str] | None = None,
    ):
        self.subject_id = subject_id  # used in the run path, e.g. a measure id
        # When set (the CLI points it at a debate folder's snapshotted `prompts/`, ADR-0006), round
        # prompts are read from there so each debate is self-contained and its prompts are editable
        # for a re-run. Unset → the shared `prompts/<name>/` in the repo (the engine-test default).
        self.prompts_dir = Path(prompts_dir) if prompts_dir else None
        # An immutable run plan carries the exact, already voice-augmented prompt text.  Resume
        # supplies that mapping so execution never re-reads an edited project prompt after the
        # resolution boundary.  The path remains the authored-input adapter for new runs.
        self.resolved_prompts = dict(resolved_prompts) if resolved_prompts is not None else None

    # --- task-specific content -------------------------------------------------
    def context_text(self) -> str:
        raise NotImplementedError

    def shared_context(self) -> str:
        return ""

    def system_prompt(self, round_name: str) -> str:
        if self.resolved_prompts is not None:
            try:
                return self.resolved_prompts[round_name]
            except KeyError as exc:
                raise ValueError(f"resolved plan has no prompt for stage {round_name!r}") from exc
        base = self.prompts_dir or resource_path("prompts", self.name)
        prompt = (base / f"{round_name}.md").read_text()
        voice = _voice()
        return f"{prompt}\n\n---\n\n{voice}" if voice else prompt

    def output_schema(self, round_name: str) -> dict | None:
        return None

    def aggregate(
        self, final_by_label: dict[str, dict], arbitrator: Debater, redteam: dict | None = None
    ) -> dict:
        """Combine the panel's final sets (post-respond, or post-revise if no red-team) into the
        result, weighing the red-team findings if present. Task-defined."""
        raise NotImplementedError

    def verify_final(self, final: dict) -> dict:
        """Deterministic gate on the aggregated result (e.g. quote-grounding, exclusivity).
        Returns {"ok": bool, "issues": [...]}. Default: no-op pass."""
        return {"ok": True, "issues": []}

    def invention_gate(self, final: dict, field_blinded: dict[str, dict]) -> list[dict]:
        """The `arbitrator_invention` gate (ADR-0014 §7): flag any aggregated item traceable to NO
        proposal in the field the arbitrator saw — a hallucinated result the union-then-arbitrate
        contract forbids. Returns finding dicts ({check, target, fact, severity}); default [] = no
        gate. It lives here (not `verify_final`) because it needs BOTH the result and the field; the
        engine runs it deterministically after the aggregate so it is resume-stable (task-0025)."""
        return []

    def ballots(self, field_blinded: dict[str, dict]) -> dict | None:
        """For a numeric/fixed-ballot task, the per-item ballots a `statistical`/`vote` aggregator
        reduces — e.g. `{item_id: [{min, mode, max, confidence?}, …]}` (three-point) or
        `{voice_id: option_id}` (a closed slate). Default None: an open (generative) task has no
        ballots and reduces via an arbitrator merge instead (ADR-0013/0017)."""
        return None

    def referees(
        self,
        point: str,
        field: dict[str, dict],
        redteam: dict | None = None,
        select: list[str] | None = None,
    ) -> list:
        """Deterministic referee checks (task-0013; ADR-0011 §referees) at an injection `point`
        (`before_revise` = after critique, `before_respond` = after the red-team). Return `Finding`s
        (from `debate.referees.base`) — FACTS the engine renders as one opaque FLAGS block into the
        next proposer round so the panel doesn't burn reasoning re-deriving them; the full set
        (incl. non-injected lanes) is recorded to `flags.json`. Pure — NO model call.

        `select` (from the plan's `referees:` block, ADR-0011) NAMES which checkers run at this
        point; `None` = the task's default set for the point. A task that ships no checkers ignores
        it and returns [], so existing runs are unaffected (ADR-0002 boundary preserved)."""
        return []

    def new_options(self, redteam: dict | None, field: dict[str, dict]) -> list[dict]:
        """Genuinely-new options a red-team / escalate pass PROPOSED (not attacks on existing ones),
        for the symmetric-scrutiny step (task-0014): a late addition gets the SAME blinded
        peer critique a floor proposal gets before it can reach aggregation. Return option dicts
        (`{id, statement, ...}`) that are NOT already in `field`. Default [] → no scrutiny step, so
        behaviour is unchanged for a task whose adversary only attacks (ADR-0002 boundary kept).
        """
        return []

    def grounding_referee(self, panel_sets: dict[str, dict]) -> dict | None:
        """In-loop grounding referee (ADR-0011). Given the current {rater_id: set}, return an
        opaque findings dict to feed into the next round so raters self-correct before the final
        gate — or None if the task has no in-loop grounding check (the default). The engine threads
        the dict into the respond round's prompt like red-team findings, without inspecting it
        (task-agnostic, ADR-0002); deterministic, so it adds no model call."""
        return None

    def panel_diagnostics(
        self, rounds: dict[str, dict[str, dict]], raters: list[dict]
    ) -> dict | None:
        """Optional per-run reliability/bias dashboard, computed from recorded round outputs.

        The engine passes `rounds` (e.g. {"propose": ..., "final": ...}, each a {rater_id: output}
        map) and `raters` ([{id, model}]); it stores the returned dict verbatim into metrics.json
        without inspecting it (the engine stays task-agnostic — ADR-0002). Default: no diagnostics.
        """
        return None

    # --- per-item identity (engine ledger hook) --------------------------------
    # The engine must not reach into a task-specific data key to enumerate a set's items (that would
    # leak the domain into the core, ADR-0002/0003). These hooks supply item identity; both default
    # to "no per-item identity", so the per-item round ledger is simply empty until a task opts in.

    def item_ids(self, panel_sets: dict[str, dict]) -> list[str]:
        """Union of this task's ITEM ids across a panel's per-rater sets (stable order), or [] if
        the task has no stable per-item identity. Default []: no per-item bookkeeping."""
        return []

    def items(self, panel_sets: dict[str, dict]) -> dict[str, dict]:
        """{item-id -> first item dict seen across the panel}, for the escalation collision hooks.
        Default {} — only tasks on the atom marginal-value path (`extract_atoms`) need it."""
        return {}

    # --- dynamic rounds (ADR-0011) ---------------------------------------------
    # The engine owns the linear plan (floor + cap + the exhausted-search stop); the TASK supplies
    # the two semantic predicates the engine cannot know task-agnostically. Both default to "off",
    # so a task gets fixed rounds until it opts in (ADR-0002 boundary preserved).
    #
    # DETERMINISM CONTRACT (audit B-1): every hook below — escalation_focus, search_signature,
    # extract_atoms, arbitrate_collision, archetype_panel — MUST be a PURE function of its inputs
    # (the field, and for the collision hooks the item dicts). No `random`, no clock, no network.
    # The engine persists each escalation pass's stop decision to `round_status.stop_ledger` and, on
    # resume of a completed escalation, REPLAYS that ledger rather than re-calling these hooks — but
    # for an interrupted (parked/budget) escalation it re-derives the stop live from the cached
    # field, so an impure hook would make that resume stop at a different pass. Keep them pure.

    def escalation_focus(self, panel_sets: dict[str, dict]) -> list[str] | None:
        """Which options warrant extra adversarial passes (the CONTESTED subset).

        `panel_sets` is the current {rater_id: output} field. Return:
          * `None`  → this task does not support escalation (the default) — fixed rounds only;
          * `[]`    → escalation supported but nothing is contested now → stop (NOT an agreement
                      stop: the floor already ran; this just declines to deepen a settled set);
          * `[ids]` → the contested items to focus the next escalation pass on.
        """
        return None

    def escalation_stop_regime(self) -> str | None:
        """Which stop rule drives the escalation loop (task-0015; ADR-0014 §6):
          * `None`       → the default — marginal-atom coverage (`extract_atoms`) if implemented,
                           else the `search_signature` exhausted-search fallback below;
          * `"novelty"`  → the owner's legible steelman rule: continue only while the latest pass
                           minted a genuinely-NEW unique option (via `new_options`, reusing the
                           `near_duplicate` primitive); a pass that adds none stops the loop
                           (STOP_NOVELTY). Still bounded by `max_rounds` + the token budget, and the
                           stop is recorded per-cycle for resume.
        Opt-in — default None leaves every existing task's stop behaviour unchanged."""
        return None

    def search_signature(self, panel_sets: dict[str, dict], redteam: dict | None) -> set:
        """A set of hashable tokens standing for everything the debate has SEARCHED so far — every
        option, evidence citation, clause value, and red-team finding. The engine compares
        consecutive passes' signatures: a pass that adds no new token has EXHAUSTED the search and
        the loop stops (ADR-0011). It never inspects the tokens' meaning — that keeps the
        stop a function of search progress, never of inter-rater agreement (ADR-0014).

        This is the FALLBACK exhausted-search signal. A task that implements `extract_atoms`
        (below) upgrades the engine to the marginal-information-value path (ADR-0011),
        which gates on requirement-atom coverage rather than surface tokens.
        """
        return set()

    # --- marginal information value (ADR-0011) ----------------------------------
    # When `extract_atoms` returns a list (not None), the engine drives the escalation stop with the
    # CoverageLedger (atom coverage + Good-Turing exhausted-search) instead of `search_signature`,
    # classifies each pass (orthogonal / decomposes / refinement / redundant / contradicts), and may
    # rank/flag with `archetype_panel`. All three default to "off" → the signature path above is
    # used, so a task opts in (ADR-0002 boundary kept; offline tests unaffected).

    def extract_atoms(self, panel_sets: dict[str, dict]) -> dict[str, list] | None:
        """Map item-id -> list of requirement-ATOMS for the current field, or None to opt out.

        An atom = one testable obligation: {"key": <normalized obligation, the dedup unit>,
        "salience": <1.0 normative / 0.5 recommendatory>, "span": <verbatim sub-span>}. The `key` is
        what the ledger dedups on — a normalized OBLIGATION, never raw clause text (the
        surface-novelty trap this replaces). Anchor each atom to a verbatim sub-span for audit.
        Default None = use `search_signature`."""
        return None

    def arbitrate_collision(self, candidate: dict, existing: dict) -> str | None:
        """For a candidate that adds no new atom-key, the verb for its relation to the colliding
        existing item: "refines" | "duplicates" | "contradicts" (None = unknown → redundant).
        `contradicts` (a same-atom opposing reading) is preserved as a finding and keeps the loop
        alive — the only route to CLS_CONTRADICTS. Default None (the deterministic fallback never
        asserts a relation; the engine treats no-new-atom as redundant)."""
        return None

    def archetype_panel(self, atom_key: str, span: str | None) -> list[float] | None:
        """Predicted pass (∈[0,1]) of `atom_key` against each fixed synthetic-company archetype, or
        None to skip. Discrimination prior = VARIANCE of this vector across archetypes (low variance
        ⇒ everyone passes/fails alike, or mature≈gamer ⇒ gaming-susceptible). It only RANKS/FLAGS —
        the engine never lets it affect the stop (no predicted quantity may gate; ADR-0011). Swapped
        for real cross-company pass-variance later (same estimand)."""
        return None
