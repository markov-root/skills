---
knowledge:
  version: 1
  id: architecture
  summary: Choose and evolve system boundaries, dependencies, data flow, and deployment structure from explicit forces and quality attributes.
  routes:
    [module-system-design, inherited-repository, technology-framework-choice]
---

# architecture.md — System Design Reference

> **Purpose:** Reference for system-level design decisions: how components fit together, where boundaries sit, how data flows, and how to record decisions so they survive the team that made them.
>
> **Read this when:** designing a new system, evaluating an existing one, considering a structural change, or recording an architecturally significant decision.
>
> **Do NOT** apply patterns from this document because they are "best practice." Apply them because they solve a problem the project actually has. See [CONTRIBUTING](contributing.md) Section 3 for what this project deliberately does not apply.

---

## The Core Premise

Architecture is the set of decisions that are **expensive to reverse**. Everything else is just code.

When evaluating a decision, ask:

- **Is this a one-way door or a two-way door?** Two-way: choose quickly and move on. One-way: slow down, document the alternatives, write a decision record.
- **What does this lock us out of?** If you choose SQL, you're not locked out of NoSQL forever, but you've committed to a migration cost. Name the lock-out cost.
- **Who pays the maintenance tax?** Every abstraction has a maintenance tax. If the team paying it doesn't see the benefit, it will rot.

---

## Architecturally Significant Decisions (ASDs)

A decision is architecturally significant if **any** of these are true:

| Criterion                                | Examples                                                   |
| ---------------------------------------- | ---------------------------------------------------------- |
| It is expensive to reverse               | Database engine, primary language, deployment model        |
| It constrains future decisions           | Sync vs async core, monolith vs services, framework choice |
| It crosses team or service boundaries    | Auth strategy, API style, event schema                     |
| It defines a quality attribute trade-off | Consistency vs availability, latency vs throughput         |
| It changes operational responsibility    | "We now run a database"                                    |
| It introduces a new external dependency  | Third-party service, new library family                    |

**Project default:** Record expensive, cross-boundary, surprising, or repeatedly disputed decisions
in an ADR or equivalent durable decision system. Small/reversible decisions may be captured in a
task, review, or code contract. Lack of an ADR does not make history unreal; it makes rationale and
ownership harder to recover.

---

## Architecture Decision Records (ADRs)

An ADR is a concise, durable record of one significant decision. Markdown files under `docs/adr/`
with sequential identifiers are a useful project convention, not part of the definition. A project
may use another indexed, versioned decision system when participants can access it and stable links,
ownership, export, and supersession are governed.

### Template

```markdown
# ADR-NNNN: <Short title in imperative mood>

- **Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD
- **Deciders:** Names
- **Tags:** database, security, frontend, ...

## Context

What is the problem? What forces are at play (technical, organisational,
political)? What constraints exist? What did we know at the time?

## Decision

What did we decide, in active voice? ("We will use PostgreSQL", not
"PostgreSQL was chosen".)

## Alternatives Considered

For each alternative:

- What it is.
- Why we rejected it.
- Under what conditions it would have been correct.

## Consequences

- **Positive:** What this enables.
- **Negative:** What this costs us; what we are now responsible for.
- **Neutral:** What changes about how we work.

## Compliance

How will we know the decision is being followed? (Code review checklist,
linter rule, architecture test, manual audit?)

## Revisit When

The conditions under which this decision should be reconsidered.
```

### Rules

- **Keep accepted decision bodies stable.** Permit explicit status, correction, and supersession
  metadata under the project's ADR policy. Reverse or materially re-scope a decision through a new
  linked record so the prior context remains recoverable.
- **One decision per ADR.** If you can't title it in one sentence, split it.
- **Write it when you decide, not when you remember.** The point is to capture the _thinking_, not the artefact.
- **A rejected option with reason is worth more than the chosen option without reason.** The "why not" prevents the same conversation in six months.
- **Preserve deliberation separately when compression loses value.** Link experiments, extended
  alternatives, dissent, transcripts worth retaining, and unresolved questions from a
  research/deliberation record. The ADR remains the decision authority; the linked artifact
  preserves how the group reached it.

