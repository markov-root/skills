---
knowledge:
  version: 1
  id: code-review
  summary: Review code for consequential correctness, design, evidence, and maintainability while keeping comments precise, actionable, and proportionate.
  routes: [review-audit, refactor-rewrite]
  sources: [src-review-conventions]
---

# code-review.md — The Discipline of Reviewing Code

> **Purpose:** Reference for reviewing code well — what to look for, what to ignore, how to leave comments that move work forward instead of stalling it, and how to balance correctness, design, and human cost. Also covers what authors owe reviewers and the cultural practices that make review valuable.
>
> **Read this when:** about to review a PR; about to open one; designing a review process; the team's PRs are stuck for days; reviews are arguments; reviews are rubber stamps.
>
> **Invariant (review integrity):** Never claim to have reviewed evidence you did not inspect, and
> never disguise personal preference as a correctness or policy requirement. Automated formatting
> should own the rules it actually enforces; language-native style policy and project instructions
> own the rest.

---

## The Premise

> _A code review is a conversation between authors and reviewers, with the code in the middle._

Three things a review is for:

1. **Catching defects** the author missed.
2. **Designing better** by surfacing alternative approaches before they're entrenched.
3. **Sharing knowledge** — the second reader is the second person who understands the change.

Two things a review is _not_ for:

1. Demonstrating the reviewer's superior taste.
2. Re-litigating decisions already made (an ADR, a documented convention, a settled discussion).

The senior engineer's question on entering a PR: **"What is this trying to do, what's the smallest change that does it, and what risks does it introduce?"** Not: "what would I have written?"

### Classify the process before applying it

Review rules are not one universal queue, SLA, or reviewer count:

| Claim type          | Rule, scope, trade-off, and counterexample                                                                                                                                                                                                                                                                                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Invariant**       | A review decision must be truthful about what was inspected, unresolved safety/privacy/integrity risks must not be waved through, and any legally or organizationally required separation of duties must be honored. The trade-off is delay; a typo-only change outside such a control does not acquire a second-review requirement merely because a high-risk repository has one elsewhere. |
| **Project default** | Match review depth and independence to consequence, reversibility, novelty, and uncertainty; record whether feedback blocks. This spends attention where it changes outcomes. A tiny authorization change can require specialist review while a large deterministic generated diff may need generator evidence rather than line-by-line reading.                                             |
| **Heuristic**       | Response targets, reviewer counts, checking out and running a change, new-test expectations, and diff-size signals help a project design its process. They are not laws. A solo maintainer, a safety-regulated team, an emergency fix, and a high-volume generated-code repository need different controls.                                                                                  |

Repository policy owns approval authority, required checks, response expectations, and ownership.
This reference supplies review judgment; it does not create an SLA or branch rule.
Unless a passage is labeled otherwise, recommendations below are **project defaults** for
collaborative change review and yield to repository policy; examples, smell lists, and diagnostic
tables are **heuristics**, not inherited requirements.

---

## The Author's Responsibilities

A reviewable PR isn't an accident. The author shapes it.

| Author duty                        | Detail                                                                                                          |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Self-review first**              | Re-read the diff before requesting review; fix issues you can detect before spending reviewer attention         |
| **Bound the change**               | One coherent concern; size, generated/move content, coupling, and risk determine whether splitting helps        |
| **Write a description**            | What, why, how, testing, risks, rollback — see [GIT_AND_VERSIONING](git-and-versioning.md) PR template          |
| **Make it easy to understand**     | Order the commits to tell a story; refactors before features ([REFACTORING](refactoring.md))                    |
| **Pre-empt the obvious questions** | "I considered X and rejected it because Y" in the description                                                   |
| **Note non-obvious decisions**     | Comments on the diff to call attention; not in the code, but in the PR                                          |
| **Run the checks**                 | Run the adopted checks applicable to the change; explain unavailable, skipped, or intentionally absent evidence |
| **Respond to comments**            | Engage with each; don't silently push commits                                                                   |
| **Don't take it personally**       | The reviewer is reviewing the code, not the author. (Hold this in both directions.)                             |

