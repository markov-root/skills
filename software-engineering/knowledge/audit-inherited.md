---
knowledge:
  version: 1
  id: audit-inherited
  summary: Audit an inherited repository by reconstructing authority, runtime behavior, risk, evidence, and operational reality before changing it.
  routes: [inherited-repository, review-audit]
---

# audit-inherited.md — Taking Over Code You Didn't Write

> **Purpose:** Reference for the moment you inherit a codebase, fork an open-source project, take over a teammate's project, or land in a legacy system. Covers how to read code at the right depth before changing it, how to assess risk and debt without overreacting, how to build a safety net, and how to deliver value while learning.
>
> **Read this when:** starting on a new-to-you codebase; doing a security/architecture audit of unfamiliar code; being asked to "clean up" something the previous owner left; deciding whether to extend, refactor, or rewrite; reviewing an open-source project before depending on it.
>
> **Do NOT** start refactoring on day one. **Do NOT** assume the previous author was wrong. **Do NOT** make changes you can't defend with evidence.

---

## The Premise

> _Every line of code in production was written for a reason. The reason may be wrong, outdated, or forgotten — but it existed, and the system was shipped, and that's not nothing._ — Chesterton's Fence, applied

Two operational corollaries:

1. **Read more than you write, for longer than feels right.** The fastest way to break an inherited codebase is to start changing it before you understand it. Days of reading save weeks of debugging.
2. **The system's working behaviour is the spec.** Whatever the docs say, whatever the code "should" do, what it _does_ is what users depend on. Refactor against current behaviour, not aspirational behaviour. ([REFACTORING](refactoring.md) — characterisation tests.)

---

## The First Week — Reconnaissance, Not Construction

Resist the urge to "improve" things. The first job is to build a mental map.

### What to do

| Day | Activity                                                                                                                                                              |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Read the README; run the project; click through the UI / hit the API; read the CHANGELOG; skim the README again with the system running                               |
| 1–2 | Read the top-level directory structure; identify modules and their stated purposes; identify the entry points (CLI, HTTP handlers, scheduled jobs, message consumers) |
| 2–3 | Run the tests; observe what they cover and what they don't; read the test names as documentation                                                                      |
| 2–4 | Read the CI configuration; what gates exist? lint, type-check, tests, security scan?                                                                                  |
| 3–5 | Read the deployment configuration; how does this run in production? how is it monitored?                                                                              |
| 4–5 | Pull `git log` summary stats: recent activity, most-changed files, file owners; identify hot spots                                                                    |
| 4–7 | Read the actual code of the core path end-to-end, following one important user journey from entry point to persistence                                                |

### What NOT to do

- **Don't refactor.** Don't even reformat. You don't yet know what's load-bearing.
- **Don't rename.** A name you don't understand might be domain language you haven't met.
- **Don't delete "dead" code.** Until proven dead — see "the dead code trap" below.
- **Don't change behaviour.** Even fixing "obvious" bugs may break consumers who depend on them.
- **Don't add abstractions.** Even ones that "would obviously help."

---

## Specific Recon Tools

### Code archaeology

| Tool                                                                                  | Use                                                         |
| ------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `git log --oneline --graph --all`                                                     | Branch topology; collaboration style                        |
| `git log --since="6 months ago" --pretty=format:"%an" \| sort \| uniq -c \| sort -rn` | Who's been active; who's the de-facto owner                 |
| `git log -p <file>`                                                                   | History of a single file                                    |
| `git log -S '<string>'`                                                               | When was this added / removed?                              |
| `git blame -w -C -C -C <file>`                                                        | Last touch per line, ignoring whitespace and tracking moves |
| `git shortlog -sn --no-merges`                                                        | Total contributors, by commit count                         |
| `tokei` / `cloc`                                                                      | Lines of code by language; size of subdirectories           |
| `scc`                                                                                 | Adds rough complexity estimate                              |
| Repository visualisations (`gource`, `code_swarm`)                                    | Sense of project's life over time                           |

### Reading the code

