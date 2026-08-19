---
summary: When and how to re-confirm comprehension mid-task — evidence-triggered, single-question, never on a timer.
status: standing
role: knowledge
---

# Re-verification — keeping comprehension honest without nagging

Re-verification is the "occasional" half of this skill. It exists because a task
frame locked at entry can quietly go stale: an assumption proves false, the work
reveals a fork the user did not anticipate, or scope creeps past the agreed
boundary. Left unchecked, you deliver something that answers the _old_
understanding.

The failure mode on the other side is worse for trust: re-asking on a cadence,
or re-opening the whole interview at every checkpoint. That is just always-on
grilling. Re-verification must be **rare, triggered, and surgical.**

## Fire only on a trigger

Re-verify when — and only when — one of these is observed:

1. **A logged assumption is contradicted.** Evidence from the repo, a tool
   result, or the user's reaction falsifies something in the assumption log.
2. **Scope drifts past the frame.** The work now touches subsystems, contracts,
   or effort well beyond the locked in/out-of-scope boundary.
3. **A genuine fork appears.** Two materially different continuations exist and
   the choice changes the outcome (this is Kiro's "gap/conflict detected →
   stream a clarification" pattern).
4. **Cost or risk jumps.** The chosen path now implies spend, irreversibility,
   or a security/privacy surface the user has not sanctioned.

No trigger → keep working on the locked frame. Do **not** schedule check-ins.

## Keep it to one question

A re-verification is one surgical question about the single thing that changed —
with your recommendation attached. Name what you now know, what it contradicts,
and the choice it forces. Do not re-derive the whole task frame; the assumption
log already holds everything else.

```text
While implementing X I found Y, which contradicts the assumption that Z.
That means either (a) <continue as framed> or (b) <adjust>.
I recommend (a) because <reason>. Proceed, or switch to (b)?
```

## Update the frame after

Whatever the answer, update the task frame and assumption log so the record
stays truthful and the next checkpoint (if any) starts from current reality.
Silent re-scoping is a comprehension failure even when the result is good.

## Relationship to the entry pass

Entry comprehension is broad and one-time; re-verification is narrow and
event-driven. The
[`elicitation-rubric`](elicitation-rubric.md) assumption log is the bridge — it
is precisely the set of things a trigger can falsify. A skill that skips the log
cannot do cheap re-verification, because it has nothing to check new evidence
against.
