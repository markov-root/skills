---
knowledge:
  version: 1
  id: refactoring
  summary: Choose and execute refactors or rewrites from explicit outcomes, seams, characterization evidence, migration strategy, and stopping conditions.
  routes: [refactor-rewrite]
---

# refactoring.md — Refactoring, Rewriting, and Paying Down Debt

> **Purpose:** Reference for changing code without changing behaviour — what refactoring is, when it's worth doing, when it isn't, how to do it safely, when to rewrite instead, and how technical debt accrues and is paid.
>
> **Read this when:** you want to "clean up" code; you're about to start a "big rewrite"; you're tempted to rename, restructure, or extract; you're inheriting code that "needs work"; the team is debating "refactor vs feature".
>
> **Project default:** Separate structural and behavioral changes into reviewable steps when
> practical. Establish risk-proportionate evidence before changing structure, and understand the
> existing system before replacing it.

---

## The Premise

> _Refactoring is a behaviour-preserving change in code structure, intended to improve clarity, maintainability, or design._

Two corollaries that drive everything else:

1. **Behavior-preserving needs a declared observation boundary.** Functional outputs, public
   contracts, persistence, timing/performance budgets, resource use, ordering, logs/telemetry, and
   failure behavior may be observable to different consumers. State what must remain invariant.
2. **Evidence comes first.** Tests are usually strongest; traces, type/static checks, production
   comparison, compatibility suites, and manual characterization may supplement gaps.

A senior engineer's reflex on hearing "let me just refactor this": _"do we have tests, what's the smallest step, and are we doing it in its own commit?"_

---

## Refactoring vs Other Activities — Don't Conflate

| Activity              | What it is                                | Allowed to change behaviour?                     |
| --------------------- | ----------------------------------------- | ------------------------------------------------ |
| **Refactoring**       | Restructure code; no behaviour change     | **No**                                           |
| **Renaming / moving** | Pure code hygiene; ideally tooling-driven | No                                               |
| **Reformatting**      | Whitespace, style only                    | No (and: separate commit; ignore in `git blame`) |
| **Feature change**    | Adding or modifying behaviour             | Yes                                              |
| **Bug fix**           | Removing unintended behaviour             | Yes                                              |
| **Optimisation**      | Same behaviour, better performance        | No (behaviour); yes (observable property)        |
| **Rewrite**           | New implementation from scratch           | Often, intentionally                             |

**Discipline:** each kind of change in its own commit, ideally its own PR. When a refactoring and a feature change must travel together, **refactor first, in a separate commit**, then add the feature.

---

## The Two Hats

Prefer separate logical steps/commits for restructuring and behavior. A compiler-assisted rename
plus required compatibility update may be atomic; keep the diff reviewable and make each behavior
change explicit.

Switching hats is fine; wearing both is how the bug enters. When a refactor reveals a bug, write it down, finish the refactor, then fix the bug as a separate change. (Or: stop, do the bug fix first, then the refactor.)

---

## When to Refactor

Defensible reasons:

| Reason                                                              | Example                                                                                                           |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **About to extend** code that's hard to extend in its current shape | "I need to add a third payment provider; the existing code has two `if/else` branches" — extract a strategy first |
| **Just understood something** while reading                         | The mental model is fresh; the change is cheap                                                                    |
| **The same change is being made repeatedly across the codebase**    | Three is the rule of thumb — abstract on the third                                                                |
| **The code has been a recurring source of bugs**                    | Defect clustering ([TESTING](testing.md) principle 4); the shape is wrong                                         |
| **The cost of working in this area is observably high**             | Velocity in the area is bad; measure before claiming                                                              |

Indefensible reasons:

| Reason                                       | Why it doesn't justify                                                                                      |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **"This isn't how I would have written it"** | Stylistic preference is not technical debt                                                                  |
| **"It doesn't follow the pattern"**          | The pattern is a means, not an end                                                                          |
| **"For cleanliness"**                        | Cleanliness without a measurable cost reduction is decoration                                               |
| **"To use [new framework/library]"**         | The framework is a tool, not a deliverable                                                                  |
| **"To increase test coverage"**              | Tests serve behaviour; reorganising to make code more testable is fine _if_ you then exercise the new seams |

---

