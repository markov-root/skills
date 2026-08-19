---
summary: How to draw out tacit/unstated knowledge from a user without distorting it, and how to find the real task behind the stated request.
status: standing
role: knowledge
---

# Eliciting latent knowledge

Users "know more than they can tell" (Polanyi). The goal, constraints, and
reasons behind a request are often **tacit** — the user can act on them but can't
recite them, especially a novice or an imprecise prompter. The job is to convert
that tacit knowledge into an explicit task frame **without putting words in their
mouth**. First verbal answers are rarely complete (Nonaka's socialization →
externalization); expect to draw it out through examples and dialogue.

## Ask for concrete episodes, not abstractions

Tacit knowledge surfaces in specifics. Prefer:

- "Walk me through the **last time** this came up — what happened first?"
- "Show me an **example** of a good result, and a bad one."
- "What would **count as done**?"
- "What's the **hardest part**, and what makes it hard?"

over "what are your requirements?" — which asks the user to do the abstraction you
should do for them.

## Technique catalog (chat-adapted)

The highest-leverage techniques for a conversational agent, from requirements
engineering and cognitive task analysis. Use a few, not all.

| Technique                               | Surfaces                                      | Chat adaptation                                                                                                       |
| --------------------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Semi-structured interview**           | goals, vocabulary, priorities, fears          | a guide of intents plus adaptive probes                                                                               |
| **Laddering** ("why does that matter?") | values, success criteria, hidden tradeoffs    | "you said speed matters — what does speed make possible?"                                                             |
| **Scenarios / use cases**               | real sequence, exceptions, success/failure    | "if it goes perfectly, what are the steps? now the two common ways it derails?"                                       |
| **Critical Decision Method**            | cues, judgment, rejected alternatives         | "tell me about a time this was unusually hard — at the key moment, what did you notice and what did you rule out?"    |
| **Think-aloud / protocol**              | attention, hesitation, local rationale        | "narrate what you're doing / deciding as you go"                                                                      |
| **Card sort / concept map**             | categories, terminology, relationships        | "here are the pieces you mentioned — which belong together, and what would you call the group?"                       |
| **Repertory grid**                      | implicit evaluation dimensions                | "name a good, a bad, and a typical example — how are two alike and different from the third?"                         |
| **Teach-back**                          | misunderstandings, false agreement            | "here's my summary — correct it as if explaining to a colleague"                                                      |
| **Unstated-requirement probe**          | edge cases, workarounds, missing stakeholders | "what would go wrong if…?", "who else touches this?", "what do people actually do that the official way doesn't say?" |

Default sequence: intent interview → scenario walkthrough → laddering (sparingly)
→ critical-incident probe → optional sort/map → **teach-back to validate**.

## Question design that doesn't distort (anti-bias)

Adapted from survey methodology (Pew, AAPOR) and expert-elicitation protocols
(SHELF, Cooke, Delphi):

- **Open-first funnel:** start broad ("what prompted this?"), then narrow to
  goals, constraints, success criteria, examples, options.
- **Neutral wording:** never "wouldn't it be better if…?"; ask "what tradeoffs
  matter?" and "what would make this unacceptable?"
- **Order control:** ask general intent _before_ offering categories or a
  solution, or you prime the answer.
- **Anti-acquiescence:** avoid agree/disagree prompts; offer balanced options
  plus "neither / not sure / doesn't apply."
- **Preserve the user's words; label inferences as hypotheses** ("my read is X —
  right?") and confirm before acting.
- **Elicit before discussing** (SHELF): get the user's own answer before you
  suggest reasons, so you don't anchor them.
- **Multiple stakeholders?** collect views independently before reconciling
  (Delphi) so a loud voice doesn't dominate.

## Find the real task behind the request

The stated request is often an attempted solution, not the goal.

- **XY problem:** "is this the goal, or something you're trying in order to reach
  a bigger goal?" Ask about the ultimate outcome.
- **Five Whys:** climb from symptom to cause/outcome — but stop before it feels
  like an interrogation.
- **Jobs To Be Done:** "when **_, I want _**, so I can \_\_\_" — include the
  functional, social, and emotional job.
- **Means-ends:** name current state, desired state, the gap, and the next
  action that most reduces it.

When laddering or an XY check reveals a better path to the user's actual goal,
surface it as a _permissioned_ suggestion (see
[`teaching.md`](teaching.md)) — don't silently substitute your own goal for
theirs.
