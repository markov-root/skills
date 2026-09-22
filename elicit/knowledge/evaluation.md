---
summary: How this skill is evaluated and improved — user-anchored evidence, calibration signals, and why agent self-judgment is low-trust here.
status: standing
role: knowledge
---

# Evaluating and improving `elicit`

This skill is different from most tools in the portfolio, and the difference
dictates how it may be improved. Read this before "tuning" the rubric, the cap,
or the triggers — and before recording any praise for this skill.

## Why this skill can't grade itself

Most skills have a **deterministic anchor**: a fact the agent can read without the
user — a test passes, a validator is green, a benchmark number drops. Self-review
is safe there because the agent's judgment is tethered to that external fact.

`elicit` has **no such anchor**. Its quality is "did the questions surface what
the user actually wanted, without wasting their patience?" — and the ground truth
lives in the user's head and reactions, which the agent cannot see. The target
(latent knowledge) is by definition the thing the agent lacks access to.

So agent self-feedback here is not merely weak, it is **actively misleading**. A
loop where the agent grades its own questions optimizes a proxy the agent
invented ("did that look thorough?"), and with no cost signal from the user's
side it drifts one way: **ask more, look more diligent.** That is Goodhart's law
/ an echo chamber. The portfolio rule applies with force: **never infer user
satisfaction from silence or from the agent's own sense of a good interview.**

**Policy:** for `elicit`, treat `agent_judgment` as **low-trust**. Do not change
the rubric, cap, or triggers on agent judgment alone. Require `explicit_user`,
`observed_user`, or `deterministic` (outcome) evidence.

## What counts as evidence, most-trusted first

1. **Deterministic outcome — rework.** After eliciting and delivering, was the
   result accepted, or bounced with "that's not what I meant"? Rework-after-
   delivery is real, unfakeable evidence that elicitation missed something;
   acceptance-without-rework is real positive evidence.
2. **Observed behavior.** Did the user disengage, say "just do it," ignore the
   questions, or express impatience? Real `observed_user` signal of **over**-
   asking. Did they answer engagedly and thank a specific question? Signal it
   helped.
3. **Explicit user feedback.** "That question saved us" / "you're over-asking."
   Scarce, so weight it highest of all when present.
4. **Independent evaluation.** A cross-vendor judge (e.g. the `debate` skill)
   scoring real transcripts against outcomes — not against "looked thorough" —
   and/or a held-out set of real underspecified requests whose true resolution
   was later learned. Use this to break the echo chamber, never a same-model
   self-score.

Record these through `skill-feedback` with an **honest `--source`**
(`explicit_user`, `observed_user`, `deterministic`, `independent_evaluation`) —
never dress `agent_judgment` as user satisfaction.

## The per-episode calibration log (cheap, reality-grounded, not self-reinforcing)

For each elicitation episode, log a few facts. They are agent-observable, but each
compares a **prediction against what reality turned out to be** — so aggregating
them does not reinforce the agent's priors.

```text
episode: <task id / short label>       date: <YYYY-MM-DD>
mode: precision | speed
questions_asked: N
per_question:
  - q: "<the question>"
    predicted_default: "<what I'd have assumed if I hadn't asked>"
    actual_answer: "<what the user said>"
    diverged: yes|no          # did the answer differ from my default?
    changed_plan: yes|no      # did it actually change what I built?
assumptions_logged: M
assumptions_falsified_later: K   # of the ones I chose NOT to ask about
user_short_circuited: yes|no     # "just proceed" / ignored / impatient
deliverable: accepted | reworked | unknown
notes: "<one line>"
```

Read the aggregate two ways:

- **Over-asking** ⇔ low **divergence rate** (answers mostly matched my defaults)
  or low `changed_plan` rate, and/or frequent `user_short_circuited`. → tighten
  the cap, raise the impact×uncertainty bar, prefer answer-with-assumptions.
- **Under-asking** ⇔ high `assumptions_falsified_later` or high `reworked` rate.
  → the entry pass is missing high-impact ambiguities; probe more (or better).

A question whose answer matched your default was wasted; a wrong assumption you
never surfaced is a miss. Good calibration sits between the two, not at "asked
the most questions."

Store logs in the dev workspace (`dev/docs/feedback/`), not in the shipped
artifact. Until enough real episodes accumulate, this is guidance to follow, not
a dataset to trust — say so rather than over-reading three data points.

## What improvement looks like

Changes to the rubric/cap/triggers are justified by a **pattern in user-anchored
evidence** (1–4 above) or a clear calibration signal from the log — cited in the
change (ADR or CHANGELOG entry). "The agent felt it asked good questions" is not
a justification for this skill. See
[`../../dev/docs/adr/0003-user-anchored-evaluation.md`] for the standing decision
(dev-only path; not shipped).
