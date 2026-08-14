# Anti-patterns & debunked myths

Two lists: timeless mistakes (from provider guidance) and myths that **fail under controlled 2025-2026
evaluation** ([source register](../references/SOURCES.md)). Verdicts: **DEBUNKED** (evidence says it doesn't work), **CONTESTED**
(mixed/narrow evidence — don't rely on it), **CONFIRMED** (real effect to respect).

## Debunked / contested myths — stop doing these

- **"I'll tip you $200" / "I'll kill you" / threats** — **DEBUNKED.** No significant aggregate benefit
  on GPQA/MMLU-Pro; individual questions swing unpredictably (Prompting Science Report 3, 2025). Cut it.
- **"Being polite improves accuracy"** — **CONTESTED.** Mixed and narrow: one small GPT-4o study found
  blunt prompts slightly *out*performed polite ones; a separate study found politeness _increased_
  harmful compliance. Don't add courtesy for accuracy (be civil for your own reasons, not performance).
- **"Always add chain-of-thought"** — **CONFIRMED counterproductive** as a blanket rule: little gain on
  reasoning models, added latency/variance, and it can _degrade instruction-following_. Use CoT
  selectively (see `model-era.md`).
- **"Ask the model to critique/verify itself"** — **DEBUNKED as a reliable verifier.** Self-critique can
  _collapse_ performance on reasoning/planning tasks; a sound external verifier helps far more (Stechly
  2025). Use self-review only for rubric-guided polish, not correctness gating.
- **"Few-shot always beats zero-shot"** — **CONTESTED.** No shot count/selection dominates; too many
  examples can _over-prompt_ and reduce accuracy (Few-shot Dilemma 2025; Santana 2025). Start
  zero-shot, add examples only where an eval shows benefit.
- **"Structured output (JSON/XML) is free"** — **CONFIRMED tax** on some models: forcing reasoning
  inside a strict schema can cost accuracy, especially on smaller/open models ("The Format Tax" 2026).
  Reason first, serialize second. (On strong closed models the tax is often negligible — measure.)
- **"'Think step by step' can't hurt"** — it can: it diverts attention from constraints and adds
  forbidden content / breaks format compliance (When Thinking Fails 2025; MathIF; ReasonIF).

## Timeless mistakes

- **Vague / underspecified.** "Write a blog post about consoles" → generic mush. Specify length, style,
  audience, content. _More detail in the instruction → closer to intent._
- **Negative-only instructions.** "Do NOT use markdown" leaves the model guessing. State the positive
  target: "Respond in flowing prose paragraphs." Positive examples > "don't" lists.
- **Constraints instead of instructions.** Prefer "do X"; reserve hard constraints for safety/strict
  format. Over-constraining clashes and limits quality.
- **Overloaded mega-prompt.** One prompt trying to analyze + reason + format + validate → fragmented
  output. Decompose; chain; one prompt = one responsibility.
- **Inconsistent example formatting.** Mixing tone/label style/structure across few-shot examples
  degrades them. Keep them uniform, relevant, diverse, edge-case-covering.
- **Answer before reasoning (in CoT).** Breaks the technique — reasoning must precede the answer.
- **Query before long documents.** Put data on top, the ask at the bottom (long context).
- **"CRITICAL: You MUST…" everywhere.** On modern models this over-triggers and bloats output. Use
  plain, specific phrasing; escalate emphasis only for genuine hard rules.
- **Skipping iteration/eval.** "Prompt optimization is not a luxury — it's a foundational practice."
  Baseline → evaluate → change one axis → re-test on a representative set.
- **Letting feedback rewrite production prompts directly.** A user click, override, or terse comment is
  a fallible signal, not a complete requirement. Preserve the triggering case; propose a versioned
  change; review policy/safety/fairness effects; rerun regression, counterexample, and holdout cases;
  then promote with rollback. Keep immutable constraints outside the optimizer's authority.
- **Unowned defensive patches and long ban lists.** A workaround for one model can become an
  over-trigger on the next. Record the motivating failure, model/configuration, regression case,
  rationale, and review/removal trigger; challenge the patch on every model migration.
- **One-sided objective proxies.** Giving only the cost of escalation, tool use, abstention, or delay
  invites the model to optimize against the required behavior. State the competing outcomes and
  authoritative thresholds. Enforce hard budgets, permissions, and mandatory handoffs in code.
- **Trusting LLM math/code blindly.** They pattern-match, not compute. Read/run generated code; offload
  real computation to tools (PAL).
- **Letting the model hardcode to pass tests, or edit/remove tests.** "Tests verify correctness, they
  don't define the solution." Ask for a general solution; if a test looks wrong, surface it.
- **Answering about code it hasn't opened.** "Never speculate about code you have not read."
- **Over-engineering.** No unrequested features, refactors, defensive code for impossible cases, or
  one-off abstractions. "The right amount of complexity is the minimum needed for the current task."
- **Generic "make it not look AI-generated."** For frontend/style, "don't use cream / make it clean"
  just shifts to another default. Specify a concrete alternative, or ask the model to propose N
  distinct directions and pick one.
- **Grading with the same model/instance ungraded-for-reliability.** For LLM-as-judge: detailed rubric,
  force a discrete verdict, reason-then-discard, and use a _different_ model to grade than to generate.
- **Assuming a knob is stable across model generations.** Effort levels, prefill support, tool
  eagerness, default verbosity all drift. Re-check `model-era.md` and re-run your eval on upgrade.

## Things that are real (respect them)

- **Delimiter/punctuation/format sensitivity is real** — a single character can swing evals (2025). Fix
  your delimiters and test them.
- **"Lost in the middle" persists** for multi-evidence long-context (2025). Position critical evidence
  at the edges.
- **Self-consistency aids calibration** but can amplify a confident wrong answer — signal, not proof.
- **Prompt sensitivity is partly real, partly an eval artifact** — rigid answer-matching exaggerates it;
  semantic judging reduces variance, but format perturbations still matter (Hua 2025).
