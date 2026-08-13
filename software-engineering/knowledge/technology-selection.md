---
knowledge:
  version: 1
  id: technology-selection
  summary: Select technologies from explicit requirements, constraints, ecosystem health, reversibility, operational fit, and task-relevant evidence.
  routes: [technology-framework-choice, new-project]
---

# Technology and Framework Selection

> **Purpose:** Choose languages, frameworks, databases, platforms, and bought services against the
> work they must perform—not fashion, familiarity alone, or benchmark theater.
>
> **Read this when:** adding a major dependency, choosing a stack, replacing a framework, deciding
> build versus buy, or making a choice that is expensive to reverse.

---

## Decision Contract

**Project default:** Start from required capabilities, constraints, and quality attributes. A
technology is fit only in relation to a workload, team, operating environment, and exit path.

Write down:

- user and business outcomes;
- functional capabilities and non-negotiable integrations;
- latency, throughput, availability, consistency, recovery, security, privacy, accessibility,
  localization, cost, and sustainability requirements;
- deployment targets, data residency, offline needs, and supported clients;
- delivery date, expected lifetime, team size, and operational ownership;
- constraints imposed by existing systems, accepted ADRs, contracts, and regulation.

Separate **must have**, **valuable**, and **speculative** requirements. Do not award a candidate
credit for features the project is unlikely to use.

## Candidate Evaluation

| Dimension                   | Questions                                                                                   |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| Capability fit              | Does it satisfy required behavior without fighting its model?                               |
| Maturity and lifecycle      | Release policy, support window, EOL, upgrade path, backwards compatibility?                 |
| Security and privacy        | Disclosure process, patch history, isolation, defaults, data flows, residency, encryption?  |
| Team competence             | Can the team build, test, debug, review, deploy, and operate it under pressure?             |
| Testability                 | Deterministic tests, real integration environment, fixtures, accessibility tooling?         |
| Operability                 | Metrics, traces, logs, profiling, backups, migrations, rollback, incident diagnostics?      |
| Ecosystem                   | Stable libraries, editor/language tools, package provenance, documentation quality?         |
| Accessibility and i18n      | Can the UI stack express semantics, keyboard/focus behavior, locale and input needs?        |
| Performance and efficiency  | Representative latency, throughput, memory, storage, network, energy, and scaling behavior? |
| Governance and supply chain | License, trademark, maintainers, funding, bus factor, signing/provenance, dependency graph? |
| Lock-in and exit            | Data export, standards, replaceable boundary, migration cost, contractual termination?      |
| Total cost                  | Build, licenses, people, training, hosting, support, migrations, and opportunity cost?      |

**Heuristic:** Familiar technology deserves a real advantage because competence reduces delivery
and incident risk. Familiarity is not a veto against a better option; quantify the learning and
migration cost.

## Evidence, Not Demos

Run a time-boxed representative spike for uncertain, decision-critical claims:

- use production-shaped data and a critical workflow;
- include authentication, failure behavior, observability, testing, deployment, and upgrade—not
  only the happy-path tutorial;
- benchmark after warm-up with multiple samples and variability reported;
- inspect failure recovery, resource use, accessibility, and debugging ergonomics;
- preserve code, commands, versions, data shape, and results.

A synthetic microbenchmark can explain one mechanism. It cannot establish application-level fit
without a representative workload.

## Weighted Decision with Uncertainty

**Project default:** Use a decision matrix to expose judgment, not to manufacture objectivity.

For each dimension record:

- importance weight;
- candidate score and evidence;
- confidence (`high`, `medium`, `low`);
- disqualifying constraint;
- sensitivity: whether a plausible score change reverses the result.

Low-confidence, high-weight claims identify the next spike or source check. If tiny weight changes
flip the winner, the decision is close; prefer reversibility and team fit over false precision.

## Build, Buy, Integrate, or Defer

**House preference:** Buy cognition; integrate commodity routing; own context, evidence, memory,
policy, outcomes, and stable capability contracts.

Build when the capability differentiates the product, contains durable local knowledge, or available
products cannot meet a measured requirement. Buy or integrate when the capability is commodity and
a replaceable boundary controls lock-in. Defer when the requirement is speculative.

Compare a custom solution against a current commodity baseline on the project's actual task
distribution. Keep custom complexity only when measured benefit exceeds lifecycle cost.

## Framework-Specific Risks

- lifecycle or rendering model conflicts with the product;
- generated code or reflection obscures behavior and debugging;
- extension points require global state or unsafe escape hatches;
- upgrades bundle unrelated migrations;
- server, browser, mobile, or desktop support differs materially;
- “batteries included” features become coupled even when unused;
- community conventions fight repository ownership boundaries.

An abstraction around one framework is useful when it protects a real domain boundary, test seam,
or exit path. A wrapper that merely renames the framework API adds maintenance without insulation.

## Decision Record and Revisit Trigger

Record candidates, rejected alternatives, evidence, assumptions, chosen version/support horizon,
exit plan, and owner. Revisit when:

- a required capability or deployment target changes;
- the dependency approaches EOL or changes license/governance;
- security, accessibility, or reliability evidence invalidates an assumption;
- operating cost crosses its budget;
- a representative migration or upgrade becomes materially harder than expected.

## Meta-Question

Which option best satisfies this project's required outcomes over its expected life, with the
smallest credible risk and a survivable exit?
