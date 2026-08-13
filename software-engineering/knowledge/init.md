---
knowledge:
  version: 1
  id: init
  summary: Bootstrap a project by making outcomes, ownership, runtime, structure, policy, verification, documentation, and release assumptions explicit.
  routes: [new-project]
---

# init.md — Project Bootstrap Checklist

> **Purpose:** This is a day-0 thinking tool. Read it once at project start, fill in the blanks, then move on. It is not a rulebook.
>
> **For agents:** Do not apply principles from this document retroactively. This is a scoping exercise, not an engineering mandate. The output of this document is a calibrated `contributing.md` for the project.
>
> **Starting from scratch?** Use this whole document.
> **Inheriting a codebase?** Read [`audit-inherited.md`](audit-inherited.md) **first** — the discipline is reconnaissance before construction. Then use this document to back-fill the scoping that the previous owner never wrote down.

---

## 0. The One-Sentence Pitch

What does this thing do?

```
[Fill in: one sentence. Example: "Scrapes research articles from multiple sources,
organizes them into projects, and provides a web UI for curation."]
```

Who uses it?

- [ ] Just me
- [ ] Small group (2–5 people)
- [ ] Internal team
- [ ] External users

How long will it live?

- [ ] Throwaway prototype (< 1 week)
- [ ] Active project (weeks to months)
- [ ] Maintained indefinitely

What's the cost of being wrong?

- [ ] Annoying — I redo some work
- [ ] Expensive — I lose data or time
- [ ] Critical — safety, security, or financial harm

---

## 1. Scope Calibration

### What this IS

```
[Example: "A research curation pipeline with scraping, project organization,
and a web UI for human oversight."]
```

### What this IS NOT (explicit boundaries)

| Not In Scope                                 | Why                                                        |
| -------------------------------------------- | ---------------------------------------------------------- |
| [Example: "RAG / vector search"]             | ["Full-context injection is preferred for deep synthesis"] |
| [Example: "Multi-user auth"]                 | ["Single user, single VM"]                                 |
| [Example: "Public API / external consumers"] | ["Internal tool only"]                                     |

> **Rule:** Add things here aggressively. Every item not in scope is a decision you don't have to make.

### The One Thing That Must Work Perfectly

```
[What is the core value? If everything else is broken, this one thing must work.
Example: "Scraping and storing articles without data loss."]
```

### What Can Be "Good Enough"

```
[What is acceptable at 80% quality? Example: "Mobile UX — usable but not polished."]
```

---

## 2. Boundary Decisions

Document each with rationale. A decision without a reason will be second-guessed.

```
Decision format:
  We choose [X] over [Y] on [DATE] because [reason].
  We will revisit this decision when [condition].
```

| Area                 | Choice | Alternatives Rejected | Rationale | Revisit When |
| -------------------- | ------ | --------------------- | --------- | ------------ |
| Database             |        |                       |           |              |
| Auth                 |        |                       |           |              |
| Frontend             |        |                       |           |              |
| Testing              |        |                       |           |              |
| Deployment           |        |                       |           |              |
| Language / Framework |        |                       |           |              |

---

## 3. Risk Inventory

### External Dependencies

| Dependency | What It Does | Likelihood of Breakage | Impact If Broken | Mitigation |
| ---------- | ------------ | ---------------------- | ---------------- | ---------- |
|            |              |                        |                  |            |

### Data

| Data Type | Stored Where | What Happens If Lost | Backup Strategy |
| --------- | ------------ | -------------------- | --------------- |
|           |              |                      |                 |

### Personal Data & Jurisdiction (see [`privacy.md`](privacy.md), [`hosting.md`](hosting.md))

The question to answer up-front, before architectural lock-in: **does this project collect, process, or store personal data — and if so, under whose laws does it live?**

| Question                                                                                                      | Answer for this project |
| ------------------------------------------------------------------------------------------------------------- | ----------------------- |
| Does this collect personal data? (Names, emails, IPs, location, behavioural, communications, health, etc.)    |                         |
| If yes — what's the lawful basis? (Consent / contract / legal obligation / legitimate interest)               |                         |
| If yes — what's the retention?                                                                                |                         |
| Where will the data physically live? (Provider, region)                                                       |                         |
| What provider role, operator/key access, contract, transfer mechanism, and dated jurisdiction analysis apply? |                         |
| What third-party services see user data? (See processor inventory in [`privacy.md`](privacy.md))              |                         |

> **Rule:** Data minimisation is the cheapest defence. Don't collect what you don't need. Pseudonymise immediately if you must. Encrypt at rest. Set a retention period from day 0.

### Maintenance Burden

What will future-me (or a future agent) hate about this?

```
[Example: "The Substack scraper uses Selenium — brittle, slow, hard to debug."]
```

---

## 4. Quality Attributes (Ranked)

Not all attributes matter equally. Rank the applicable set; ties are allowed and omitted attributes
need a reason when they could materially change the design.
Turn consequential rankings into contextual outcomes, requirements, or acceptance criteria using
[`requirements and traceability`](requirements-and-traceability.md); an attribute name alone is not
a measurable target.

| Attribute              | Rank | Notes                                                                |
| ---------------------- | ---- | -------------------------------------------------------------------- |
| Correctness            |      | Does it do what it should?                                           |
| Clarity                |      | Can someone understand it quickly?                                   |
| Changeability          |      | Can it evolve without falling apart?                                 |
| Testability            |      | Can we verify it works confidently?                                  |
| Operability            |      | Can we run, monitor, and fix it?                                     |
| Performance            |      | Fast enough for the use case?                                        |
| Security               |      | Resilient to abuse / attack? (See [`security.md`](security.md))      |
| Privacy                |      | Minimal data; respectful retention? (See [`privacy.md`](privacy.md)) |
| Accessibility          |      | Can people use it across declared access needs/platform tools?       |
| Reliability & recovery |      | Does it degrade, recover, and preserve state within objectives?      |
| Compatibility          |      | Which clients/platforms/versions must interoperate?                  |
| Cost                   |      | Is total and unit monetary/resource cost within budget?              |
| Sustainability         |      | Are workload, energy/carbon, data, and hardware lifecycle measured?  |

