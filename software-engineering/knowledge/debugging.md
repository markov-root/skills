---
knowledge:
  version: 1
  id: debugging
  summary: Diagnose defects by reproducing observations, narrowing hypotheses, locating causes, and verifying repairs against the failure boundary.
  routes: [defect-diagnosis]
---

# debugging.md — The Discipline of Finding Bugs

> **Purpose:** Reference for finding the cause of unexpected behaviour. Covers the scientific method, hypothesis-driven debugging, bisection, the difference between fixing the symptom and fixing the cause, when to stop, and the specific traps that turn a one-hour bug into a one-week bug.
>
> **Read this when:** something doesn't work and you don't know why; you've been at it for an hour and aren't closer; you're about to "just add a try/except"; you found "a fix" and want to know whether it's the right one.
>
> **For non-trivial defects:** **Do NOT** change code at random. **Do NOT** stop at the first plausible cause. **Do NOT** ship a fix without understanding why the bug existed. Emergency mitigation can come first when needed to contain user harm, security exposure, or data loss; record what remains unknown and continue diagnosis after containment.

---

## The Premise

> **Unattributed aphorism:** Code that is written at the edge of your cleverness is harder to debug
> than code written plainly enough to inspect under stress.

Two operational corollaries:

1. **You are not debugging the code; you are debugging your mental model of the code.** The bug is the gap between what you believe is happening and what is happening. The work is finding the gap.
2. **The cost of a bug is dominated by the time to diagnose**, not the time to fix. The fix is usually small. The diagnosis is the work.

The senior reviewer's first question on hearing a fix is rarely "is this code correct?" — it is **"what causal story explains the defect, and how do we know this fix addresses it?"**

---

## The Scientific Method, Adapted

Debugging is empirical science applied to a system you wrote. The loop:

```
1. Observe—collect evidence; reproduce when safe and feasible
2. Hypothesise — propose a cause that could produce all observations
3. Predict — what else, if this hypothesis is correct, should be true?
4. Test — make a minimal change or measurement to confirm/refute
5. Refine — narrow the hypothesis based on result
6. Stop when the explanation fits material observations and alternatives are sufficiently ruled out
```

**Two anti-loops:**

- **"Random changes until it works".** A change "fixes" the symptom by accident. The bug returns later, or migrates.
- **"Belief debugging".** Defending the first hypothesis because it sounded right, instead of refuting it.

---

## Step 0 — Reproduce

A report is evidence of a defect even when the exact event cannot be reproduced. Reproduction
usually gives the strongest feedback loop, but incidents involving lost state, hardware,
concurrency, third parties, or rare distributions may require diagnosis from telemetry, artifacts,
controlled experiments, and competing hypotheses.

| Action                            | Detail                                                                                                  |
| --------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Reproduce locally if possible** | The fastest feedback loop                                                                               |
| **Reproduce in CI**               | Catches environmental dependencies                                                                      |
| **Capture inputs precisely**      | The user's request; the exact data; the time of day; the deployment version; the OS; the locale         |
| **Minimal reproducer**            | Strip the surroundings; smallest possible script / input / sequence                                     |
| **Watch for "sometimes"**         | Intermittent reproduction is a clue: concurrency, timing, ordering, data variation, caching, randomness |

Invest in capture and reproduction proportionate to consequence. Do not recreate a destructive or
security incident before containment and evidence preservation; use an isolated copy or model.

### What to do when you can't reproduce

1. **Increase observability** at the failure site. Add logs, metrics, traces ([OBSERVABILITY](observability.md)) — _then re-deploy and wait_. Patience over guessing.
2. **Check assumptions about the input.** What data was actually involved? Production data often has shapes you didn't anticipate.
3. **Check the timing.** Was the failure correlated with a deploy, a load spike, a cron run, a backup, a leader election?
4. **Check the environment.** Same OS? Same version? Same network? Same time zone? Same locale?
5. **Look for analogues.** Has this kind of bug happened before in this system? In a similar one?

---

## Evidence, Provenance, and Failure Modes

Before forming a hypothesis, collect evidence and label where it came from. Evidence is not truth by
itself; it is an observation with authority, freshness, and known ways to mislead you.