| Question                                                 | Where to look                                                                                                             |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **What does this system do?**                            | README; product copy; UI; API docs                                                                                        |
| **What kind of architecture?**                           | Top-level directory layout; framework choice; presence of an `architecture.md` / `ADR/` directory                         |
| **What are the bounded contexts?**                       | Major modules / packages; the language they use (different module ⇒ different vocabulary often signals different context) |
| **Where is the source of truth for each piece of data?** | Schema; primary database; configuration loading                                                                           |
| **What are the boundaries?**                             | Imports; module-level entry/exit; HTTP handlers; queue consumers                                                          |
| **Where is the riskiest code?**                          | Recent bug fixes (`git log --grep "fix"`); files with most churn; files with most blame layers                            |
| **What are the obvious hacks?**                          | Search for `TODO`, `FIXME`, `XXX`, `HACK`, `WORKAROUND`, `temporary`, `revisit` — but treat them as clues, not commands   |
| **What's the testing strategy?**                         | Test count; test type ratio; presence of integration / E2E tests; CI configuration                                        |
| **What's the deploy story?**                             | `Dockerfile`, `docker-compose.yml`, CI/CD configuration, `k8s/`, Terraform, `Procfile`, `deploy.sh`                       |
| **What are the runtime dependencies?**                   | Lockfile; package manifest; transitive deps if relevant — see [DEPENDENCIES](dependencies.md)                             |
| **What are the external services?**                      | Env vars; config files; URLs in code; comments about "the X API"                                                          |
| **What's been deprecated?**                              | CHANGELOG; commit messages; comments mentioning deprecation                                                               |

### Talking to people

The codebase is half the story. The other half lives in heads.

| Person                                  | Ask                                                                                                                       |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Previous maintainer** (if accessible) | "What would you change if you had time?" / "What scares you about this code?" / "What looks wrong but is actually right?" |
| **Users / customer support**            | "What do you wish worked better?" / "What's the most common problem you see?"                                             |
| **Operations / on-call**                | "What pages you most often?" / "What workarounds do you have?"                                                            |
| **Adjacent team**                       | "How do you interact with this system? What contracts do you depend on?"                                                  |

These conversations are the cheapest way to find the **Chesterton's Fences** — the unobvious reasons something is the way it is.

---

## Chesterton's Fence

> _In the matter of reforming things, as distinct from deforming them, there is one plain and simple principle; a principle which will probably be called a paradox. There exists in such a case a certain institution or law; let us say, for the sake of simplicity, a fence or gate erected across a road. The more modern type of reformer goes gaily up to it and says, "I don't see the use of this; let us clear it away." To which the more intelligent type of reformer will do well to answer: "If you don't see the use of it, I certainly won't let you clear it away. Go away and think. Then, when you can come back and tell me that you do see the use of it, I may allow you to destroy it."_ — G. K. Chesterton

Operational form:

- **Before removing anything, understand why it's there.**
- The answer may be "no reason; the original author was wrong" — fine, but you've earned the removal.
- The answer may be "it handles an obscure case that comes up once a quarter" — and you've saved a quarterly outage.
- "It's old code, surely nothing important uses it" is not understanding; it's a guess.

The fence applies to: removing code, removing tests, removing config options, removing dependencies, removing endpoints, removing fields, removing entries in lookup tables, changing defaults, refactoring away "redundant" layers.

---

## The Dead Code Trap

Code that _looks_ dead often isn't. Before deleting:

| Check                                         | Why                                                                              |
| --------------------------------------------- | -------------------------------------------------------------------------------- |
| **Static analyser / linter** says it's unused | Necessary, not sufficient                                                        |
| **Grep the codebase**, including strings      | Reflection, dynamic dispatch, runtime registration                               |
| **Grep the configuration**                    | Config might enable a path                                                       |
| **Check templates, fixtures, generated code** | Used somewhere not the linter sees                                               |
| **Check the build / CI**                      | Maybe it's referenced by a build script                                          |
| **Check runtime data**                        | Are there enum / type values stored in the DB whose meaning is in this code?     |
| **Check external consumers**                  | An API endpoint may be used by clients you don't know about                      |
| **Add observability before deleting**         | Log a counter; deploy; wait a quarter; then delete if the counter stayed at zero |

**The safest deletion is staged:** mark deprecated, instrument, wait, then delete. The week of dead-code cleanup that recovers six months of bug-hunting was not worth it.

---

## Building the Safety Net

Once you understand the area you're going to change, establish proportionate behavior and risk
evidence **before** changing it. See [TESTING](testing.md) (evidence contract) and
[REFACTORING](refactoring.md) (small-step discipline).