---

## Architectural Fitness Functions — Make Decisions Executable

An ADR records architectural intent. A **fitness function** checks whether the running system or
codebase still satisfies that intent. It is an automated or deliberately scheduled test of an
architectural characteristic: dependency direction, compatibility, resilience, security,
performance, operability, or another quality attribute.

Without a check, “the UI never imports persistence code” is advice. With an import-boundary test in
CI, it is an invariant.

### What deserves a fitness function

Create one when a property is:

- Important enough that silent drift would be expensive.
- Repeatedly relevant to ordinary changes.
- Objective enough to check reliably.
- Cheaper to automate than to rediscover in review or production.

Do not automate taste. “Modules should feel elegant” is not a fitness function. “No dependency cycle
may cross these package boundaries” can be.

### A portfolio, not one score

| Characteristic       | Example invariant                                                      | Cheapest useful check                                                |
| -------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Dependency direction | Domain code does not import web, ORM, or vendor adapters               | Import/layer rule in unit tests or a dependency analyser             |
| Cycles               | Production modules contain no dependency cycles                        | Static dependency-graph check                                        |
| API compatibility    | Existing clients continue to validate against the schema               | OpenAPI/protobuf/schema compatibility diff                           |
| Data evolution       | A deploy can run against both old and expanded schemas during rollout  | Migration compatibility test against previous and next schema states |
| Security             | Sensitive routes require the expected policy                           | Route inventory test plus security-focused integration tests         |
| Supply chain         | Only approved registries and licences enter the build                  | Lockfile, provenance, vulnerability, and licence policy checks       |
| Performance          | The critical operation remains within its measured budget              | Stable benchmark or load test with a justified regression threshold  |
| Resilience           | A dependency timeout does not exhaust the worker pool                  | Fault-injection or integration test with bounded time                |
| Operability          | Every paging alert links to a runbook; telemetry fields remain present | Configuration/schema validation in CI                                |
| Repository hygiene   | Generated files match their sources; docs links resolve                | Regenerate-and-diff and link checks                                  |

### Worked examples

**Layer boundary**

```text
Allowed:
  interface -> application -> domain
  infrastructure -> application/domain ports

Forbidden:
  domain -> framework
  domain -> database driver
  application -> HTTP handler
```

Encode that rule with the ecosystem's dependency analyser or a small import-graph test. Keep the
rule beside the documented boundary in `contributing.md`; run it on every change that can affect
imports.

**Public contract**

```text
Given the last released API schema
When the proposed schema is generated
Then removed fields, narrowed types, and changed semantics are reported as breaking
```

The tool does not decide whether a breaking change is forbidden. It makes the change visible so the
versioning and deprecation policy can decide.

**Performance budget**

```text
Critical operation: import 10,000 representative records
Environment: pinned CI runner or dedicated benchmark host
Budget: p95 <= 8 s and peak memory <= 500 MiB
Policy: warn on noisy evidence; block only on a reproducible regression
```

A threshold without a controlled workload is theatre. Record the fixture, environment, variance,
and reason for the budget.

### Design rules

1. **Trace each check to a decision or quality attribute.** Name the ADR or project invariant.
2. **Fail with a repairable message.** State which boundary was crossed and where its rule lives.
3. **Prefer reproducible checks when the property is deterministic.** Preserve and investigate
   flakes; represent expected statistical variation, unavailable inputs, and inconclusive results
   explicitly rather than rerunning until green.
4. **Use the lowest-cost feedback loop.** Static checks before unit tests; unit before integration;
   scheduled production probes where pre-merge testing cannot answer the question.
5. **Calibrate enforcement.** A new or noisy check may report first, then block after its signal is
   trusted.
6. **Version the check with the architecture.** When an ADR is superseded, update or retire its
   fitness function in the same change.
7. **Test the checker.** Seed a known violation or fixture so a silently broken rule cannot report
   permanent success.

### Failure modes

