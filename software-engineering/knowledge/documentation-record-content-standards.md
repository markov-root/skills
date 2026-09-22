---
knowledge:
  version: 1
  id: documentation-record-content-standards
  summary: Distill the per-role content-quality standard for the seven record roles so an author knows what a good instance actually contains, not just its shape.
  routes: [documentation-repository-organization]
  sources: [src-documentation-practices, src-documentation-structures]
---

# Record-role content standards

> **Purpose:** State the content-quality standard for the seven record roles (task, ADR, audit,
> research, lesson, handoff, plan) — the telos each one serves, the properties that make its
> content good, the test that discriminates a good record from a well-formed empty one, and a
> compact exemplar/anti-example for each.
>
> **Read this when:** authoring or reviewing a record role; choosing whether an artifact earns its
> role and authority; sharpening the quality bar an author is given before writing.

Every record below can be **well-formed yet content-empty**. Passing a structural contract
(correct role, dates, relationships) proves little about whether the record earns its authority.
Read this guidance alongside [`documentation-structure.md`](documentation-structure.md), which fixes
the folder and lifecycle shape; these sections say what the content must be.

## The shared floor

A record's quality has two independent axes:

- **Well-formedness** — does it satisfy its structural contract (role, lifecycle, metadata,
  relationships, currentness)?
- **Warrant and content quality** — does it earn this role and authority, is its reasoning honest
  and useful, and does it produce the role's distinct reader outcome?

A document can pass either axis and fail the other. **Structure hard, warrant loud**: shape is
mechanically checkable, but content judgments stay irreducible. Verifiable proxies are necessary-not-sufficient — a proxy pass is never semantic approval and never a reason to skip the content judgment.

The role contract below is the authoring signal: one section per role, each stating the role's
purpose, its content-quality properties, a discriminating test, and an exemplar/anti-example pair.
The template quality bars point here so the author meets this standard at the point of writing.

## Task

**Telos:** Define a bounded work outcome and the acceptance contract by which completion is
independently verified.

**Content-quality properties:**
- Acceptance criteria are objective and independently judgeable — a reviewer can say "done" from
  them without the author.
- Scope and non-goals are explicit, so the work boundary is honest.
- Completion evidence is criterion-linked: pointers to the artifacts (PRs, test runs, logs) that
  prove each criterion.

**Discriminating test:** Can a reviewer decide "done" from the criteria and evidence without
undocumented proof or author clarification?

**Exemplar:** A race-condition fix whose "done when" names the concrete behavior (no duplicate
record under concurrent identical submissions) and a parallel integration test that proves it under
load; its non-goal is the unrelated queueing refactor; its evidence links the passing test run and
merged PR.

**Anti-example:** "Fixed the race condition in the payment service. See PR #1234. Tests passed."
There are no pre-stated criteria, no scope bounds, and no artifact that proves the acceptance
contract — a redundant commit message wearing task authority.

## ADR

**Telos:** Preserve authorized counterfactual memory: why one consequential choice defeated
credible alternatives under named conditions.

**Content-quality properties:**
- One authorized decision at the altitude of its consequences, with named decider and authority.
- A contestable (not curated) premise set — requirements, constraints, risks, affected parties,
  contrary premises — that made the choice hard.
- Genuine counterfactual alternatives receiving the same criteria as the chosen option.
- A visible trade-off: the choice follows from evidence available at decision time, not a
  plausible post-hoc story; reconstruction is labelled.
- Consequences as an obligation ledger (benefits, costs, transferred risks, dissent), not a
  victory paragraph.
- Bounded uncertainty: material unknowns visible, with the evidence that would reopen the choice.

**Discriminating test:** Can a competent future reader trace the actual authorized choice to
contemporaneous evidence, see the strongest viable rival and contrary or omitted premise, and name
a decisive driver whose change would justify a different choice?

**Interpreting status, scope, and timing.** Whether a decision record constrains current work is a
separate question from how well it is written. Read the operative choice, its conditions, scope,
and authority — do not classify by keyword:

- **Proposed** = adds no new operative authority: it neither binds anyone nor, by itself, changes
  what governs. It also does **not** erase an existing accepted baseline — the prior accepted
  decision still governs the work it covered until a successor is accepted or the baseline is
  explicitly superseded. Treat a proposal as input and drive it to acceptance or rejection when
  the choice matters.
