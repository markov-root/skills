---
summary: How to select, rank, cap, and phrase comprehension questions, and how to log assumptions.
status: standing
role: knowledge
---

# Elicitation rubric — the comprehension pass

The goal of the entry pass is a **locked task frame** with the fewest possible
questions. Questions are a cost paid by the user; spend them only where the
answer changes what you build.

## Rank by impact × uncertainty

For each candidate ambiguity, score two axes quickly:

- **Impact** — if I guess wrong, how expensive is the correction? (throwaway
  work, rebuilt architecture, broken contract, wasted spend, harm.)
- **Uncertainty** — how unsure am I of the answer given the request, the repo,
  and sensible defaults?

Only **high-impact × high-uncertainty** items become questions. High-impact but
low-uncertainty → state the assumption and proceed. Low-impact → never ask;
default and move on.

## The cap

- **1–3 questions** for ordinary ambiguity.
- **Up to 5** for spec-heavy or high-stakes work (new system, irreversible
  change, external audience).
- **Never a questionnaire.** If you have more than five, you have not ranked.

This mirrors the strongest implementations (Spec Kit's `/clarify` caps at five,
one at a time, prioritized by impact/uncertainty; OpenAI's model spec: 1–3
precise clarifying questions _or_ labeled assumptions).

## Question quality bar

A good comprehension question:

- would change the plan depending on the answer;
- is **specific**, not generic ("Which auth provider — A, B, or C?" not "any
  requirements?");
- offers **multiple choice + a "something else" escape** wherever the option
  space is knowable — cheaper for the user and higher-signal than open prompts;
- carries your **recommended default** so the user can one-tap agree;
- is phrased so silence/"proceed" maps to a safe default.

Use the harness's structured-question primitive (e.g. `AskUserQuestion`) rather
than free-text walls. Batch the 2–4 that fit one screen; ask one at a time only
when a later question depends on an earlier answer.

## The task frame (what a locked comprehension produces)

- **Goal:** one sentence.
- **In scope / out of scope:** explicit boundaries.
- **Done-criteria:** observable, checkable outcomes.
- **Audience / consumer:** who uses the result and how.
- **Constraints:** stack, budget, deadline, compliance, non-negotiables.
- **Assumption log:** every default you chose _instead of_ asking (see below).

## The assumption log

Everything you did **not** ask about but had to decide becomes a logged
assumption. Format each as: _assumption → why chosen → what would falsify it._

```text
- Output format = single Markdown file. (default: matches sibling docs.)
  Falsified if: the user wanted a multi-file spec set.
- Target = OpenCode + Claude Code only. (default: current harnesses in use.)
  Falsified if: Codex parity is required.
```

The log is the contract for [`reverification.md`](reverification.md): a
re-verification fires exactly when new evidence _falsifies_ a logged assumption.
Without the log, every checkpoint degenerates into re-interrogation.

## Anti-patterns

- Asking to look diligent when the answer would not change the work.
- Open-ended "tell me everything about X" dumps.
- Re-asking something the request, repo, or a prior answer already settled.
- Withholding a recommendation and forcing the user to author the answer.
- Blowing past the cap because "more context is always better" — it is not; it
  costs user time and trust.