| Failure                                 | Why it fails                                        | Correction                                             |
| --------------------------------------- | --------------------------------------------------- | ------------------------------------------------------ |
| One composite “architecture score”      | Hides which property regressed and invites gaming   | Keep independently named checks                        |
| Brittle file-count or line-count gates  | Measures proxies, not structure                     | Use as review signals unless tied to demonstrated risk |
| Threshold copied from another project   | No relationship to this workload or quality ranking | Establish a baseline and record the local reason       |
| Check exists only on a developer laptop | Agents and CI can bypass it accidentally            | Put the canonical command in CI and `contributing.md`  |
| Documentation-only boundary             | Reviewers eventually miss it                        | Automate the highest-cost violations                   |
| Permanent exception list                | Becomes an architecture landfill                    | Give exceptions an owner, reason, and review trigger   |

**Diagnostic:** For every statement containing “must never cross,” “must remain compatible,” or
“must stay below,” ask: _what detects a violation before users do?_

---

## Quality-Attribute Scenarios

“Fast,” “secure,” “accessible,” “scalable,” and “maintainable” are not testable until grounded.
Describe consequential qualities as:

| Element     | Question                                                               |
| ----------- | ---------------------------------------------------------------------- |
| Source      | Who or what causes the stimulus?                                       |
| Stimulus    | What event, change, failure, load, or user action occurs?              |
| Environment | Normal, peak, degraded, attack, migration, offline, or recovery state? |
| Artifact    | Which component, data, or workflow is affected?                        |
| Response    | What should the system do?                                             |
| Measure     | What observable threshold or evidence decides whether it succeeded?    |

Rank scenarios and expose conflicts: stronger consistency may cost latency; isolation may cost
money; caching may harm freshness/privacy; animation may harm accessibility. Include correctness,
changeability, security, privacy, accessibility, operability/recovery, compatibility, performance,
monetary cost, and sustainability where they can materially change design.

---

## The C4 Model — Levels of Description

Most architecture diagrams fail because they mix levels. The C4 model says: pick a level, stay there.

| Level                 | Audience                    | Shows                                                                                          | Hides                           |
| --------------------- | --------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------- |
| **1. System Context** | Anyone                      | The system as a black box; external users and systems it talks to                              | All internal structure          |
| **2. Container**      | Devs, ops                   | Deployable/runnable things (web app, API, database, queue) and how they communicate            | Internal code structure         |
| **3. Component**      | Devs in a container         | Major modules/components inside one container, and their relationships                         | Class-level detail              |
| **4. Code**           | Devs editing that component | UML-level class/sequence diagrams. **Usually not worth drawing by hand** — generate from code. | Nothing — but often unnecessary |

**Diagnostic:** If your diagram has both "User" and "PostgreSQL connection pool" on it, you're mixing levels. Split it.

**Practical advice:** Maintain levels 1 and 2 by hand. Level 3 only for components that are non-obvious. Level 4 essentially never — read the code.

---

## Layered Architecture

```
Presentation   (HTTP handlers, CLI, UI)
    ↓
Application    (use cases, orchestration, transactions)
    ↓
Domain         (business rules, entities, value objects)
    ↑
Infrastructure (DB, queues, HTTP clients, file system)
```

**Dependency rule:** Domain knows nothing about infrastructure. Infrastructure depends on domain interfaces, not the other way around. Application orchestrates between them. Presentation is replaceable.

**When to use:**

- Non-trivial business logic exists.
- The team has more than one person working in parallel.
- The system is expected to outlive any one framework.

**When NOT to use:**

- The whole system is glue (CRUD over a database, ETL pipeline).
- The "business logic" is "store this row".
- You have < ~1000 lines of code.

**Failure modes:**

| Anti-pattern                 | What it looks like                                          | Why it hurts                                          |
| ---------------------------- | ----------------------------------------------------------- | ----------------------------------------------------- |
| **Layer bypass**             | Controller queries the database directly                    | Defeats the layering; spreads SQL across the codebase |
| **Anemic domain**            | Domain objects are bags of getters; logic lives in services | The domain layer adds ceremony without value          |
| **Leaky abstraction**        | Repository returns ORM-specific exceptions                  | Callers couple to the storage tech                    |
| **Upside-down dependencies** | Domain `import`s from infrastructure                        | The domain becomes unrunnable in isolation            |

