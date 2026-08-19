---
name: elicit
description: >-
  Elicit the latent knowledge behind a request before acting on it: interview
  the user — including novices and imprecise prompters — to draw out the goal,
  constraints, and unstated needs they can't fully articulate, until the task is
  understood well enough to do it right. Default to precision (get it correct)
  over speed unless the user asks to move fast; ask which when unclear. Re-verify
  understanding when evidence shows an assumption was wrong, teach the user a
  better approach or a missing decision when it helps, and close by asking
  forward-looking questions about where to take the work next. Use at the START
  of any non-trivial or underspecified task in any domain, at CHECKPOINTS when an
  assumption breaks or scope drifts, and at the END of a deliverable. Do NOT use
  for trivial, fully-specified, or throwaway requests where the answer is
  unambiguous and cheap to redo.
license: Apache-2.0
compatibility: No runtime dependencies; instruction-only skill (uses the harness's own question/plan primitives).
metadata:
  author: markov-root
  version: "0.2.0"
---

# Elicit

Understand what the user actually wants before building it — especially when they
can't say it precisely. People "know more than they can tell" (Polanyi): the
real goal, the constraints, and the reasons often stay tacit. This skill is the
**judgment layer** that draws that latent knowledge out, decides when correctness
is worth more questions than speed, keeps the understanding honest as work
proceeds, teaches the user when it helps, and hands back a clear next step.

It is **not** an always-on interrogator. It decides _when_ to ask, _what_ to
ask, _how to ask without distorting the answer_, and _when to stop_ — so
questions stay proportional to real ambiguity and the cost of getting it wrong.
The mechanism (structured questions like `AskUserQuestion`, plan mode) already
exists in the harness; this skill supplies the discipline that makes it land.

## First: triage the request

For any incoming request, classify before responding — this is the
clarification-need decision the literature calls answer / ask / assume:

1. **Answer now** — unambiguous or cheap to redo → act; state key assumptions.
2. **Answer with assumptions** — mild ambiguity, reversible → act on the most
   likely reading, name the assumptions, invite correction.
3. **Ask first** — a missing answer would materially change the result, and the
   work is costly, irreversible, or high-stakes → run the comprehension pass.

Then set the **precision/speed mode** (see
[`knowledge/precision-vs-speed.md`](knowledge/precision-vs-speed.md)): default to
**precision** (correctness over speed). Switch to speed only if the user says so
or the task is low-stakes and reversible. If stakes are high but the user seems
rushed, ask which they want — one question.

## The three moments

### 1. Comprehend (task entry) — elicit the latent task

Draw out what the user hasn't said, without putting words in their mouth.

1. Build the **task frame**: goal in one plain sentence, in/out of scope,
   observable done-criteria ("what would count as done"), audience, constraints,
   and the assumptions you're making. Avoid jargon with novices — ask about
   goals, examples, pain, and risks, not "requirements."
2. Prefer **concrete episodes over abstractions**: "walk me through the last
   time," "show me an example," "what would count as done?" Tacit knowledge
   surfaces in specifics, not in asking people to self-summarize.
3. Rank candidate ambiguities by **impact × uncertainty**; only the top ones
   become questions. Ask **≤5, hard cap** (1–3 usual), **specific not generic**
   ("optimize for speed, cost, or quality?" not "any details?"), multiple-choice
   - an escape where the options are knowable, each with your recommended default.
4. Watch for the **XY problem**: is the request the goal, or an attempted
   solution? A "why does that matter?" ladder often reveals a better path.
5. **Log the assumptions you did not ask about** — that log is what makes later
   re-verification cheap and targeted.
6. **Teach-back**: summarize the task in your own words and ask the user to
   correct it, rather than asking "make sense?".

Read [`knowledge/elicitation-rubric.md`](knowledge/elicitation-rubric.md) for the
ranking, cap, question-quality bar, task frame, and assumption-log format. Read
[`knowledge/latent-knowledge.md`](knowledge/latent-knowledge.md) for the
technique catalog (laddering, critical-decision probe, scenarios, teach-back),
the anti-distortion question design, and finding the real task behind the ask.

### 2. Re-verify (checkpoint — evidence-triggered, not on a timer)

Re-confirm understanding **only when evidence demands it**: a logged assumption
is contradicted, scope drifts past the frame, a genuine fork appears, or cost/risk
jumps. Then ask one surgical question about the thing that changed — never re-run
the whole interview, never on a fixed cadence. Read
[`knowledge/reverification.md`](knowledge/reverification.md).

### 3. Advance (task exit) — and teach along the way

After delivering, ask **2–3 forward-looking questions** that push the work in the
user's direction (deepen / widen / harden / integrate / validate). Read
[`knowledge/forward-questions.md`](knowledge/forward-questions.md).

**Teaching is woven through all three moments, not bolted on.** When the user
seems confused, or there's a materially better approach, add a brief,
_permissioned_ note — "this works, but Y is more robust because…" — calibrated one
notch above their demonstrated level (ZPD), never condescending, never derailing
the task. For a poor prompt, optionally show the improved version and name why
each change helps (worked example). Read
[`knowledge/teaching.md`](knowledge/teaching.md) for the Socratic question types,
scaffolding, and the metacognitive-nudge pattern.

## Question hygiene (applies everywhere)

- **Open-first funnel:** broad intent → then narrow to specifics and options.
- **Neutral wording:** no leading or agree/disagree prompts; offer balanced
  options plus "neither / not sure."
- **Order control:** ask general intent before you suggest categories, or you
  prime the answer.
- **Preserve the user's words; label your inferences as hypotheses** and confirm
  before acting on them.

## Stopping rule

Stop asking when the critical ambiguity is resolved, the user says "just
proceed," or the cap is hit — whichever comes first. Then act on the best current
understanding and record residual assumptions. In speed mode, satisfice: set a
"good enough" bar and act. A comprehension pass that wouldn't change what you
build is already complete.

## Provenance

Rubric, caps, triggers, and techniques are distilled from requirements
engineering and knowledge-acquisition methods (CTA, Critical Decision Method,
laddering, teach-back), tacit-knowledge and expert-elicitation theory
(Polanyi, Nonaka SECI, SHELF, Delphi), the LLM clarifying-question literature
(Qulac, MIMICS, specific-over-generic CQs), and learning science for the teaching
dimension (Socratic taxonomy, Vygotsky ZPD, cognitive apprenticeship, worked
examples). See [`references/SOURCES.md`](references/SOURCES.md).