| Evidence source                          | What it gives you                                                   | Provenance to record                                                   | How it can mislead                                                                                   |
| ---------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Stack trace / error message**          | Where a failure surfaced and how the runtime classified it.         | Runtime, version, deployed build, full cause chain, first throwing frame. | Wrapper errors can hide the cause; diagnostics can be stale, generic, localized, or emitted after corruption. |
| **Logs at the time**                     | A narrative of selected events before, during, and after failure.   | Service, host, clock source, correlation ID, sampling/redaction policy. | Missing fields, async buffering, clock skew, dropped logs, and log-level changes can reorder or erase events. |
| **Metrics over the same window**         | Load, latency, saturation, error rate, dependency health.           | Metric definition, scrape interval, labels, aggregation window.         | Aggregation hides outliers; cardinality drops labels; instrumentation can change timing or allocation. |
| **Traces**                               | Cross-service path, spans, timings, dependency calls.               | Trace ID, sampling decision, propagation boundaries, collector version. | Sampling bias, broken context propagation, clock skew, and missing spans can make a path look complete when it is not. |
| **Types / schemas / static analysis**    | Stated contracts and classes of impossible states.                  | Compiler/checker version, strictness flags, generated-schema timestamp. | Types can be unsound, widened through `any`/casts/reflection, or stale relative to deployed schema/data. |
| **Reproduction**                         | A repeatable observation under known inputs and environment.        | Exact input, seed, data snapshot, build, environment, commands, timing. | A reproducer can exercise a similar symptom but not the production cause; instrumentation can remove timing bugs. |
| **Recent changes (deploy log, commits)** | Candidate triggers and changed contracts.                           | Commit/build IDs, rollout timing, flags, dependency versions.           | Correlation is not causation; several changes can interact; the real trigger may be input or environment drift. |
| **Affected vs unaffected**               | The slice that differs: users, tenants, requests, hosts, data.      | Population definition, sample size, time range, exclusions.             | Survivorship bias and missing labels can make the affected set look narrower than it is.               |
| **Source code at the failure point**     | The implementation that appears responsible.                        | Verified deployed version, generated code, feature flags, build profile. | The code you read may not be the code running; generated or optimized code can differ from source intent. |
| **Documentation / release notes**        | Declared behavior, caveats, migration notes.                        | Version/effective date and whether the docs match the deployed version. | Docs can lag behavior, omit edge cases, or describe defaults overridden by project configuration.       |

**Heuristic:** Read error messages, types, and logs carefully, then ask what would make each source
wrong. Scope: defect diagnosis. Trade-off: skepticism costs time; a counterexample is a syntax error
in a local build where the compiler diagnostic and the visible source line are enough to act.

---

## Hypothesis-Driven Debugging — The Recipe

State the hypothesis aloud (or write it down):

> _"I think the bug is X, because of evidence Y and Z. If X is true, then I'd also expect to see A and not see B. I'll test by C."_

The pattern forces:

- Naming the cause specifically (not "something is wrong with the cache").
- Anchoring it in evidence (not "I have a feeling").
- Generating a prediction (not "let me just try this").
- Designing a test (not "let me change this and see").

**When the prediction doesn't hold, abandon the hypothesis.** The fastest debugger is the one who lets bad hypotheses die early.

### Competing hypotheses and disconfirmation

**Project default:** Keep at least two plausible hypotheses alive until one is disconfirmed or the
evidence strongly distinguishes them. Scope: defects with ambiguous, production-only, intermittent,
or cross-boundary evidence. Trade-off: maintaining alternatives slows simple fixes; a counterexample
is a deterministic unit-test failure where one changed line directly violates the assertion.

For each serious hypothesis, write:

| Field                    | Example question                                                                                   |
| ------------------------ | -------------------------------------------------------------------------------------------------- |
| **Claim**                | What exact mechanism would produce the symptom?                                                     |
| **Supporting evidence**  | Which observations does it explain, and what is their provenance?                                   |
| **Awkward evidence**     | Which observations does it not explain cleanly?                                                     |
| **Prediction**           | What else should be true if this mechanism is real?                                                 |
| **Disconfirmation test** | What cheap observation would make this hypothesis unlikely?                                         |
| **Blast radius**         | Which users, data, services, or time windows should and should not be affected?                     |
| **Next action**          | What measurement, reproducer, bisect, rollback, flag change, or isolation step will separate cases? |

Prefer tests that can be wrong in an informative way. A confirming observation is weaker when many
hypotheses predict it; a disconfirming observation often narrows the search faster.

### Experiment records

An experiment record is not proof of a unique root cause. It is a durable account of what was tried
so the team stops repeating tests and can see how confidence changed.

Record:

- hypothesis under test;
- exact command, input, seed, fixture, data snapshot, build, environment, and instrumentation;
- expected result and the reason that result would distinguish hypotheses;
- actual result, including negative or ambiguous outcomes;
- whether the observation confirms, weakens, disconfirms, or does not distinguish the hypothesis;
- side effects created by the experiment, such as cache warming, queue drain, timing shifts, or data
  mutation.

**House preference:** Preserve experiment records for incidents, intermittent defects, data loss,
security/privacy bugs, and any debugging session handed between people. Scope: team debugging and
production diagnosis. Trade-off: recordkeeping is overhead; a counterexample is a local typo fixed
within one editor session where the failing compiler diagnostic and correction are self-evident.

---

## Useful Heuristics — The Detective's Toolkit

| Heuristic                                                                | When to use                                                                                               |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| **"What changed recently?"**                                             | Most bugs are introduced by recent change                                                                 |
| **Bisection** (binary search through commits / data / config / inputs)   | When you have a known-good and a known-bad                                                                |
| **`git bisect`**                                                         | When the bad commit is somewhere in history; pairs with a deterministic reproducer                        |
| **Rubber duck**                                                          | Explain the problem to someone (or something); the act of explanation often reveals the gap in your model |
| **Read the code aloud**                                                  | Forces you to slow down enough to notice                                                                  |
| **Look for the obvious thing twice**                                     | "It can't be the network" is usually said by people about to discover the network is to blame             |
| **Parse the error message as evidence**                                  | It is often more specific than your first hypothesis; verify the frame, cause chain, and runtime version  |
| **Treat the type system as scoped evidence**                             | Types reveal contract mismatches; casts, `any`, reflection, stale schemas, and generated clients can lie  |
| **Bisect inputs**                                                        | "Which row of the input causes it?" — halve the input repeatedly                                          |
| **Differential debugging**                                               | Compare a working environment with the broken one — what differs?                                         |
| **Five Whys**                                                            | "Why did X fail? Because Y. Why Y? Because Z. ..." Pursue the chain until it exposes contributing conditions |
| **Suspect the boundary**                                                 | Most bugs live at module, service, encoding, time-zone, or trust boundaries                               |
| **Look for the assumption**                                              | "I assumed X is always true" — find the assumption, then verify it                                        |
| **When two things changed and something broke, suspect the interaction** | Not just one or the other                                                                                 |

---

## Bisection — A Power Tool

Halving the search space repeatedly is `O(log n)`. **Project default:** use bisection when you have a
working state, a broken state, and a cheap enough test that preserves evidence. Exceptions: the state
transition is destructive or costly to recreate, the reproducer is too flaky to classify halves, or
the setup cost exceeds the value of a narrower search.

| What you're bisecting | Tool                                          |
| --------------------- | --------------------------------------------- |
| Commits               | `git bisect`                                  |
| Input data            | Comment out / delete half; re-run; repeat     |
| Config                | Half the flags / vars to defaults; repeat     |
| Dependencies          | Pin to old versions in halves                 |
| Time window           | "Was it broken at 09:00? At 09:30? At 09:15?" |
| Code paths            | Comment out branches; binary search           |

`git bisect` needs a deterministic reproducer and clean atomic commits (see [GIT_AND_VERSIONING](git-and-versioning.md)). When both are present, it finds the culprit commit in `log2(N)` builds.

---

## Print, Log, Debug, Profile — The Tools

| Tool                                                         | Best for                                                                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| **Print / log statements**                                   | The fast, ubiquitous, sometimes-the-only-way option. Strategic; not random                             |
| **Logger at DEBUG with structured fields**                   | A step up from `print` — searchable, correlatable ([OBSERVABILITY](observability.md))                  |
| **Interactive debugger**                                     | Stepping through; inspecting state; trying small experiments — invaluable when the system supports it  |
| **Conditional breakpoints**                                  | "Break when `user_id == 42 and amount > 1000`" — bypasses the haystack                                 |
| **Watchpoints**                                              | "Break when `this.balance` changes" — the only way to find "who is modifying this?" in mutable systems |
| **Postmortem (core dump / heap dump)**                       | The state at the moment of crash — irreplaceable                                                       |
| **Time-travel / reversible debuggers** (`rr`, GDB recording) | "What was the value before?" — turns a hard bug into a tractable one                                   |
| **Tracing** (distributed)                                    | Cross-service investigation                                                                            |
| **Profilers**                                                | When the bug is performance, not correctness                                                           |
| **`strace` / `dtrace` / `ptrace` / eBPF**                    | What is the process actually doing? syscalls, file I/O, signals                                        |
| **`tcpdump` / `wireshark`**                                  | What's actually on the wire?                                                                           |
| **`SQL` query log**                                          | What did the ORM actually generate?                                                                    |