## The Safety Net — Calibrate Before You Refactor

Select evidence for the behavior and risks being preserved:

| Evidence                                                                                 | Use and limitation                                                                                                     |
| ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Behavioral tests over the affected contract**                                          | Strong for represented scenarios and oracles; a coverage percentage does not rank this evidence                        |
| **Characterisation tests** written specifically to pin current behaviour, including bugs | Useful when intended behavior is uncertain; records observations rather than establishing that the behavior is correct |
| **Type system, compiler, and structural checks**                                         | Detect represented structural/type violations, not every logical or runtime change                                     |
| **Replay, differential/shadow comparison, or state/data invariants**                     | Useful when ordinary test seams are absent; workload, environment, model, and side-effect containment bound the result |
| **Manual characterization/checklist**                                                    | Sometimes the only practical starting evidence; record the observer, environment, steps, result, and omissions         |

Characterisation tests record _what the system does in represented cases_, not whether that
behavior is correct. If one changes after a refactor, investigate whether the implementation
changed, the environment/fixture drifted, or the observation was intentionally superseded; do not
update it reflexively.

See [TESTING](testing.md) for the broader testing discipline.

---

## Code Smells — The Catalog

Refactoring is reactive. A smell is a signal that _something_ may want attention. Smells are heuristics, not laws — they sometimes lie.

### Bloaters

| Smell                   | What it is                                                     |
| ----------------------- | -------------------------------------------------------------- |
| **Long Method**         | Hard to grasp at a glance; doing too many things               |
| **Large Class**         | Multiple responsibilities; god object                          |
| **Long Parameter List** | Should be an object, or the function does too much             |
| **Primitive Obsession** | "stringly typed" — money as float, ID as string, status as int |
| **Data Clumps**         | The same group of values travels together — make a type        |

### Object-orientation abusers

| Smell               | What it is                                                    |
| ------------------- | ------------------------------------------------------------- |
| **Switch on type**  | Polymorphism missing — type-based dispatch in conditionals    |
| **Temporary Field** | A field set only sometimes; the object is in multiple shapes  |
| **Refused Bequest** | A subclass doesn't use most of the parent — wrong abstraction |

### Change-preventers

| Smell                    | What it is                                           |
| ------------------------ | ---------------------------------------------------- |
| **Divergent Change**     | One module changes for many unrelated reasons        |
| **Shotgun Surgery**      | One change touches many modules                      |
| **Parallel Hierarchies** | Adding a class in one tree forces a class in another |

### Dispensables

| Smell                            | What it is                                                                        |
| -------------------------------- | --------------------------------------------------------------------------------- |
| **Comments explaining the code** | Often the code is unclear; rewrite the code (keep comments for _why_, not _what_) |
| **Duplicated Code**              | The same logic in many places — but beware the wrong abstraction                  |
| **Lazy Class**                   | Class that does too little to justify its existence                               |
| **Dead Code**                    | Unused; remove (`git` is the history)                                             |
| **Speculative Generality**       | Abstractions for needs that don't exist yet — YAGNI                               |

### Couplers

| Smell                      | What it is                                           |
| -------------------------- | ---------------------------------------------------- |
| **Feature Envy**           | A method uses another class's data more than its own |
| **Inappropriate Intimacy** | Classes know each other's internals                  |
| **Message Chains**         | `a.b().c().d()` — Law of Demeter violation           |
| **Middle Man**             | A class that only delegates; cut it out              |

Smells point at _something_. They don't say _what_ to do. Refactor with judgment; the cure can be worse than the disease.

---

## Catalog of Refactorings — The Most Used

