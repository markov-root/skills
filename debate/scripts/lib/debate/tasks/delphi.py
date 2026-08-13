"""Generic, run-spec-driven debate tasks (ADR-0002). Domain-free: the question and grounding come
entirely from the run-spec, so one engine serves any topic.

`DelphiTask` — the panel proposes a SET of options, critiques blinded peers, revises, optionally
red-teams + responds, then an LLM arbitrator merges the field into a consensus set (Delphi-style).
The aggregate is an arbitrator merge, not numeric.

The IDEA three-point variant (each rater gives low/best/high per item; the aggregate runs the
`debate/aggregate` PERT -> opinion-pool -> Monte-Carlo math) is the sibling task; see task-0002.
"""

from __future__ import annotations

import re

from debate.backends import Debater, extract_json
from debate.engine.prompting import blocks, json_block
from debate.referees.base import Finding
from debate.tasks.base import DebateTask

# arbitrator_invention gate (ADR-0014 §7): a merged option must be traceable to some proposal the
# arbitrator saw. Traceability = max token-Jaccard of the option's statement against every proposal
# statement >= this floor; below it the option is treated as invented (hallucinated), a HIGH gate.
_INVENTION_TAU = 0.30
_WORD = re.compile(r"[a-z0-9]+")


def _toks(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --- referee checkers (task-0013): pure, deterministic, NO model call ----------------------------
# Thresholds are hand-set + versioned here (not learned). Each checker returns FACTS (Findings),
# never verdicts — the panel decides what to do with them.
_NEAR_DUP_TAU = 0.6  # token-Jaccard at/above which two options are "near-duplicate"
_THIN_RATIONALE_WORDS = 10  # a rationale below this word count is "thin"
_OVERREACH_MIN_WORDS = 6  # a red-team ATTACK thinner than this reads as manufactured/padding
# The red-team ATTACK lane (task-0020): objections that CLAIM a gap. The honest OVER-REACH lane
# (type="overreach") is the red-team conceding the opposing case is too strong — never itself a
# manufactured attack, so `_overreach` leaves it alone.
_ATTACK_TYPES = {"missing", "unsupported", "redundant", "weak"}


def _unique_options(field: dict[str, dict]) -> list[dict]:
    """The distinct options across the panel's per-voice sets (first seen per id, stable order) —
    the unit the structural checkers inspect."""
    seen: dict[str, dict] = {}
    for s in field.values():
        for o in s.get("options") or []:
            oid = o.get("id")
            if oid is not None and oid not in seen:
                seen[oid] = o
    return list(seen.values())


def _near_duplicate(opts: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for i, a in enumerate(opts):
        for b in opts[i + 1 :]:
            j = _jaccard(_toks(a.get("statement", "")), _toks(b.get("statement", "")))
            if j >= _NEAR_DUP_TAU:
                out.append(
                    Finding(
                        check="near_duplicate",
                        target=f"{a.get('id')}~{b.get('id')}",
                        fact=f"options overlap {j:.2f} (>= {_NEAR_DUP_TAU}) — merge or split",
                        severity="medium",
                        data={"jaccard": round(j, 4)},
                    )
                )
    return out


def _non_atomic(opts: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for o in opts:
        stmt = o.get("statement", "")
        # a bundle: multiple sentences, a semicolon list, or a clause conjoined by " and "
        sentences = [s for s in re.split(r"[.;]\s", stmt) if s.strip()]
        if len(sentences) >= 2 or " and " in stmt.lower():
            out.append(
                Finding(
                    check="non_atomic",
                    target=str(o.get("id")),
                    fact="option bundles >=2 claims — split into atomic options",
                    severity="low",
                )
            )
    return out


def _thin_rationale(opts: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for o in opts:
        words = len(_WORD.findall(o.get("rationale", "") or ""))
        if words < _THIN_RATIONALE_WORDS:
            out.append(
                Finding(
                    check="thin_rationale",
                    target=str(o.get("id")),
                    fact=f"rationale is {words} words (< {_THIN_RATIONALE_WORDS}) — justify it",
                    severity="low",
                    data={"words": words},
                )
            )
    return out


def _overreach(redteam: dict) -> list[Finding]:
    """Down-grade a MANUFACTURED weak objection — task-0020 acceptance #2. A red-team ATTACK-lane
    finding whose detail is thin (< `_OVERREACH_MIN_WORDS` words) reads as padding rather than a
    grounded objection; flag it so the arbitrator weights it down. The honest over-reach lane
    (type="overreach") and substantive, well-argued attacks are left untouched. Pure/deterministic;
    this is the ENGINE-side complement to the prompt's honesty clause (a prompt can't self-enforce,
    but a checker can, and FakeDebater output is fixed so this is golden-testable)."""
    out: list[Finding] = []
    for i, f in enumerate(redteam.get("findings") or []):
        ftype = (f.get("type") or "").lower()
        if ftype and ftype not in _ATTACK_TYPES:
            continue  # not an attack (e.g. the honest 'overreach' lane) → not manufactured padding
        detail = f.get("detail") or f.get("issue") or f.get("fact") or ""
        words = len(_WORD.findall(detail))
        if words < _OVERREACH_MIN_WORDS:
            out.append(
                Finding(
                    check="overreach",
                    target=f"finding-{i}",
                    fact=f"red-team objection is thin ({words} words < {_OVERREACH_MIN_WORDS}) — "
                    f"likely manufactured to pad count; weight it down unless it can be grounded",
                    severity="low",
                    data={"finding": i, "words": words},
                )
            )
    return out


def _unaddressed(opts: list[dict], redteam: dict) -> list[Finding]:
    """A red-team finding no option's text (statement+rationale) overlaps — likely unaddressed."""
    corpus = _toks(" ".join(f"{o.get('statement', '')} {o.get('rationale', '')}" for o in opts))
    out: list[Finding] = []
    for i, f in enumerate(redteam.get("findings") or []):
        issue = f.get("issue") or f.get("fact") or ""
        if issue and not (_toks(issue) & corpus):
            out.append(
                Finding(
                    check="unaddressed",
                    target=f"finding-{i}",
                    fact=f"red-team finding not reflected in any option: {issue[:120]}",
                    severity="medium",
                )
            )
    return out


# One proposed position/answer with its reasoning. `additionalProperties` stays open so a model may
# attach extra fields (e.g. evidence) without failing the boundary check.
_OPTION = {
    "type": "object",
    "required": ["id", "statement"],
    "properties": {
        "id": {"type": "string"},
        "statement": {"type": "string"},
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
        # Provenance (task-0023): the panel option id(s) a merged option traces to, so the
        # arbitrator's EDITOR-not-author discipline is auditable. Optional; only the arbitrate round
        # is asked to populate it, and `invention_gate` already checks traceability independently.
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}

DELPHI_SCHEMA = {
    "type": "object",
    "required": ["options"],
    "properties": {
        "options": {"type": "array", "items": _OPTION},
        "summary": {"type": "string"},
        "disagreements": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}

# critique + redteam are advisory (free-form JSON findings, not option sets) → not schema-validated.
_VALIDATED_ROUNDS = {"propose", "revise", "respond", "aggregate"}


class DelphiTask(DebateTask):
    name = "delphi"

    def __init__(self, spec: dict, prompts_dir=None, *, resolved_prompts=None):
        super().__init__(
            spec["id"], prompts_dir=prompts_dir, resolved_prompts=resolved_prompts
        )
        self.spec = spec

    def context_text(self) -> str:
        parts = [f"QUESTION:\n{self.spec['question'].strip()}"]
        if self.spec.get("context"):
            parts.append(f"CONTEXT:\n{str(self.spec['context']).strip()}")
        return blocks(*parts)

    # Materials-mode instruction (ADR-0010): tells the voice how it may reach evidence beyond the
    # injected map. `context` needs none; `disk` (CLI voices) may open files; `search` goes online.
    _MODE_NOTE = {
        "disk": "MATERIALS ACCESS: the corpus files listed in the map live in this project's "
        "materials/ folder — OPEN the specific file when you need its full text, don't rely on "
        "the abstract alone.",
        "search": "MATERIALS ACCESS: you MAY SEARCH the web for sources beyond the provided "
        "materials to surface genuinely new arguments; cite what you find. Verbatim-quote "
        "grounding is NOT enforced in this mode.",
    }

    def shared_context(self) -> str:
        parts = []
        if crit := self.spec.get("criteria"):
            parts.append(f"CRITERIA (apply exactly):\n{str(crit).strip()}")
        if note := self._MODE_NOTE.get(self.spec.get("materials_mode")):
            parts.append(note)
        return blocks(*parts)

    def grounded(self) -> bool:
        """False in `search` mode — sources aren't pinned, so the verbatim-quote gate is off."""
        return self.spec.get("materials_mode") != "search"

    def output_schema(self, round_name: str) -> dict | None:
        return DELPHI_SCHEMA if round_name in _VALIDATED_ROUNDS else None

    def aggregate(
        self, final_by_label: dict[str, dict], arbitrator: Debater, redteam: dict | None = None
    ) -> dict:
        sets = blocks(
            *(
                json_block(f"FINAL PROPOSAL {label}", p)
                for label, p in sorted(final_by_label.items())
            )
        )
        rt = json_block("RED-TEAM FINDINGS", redteam) if redteam else ""
        user = blocks(self.shared_context(), self.context_text(), sets, rt)
        return extract_json(
            arbitrator.generate(self.system_prompt("aggregate"), user, want_json=True)
        )

    # Named checker registry (task-0013 follow-up): every checker addressable by name so the plan's
    # `referees:` block can SELECT which run at which point. Uniform (opts, redteam) signature — a
    # checker that ignores one argument just drops it. Add a checker here to make it selectable.
    _CHECKERS = {
        "near_duplicate": lambda opts, rt: _near_duplicate(opts),
        "non_atomic": lambda opts, rt: _non_atomic(opts),
        "thin_rationale": lambda opts, rt: _thin_rationale(opts),
        "unaddressed": lambda opts, rt: _unaddressed(opts, rt) if rt else [],
        "overreach": lambda opts, rt: _overreach(rt) if rt else [],
    }
    # Default selection per injection point when config names none. `before_revise` keeps the three
    # structural checks; `before_respond` adds the red-team-aware `unaddressed` + `overreach`
    # (task-0020 #2). Steelman is the primary use, so over-reach detection is ON by default here —
    # a deliberate improvement; turn any off by naming a subset in the plan `referees:` block.
    _DEFAULT_REFEREES = {
        "before_revise": ("near_duplicate", "non_atomic", "thin_rationale"),
        "before_respond": (
            "near_duplicate",
            "non_atomic",
            "thin_rationale",
            "unaddressed",
            "overreach",
        ),
    }

    @classmethod
    def available_referees(cls) -> tuple[str, ...]:
        """Every selectable checker name — for validating a plan's `referees:` block."""
        return tuple(cls._CHECKERS)

    def referees(
        self,
        point: str,
        field: dict[str, dict],
        redteam: dict | None = None,
        select: list[str] | None = None,
    ) -> list:
        """The steelman referee checks (task-0013). `select` (from the plan's `referees:` block)
        NAMES which checkers run at `point`; `None` uses the point's default set. Unknown names are
        skipped (robust; validate at load via `available_referees`). Pure/deterministic."""
        opts = _unique_options(field)
        names = tuple(select) if select is not None else self._DEFAULT_REFEREES.get(point, ())
        out: list[Finding] = []
        for name in names:
            checker = self._CHECKERS.get(name)
            if checker is not None:
                out.extend(checker(opts, redteam))
        return out

    def escalation_stop_regime(self) -> str:
        """Steelman uses the NOVELTY regime (task-0015): loop only while the adversary mints a
        genuinely-new unique option. Inert until escalation is activated for Delphi (this task
        returns no `escalation_focus` yet, so a default steelman run does not escalate and stays
        byte-identical); wiring steelman escalation ON is a deliberate, cost-changing follow-up."""
        return "novelty"

    def new_options(self, redteam: dict | None, field: dict[str, dict]) -> list[dict]:
        """Surface genuinely-new options the adversary PROPOSED (task-0014). The red-team/escalate
        output may carry a `new_option` (str or option dict) and/or a `new_options` list; we
        normalise each to an option dict and keep only those that are actually new — id not already
        in the field, and statement not a near-duplicate (>= `_NEAR_DUP_TAU`) of any existing one.
        Empty → no scrutiny step (behaviour unchanged)."""
        if not redteam:
            return []
        existing_ids = {o.get("id") for s in field.values() for o in (s.get("options") or [])}
        existing_toks = [
            _toks(o.get("statement", "")) for s in field.values() for o in (s.get("options") or [])
        ]
        raw: list = []
        if redteam.get("new_option"):
            raw.append(redteam["new_option"])
        raw.extend(redteam.get("new_options") or [])
        out: list[dict] = []
        for i, item in enumerate(raw):
            if isinstance(item, str):
                opt = {"id": f"rt-new-{i + 1}", "statement": item}
            elif isinstance(item, dict) and item.get("statement"):
                opt = {"id": item.get("id") or f"rt-new-{i + 1}", **item}
            else:
                continue
            if opt["id"] in existing_ids:
                continue
            stoks = _toks(opt.get("statement", ""))
            if any(_jaccard(stoks, e) >= _NEAR_DUP_TAU for e in existing_toks):
                continue
            out.append(opt)
        return out

    def invention_gate(self, final: dict, field_blinded: dict[str, dict]) -> list[dict]:
        """Flag any merged option whose statement is traceable (token-Jaccard) to no proposal the
        arbitrator saw — an invented result (ADR-0014 §7). Pure/deterministic; no model call."""
        proposals = [
            _toks(o.get("statement", ""))
            for s in field_blinded.values()
            for o in (s.get("options") or [])
        ]
        flags: list[dict] = []
        for opt in final.get("options") or []:
            best = max(
                (_jaccard(_toks(opt.get("statement", "")), p) for p in proposals), default=0.0
            )
            if best < _INVENTION_TAU:
                flags.append(
                    {
                        "check": "arbitrator_invention",
                        "target": opt.get("id"),
                        "fact": f"merged option traceable to no proposal (max jaccard "
                        f"{best:.2f} < {_INVENTION_TAU})",
                        "severity": "high",
                    }
                )
        return flags