> **Rule:** You cannot maximize all of them. The ranking tells you which principles to privilege when they conflict.
>
> **Note:** Security and privacy _floors_ exist regardless of rank. Even a personal tool with personal data has minimum obligations — see the relevant references.

---

## 5. Quick Start for This Project

- [ ] Copy [`contributing.md`](contributing.md) into the project root and calibrate it.
- [ ] Fill in Section 1 (Scope & Calibration) of `contributing.md` based on this document.
- [ ] Give consequential outcomes, constraints, assumptions, non-goals, and acceptance criteria
      stable ownership using [`requirements and traceability`](requirements-and-traceability.md).
- [ ] Fill in Section 3 (Principles Not Applied) — be specific and honest.
- [ ] Fill in Section 5 (Project Structure) with the ACTUAL structure, not an ideal one.
- [ ] Set up version control. See [`git-and-versioning.md`](git-and-versioning.md) for commit / branching conventions.
- [ ] Create `.env.example` with all config variables, per [`configuration.md`](configuration.md).
- [ ] Choose or document the project's documentation roles, authority, indexes, and storage. Adopt
      the [`documentation-structure`](documentation-structure.md) profile only when it fits.
- [ ] Implement the smallest working version of the core feature.
- [ ] Do NOT apply any principle that doesn't solve a problem you HAVE. See [`principles.md`](principles.md) and [`contributing.md`](contributing.md) Section 3.
- [ ] Preserve material experiments, rejected alternatives, and open questions in the project's
      indexed research/deliberation or lessons role; link concise decisions to that history.
- [ ] Add a link checker (`lychee` or equivalent) when repository documentation is a relied-upon
      surface; run it locally until the project has an authorized CI path — see
      [`dependencies.md`](dependencies.md).

---

## 6. First Task Anti-Patterns

Do NOT do these on day 0:

- [ ] Build a broad CI/CD platform before a working vertical slice identifies useful checks. A
      minimal existing or ecosystem-provided test workflow can still be appropriate when its cost is
      low and its feedback is already required.
- [ ] Create `domain/`, `services/`, `adapters/` directories for a CRUD app
- [ ] Abstract on the first duplication (wait for the third)
- [ ] Polish low-level tests that pin a volatile implementation; verify volatile code with the
      cheapest stable behavior-level smoke, integration, or acceptance test instead
- [ ] Optimize for a scale you don't have
- [ ] Add a framework because "we might need it later"
- [ ] Select a personal-data provider from region or headquarters alone without reviewing actual
      roles, access, contract, transfers, operations, and exit — see [`privacy.md`](privacy.md) and
      [`hosting.md`](hosting.md)
- [ ] Skip writing down _why_ you chose what you chose — ADRs cost minutes and pay back for years (see [`architecture.md`](architecture.md))

---

## 7. Where To Look Next

The knowledge library this document lives in covers each topic above in depth. Read selectively, based on what the project actually needs (per Section 4's ranking):

| Concern                                | Reference                                                  |
| -------------------------------------- | ---------------------------------------------------------- |
| Design vocabulary                      | [`principles.md`](principles.md)                           |
| Architecture / ADRs                    | [`architecture.md`](architecture.md)                       |
| Technology / framework choice          | [`technology-selection.md`](technology-selection.md)       |
| Repository/module ownership            | [`repository-structure.md`](repository-structure.md)       |
| Threat model / authn / authz / secrets | [`security.md`](security.md)                               |
| Personal data, retention, jurisdiction | [`privacy.md`](privacy.md)                                 |
| Hosting & deployment                   | [`hosting.md`](hosting.md)                                 |
| Schema, transactions, migrations       | [`data.md`](data.md)                                       |
| Logs / metrics / traces / alerts       | [`observability.md`](observability.md)                     |
| API design & versioning                | [`api-design.md`](api-design.md)                           |
| Errors, retries, timeouts              | [`error-handling.md`](error-handling.md)                   |
| Races, locks, distributed coordination | [`concurrency.md`](concurrency.md)                         |
| Latency, scale, caching                | [`performance.md`](performance.md)                         |
| Configuration, secrets, flags          | [`configuration.md`](configuration.md)                     |
| Supply chain & link rot                | [`dependencies.md`](dependencies.md)                       |
| Test strategy                          | [`testing.md`](testing.md)                                 |
| Advanced test domains / operations     | [`testing-advanced.md`](testing-advanced.md)               |
| Accessibility engineering              | [`accessibility.md`](accessibility.md)                     |
| Cost and sustainability                | [`cost-and-sustainability.md`](cost-and-sustainability.md) |
| Debugging discipline                   | [`debugging.md`](debugging.md)                             |
| Refactoring safely                     | [`refactoring.md`](refactoring.md)                         |
| Code review practice                   | [`code-review.md`](code-review.md)                         |
| Version control hygiene                | [`git-and-versioning.md`](git-and-versioning.md)           |
| Doc organisation                       | [`documentation.md`](documentation.md)                     |
| Strategic roadmap shape                | [`roadmap.md`](roadmap.md)                                 |
| Taking over a codebase                 | [`audit-inherited.md`](audit-inherited.md)                 |

---

_Last updated: [DATE]_
_Update this when the project's scope or constraints change._