Named refactorings (Fowler's catalog) — pick the right one:

| Refactoring                                              | When                                                         |
| -------------------------------------------------------- | ------------------------------------------------------------ |
| **Extract Function / Method**                            | Long method; same code in two places; needs a name           |
| **Inline Function**                                      | The function adds no clarity; the body is more readable      |
| **Extract Variable**                                     | Express intent of a complex expression                       |
| **Inline Variable**                                      | The variable name adds no information                        |
| **Change Function Declaration**                          | Rename; reorder, add, or remove parameters                   |
| **Encapsulate Variable**                                 | Wrap shared state in getters/setters; gain a hook for change |
| **Rename**                                               | The name doesn't match what it does                          |
| **Introduce Parameter Object**                           | Long parameter list with related data                        |
| **Replace Conditional with Polymorphism**                | Switch on type; growing `if/else` chain                      |
| **Replace Type Code with Subclasses / State / Strategy** | Behaviour varies on a type code                              |
| **Replace Loop with Pipeline**                           | Loop with several stages — make it explicit                  |
| **Move Function / Field**                                | Code lives in the wrong place                                |
| **Extract Class**                                        | A class has multiple responsibilities                        |
| **Inline Class**                                         | A class doesn't justify its existence                        |
| **Hide Delegate**                                        | Reduce coupling: don't expose `a.getB().getC()`              |
| **Introduce Special Case**                               | A null check repeated everywhere → a Null Object             |
| **Replace Primitive with Object**                        | Strings/ints with rules become a type                        |
| **Decompose Conditional**                                | Complex `if`s become named functions                         |
| **Combine / Split Loops**                                | Trade clarity for performance, or vice versa                 |
| **Replace Magic Literal with Symbolic Constant**         | `0.07` → `TAX_RATE`                                          |
| **Slide Statements**                                     | Reorder a function so related statements are adjacent        |

**Tooling does the safe ones.** Modern IDEs do extract function, rename, move, change signature, inline — _use the tools_. They preserve scope correctness in ways hand-edits often don't.

---

## The Small-Step Discipline

Refactoring is **a sequence of tiny, verifiable steps.** After each step, the code compiles, the tests pass, the system runs.

The pattern:

```
1. Pick a target shape.
2. Make the smallest change toward it.
3. Compile / test / run.
4. Commit.
5. Repeat.
```

This is unbearably slow when wrong; it's fast when right. The reason it works: every step is recoverable. If step 7 broke, you `git revert` step 7 alone — you don't lose steps 1–6.

**Anti-pattern:** the "big refactor" — three days of changes, "let me just make it work first, then I'll commit." The result is unmergeable, untested, untraceable, and usually wrong in two places that mask each other.

---

## Specific Patterns for Larger Changes

### The Strangler Fig

When you must replace a subsystem without a flag day:

1. Build the new system alongside the old, behind an interface.
2. Route some traffic to the new; compare results.
3. Migrate consumers one at a time.
4. When the old is unused, delete.

Named after the strangler fig tree, which grows around its host and eventually replaces it. Works for: replacing a service, replacing a database, replacing a UI framework, replacing an internal library.

### Mikado Method

When you start refactoring and discover prerequisites:

1. Try the change. It fails.
2. Note what would be needed to make it succeed (a precondition).
3. Revert.
4. Tackle the precondition first.
5. Repeat until the original change succeeds.

The output is a tree (the Mikado graph) of dependencies; leaves are independent, doable now. Avoids the "half-refactored codebase" purgatory.

### Branch by Abstraction

When changing something used everywhere:

1. Introduce an abstraction layer that wraps the existing implementation.
2. Migrate callers to use the abstraction (no behaviour change).
3. Build a second implementation behind the abstraction.
4. Switch the abstraction's default; verify.
5. Remove the old implementation.

Avoids long-lived branches; everything stays mergeable.

### Parallel Run

For high-stakes changes (e.g., a payment calculator rewrite):

1. Run old and new in parallel for every request.
2. Return the old; record disagreements.
3. Investigate every disagreement until none remain.
4. Switch to the new; remove the old.

Slower; but for "this must not break" subsystems, the right level of caution.

### Parallel Change and Data/API Migration

When consumers or stored data cannot change atomically:

1. expand with an additive compatible contract;
2. deploy readers that understand old and new forms;
3. migrate writers/data/consumers with observable progress and resumability;
4. verify mixed-version, rollback, partial-failure, and reconciliation behavior;
5. contract/remove the old form only after usage and recovery evidence.

Shadow/parallel execution must not duplicate external side effects or disclose production data to an
unauthorized path. Compare canonicalized results with privacy, cost, and load budgets. “No observed
disagreement” is bounded evidence, not proof of equivalence.

---

## Working in Inherited / Legacy Code

See [AUDIT_INHERITED](audit-inherited.md) for the full treatment. Specific refactoring tactics:

- **Establish a risk-proportionate behavior anchor.** Characterisation tests are often useful; a
  replay, invariant, differential comparison, or controlled manual record may be more credible
  where a test seam does not yet exist.
- **Identify seams** — places where you can change behaviour without editing many sites (a function call, an interface, a configuration point).
- **Extract pure functions** from imperative tangles. Pure functions test trivially; imperative globs do not.
- **Eliminate hidden inputs and outputs** (globals, singletons, ambient calls). Make them parameters.
- **Sprout method / class** — instead of modifying the legacy method, add a new one and call into it.
- **Wrap, don't change** — when a function is dangerous to touch, wrap it; change the wrapper.

The lodestar: **leave the area more testable than you found it,** by one seam per touch. Over time, the legacy thaws.

---

## When to Rewrite Instead

Rewrites are tempting and usually wrong. Joel Spolsky's classic essay ("Things You Should Never Do") is the warning shot; the reality is more nuanced.

**Refactor when:**

- The current code can evolve into the desired shape via small steps.
- The team understands the current code.
- The business value of new behaviour is incremental.
- A safety net exists or can be built.

**Rewrite when:**

- The architecture is fundamentally wrong for the requirements that now exist.
- The technology is unsupported (language EOL, framework abandoned, platform retired).
- The team has lost the knowledge of the existing system, _and_ the existing system is small enough to rewrite faster than relearn.
- Operational cost (build, deploy, observability) is permanently broken.

**Rewrite carefully:**

- Spec what the existing system actually does first. Most rewrites fail because the new system doesn't replicate the old's quiet correctness.
- Run them in parallel (strangler fig, parallel run).
- Keep the rewrite focused. "Rewrite + add new features" is two projects.
- Set a deadline. Rewrites without deadlines become permanent.
- Have a rollback plan. Until the rewrite carries production load for a sustained period, it isn't done.

---

## Technical Debt — A Useful Metaphor If Used Carefully

The metaphor (Ward Cunningham): expedient design choices accrue interest. You pay either by being slower, or by refactoring.

The metaphor breaks down in two ways:

1. **Not all "debt" is intentional.** Sometimes it's ignorance, sometimes it's drift, sometimes it's neglect. Each requires different attention.
2. **Interest rates vary.** Some debt is dormant (rarely-touched code that's ugly but stable); some is compounding (the area where every feature is slower than the last).

### A useful taxonomy

| Type                      | Description                               | Pay-down approach                           |
| ------------------------- | ----------------------------------------- | ------------------------------------------- |
| **Deliberate, prudent**   | "Ship now, refactor when we learn more"   | Schedule the refactor; track the commitment |
| **Deliberate, reckless**  | "We know this is wrong, let's not fix it" | Cultural problem; address with leadership   |
| **Inadvertent, prudent**  | "We learned a better way after shipping"  | Refactor when convenient                    |
| **Inadvertent, reckless** | "We didn't know better"                   | Education first; then refactor              |

### Operational discipline

- **Track debt explicitly.** A backlog item, an ADR, a `// TECH_DEBT:` comment with a ticket reference.
- **Bound the size of work-in-progress debt.** Cap "refactor this someday" items; close stale ones.
- **Pay down where it hurts most.** The defect-cluster module gets attention before the dormant one.
- **Pay continuously.** A 10% allocation in every cycle beats a yearly "refactor week".
- **Communicate the cost.** Debt is invisible to non-engineers; surface it through metrics (lead time, change failure rate, on-call incidents).

---

## Refactoring at Scale — Org-Level Discipline

For changes that touch many modules:

| Concern                               | Pattern                                                             |
| ------------------------------------- | ------------------------------------------------------------------- |
| **Codemods**                          | Automated transforms — `comby`, `ast-grep`, language-specific tools |
| **Migrations in waves**               | One module at a time, with the new pattern documented               |
| **Linters that flag the old pattern** | Make the regression visible                                         |
| **A central tracking document**       | Where the migration is; what's left                                 |
| **Communication**                     | Other teams must know what's happening and when                     |

---

## The Wrong Abstraction

> _Duplication is far cheaper than the wrong abstraction._ — Sandi Metz

Three pieces of code that look similar are not necessarily three instances of the same idea. If you abstract prematurely:

- The abstraction calcifies; future variations are forced to fit.
- Callers become coupled to the abstraction's quirks.
- Removing the abstraction is a refactor harder than the duplication ever was.

**Discipline:**

- **Rule of three.** Two instances may differ. Three is when the pattern starts to look real.
- **Watch the abstraction grow.** If parameters multiply, flags accumulate, conditionals nest — the abstraction is wrong; revert to duplication and re-think.
- **A wrong abstraction with two callers is a refactor. With twenty callers, it's a project.** Cheaper to fix earlier.

---

## Renames — The Underrated Refactor

Names are public APIs of code. A bad name miscommunicates forever to every reader. **Renaming is cheap and high-impact.**

Discipline:

- **Use tooling** for renames — IDE, language-server. Hand-edits miss references in strings, configs, docs.
- **Rename in stages** when the name is in an external API: introduce the new name, deprecate the old, remove the old.
- **Search for the old name** after renaming — code, docs, scripts, dashboards, alerts, runbooks.

---

## Anti-Patterns

| Pattern                                              | Why it fails                                                                     |
| ---------------------------------------------------- | -------------------------------------------------------------------------------- |
| **Refactor + feature in one commit**                 | If a bug surfaces, you can't tell which half caused it                           |
| **Refactor without tests**                           | You've rewritten, not refactored — and you don't know whether you broke anything |
| **"Just clean up while I'm here"**                   | The PR's scope explodes; reviewers can't tell signal from noise                  |
| **The Great Refactor**                               | Multi-week branch; un-mergeable; falls behind `main`; abandoned                  |
| **Abstracting on the first duplication**             | YAGNI violation; usually the wrong abstraction                                   |
| **Renaming without tooling**                         | References to the old name survive                                               |
| **Reformatting and refactoring in one commit**       | The diff is dominated by whitespace; the substantive change is hidden            |
| **Refactor commits that don't preserve tests**       | "I'll fix the tests after" — you won't, and you've broken the safety net         |
| **Adopting a new architecture pattern mid-refactor** | The refactor's goal becomes "make it look like X" instead of "solve the problem" |
| **Rewriting because "this is messy"**                | Messy and working beats clean and broken                                         |
| **Deleting "dead code" without a search**            | It's referenced in a config / template / runtime-loaded plugin                   |
| **Refactor as procrastination**                      | The actual feature isn't getting built                                           |

---

## Diagnostic Framework

| Symptom                                               | Likely cause                                                     |
| ----------------------------------------------------- | ---------------------------------------------------------------- |
| Refactor broke production                             | Behaviour changed; no characterisation tests                     |
| Refactor PR is enormous                               | Too many concerns; small-step discipline missing                 |
| Refactor stalled mid-flight                           | Mikado not used; prerequisites discovered late                   |
| Same area refactored repeatedly                       | Abstractions don't fit the actual change axis                    |
| New developer can't extend a "well-refactored" module | The abstraction is for the previous problem, not the current one |
| Velocity slower after a refactor                      | Wrong abstraction; or the refactor wasn't an improvement         |
| Tests rewritten alongside the refactor                | Lost the behaviour anchor — investigate before accepting         |
| "We're going to rewrite this" — every six months      | Cultural pattern; address before the rewrite                     |
| Technical debt tickets never close                    | They're aspirational; treat differently or close them            |
| Big refactor lands; immediate bug surge               | Insufficient testing; insufficient parallel-run discipline       |

---

## Meta-Question

Refactoring is the answer to: _how do I make this code easier to change next time, without changing what it does today?_ The discipline is in the **without**.

The healthiest refactoring is continuous, small, and almost invisible — a constant background hum of the team improving the code it's currently working in. The unhealthiest is the dramatic, code-frozen, multi-month effort that ends in a merge no one can verify.

---

_See [PRINCIPLES](principles.md) for the design principles that make refactor targets recognisable._
_See [TESTING](testing.md) for the safety net._
_See [AUDIT_INHERITED](audit-inherited.md) for refactoring in legacy code._
_See [GIT_AND_VERSIONING](git-and-versioning.md) for the commit discipline._
_See [CODE_REVIEW](code-review.md) for the social side._
