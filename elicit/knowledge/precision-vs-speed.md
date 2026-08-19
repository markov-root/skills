---
summary: Default to precision; switch to speed only when warranted; how to triage and how much to probe on each.
status: standing
role: knowledge
---

# Precision vs speed

The user's standing preference is **precision — get the task done right** — over
speed, unless they explicitly ask to move fast. This governs how hard the
comprehension pass probes. It is the practical form of Simon's **satisficing**:
optimize (keep probing for the best-fit understanding) when stakes are high;
satisfice (act on "good enough") when they're low.

## Default and override

- **Default = precision.** When correctness matters and the mode is unstated,
  probe until the task is understood well enough to do it right.
- **Override = speed**, when the user says so ("just do it," "quick and dirty,"
  "don't ask, guess") **or** the task is clearly low-stakes and reversible.
- **Unclear + high stakes + user seems rushed?** Ask _one_ question: "This is
  worth getting exactly right — a couple of quick questions, or should I make my
  best call and move fast?"

Record the chosen mode in the task frame; it changes the stopping rule.

## Triage: how much to probe

| Signal        | Lean precision (probe more)                                    | Lean speed (probe less / act)  |
| ------------- | -------------------------------------------------------------- | ------------------------------ |
| Reversibility | irreversible, hard to undo                                     | easily redone or discarded     |
| Cost of redo  | expensive (time, money, trust)                                 | cheap                          |
| Blast radius  | safety, legal, financial, security, privacy, or affects others | isolated, personal, low-impact |
| Ambiguity     | many valid readings, unstated goal                             | one obvious reading            |
| User signal   | wants it right, is exploring                                   | explicitly rushed, throwaway   |

High on the left → **ask first**. High on the right → **answer now / with
assumptions**. Mixed → answer with assumptions and name them so the user can
correct cheaply.

## Stopping rule by mode

- **Precision mode:** stop when the critical ambiguity is resolved, the user says
  proceed, or the ≤5 cap is hit. Correctness first — but the cap still holds;
  precision is not license to interrogate.
- **Speed mode:** set an explicit "good enough" bar, make the most-likely
  assumptions, act, and list what you assumed so a wrong guess is cheap to fix.

## Don't weaponize precision

Precision-first is about _correctness of outcome_, not maximal questioning. The
impact×uncertainty cap in [`elicitation-rubric.md`](elicitation-rubric.md) still
governs: ask only what changes the result. Over-asking in the name of precision
still erodes trust and is its own failure mode.