---

## Hexagonal / Ports and Adapters

The domain sits in the centre. Everything else is a **port** (an interface the domain owns) implemented by an **adapter** (the concrete tech).

```
   [HTTP adapter] →┐                ┌→ [Postgres adapter]
                   ├→ [Port] → Core ↔ [Port] →
   [CLI adapter] →┘                  └→ [In-memory adapter]
```

**Use when:** you need to swap the delivery mechanism (HTTP ↔ CLI ↔ message bus) or the persistence (real DB ↔ fake) symmetrically — particularly when testing the domain in isolation matters.

**Cost:** Boilerplate and translation. Create a port for a domain capability or meaningful
test/vendor boundary, not mechanically for every library call.

**Heuristic:** A one-implementation interface may still buy domain vocabulary, ownership,
substitutability in tests, capability restriction, or vendor isolation. If it merely mirrors the
implementation API and no consumer-level contract is clearer, it probably adds indirection.

---

## Event-Driven Architecture

```
Producer → [Event Bus] → Consumer A
                       → Consumer B (added later, producer unaware)
```

**Use when:**

- Multiple consumers of the same fact.
- Producer should not know who cares.
- Multiple consumers or time-decoupling justify an event contract.
- Time-decoupling matters (consumer can be down while producer runs).

**Do NOT use when:**

- You actually need a synchronous response.
- Consistency between producer and consumer is required immediately.
- The team has never debugged a distributed system before.

**Trade-offs you sign up for:**

| Property                        | Consequence                                                      |
| ------------------------------- | ---------------------------------------------------------------- |
| Eventual consistency by default | "Just refresh" is now a feature                                  |
| Debugging is _hard_             | A single request leaves traces across N services                 |
| Events become a contract        | Renaming an event field can break consumers you don't know exist |
| Replay matters                  | "How do I re-process the last 24 hours?" must have an answer     |

**Patterns to learn before adopting:** idempotent consumers, outbox pattern, schema registry, dead-letter queues.

An event bus does not provide an audit log for free. An audit record requires explicit coverage,
durability, completeness, actor/subject identity, ordering semantics, tamper protection, access
control, retention, privacy, replay/reconciliation, and evidence that every audited path emits it.

---

## Microservices vs Monolith

**House preference:** Start with the simplest deployable topology that meets the ranked quality
attributes. A modular monolith is often the best default for a small team with uncertain boundaries;
regulatory isolation, independent ownership/deployment, edge/offline constraints, or scaling may
justify services earlier.

**Move to services when:**

| Reason                           | What "good" looks like                                                |
| -------------------------------- | --------------------------------------------------------------------- |
| Independent scaling needs        | One module dominates CPU/RAM and others don't                         |
| Independent deployment           | Teams genuinely block each other on release cadence                   |
| Independent technology           | One module _needs_ a different runtime (e.g., GPU, JVM, embedded)     |
| Hard ownership boundaries        | Different teams, different on-call, different SLAs                    |
| Bounded contexts have stabilised | You know where the seams _actually_ are, not where you wish they were |

**The distributed-monolith trap:** Services that share a database, deploy together, fail together, and require each other to be up. You've paid the cost of distribution and bought none of the benefits.

**Rule of thumb:** If "deploy service A independently of service B" is not a thing you actually do, they are not separate services. They are a monolith spread across two binaries.

---

## Modular Monolith

A modular monolith has one deployable/runtime boundary with internally enforced modules:

- domain ownership and public module APIs;
- no imports of another module's internals;
- explicit transaction and data ownership;
- in-process calls where synchronous semantics fit;
- events/interfaces at real module seams;
- fitness tests for cycles and forbidden dependencies.

It preserves simple deployment and transactions while making later extraction possible where
measured need emerges. It fails when “modules” are folders over a shared mutable model with
unrestricted imports.

---

## Frontend, Mobile, and Desktop Architecture

Client applications have architecture too: state ownership, navigation, rendering, accessibility,
offline/sync, storage, security boundary, platform integration, update/version support, and backend
compatibility.