**The rule on adding logs:** add them, run, **read what you added**. Reading what you wrote is more revealing than running it.

---

## Common Bug Categories — Pattern Recognition

| Category                                             | Telltale signs                                                                                           |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **Off-by-one**                                       | Edges of ranges; first/last item; empty inputs; size-1 inputs                                            |
| **Null / undefined / Optional misuse**               | `NoneType has no attribute`; "TypeError: cannot read property of undefined"                              |
| **Race condition**                                   | Intermittent; only at scale; depends on timing; "but it worked once" — see [CONCURRENCY](concurrency.md) |
| **Stale cache**                                      | "Worked before, broken now"; "fine after refresh"; recently changed source data                          |
| **Wrong environment / config**                       | Works in dev, breaks in prod; works in CI, breaks locally — see [CONFIGURATION](configuration.md)        |
| **Wrong version**                                    | "But the code clearly says X" — the deployed version doesn't say X                                       |
| **Encoding / time zone / locale**                    | Special characters break; "two hours off"; "works in US, broken in EU"                                   |
| **Floating-point comparison**                        | "0.1 + 0.2 != 0.3"; precision drift; financial math without `Decimal`/`numeric`                          |
| **Integer overflow / underflow**                     | Numbers wrap; sign flips; negative counts                                                                |
| **Resource leak**                                    | Slow growth; eventual OOM / FD-exhaustion; symptoms hours after the cause                                |
| **Wrong assumption about ordering**                  | "Sometimes results come back in a different order" — no `ORDER BY`, no documented contract               |
| **Wrong assumption about uniqueness**                | Duplicate keys; collision; race in check-then-insert                                                     |
| **Wrong assumption about idempotency**               | Retried operation duplicated state                                                                       |
| **Wrong assumption about atomicity**                 | Two operations expected as one weren't — see [DATA](data.md) isolation                                   |
| **Wrong assumption about types**                     | "I thought it was a string"; "the API changed the response shape"                                        |
| **Hidden mutable global / singleton**                | One test sets it; another reads it; test order matters                                                   |
| **TOCTOU** (time of check vs time of use)            | Permission checked, then bypassed by another writer between check and use                                |
| **Implicit dependency on framework / library quirk** | Updating broke it; the quirk was load-bearing                                                            |
| **Bug in your assumptions about the dependency**     | The library doesn't do what you thought it did; read its source                                          |

---

## Symptom vs Cause

A fix that makes the symptom disappear is not necessarily causal. Incidents commonly have multiple
contributing technical and organizational conditions. Use “root cause” only when one causal factor
is genuinely dominant; otherwise record contributing factors and the level each corrective action
addresses.

| Layer       | Question to ask                                        |
| ----------- | ------------------------------------------------------ |
| **Surface** | What did the user see?                                 |
| **Code**    | Which line / function / branch failed?                 |
| **Logic**   | What was the wrong assumption?                         |
| **Design**  | Why did the code permit this assumption?               |
| **Process** | Why didn't the test / review / type system catch this? |

**The Five Whys**:

> _"User saw a 500."_
> Why? _"The server threw an unhandled exception."_
> Why? _"It called `user.email.lower()` and `email` was None."_
> Why? _"Email is nullable in the schema."_
> Why? _"Old accounts predate the email requirement."_
> Why? _"There was no backfill when email was made required."_

The fix at each layer is different:

- Surface: show a friendlier error.
- Code: null check.
- Logic: handle absent email.
- Design: make `email` non-nullable in the schema; backfill old rows.
- Process: schema-design review for migrations.

**Pick the cheapest level of fix that prevents the class of bug**, not just this instance. Don't fix at every level for one bug, but be honest about which level you fixed.

---

## When to Stop

Three related decisions:

### Stop debugging when:

- You have a hypothesis that explains the material observations, including the parts you initially
  ignored.
- At least one discriminating test, reproduction, trace, bisect, rollback, or operational
  observation separates the chosen hypothesis from plausible alternatives.
- You have recorded what evidence is still missing or ambiguous.
- You have identified the triggering change, wrong assumption, violated contract, or external
  condition closely enough to choose a fix level.
- The fix candidate addresses the mechanism rather than only suppressing the symptom.

### Stop fixing when:

- The bug is reproducibly fixed by your change.
- A test exists that fails without the fix and passes with it.
- You've checked for analogous bugs in the same code, or noted that no analogues exist.
- The fix doesn't introduce a regression in related areas.
- The fix's scope matches the cause; you haven't included unrelated cleanup.

### Escalate or pause when:

- The failure may involve data loss, security/privacy exposure, safety, money movement, or legal
  obligations; containment and evidence preservation outrank local reproduction.
- You lack access to the production evidence, domain knowledge, or dependency contract needed to
  distinguish hypotheses.
- The next experiment would mutate production state, erase evidence, or materially change timing.
- The investigation is stuck: write down known observations, rejected hypotheses, remaining
  hypotheses, experiment records, and the smallest useful next question before handing it off.

**Heuristic:** If you find yourself "still investigating after one hour", step back and write down
what you know, what you do not know, and which observation would change your mind. Scope: ordinary
defect diagnosis. Trade-off: some outages need immediate mitigation before a clean record exists; a
counterexample is a live dependency outage where a documented rollback or failover is the fastest
safe containment step.

---

## Specific Tactics — A Field Guide

### "It works on my machine"

The most-mocked phrase in software, and almost always a real and important signal. The question is: **what differs between "your machine" and the broken environment?**

| Dimension          | Often divergent                                                         |
| ------------------ | ----------------------------------------------------------------------- |
| OS / kernel        | Linux vs macOS; kernel features; case-sensitive vs not                  |
| Locale / time zone | Numeric/date formatting; sort order; encoding                           |
| Network            | Proxies; corporate DNS; IPv6; MTU                                       |
| Dependencies       | Pinned versions in lockfile; native dep versions                        |
| Data               | Production data has shapes dev data doesn't                             |
| Concurrency        | Multiple cores; real load; real timing                                  |
| State              | Long-running process vs fresh restart                                   |
| Configuration      | Env vars; secrets; flags                                                |
| Permissions        | User; group; capabilities; SELinux/AppArmor; container security context |

The fix is rarely "make my machine match production". The fix is to **identify the differing factor and make the code resilient to it** — or normalize the environment.

### "But the code clearly says X"

The deployed code may not say X. Check:

- What version is actually running? (Build hash; deployed tag.)
- Is there a caching layer (CDN, browser) serving an old version?
- Did the deploy actually take effect on all instances?
- Is there a feature flag override?

### "Random" failures

Randomness is data. The failure depends on **something** you haven't yet identified. Suspect:

| Source                   | Symptom                                              |
| ------------------------ | ---------------------------------------------------- |
| Wall-clock time          | Fails at midnight; daylight-saving; on certain dates |
| Concurrency / scheduling | Different threads, different cores, different load   |
| RNG / hash randomization | Different orderings between runs                     |
| Data dependence          | Specific rows; specific Unicode; specific sizes      |
| Resource state           | Memory pressure; FD exhaustion; cache warmness       |
| Network                  | Packet loss; retransmits; DNS variability            |
| Dependency variability   | Upstream sometimes slow; rate limit hits             |

### "Heisenbugs" — bugs that disappear when observed

Classic: adding a `print` slows the loop just enough that the race goes away. The bug is real; it's hiding from your instrumentation. Tactics:

- Use non-intrusive observation (eBPF, kernel tracing) when possible.
- Use post-mortem (record + replay) rather than live observation.
- Slow other parts of the system to widen the window.
- Suspect concurrency / timing / memory ordering.

### Performance bugs

Different discipline. See [PERFORMANCE](performance.md) for the measurement loop. Briefly: **don't guess where time goes — profile.** The bottleneck is almost never where you'd expect.

### Production-only bugs

When the bug only surfaces in production:

- **Improve observability** at the suspect site (logs, metrics, traces) and wait for it again. ([OBSERVABILITY](observability.md).)
- **Bisect deploys** if a deploy correlated.
- **Compare prod and staging** — diff the differences.
- **Set up a parallel run** (shadow traffic) against a hypothesis fix.
- **Resist the urge to fix without diagnosis.** Production bugs that were "just fixed" without understanding recur.

---

## Documenting the Fix

After every non-trivial bug, write down:

| Item                                                                           | Why                                              |
| ------------------------------------------------------------------------------ | ------------------------------------------------ |
| **What was the symptom?**                                                      | Future search will find this incident            |
| **What was the dominant cause or contributing conditions?**                    | Distinct from the symptom; the level of fix      |
| **Why did it survive review / tests?**                                         | Process insight                                  |
| **What other code might have the same bug?**                                   | One occurrence is rarely one bug                 |
| **What is the fix, and why does it address the cause or condition (not only the symptom)?** | Justify the level chosen                         |
| **What test will catch a regression?**                                         | The fix is incomplete without a test             |
| **What's the broader prevention?**                                             | A linter, a type, a contract test, a docs change |