**Heuristic:** Review effectiveness generally falls as semantic scope and interaction count grow.
Large generated changes, mechanical moves, or atomic migrations differ from a large novel-logic
diff. Separate mechanical/semantic work, provide navigation, and split only where intermediate
states remain coherent.

---

## The Reviewer's Responsibilities

| Reviewer duty                            | Detail                                                                                                                                   |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Read what the change is trying to do** | Description, linked issue, ADR if any                                                                                                    |
| **Read the diff carefully**, not skim    | Skim reviews catch little and miss many semantic defects                                                                                 |
| **Exercise the behavior when useful**    | Run or inspect the smallest evidence that can expose the material risk; do not execute generated or mechanical output merely as ceremony |
| **Look at the evidence**                 | Tests, proofs, generated diffs, manual observations, or contract checks should support the claims the change makes                       |
| **Look at the _not_ changed**            | What's missing? Tests? Docs? Migration? Changelog?                                                                                       |
| **Comment with care**                    | Specific, kind, actionable; mark severity (see below)                                                                                    |
| **State the disposition clearly**        | Approve, request changes, abstain for missing expertise, or leave explicitly non-blocking feedback                                       |
| **Respond within project expectations**  | Optimize feedback latency without inventing a universal hours-or-days SLA; surface capacity constraints early                            |
| **Distinguish opinion from concern**     | "I'd write this differently" ≠ "this is wrong"                                                                                           |
| **Don't repeat the linter's job**        | If the formatter handles it, don't comment                                                                                               |

---

## The Severity Ladder for Review Comments

Review comments live on a spectrum. Most teams informally use a few levels; **make them explicit**. A common scheme:

| Prefix / label      | Meaning                                                    | Author's response                   |
| ------------------- | ---------------------------------------------------------- | ----------------------------------- |
| `blocking:` or 🛑   | Must be addressed before merge                             | Required                            |
| `question:` or ❓   | Reviewer doesn't understand; needs clarification           | Answer (in PR or in code)           |
| `suggestion:` or 💡 | Reviewer thinks there's a better way; author may push back | Considered; may decline with reason |
| `nit:` or 🪶        | Cosmetic; reviewer wouldn't block on it                    | Author's choice                     |
| `praise:` or ✨     | Positive note                                              | Read and feel good                  |
| `thought:` or 💭    | Sharing context; not a request for change                  | Acknowledge                         |

**The point of the labels** is to remove ambiguity. Without them, a "have you considered..." comment is both a polite suggestion and a hidden veto, and the author can't tell which. With labels, a `nit:` is unambiguous; a `blocking:` is unambiguous; nobody is guessing.