- Separate server-authoritative, client-cache, draft/UI, and durable offline state.
- Model synchronization conflicts and interrupted operations explicitly.
- Keep platform adapters around domain/application behavior when multiple platforms share it.
- Use a backend-for-frontend when a client class has distinct aggregation, latency, security, or
  evolution needs; do not turn it into an unowned duplicate domain.
- Treat forced/slow client upgrades and app-store review as deployment constraints.

Read [accessibility](accessibility.md) and [advanced testing](testing-advanced.md) for interaction and
compatibility evidence.

---

## Multi-Tenancy

Choose isolation from consequence and regulation:

| Model                       | Trade-off                                                                        |
| --------------------------- | -------------------------------------------------------------------------------- |
| Shared rows with tenant key | Efficient; every query/cache/job/search/log path must preserve tenant scope      |
| Schema/database per tenant  | Stronger operational boundary; migration, connection, and fleet cost increase    |
| Account/project isolation   | Flexible hierarchy; authorization and billing ownership become central contracts |
| Dedicated deployment        | Strongest infrastructure separation; highest provisioning and update burden      |

Define tenant identity propagation, data/key/cache/queue/search isolation, admin/support access,
noisy-neighbor controls, backups/restore, migration, deletion/export, and tests that try cross-tenant
access. A UUID or separate schema is not authorization by itself.

---

## Plugin and Extension Architecture

A plugin boundary is an untrusted or semi-trusted capability contract:

- versioned manifest/API and compatibility range;
- declared permissions/capabilities, resource budgets, and network/filesystem policy;
- isolation/sandbox or explicit in-process trust;
- lifecycle, dependency, update, signing/provenance, migration, and uninstall/data cleanup;
- failure containment and observability;
- deterministic conformance tests and deprecation path.

Do not promise a plugin ecosystem by exposing internal classes. Stabilize the smallest extension
contract after real use cases and design for a malicious, buggy, slow, or abandoned extension.

---

## Pipe and Filter

```
Source → [Filter A] → [Filter B] → [Filter C] → Sink
```

Each filter is a pure transformation. State lives in the pipeline, not the filters.

**Use when:** Data processing, ETL, build pipelines, image processing, compilers, anything with sequential transformations.

**Failure modes:**

- Filters that maintain state (no longer pure → no longer composable).
- A "filter" that's really an orchestrator (probably wants a different pattern).
- Backpressure ignored (fast producer + slow consumer = OOM).

---

## CQRS and Event Sourcing — Use With Care

**Command-Query Responsibility Segregation:** Separate models for reads and writes. Useful when read and write loads are radically different, or when projections benefit from denormalisation.

**Event Sourcing:** Store events, not state. Current state is a fold over events.

**Both are advanced patterns.** The maintenance burden is real. Do not adopt because they sound principled. Adopt because:

- You need a full audit trail by law or contract.
- You need to time-travel (debug what state existed at time T).
- Your write model and read model genuinely diverge.

Otherwise, a normal database is the right answer.

---

## Bounded Contexts (Domain-Driven Design, lightly)

A **bounded context** is a region of code where a word has one meaning. Outside that region, the same word may mean something different.

Example: "Customer" in billing is a payment relationship with an address. "Customer" in shipping is a delivery target with a tolerance for late arrival. The same row in the database, but different _models_.

**Why this matters:** When two contexts share a model, every change to that model is a negotiation between both sides. Bounded contexts let each side evolve independently.

**Signs you have a bounded-context problem:**

- The same noun behaves differently depending on which part of the system uses it.
- "We need to add a field" turns into a multi-team conversation.
- A class has accumulated fields that only some callers use.

**Solution:** Two models. Translate at the boundary (anti-corruption layer).

---

## One-Way vs Two-Way Doors

A useful framing from Jeff Bezos:

- **Two-way door:** Easily reversed. Choose quickly. Examples: a function name, a folder layout, a button colour.
- **One-way door:** Hard or impossible to reverse. Slow down. Examples: a public API URL, a database schema in production, a deployed event shape, a chosen license.