For larger incidents, run an incident review or post-mortem using [reliability](reliability.md) as
the owner of incident practice; use [observability](observability.md) for telemetry evidence.

---

## Anti-Patterns

| Pattern                                                                       | Why it fails                                                                                                                                       |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Random changes until it works**                                             | A coincidental fix; the bug recurs                                                                                                                 |
| **"It's intermittent, we'll move on"**                                        | Intermittent ≠ rare in production at scale                                                                                                         |
| **Adding `try/except` around the failure point**                              | Hides the bug forever; the next person sees an empty log                                                                                           |
| **Catching the exception, logging it, and continuing as if nothing happened** | Same                                                                                                                                               |
| **Claiming a fix without discriminating evidence**                            | A deterministic reproducer is ideal; rare/statistical/hardware incidents need bounded experiments, rates, or stronger operational evidence         |
| **Fixing the symptom without understanding the cause**                        | The cause produces other symptoms later                                                                                                            |
| **Ignoring the warning ("just a warning")**                                   | Warnings are bugs the system noticed for you                                                                                                       |
| **"It must be a flaky test"**                                                 | Sometimes; usually it's a real concurrency bug — investigate                                                                                       |
| **Skipping the test to unblock the deploy**                                   | The test was telling the truth                                                                                                                     |
| **"I refactored a bit while debugging"**                                      | Two hats; if the bug isn't reproducible after, you don't know which hat caused which effect                                                        |
| **Not reading the error message**                                             | The answer is often in line one                                                                                                                    |
| **Not reading the logs**                                                      | Same                                                                                                                                               |
| **Treating instrumentation as neutral**                                       | Logs, traces, profilers, and debug prints can change timing, allocation, sampling, and visibility                                                   |
| **Treating types or schemas as current truth**                                | Unsound types, generated clients, stale schemas, and permissive casts can preserve a false model                                                    |
| **Closing without durable regression evidence where practical**               | Use a test when it can discriminate the defect; otherwise preserve monitoring, fixture, static rule, fault injection, or documented evidence limit |
| **Not noting the fix in the changelog**                                       | Users don't know to upgrade                                                                                                                        |

---

## Diagnostic Framework

| Symptom                          | First steps                                                                           |
| -------------------------------- | ------------------------------------------------------------------------------------- |
| Can't reproduce                  | Improve observability; capture inputs; reproduce in test first                        |
| Hard to localize                 | Bisect (commits, inputs, config); read the trace; reduce the reproducer               |
| Different in dev vs prod         | Diff the environments; check version, config, data, concurrency                       |
| Intermittent                     | Suspect timing/concurrency/data; check for races, caching, ordering assumptions       |
| New code broke old behaviour     | Bisect commits; characterisation tests would have caught — write them now             |
| Old behaviour, new failure       | What changed in inputs, data, dependencies, infra?                                    |
| Fixed and broke again            | Symptom-level fix; revisit root cause                                                 |
| "Random" segfaults / crashes     | Memory corruption; FFI mismatch; missing locking; broken invariants — read core dumps |
| Performance regression           | Profile before and after; compare; bisect deploys                                     |
| Bug only at scale                | Lock contention; resource exhaustion; queue depth; tail latency — load test           |
| Test passes locally, fails in CI | Environmental dependency; non-determinism; ordering assumption; concurrency           |

---

## Meta-Question

Debugging is the answer to: _what is the smallest, simplest, true explanation that accounts for every observation?_ The discipline is in the **every observation** — the one that "doesn't fit" is the one that breaks the wrong hypothesis.

When the work is done, you should be able to **describe the bug in one sentence**, **the cause in one paragraph**, and **show the test that will catch it next time**. If you can't, you haven't finished.

---

_See [OBSERVABILITY](observability.md) for the instrumentation that makes diagnosis fast._
_See [TESTING](testing.md) for the regression tests that close the loop._
_See [CONCURRENCY](concurrency.md) for the bug categories that resist single-threaded reasoning._
_See [PERFORMANCE](performance.md) for performance-bug-specific tactics._
_See [REFACTORING](refactoring.md) for what to do after — and what NOT to bundle with the fix._
_See [ERROR_HANDLING](error-handling.md) for the discipline that prevents the next class of these._