| Step                                                        | Detail                                                                                                                                                                                                                          |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pin current behaviour with a test**                       | Characterisation test — even if the current behaviour is buggy. The test's role is "this is what it does today"; the bug fix is a separate change                                                                               |
| **Identify the seam** at which you'll inject the safety net | A function call, an interface, a wrapper                                                                                                                                                                                        |
| **Demonstrate that the test discriminates**                 | A characterisation test passes on the represented baseline; a bug-regression test fails before the fix. Mutate or temporarily revert the relevant behavior when practical to show that the test detects that bounded difference |
| **Then refactor or modify** behind the safety net           | Keep the safety net green for preserved behavior and make the regression test green with the smallest coherent fix                                                                                                              |

For a really hostile codebase: see Michael Feathers' _Working Effectively with Legacy Code_. The strategies (sprout method, sprout class, wrap method, extract interface, etc.) are exactly for this situation.

---

## The Risk Map

Before changing anything, build a one-page mental model of the risk:

| Question                                                                                                          | Answer for this codebase                                  |
| ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| **Critical paths**: what would cause user-visible breakage if it failed?                                          | (Login, payment, data ingest, ...)                        |
| **Single points of failure**: what's the one thing that, if broken, breaks everything?                            | (The DB, the cache, the auth service, the cron, ...)      |
| **Hot spots**: where do most bugs come from? (`git log --grep fix \| ... \| sort \| uniq -c`)                     |                                                           |
| **Hidden state**: where is mutable state not visible from the local code?                                         | (Globals, env vars, files, DB rows, third-party services) |
| **Time-sensitive code**: anything that runs on a schedule, depends on calendar dates, depends on time zones       |                                                           |
| **External contracts**: what does the outside world depend on? (Public API, exports, file formats, event schemas) |                                                           |
| **Migrations in flight**: half-finished structural changes                                                        |                                                           |
| **Operational risk**: deploys, rollbacks, on-call burden                                                          |                                                           |

This map drives where you put effort. Most of it goes to critical paths and hot spots; little of it goes to dormant code with no recent activity.

---

## Audit Dimensions — A Checklist

When formally auditing, run a pass across each of these. Each maps to a deeper reference.

| Dimension                    | What to check                                                                             | Reference                                                  |
| ---------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| **Scope & purpose**          | Does the project's stated purpose match what it does?                                     | [INIT](init.md), [CONTRIBUTING](contributing.md)           |
| **Architecture**             | Layers, modules, bounded contexts, ADRs (or absence)                                      | [ARCHITECTURE](architecture.md)                            |
| **Design principles**        | SOLID, GRASP, coupling/cohesion; smells                                                   | [PRINCIPLES](principles.md), [REFACTORING](refactoring.md) |
| **API design**               | Public APIs versioned? Errors structured? Idempotent?                                     | [API_DESIGN](api-design.md)                                |
| **Data layer**               | Schema, constraints, indexes, migrations, integrity                                       | [DATA](data.md)                                            |
| **Concurrency**              | Race conditions, locks, atomicity, ordering assumptions                                   | [CONCURRENCY](concurrency.md)                              |
| **Performance**              | Hot paths profiled; obvious O(n²); N+1 queries; pool sizing                               | [PERFORMANCE](performance.md)                              |
| **Security**                 | OWASP top 10; authn/authz; secrets handling; threat model                                 | [SECURITY](security.md)                                    |
| **Privacy**                  | What data is collected; lawful basis; retention; processors; jurisdiction                 | [PRIVACY](privacy.md)                                      |
| **Observability**            | Logs, metrics, traces; correlation IDs; alerts; SLOs                                      | [OBSERVABILITY](observability.md)                          |
| **Error handling**           | Caught broadly? Swallowed? Idempotent retries? Timeouts?                                  | [ERROR_HANDLING](error-handling.md)                        |
| **Testing**                  | Coverage by risk, not by line; test smells; characterisation tests                        | [TESTING](testing.md)                                      |
| **Advanced verification**    | Compatibility, accessibility, fuzzing, migration/recovery, fault and statistical evidence | [TESTING_ADVANCED](testing-advanced.md)                    |
| **Accessibility**            | Semantics, keyboard/focus, assistive technology, platform matrix, known exceptions        | [ACCESSIBILITY](accessibility.md)                          |
| **Configuration**            | What's where? Secrets management? `.env.example` complete?                                | [CONFIGURATION](configuration.md)                          |
| **Dependencies/provenance**  | Resolved graph, license, origin/signing, vulnerability triage, update and exit            | [DEPENDENCIES](dependencies.md)                            |
| **Hosting / data residency** | Where is the data? What's the jurisdiction?                                               | [HOSTING](hosting.md), [PRIVACY](privacy.md)               |
| **Legal/contractual duties** | Applicable regimes/contracts, qualified decisions, evidence and review triggers           | [PRIVACY](privacy.md), [ACCESSIBILITY](accessibility.md)   |
| **Cost & sustainability**    | Unit/total cost, dominant resources, retention/transfer, lifecycle impact                 | [COST_AND_SUSTAINABILITY](cost-and-sustainability.md)      |
| **Production evidence**      | Incidents, support cases, SLOs, usage, restore/rollback, real dependency behavior         | [OBSERVABILITY](observability.md), [HOSTING](hosting.md)   |
| **Version control hygiene**  | Atomic commits? Meaningful messages? Tags for releases?                                   | [GIT_AND_VERSIONING](git-and-versioning.md)                |
| **Documentation**            | README, CHANGELOG, ADRs, runbooks, onboarding                                             | [DOCUMENTATION](documentation.md)                          |
| **Code review culture**      | PR sizes; reviewer engagement; CODEOWNERS                                                 | [CODE_REVIEW](code-review.md)                              |