- **Accepted** = operative within its bounded scope. Scope and conditions beat keyword matches.
- **"Deferred" is ambiguous** — it can be a scheduling fact or a durable exclusion ("we do not
  ship X until Y"). Which one it is comes from the operative choice and its stated conditions,
  not from the word.
- **Implementation is not acceptance, and acceptance is not implementation.** An accepted decision
  with deferred implementation is still accepted; an implemented change is not automatically an
  accepted decision. A durable policy and its delivery date are separate facts.
- **A mis-filed scheduling commitment still constrains those who accepted it.** If an accepted
  record is really a schedule in the wrong container, recommend relocating future work to task
  state — do not silently revoke the existing commitment or rewrite the historical body.
- **Supersession governs the replaced scope only.** Scope the old record left unaffected persists
  per its own terms; check effective dates and reconcile contradictory status metadata through
  evidence rather than picking a state by guess. Citing a superseded record against its successor
  is an error; so is reading the successor as covering more than it replaced.

Post-authoring semantic review asks: *What is the operative choice today, within what scope and
authority? Is a date or deferral here scheduling or a durable rule? Does an accepted baseline
still govern this work, and what would change it?* A date change alone triggers rescheduling in
task state, not automatic escalation into decision authority.

Whether a decision deserves a record at all is routed beforehand by the worthiness table in
[`documentation-structure.md`](documentation-structure.md).

**Exemplar:** A record whose alternatives could genuinely have been chosen, whose chosen mechanism
answers the named failure, whose authority is grounded in an accepted transition, and whose revisit
condition is an actual observable that would challenge a decisive premise — not a deferral.

**Anti-example:** A deferral dressed as a decision: "plan migration separately" is a schedule
wearing permanent decision authority. A perfectly filled template stays bad if it compares only
scheduling variants and fails to isolate the actual durable rule.

## Audit

**Telos:** Establish a dated, bounded evaluation against an objective baseline, including the
limits of what was examined.

**Content-quality properties:**
- A method and scope that bound what was examined, with what was not tested stated explicitly.
- Findings separated from recommendations, and proportionate to the observations.
- Findings derived from method/evidence, with the proof boundary made plain.

**Discriminating test:** Can a reviewer derive the findings from the method and evidence, and
understand exactly where the proof stops?

**Exemplar:** A dated audit whose scope lists the examined population and counts, whose method
precedes its conclusions, and whose limitations state what was not tested — the cleanest
reading is the honest one, not the flattering one.

**Anti-example:** Findings selected to manufacture a clean result — scope and omissions narrowed to
hide what was not examined rather than stated.

## Research

**Telos:** Reduce a consequential uncertainty through a reproducible path from question and method
to bounded conclusion.

**Content-quality properties:**
- A decision-relevant question stated up front, and a method that another investigator can follow.
- Sources and claims typed by strength, with access dates and reproducible provenance.
- Rival/null/conflict/currency records retained, so the strongest rival and what would reverse the
  ordering are visible.

**Discriminating test:** Can another investigator reproduce the selection and reasoning, derive the
strongest rival from retained evidence, explain why it loses, and name what would reverse the
ordering?

**Exemplar:** A record whose question is consequential, whose method and sources let a peer
reproduce the reasoning, whose rival is honestly presented and defeated on the evidence, and whose
conclusion is bounded to the uncertainty actually reduced.

**Anti-example:** A selection curated to produce the desired conclusion — rivals dropped or
weakly steelmanned, confidence overstated relative to the design, and no retained evidence to
challenge the ordering.

## Lesson

**Telos:** Turn experience into a bounded, retrievable change in future prediction, interpretation,
decision, or behavior.

**Content-quality properties:**
- An actionable inference with a mechanism beyond simple chronology.
- Provenance and maturity (originating event, status) recorded.
- A retrieval cue, applicability boundary, and counter-signal so the inference transfers without
  over-application.

**Discriminating test:** Does it change a competent reader's future judgment while preventing
transfer to a merely similar-looking case?

**Exemplar:** A lesson whose inference adds a durable mechanism (not "X happened, then Y"), whose
use-when / do-NOT-use-when boundary is explicit, and whose cue fires for the right case and is
guarded against the similar-looking one.

**Anti-example:** A lesson broad enough to apply anywhere, which thus changes nothing: an
over-generalized inference with no boundary and no counter-signal.

## Handoff

**Telos:** Transfer continuation state for one work boundary so a cold successor can resume safely
from evidence.

**Content-quality properties:**
- First action resolves from current state and is safe.
- Done/next/blocked work separated, owners and done-when conditions recorded, material evidence
  linked.
- Limits and current authority recorded; pointers resolve to live authority, not stale state.

**Discriminating test:** Can a cold reader take the first correct evidence-aware action without
interviewing anyone or selecting stale authority?

**Exemplar:** A handoff whose first action resolves from the current state, whose done/next/blocked
work is separated, and whose evidence and owner links resolve to live authority — a successor
resumes safely from the document alone.

**Anti-example:** A handoff that reads as a memory dump — pointers to stale authority, state and
evidence assignments unclear, and no safe first action — so a cold reader cannot proceed without
interviews.

## Plan

**Telos:** Choreograph complex work and preserve a bankable execution frontier through an
append-only progress record.

**Content-quality properties:**
- Dated progress log; banked versus uncompleted state separated.
- An unambiguous resume point, with contingencies/rollback proportional to risk.
- Validation signals for critical steps.

**Discriminating test:** If execution stops anywhere, can a successor identify what is banked, what
remains, and the exact next safe action?

**Exemplar:** A plan whose progress log is dated and append-only, whose banked state is clearly
separated from uncompleted work, and whose current-state and next-steps let a successor resume at
any stopping point from evidence rather than the conversation.

**Anti-example:** A plan that reads as a work list — no dated banked/uncompleted boundary, no
resume point — so after an interruption a successor cannot tell what actually completed.

## Meta-Question

What does the author of a record role need to know that shape validation alone will not tell them?
For each role the answer is the discriminating test above: the one question that separates a
well-formed record from one that earns its role. Use the template quality bar to surface that test
at the point of writing.