**Spend deliberation budget on one-way doors.** Don't argue for a week about a two-way door.

**Diagnostic:** If you can ship a change and revert it within a day with no external impact, it's two-way. Otherwise, treat it as one-way until proven otherwise.

---

## Conway's Law

> _Any organisation that designs a system will produce a design whose structure is a copy of the organisation's communication structure._

Implications:

- Three teams cannot easily build two services. The third service appears, or one of them becomes a god service.
- A monolith maintained by one person scales fine until person two appears, and then the seams must form.
- **Inverse Conway manoeuvre:** Design the team structure you want, and the system structure follows.

**For a solo developer:** This means you can pick _any_ boundary, but you will _enforce_ none, because there is no second team to push back on a leaky one. Be deliberate about boundaries you commit to.

---

## Data Flow and Source of Truth

For every important piece of data, answer:

| Question                                            | Why                                                                                                           |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| What is **authoritative** for this datum/invariant? | When stores, external authorities, events, and projections disagree, what reconciles or wins?                 |
| Where are the **caches and projections**?           | What goes stale, and how is it refreshed?                                                                     |
| What is the **invalidation strategy**?              | "Cache invalidation is one of the two hardest problems in CS" — Phil Karlton                                  |
| Who can **write** to it?                            | If many can write, you need a conflict-resolution story                                                       |
| What is its **retention**?                          | How long do we keep it, and what triggers deletion? (See [PRIVACY](privacy.md) for the legal/ethical version) |

---

## Synchronous vs Asynchronous Communication

| Synchronous (RPC, HTTP request/response) | Asynchronous (queue, event)       |
| ---------------------------------------- | --------------------------------- |
| Simple mental model                      | Time-decoupled                    |
| Easy to debug                            | Resilient to consumer downtime    |
| Caller blocks on callee                  | Caller is unblocked               |
| Failure cascades                         | Failures absorbed (if idempotent) |
| Strong consistency easier                | Eventual consistency by default   |
| **Default for queries**                  | **Default for facts/events**      |