---

## Output of the Audit

The audit produces artefacts, in roughly this priority:

| Artefact                                                              | Purpose                            |
| --------------------------------------------------------------------- | ---------------------------------- |
| **Risk map / threat list**                                            | What hurts most if it goes wrong   |
| **Hot-spot list**                                                     | Where bugs cluster                 |
| **Critical-path documentation**                                       | The user journeys that must work   |
| **ADRs back-filled** for significant existing decisions               | Capture the _why_ before it's lost |
| **`docs/`** structure populated per [DOCUMENTATION](documentation.md) | Living context                     |
| **`.env.example`** completed                                          | Reproducible startup               |
| **Test coverage of critical paths** improved                          | Safety net for future change       |
| **Runbook** for the top 3–5 operational incidents                     | On-call survival                   |
| **Backlog of remediations** prioritised by risk × cost                | Ongoing work                       |

**Do NOT** produce a "rewrite from scratch" document as the audit's conclusion unless the evidence overwhelmingly supports it. See [REFACTORING](refactoring.md) — rewrites are tempting and usually wrong.

---

## "What Should I Change First?"

Once you understand the system, deliver something visible early. Visibility builds trust.

**Good first changes:**

- A meaningful test that pins an important behaviour (the safety net pays itself off).
- A `.env.example` that lets the next person bring the project up.
- Documentation of the one user journey you traced end-to-end.
- A runbook for the top alert.
- A fix for a high-confidence bug **with a regression test**.
- An ADR back-filling the _why_ of a decision you needed to understand.
- A `lychee` (or equivalent) link check on the docs to catch link rot ([DEPENDENCIES](dependencies.md)).
- A vulnerability scan run, with findings filed (not necessarily fixed yet).

**Bad first changes:**

- Reformatting the codebase. (Even with a formatter — it pollutes blame.)
- Renaming "for clarity" without a behaviour change driver.
- "Architectural improvement" PRs that touch every file.
- Dependency major-version bumps unless required.
- Removing dead code (see "the dead code trap" above).
- Switching frameworks.

---

## The "What's Wrong With This Codebase" List — Beware

Every inherited codebase has things that look wrong. **Resist** the impulse to produce a long, righteous list of failings on week one. Even when the list is accurate, it:

- Alienates the people who built the system.
- Mistakes "different style" for "wrong".
- Comes from incomplete understanding — half the items, you'd retract on week three.
- Sets the wrong tone for collaboration.

Instead: keep a private notebook. Things that look concerning. Things you don't understand. Things that seem inconsistent. **Don't act on the list. Revisit it in a month.** Items that still look wrong then — with the benefit of context — are real. Items that resolved themselves through your growing understanding are the ones that would have wasted everyone's time.

---

## Open-Source Audits — Variations

Some specifics for evaluating an open-source project you might depend on or fork:

| Question                            | Where to look                                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Is it alive?**                    | Commit cadence over the last year; issue / PR response time; release cadence                                  |
| **Is it healthy?**                  | Maintainer count; bus-factor; funding; corporate backing or sponsorship                                       |
| **Is it documented?**               | README; docs site; examples; changelog                                                                        |
| **Is it tested?**                   | CI configuration; test coverage; visible test runs                                                            |
| **Is it secure?**                   | `security.md`; CVE history; vulnerability disclosure                                                          |
| **What's the license?**             | Compatible with your use? Copyleft? Source-available with restrictions? — see [DEPENDENCIES](dependencies.md) |
| **How big is the dependency tree?** | Inspect; trim what isn't needed                                                                               |
| **Who else uses it?**               | GitHub "used by"; ecosystem references                                                                        |
| **Is there a roadmap?**             | Or, equivalently, an issue tracker showing direction                                                          |
| **What's the upgrade story?**       | Major version transitions documented?                                                                         |
| **Where's the data, if any?**       | If hosted, see [PRIVACY](privacy.md) and [HOSTING](hosting.md)                                                |
| **What's the trust signal?**        | Code-signing of releases; provenance attestations; SLSA level                                                 |

Forking is acceptable but expensive — see [DEPENDENCIES](dependencies.md) (vendoring/forking section).

---

## Anti-Patterns

| Pattern                                            | Why it fails                                                           |
| -------------------------------------------------- | ---------------------------------------------------------------------- |
| **Day-1 refactor**                                 | No safety net; no understanding; introduces regressions                |
| **Day-1 reformat**                                 | Pollutes `git blame`; makes future archaeology harder                  |
| **"Just clean up while reading"**                  | Mixes recon with change; you can't trust your model                    |
| **Trusting the README more than the code**         | The README is aspirational; the code is the spec                       |
| **Trusting comments more than the code**           | Comments age; code runs                                                |
| **Assuming previous authors were bad**             | Almost always wrong; they had context you don't                        |
| **Big-bang rewrite proposal in week one**          | Premature; almost always wrong; politically expensive                  |
| **Removing dead code without observability**       | Dead code that isn't dead bites                                        |
| **Deleting tests "because they're flaky / wrong"** | The tests may be the only thing pinning critical behaviour             |
| **Setting a strict deadline for "modernisation"**  | Forces premature commitments                                           |
| **Ignoring on-call learning**                      | The on-call experience is the cheapest source of "where the bugs live" |
| **Not talking to users**                           | What seems "obviously wrong" sometimes is what users actually need     |

---

## Diagnostic Framework

| Symptom                         | First steps                                                                                    |
| ------------------------------- | ---------------------------------------------------------------------------------------------- |
| "I don't know where to start"   | Run the project; click through; read the README; pick one user journey to trace end-to-end     |
| "It's all spaghetti"            | Identify the entry points; trace one path; the rest will yield                                 |
| "The tests don't pass"          | Get them passing on `main` (or whichever the base is) before any change                        |
| "I can't run it locally"        | Either the docs are wrong or the environment is undocumented; fix the docs                     |
| "Nobody knows why this is here" | Search `git log -S` for the string; look at the surrounding commit; ask on a channel           |
| "It works but I'm scared of it" | Add observability; characterisation tests; small step refactors at the seams                   |
| "Massive PRs are the norm"      | Start sending small PRs; demonstrate value; cultural change takes time                         |
| "No tests / poor tests"         | Add tests for the change you're making; don't try to retrofit the whole suite                  |
| "No docs"                       | Write the runbook for the next alert; write the ADR for the next decision                      |
| "Stack is unfamiliar"           | Pair-program with the previous maintainer where possible; read the language / framework idioms |

---

## Meta-Question

Inheriting a codebase is the answer to: _what is here, why is it here, and what can I change next without making it worse?_ The discipline is humility — the original author had context, the system shipped, the users are using it. Improvements are possible and important, but they come from understanding first, change second.

The single best thing you can do in the first month is **leave the codebase more understandable than you found it**: an ADR back-filled, a runbook written, a characterisation test added. Compound interest on that pays off for years.

---

_See [REFACTORING](refactoring.md) for the small-step discipline applied to legacy code._
_See [TESTING](testing.md) for characterisation tests._
_See [SECURITY](security.md) / [PRIVACY](privacy.md) / [DATA](data.md) / [ARCHITECTURE](architecture.md) as the topical audit references._
_See [OBSERVABILITY](observability.md) for the instrumentation needed before risky changes._
_See [CONTRIBUTING](contributing.md) / [INIT](init.md) for the per-project docs that capture what you've learned._
*Reference: Michael Feathers, *Working Effectively with Legacy Code* — the canonical handbook for inherited code.*