**External convention/example:** [Conventional Comments](https://conventionalcomments.org/)
illustrates this kind of explicit label. **Project default:** use it or another
documented scheme when ambiguity is recurring; a small synchronous team may communicate severity
without prefixes, while a cross-time-zone or compliance-sensitive project benefits from an
explicit recorded disposition.

---

## What to Look For — In Order

A structured review can use this order. Depth and number of passes are **heuristics** selected from
risk, change shape, and available expertise; a low-risk mechanical diff and a small authorization
change warrant different attention.

### 1. Does it do the right thing?

- **Is the stated purpose actually what the user / business wants?** (Sometimes the PR description reveals a misunderstanding.)
- **Does the code do what the description says?** Is there _more_ — scope creep?
- **Edge cases** — empty, null, zero, max, negative, Unicode, time zone, currency, locale.
- **Error paths** — what happens when this dependency fails? When the input is invalid?
- **Idempotency** — is this safe to retry? See [API_DESIGN](api-design.md) / [ERROR_HANDLING](error-handling.md).
- **Backward compatibility** — what does this break?

### 2. Is it correct?

- **Logic.** Walk through the algorithm with a sample input.
- **Off-by-one.** Inclusive vs exclusive boundaries; first/last item handling.
- **Null / Optional handling.** Where can None enter?
- **Concurrency.** Two requests at once — what happens? ([CONCURRENCY](concurrency.md).)
- **Data integrity.** Constraints, transactions, idempotency, sources of truth ([DATA](data.md)).
- **Security.** Input validation, authn/authz, injection vectors ([SECURITY](security.md)).
- **Privacy.** What data is touched, logged, transmitted, retained ([PRIVACY](privacy.md)).

### 3. Is it readable?

- **Names.** Do they say what the thing does?
- **Structure.** Does the code's shape match what it does?
- **Comments and API docs.** Do they preserve a contract, invariant, non-obvious mechanism,
  protocol citation, generated boundary, or operational constraint? Pure syntax restatement is a
  smell, but “why, not what” is too narrow; see [DOCUMENTATION](documentation.md).
- **Length/cohesion.** Does the unit mix responsibilities or hide control flow? Screen height is only
  a review signal; splitting can make a cohesive algorithm harder to read.
- **Cohesion.** Does this module / function do one thing?

### 4. Is it well-designed?

- **Coupling.** What does this change drag along? ([ARCHITECTURE](architecture.md).)
- **Abstraction level.** Is the abstraction earning its keep, or speculative? ([REFACTORING](refactoring.md).)
- **Single Responsibility.** Does this class / function have one reason to change? ([PRINCIPLES](principles.md).)
- **Boundaries.** Does this respect the project's layering?
- **Reusable parts.** Did the author solve a problem the codebase already solved?

### 5. Is the changed claim supported?

- **Project default:** Add or update evidence for behavior whose risk or contract changed. A bug fix
  often deserves a regression test that fails before the fix; a generated refresh may instead need
  deterministic regeneration and drift evidence; a comment-only clarification may need link or
  documentation validation.
- **Tests are at the right level** and use a credible oracle — see [TESTING](testing.md).
- **Challenge the evidence:** Would it fail with the defect present? What claim can it not establish?
- **Heuristic:** A surprising absence of test changes can prompt investigation. Test/source line
  ratios are not quality measures: a one-line authorization change may need many scenarios, while a
  large rename can rely on existing compile and behavior checks.

### 6. Is it operable?

- **Observability** — logs, metrics, traces at meaningful boundaries ([OBSERVABILITY](observability.md)).
- **Failure modes** — timeouts, retries, fallbacks where applicable.
- **Configuration** — new config declares its type, authority, precedence, validation phase, and
  documentation surface; `.env.example` applies only when that file is the adopted interface
  ([CONFIGURATION](configuration.md)).
- **Migration / rollout** — schema, feature flag, deploy order.
- **Rollback story** — can we revert this safely?

### 7. Hygiene

- **Lockfile / generated files** — only the expected ones changed.
- **Docs** — README, CHANGELOG, ADR, runbook updates as appropriate.
- **Dead code** — anything left over? `TODO`s with no follow-up?
- **Secrets** — none in the diff.

---

## The "Diff vs File" Trap

Reviewers see the diff. Bugs often live outside the diff:

- A function called with new argument shape — the caller compiles but the callee's invariant is now wrong.
- A new field added to a model — all serialisers and forms now need to handle it.
- A removed parameter — every caller's site needs updating.

**Read the surrounding context.** When the diff is a small change in a large file, read the whole function, often the whole file. Cross-reference callers.

---

## When to Block vs When to Suggest

The reviewer's hardest decision is whether to block merge or let it go with a note.

**Block when:**

- Correctness defect (any of the items above).
- Security or privacy risk.
- Data loss or corruption risk.
- Breaking change without explicit acknowledgement.
- Missing critical evidence for a consequential changed behavior or contract.
- Significant scope creep (force a re-scoping conversation).
- The change is irreversible _and_ the reviewer has reason to doubt the design.

**Don't block on:**

- Personal style preference.
- Alternate design that's also reasonable.
- "We might extend this later in a way that..."
- Things the formatter / linter doesn't catch but could.
- Refactors of pre-existing code that wasn't touched.

**A blocking comment imposes a cost on the author.** Use it deliberately. Lukewarm "I'd prefer X" disguised as a block is a process bug — either it's important enough to block, or it isn't.

---

## Comment Hygiene

Implementation comments are only one documentation form. **Project default:** place information at
the narrowest durable authority that its consumers will actually see, using the language's native
doc-comment and module conventions where available. The trade-off is proximity versus duplication:
nearby comments help a maintainer in the code, while a second copy of a schema or runbook silently
drifts. A protocol citation beside a workaround and a generated API reference derived from the
schema can both be correct.

| Role                            | What a reviewer should require                                                                                                                           | Staleness control and counterexample                                                                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Implementation comment**      | Explain a surprising mechanism, rejected simpler path, or compatibility quirk—not syntax already expressed clearly by the code.                          | Change or remove it with the mechanism. A clear bit-mask operation may need a protocol citation even though it describes “what.”                                    |
| **API documentation/docstring** | State observable inputs, outputs, errors, ownership/lifetime, side effects, thread safety, and compatibility where they are part of the public contract. | Keep it with the public declaration or canonical schema and verify generated output. An obvious private helper does not need a ceremonial docstring.                |
| **Module/file documentation**   | Explain responsibility, boundary, public surface, and load-bearing dependency direction when the language/repository does not make them evident.         | Review when files move or ownership changes. A tiny single-purpose module whose package documentation already owns this need not repeat it.                         |
| **Invariant**                   | Name the invariant, its scope, why it matters, and the authority that establishes it; prefer executable enforcement where feasible.                      | Review when the enforcing code, schema, or policy changes. A comment cannot override a database constraint or protocol specification.                               |
| **Algorithm/protocol**          | Cite the algorithm, specification/version, units, ordering, complexity, or deliberate deviation needed to maintain it safely.                            | Re-verify volatile external behavior at its trigger. Straightforward standard-library use needs no tutorial in the source.                                          |
| **Generated code**              | Declare the source, generator/version where needed, regeneration command, and whether a maintained patch layer exists.                                   | Review the generator and representative or risk-bearing output; do not demand hand-edits to disposable output. See [REPOSITORY STRUCTURE](repository-structure.md). |
| **TODO/FIXME**                  | State the deferred outcome, owner or discoverable tracker, and trigger/expiry when delay creates risk.                                                   | Remove it when resolved or obsolete. A local dated TODO can be enough in a small repository; a security debt item may require governed tracking.                    |
| **Operational constraint**      | Record limits, rollout ordering, kill/rollback conditions, permissions, and the runbook/incident evidence that makes the constraint actionable.          | Test or rehearse where consequence warrants it. Do not bury an organization-wide deployment rule only inside one function.                                          |

For full lifecycle and placement guidance, [DOCUMENTATION](documentation.md) is canonical. Repository
layout and generated/vendor boundaries belong to [REPOSITORY STRUCTURE](repository-structure.md);
language-native policy owns syntax and tool-visible tags. Review comments should point to those
authorities instead of creating a competing contract in the thread.

The bad comment vs the good comment:

| Bad                  | Good                                                                                                                                            |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| "This is wrong"      | "This drops the timezone; the test for DST won't pass"                                                                                          |
| "Why?"               | "What's the reason for swallowing the exception here? I want to understand the intent — happy to merge if there's a reason this is unreachable" |
| "Refactor this"      | "suggestion: the three branches share the validation logic; could be a helper. Non-blocking"                                                    |
| "Tests?"             | "I don't see a test for the rate-limit-hit path. Could you add one? blocking"                                                                   |
| Demanding            | Inquisitive when uncertain, direct when certain                                                                                                 |
| Reviewing the author | Reviewing the code                                                                                                                              |

**Be specific.** "This isn't great" is not a useful comment. "This locks for the duration of the HTTP call; if upstream is slow we'll back up the whole pool" is.

**Propose a fix when you can.** Suggested-change blocks in GitHub/GitLab make this trivial. The author doesn't have to guess at what you wanted.

**Praise non-obvious good choices.** A reviewer who only complains becomes background noise; reviews that surface and validate good work strengthen the team's standards.

---

## The Author's Pushback — Healthy

A review is a conversation. The author's job is not to obey every comment.

| Author response pattern                                   | Healthy? |
| --------------------------------------------------------- | -------- |
| Fixes the issue, replies "fixed"                          | Yes      |
| Asks a clarifying question                                | Yes      |
| Disagrees with reasoning, explains                        | Yes      |
| Suggests a compromise                                     | Yes      |
| Pushes back: "Out of scope for this PR; tracked at #1234" | Yes      |
| Silently pushes a commit and ignores the comment          | No       |
| Caves to every suggestion without engaging                | No       |

The author owes the reviewer an explanation when they disagree. The reviewer owes the author an explanation when they insist. **Resolution comes from arguing the principle, not the people.**

---

## Asynchronous Review vs Synchronous

| Mode                                      | When                                                                       |
| ----------------------------------------- | -------------------------------------------------------------------------- |
| **Asynchronous (common project default)** | Independent work where a durable record and time-zone flexibility matter   |
| **Synchronous (pair review / call)**      | Big PRs; difficult subject matter; learning opportunity; when async stalls |

When an async exchange stops producing new information, consider a synchronous discussion and
record the resulting decision. The trade-off is scheduling and loss of an automatic transcript;
async remains appropriate when participants cannot meet or the decision needs careful written
review.

---

## Reviewer Capacity and Independence

**Project default:** Choose required independence and expertise from consequence and governing
policy, not a fixed headcount.

| Context                                                                | Proportionate review shape                                                                                                                   | Trade-off / counterexample                                                                                                                    |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Safety-, security-, privacy-, finance-, or integrity-critical boundary | Named specialist or control owner plus any required independent approver; use multiple reviewers only when their roles add distinct evidence | Extra approvers add latency and can diffuse responsibility. A risky one-line permission change deserves more scrutiny than its size suggests. |
| Ordinary team change                                                   | One capable reviewer or pair review is a common default; rotate to spread knowledge                                                          | A second generalist may add less value than one domain expert.                                                                                |
| Solo or very small project                                             | Structured self-review, delayed second pass, automated checks, and targeted external review for one-way doors                                | Pretending independence exists produces false assurance; a typo or reversible local script may be responsibly self-merged.                    |
| Incident response                                                      | Time-bounded pair/specialist review where available, followed by explicit post-incident review for deferred evidence                         | Waiting for normal quorum can prolong harm; emergency authority must not become the everyday path.                                            |
| Mob/pair development                                                   | Continuous review can satisfy the intent when project policy recognizes it and decision evidence is retained                                 | Attendance alone is not independent approval where separation of duties is required.                                                          |

### Scenario calibration

| Scenario                   | Focus and suitable evidence                                                                                                                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **High-risk small diff**   | Trace authorization, state, failure, and rollback end to end; require relevant specialist/policy approval and targeted negative tests. Small size does not lower consequence.                                        |
| **Low-risk change**        | Verify scope, rendered/observable result, and adopted lightweight checks; avoid imposing a full local runtime exercise on a reversible copy edit.                                                                    |
| **Generated change**       | Review source inputs, generator identity, deterministic regeneration/drift, and representative or security-sensitive output; avoid line-by-line ritual over disposable output.                                       |
| **Mechanical move/rename** | Separate it from semantic changes when coherent; rely on move-aware diff, build/import/link checks, and caller search. New behavior tests are unnecessary when existing evidence credibly covers unchanged behavior. |
| **Public API change**      | Inspect consumer impact, schema/contract diff, compatibility matrix, migration/deprecation path, examples, and failure semantics—not only the implementation diff.                                                   |
| **Stacked changes**        | State dependencies and the review base for each layer; keep each stack item coherent, rebase evidence when earlier layers change, and do not approve the top as if its base were already accepted.                   |

---

## Specific Smells Worth a Comment

(From senior-reviewer instincts — the things that trigger automatic attention.)

| Smell                                                                     | Why it deserves attention                                                                                                          |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `try: ... except Exception: pass` (or equivalent)                         | Likely hides a bug; see [ERROR_HANDLING](error-handling.md)                                                                        |
| `time.sleep(N)` in production code                                        | Probably racing something; concurrency smell                                                                                       |
| Magic numbers / strings                                                   | Often domain knowledge unexpressed; extract a constant                                                                             |
| Long or repeatedly confused parameter lists                               | Consider a value/parameter object when it adds domain meaning; a raw count is only a signal                                        |
| Boolean parameter that's never `false`                                    | Caller does one thing; remove the flag                                                                                             |
| Function returning `Optional[T]` _and_ throwing without a clear contract  | Ambiguous error channels; both may be valid when absence and failure are distinct                                                  |
| `if/elif/elif` on a type code                                             | Polymorphism candidate ([PRINCIPLES](principles.md))                                                                               |
| Loops over collections to find a single item                              | Linear; consider hash/index                                                                                                        |
| Long parameter chains (`a.b.c.d`)                                         | Law of Demeter                                                                                                                     |
| Mutable default arguments                                                 | Language footgun in some languages                                                                                                 |
| `assert` in production paths in Python                                    | Disabled with `-O`; security-relevant assertions become no-ops                                                                     |
| Hard-coded paths, hosts, ports that vary by deployment/user               | Likely configuration; protocol constants or embedded/build targets may correctly live in code ([CONFIGURATION](configuration.md))  |
| `# TODO` without a ticket reference                                       | Forgets itself                                                                                                                     |
| Commented-out code                                                        | Delete; git remembers                                                                                                              |
| Imports that are unused                                                   | Linter would catch — but check why they were added                                                                                 |
| Tests with no assertion                                                   | The "test" just exercises the code                                                                                                 |
| Tests that catch the very exception they're testing for as `Exception`    | Will catch unrelated bugs the test should have surfaced                                                                            |
| New endpoint without auth check                                           | See [API_DESIGN](api-design.md) / [SECURITY](security.md)                                                                          |
| Retryable mutation with unbounded duplicate effects and no retry contract | Idempotency, deduplication, operation identity, or an explicit at-most-once limitation may be needed ([API_DESIGN](api-design.md)) |
| Adding a column with a default to a large table                           | See [DATA](data.md) migrations                                                                                                     |
| Logging that includes whole request / response                            | See [PRIVACY](privacy.md) / [SECURITY](security.md)                                                                                |
| `verify=False` or equivalent disabling of TLS                             | See [SECURITY](security.md)                                                                                                        |
| Catching `KeyboardInterrupt` / `SystemExit`                               | Almost always wrong                                                                                                                |

---

## Anti-Patterns

| Pattern                                                                            | Why it fails                                                                                                                                                          |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Rubber-stamp ("LGTM" with no commentary)**                                       | The point of review is lost                                                                                                                                           |
| **Architecture astronaut comments** ("you should rewrite this as a state machine") | Often out of scope, often wrong, almost always disruptive                                                                                                             |
| **Reviewing-as-rewriting**                                                         | Reviewer effectively dictates the implementation; author becomes a typist                                                                                             |
| **Block on personal preference**                                                   | "I'd write it this way" — fine; just don't block                                                                                                                      |
| **Uncommunicated delay beyond project expectations**                               | The PR cost is real; expose capacity and reassign or change review mode                                                                                               |
| **Approving without reading**                                                      | Pure social ritual; defects sail through                                                                                                                              |
| **Reviewing only style**                                                           | The formatter does style; review the substance                                                                                                                        |
| **One reviewer always, never rotating**                                            | Single point of knowledge; bottleneck                                                                                                                                 |
| **Reviewer-author bickering in comments**                                          | Move to a call; resolve quickly                                                                                                                                       |
| **Letting a "no comments" PR mean "reviewer didn't read"**                         | Sometimes it does; build trust through visible engagement, not silence                                                                                                |
| **No standard for blocking vs nit**                                                | Authors second-guess every comment                                                                                                                                    |
| **Re-litigating settled decisions per PR**                                         | Reference the ADR; move on                                                                                                                                            |
| **Demanding a new test for every moved line**                                      | A behaviour-preserving refactor is verified by an adequate existing safety net; if that confidence is absent, add characterization or boundary tests before approving |
| **Asking for changes without explaining why**                                      | Costly to the author; unclear to the team; doesn't teach                                                                                                              |
| **Treating self-review as independent review**                                     | Self-review is valuable but cannot satisfy a control that requires independent approval; small/solo projects may explicitly accept that limitation                    |
| **Final approval before required checks settle**                                   | Evidence can change after review; early human feedback remains useful when its provisional status is clear                                                            |

---

## Process Discipline

| Practice                                              | Why                                                                                                   |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Required CI checks**                                | The author can't rely on "the reviewer will catch it"                                                 |
| **Risk-based review requirements**                    | Protected branches can enforce independent review where consequence/segregation of duties warrants it |
| **Code ownership** (`CODEOWNERS`) for sensitive areas | The right eyes see the change                                                                         |
| **Stale PR sweeping**                                 | Open PRs accumulate; review or close on a cadence                                                     |
| **Capacity-aware response target** where useful       | Reduces stalled work when ownership, time zones, interrupt cost, and escalation are explicit          |
| **Definition of done** (tests, docs, changelog, ...)  | Reviewers know what to check                                                                          |
| **Templates** for PRs and review comments             | Lower friction; better consistency                                                                    |
| **Periodic process retrospective**                    | Adjust as the team grows                                                                              |

---

## Diagnostic Framework

| Symptom                                                | Likely cause                                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| PRs sit beyond the project's target                    | Reviewers overloaded, ownership unclear, scope hard to review, or target unrealistic |
| Reviewers approve without comment                      | Cultural problem; reviewing is "social"; raise the bar                               |
| Same issues found in production over and over          | Reviews miss certain classes; add to the checklist; pair on the first few            |
| Author and reviewer in protracted argument             | Move to synchronous; escalate to the principle being debated                         |
| Reviews block on subjective style                      | No explicit `nit:` vs `blocking:` distinction; introduce the labels                  |
| Reviewer says "I don't have time"                      | PRs too big, or process is too heavy                                                 |
| Reviewers fix issues themselves rather than commenting | Sometimes appropriate; long-term it disempowers authors and breaks the audit trail   |
| PRs squash to a meaningless single commit              | Conventional commit / squash discipline needed                                       |
| New developers feel reviewed harshly                   | Tone calibration; pair with a peer reviewer initially                                |

---

## Meta-Question

Code review is the answer to: _will the change make the system better, knowing what we know now, with the team that will maintain it?_ Not "is this how I would have done it?" — the only useful question is **does this work, today and as it will need to evolve, with the people who will read it next?**

One healthy review culture—subject to project size, risk, and governance—is one where:

- Authors send small, well-described PRs.
- Reviewers communicate capacity and respond with specific, kind, unambiguous comments.
- Disagreements resolve quickly through principle, not status.
- The conversation is on the record.

The unhealthiest is silent rubber-stamping or one-sided gatekeeping. Both are correctable; both require deliberate culture.

---

_See [GIT_AND_VERSIONING](git-and-versioning.md) for PR descriptions and commit hygiene._
_See [TESTING](testing.md) for what reviewers should look for in tests._
_See [SECURITY](security.md) / [PRIVACY](privacy.md) / [CONCURRENCY](concurrency.md) / [DATA](data.md) for the topical concerns by area._
_See [CONTRIBUTING](contributing.md) for project-specific reviewer / approver rules._
_External convention/example: [Conventional Comments](https://conventionalcomments.org/) provides
one review-comment labeling vocabulary; project policy decides whether to adopt it._