**Anti-pattern:** Synchronous "fire and forget" (HTTP POST you don't await). Use a queue.

**Anti-pattern:** Synchronous chain of 5 calls. Latency multiplies, failure probability stacks, debugging becomes a tree.

---

## Failure Modes — Build the System That Handles Them

Every distributed boundary is a failure boundary. For each:

| Failure mode                            | Pattern                                                                                                         |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Slow callee                             | Caller deadline/cancellation, concurrency bounds, and tested degraded behavior appropriate to the call contract |
| Transient failure                       | **Retry with exponential backoff and jitter.** Cap the retries.                                                 |
| Persistent failure                      | **Circuit breaker.** Stop calling for a window.                                                                 |
| One dependency taking everyone down     | **Bulkhead.** Isolate resource pools per dependency.                                                            |
| Whole system down                       | **Graceful degradation.** Return a useful partial response.                                                     |
| Repeated processing of the same message | **Idempotency.** Same input + same key ⇒ same effect.                                                           |
| Cascade from one slow service           | **Load shedding.** Drop low-priority work under stress.                                                         |

**A retry without idempotency is a bug-amplifier.** Pair them.

---

## Cross-Cutting Concerns — Where They Live

| Concern                  | Where it lives                                                             | See                                 |
| ------------------------ | -------------------------------------------------------------------------- | ----------------------------------- |
| Authentication           | A boundary (API gateway, middleware) — never sprinkled in handlers         | [SECURITY](security.md)             |
| Authorisation            | The domain (it knows who is allowed) or a policy module — not the database | [SECURITY](security.md)             |
| Logging                  | Pervasive but structured. One logger per module.                           | [OBSERVABILITY](observability.md)   |
| Metrics                  | Boundaries and important state transitions                                 | [OBSERVABILITY](observability.md)   |
| Tracing                  | Across every async boundary                                                | [OBSERVABILITY](observability.md)   |
| Caching                  | The repository / adapter layer — _never_ in domain logic                   | [PERFORMANCE](performance.md)       |
| Retries                  | The adapter — domain doesn't know about retries                            | [ERROR_HANDLING](error-handling.md) |
| Rate limiting            | The boundary — earliest possible point                                     | [SECURITY](security.md)             |
| Configuration            | Read once at startup, validated, then immutable                            | [CONFIGURATION](configuration.md)   |
| Feature flags            | A first-class concept — see [CONFIGURATION](configuration.md)              | [CONFIGURATION](configuration.md)   |
| Privacy / data residency | Architecturally enforced — not "we'll be careful"                          | [PRIVACY](privacy.md)               |

---

## Anti-Patterns at the Architecture Level

| Name                          | What it is                                             | Why it fails                                            |
| ----------------------------- | ------------------------------------------------------ | ------------------------------------------------------- |
| **Big Ball of Mud**           | No discernible structure                               | Every change touches everything                         |
| **Distributed Monolith**      | Services that must deploy together                     | Costs of distribution, none of the benefits             |
| **God Service**               | One service that does everything                       | Single point of failure, contention, deploy risk        |
| **Database as Integration**   | Multiple services read/write the same tables           | Tightest possible coupling, masquerading as decoupling  |
| **Shared Library Hell**       | Common code in a library imported by every service     | A library upgrade becomes a coordinated deploy          |
| **Anaemic Microservices**     | Services so small that one feature crosses ten of them | Coordination cost crushes feature velocity              |
| **Premature Abstraction**     | Interfaces with one implementation, "for flexibility"  | Cost paid, benefit never realised                       |
| **Framework as Architecture** | "Our architecture is Rails"                            | The framework is a delivery mechanism, not a design     |
| **Architecture by Resume**    | New tech because it's trendy                           | Maintenance burden + onboarding cost + risk for novelty |

---

## Architecture Reviews — Questions to Ask

When reviewing an existing system, ask these in order:

1. **What does this system do, in one sentence?** If no one agrees, the problem is upstream.
2. **What are its quality attributes, ranked?** (Correctness, clarity, changeability, testability, operability, performance, security, privacy.) Different rankings imply different designs.
3. **What is authoritative for each important datum/invariant, and how do other stores reconcile?**
4. **What are the boundaries, and who enforces them?**
5. **What changes together?** Things that change together should live together.
6. **What is the deployment unit?** What gets shipped, by whom, how often, with what rollback?
7. **What does production failure look like, and how is it observed?**
8. **What is the threat model?** (See [SECURITY](security.md).)
9. **What data is collected, why, and how long is it kept?** (See [PRIVACY](privacy.md).)
10. **What did the team explicitly decide _not_ to do, and why?** (The ADRs answer this. If there are none, the team did not _decide_ — they drifted.)

---

## Diagnostic Framework

| Symptom                                          | Likely architectural cause                                                               |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Every feature touches many files                 | Boundaries don't match change patterns                                                   |
| Releases are scary                               | No isolation; no rollback story; insufficient observability                              |
| Tests are slow or impossible to run              | Domain coupled to infrastructure                                                         |
| Adding a developer slows the team down           | No bounded contexts; everyone steps on everyone                                          |
| Database changes require downtime                | Schema treated as private, but everyone reads it                                         |
| A single dependency outage takes the system down | Missing timeouts, retries, fallbacks                                                     |
| Production bugs can't be reproduced locally      | Environment-specific state, hidden dependencies, missing observability                   |
| "We need to rewrite it"                          | Architecture has drifted from the team's mental model; document the model, then evaluate |

---

## Meta-Question

Architecture is the answer to: _what decisions, made now, will make the next ten decisions easier?_ If a decision doesn't make future work easier, it isn't an architectural decision — it's just code, and it can be changed later.

Capture the **why**, not the **what**. The what is in the code. The why is in your head, and it leaves with you.

---

_See [PRINCIPLES](principles.md) for class- and module-level design._
_See [SECURITY](security.md), [PRIVACY](privacy.md), [OBSERVABILITY](observability.md), [PERFORMANCE](performance.md) for the cross-cutting concerns._
_See [CONTRIBUTING](contributing.md) Section 4 for the project-specific decision log._
