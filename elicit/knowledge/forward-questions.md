---
summary: The task-exit pass — 2-3 forward-looking questions and the named techniques that generate them.
status: standing
role: knowledge
---

# Forward-looking close — pointing at the next step

After a deliverable lands, the highest-leverage thing you can do is hand the user
a **specific** next direction to react to, rather than "anything else?". This is
a _post-generation elicitation_ pass — the same move BMAD calls "advanced
elicitation": a structured second look once concrete output exists.

## The contract

- Ask **2–3** forward-looking questions, offered not forced.
- Each must be **specific and grounded in the delivered artifact** — a real fork
  the user now faces, not a generic "want more?".
- Attach a recommendation or a default direction where you have one.
- One tap should be enough to choose; use the structured-question primitive.

## Directions worth asking about

- **Deepen:** take the current thing further along the same axis (more rigor,
  more coverage, production-hardening).
- **Widen:** the adjacent capability this unlocks or naturally pairs with.
- **Harden:** the failure modes, edge cases, or scale limits to address next.
- **Integrate:** where this now connects to the rest of the user's system.
- **Validate:** what evidence would confirm this was the right thing to build.

## Named techniques to generate them

Borrow the classic elicitation moves — each surfaces a different kind of next
question:

- **Pre-mortem:** "Assume this fails in a month — what was the cause?" → the
  hardening question.
- **Inversion:** "What would make this the _wrong_ thing to have built?" → the
  validation question.
- **Socratic laddering:** ask _why_ one level up ("what is this in service of?")
  → the widen/integrate question.
- **Stakeholder framing:** "Who else touches this, and what do they need?" → the
  integrate question.
- **Impact × uncertainty (again):** rank the open forks the same way the entry
  pass ranks ambiguities; ask about the top 2–3.

## Keep it honest

If there is no meaningful next direction, say so and stop — a manufactured
follow-up is as much noise as an unnecessary entry question. The forward pass is
value when it is real, telemetry when it is reflexive.
