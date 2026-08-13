---
knowledge:
  version: 1
  id: requirements-and-traceability
  summary: Separate outcomes, constraints, requirements, acceptance criteria, assumptions, decisions, and evidence while preserving change-aware traceability.
  routes: [requirements-acceptance-scope]
  sources: [src-requirements-standards]
---

# Requirements, Outcomes, Acceptance, and Traceability

> **Purpose:** Turn intent and constraints into observable acceptance without confusing desired
> outcomes, implementation choices, work items, checks, or evidence.
>
> **Read this when:** framing a feature, inheriting uncertain behavior, fixing a defect, planning a
> migration, running a research spike, changing accepted scope, or deciding what “done” can
> truthfully mean.

---

## Epistemic position

**Project default:** Use the smallest durable record that keeps consequential intent, uncertainty,
decisions, work, and evidence distinguishable. Project instructions, accepted decisions, contracts,
and applicable external constraints outrank this workflow.

**Standard/fact:** ISO/IEC/IEEE 29148:2018 defines requirements-engineering processes and information
items across system and software life cycles. ISO lists the 2018 edition as current but “to be
revised” as of 2026-02-16, so verify its status before making a conformance claim
([ISO 29148](https://www.iso.org/standard/72089.html), verified 2026-07-31).

**Standard/fact:** ISO/IEC 25010:2023 supplies a product-quality model that can support requirements,
test objectives, acceptance criteria, and measurement. It is a vocabulary and completeness aid,
not a mandate to require every characteristic
([ISO 25010](https://www.iso.org/standard/78176.html), verified 2026-07-31).

This reference is an engineering synthesis, not a claim of conformance to either standard.

## Separate the artifacts

| Artifact             | Question it answers                                                     | It is not                                                          |
| -------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Problem evidence     | What observed condition or unmet need justifies attention?              | A requested feature by itself                                      |
| Outcome              | What valuable change should an actor, operation, or system experience?  | An output, screen, endpoint, or implementation plan                |
| Constraint           | What externally or project-authoritatively limits acceptable solutions? | A preference promoted without authority                            |
| Requirement          | What capability, behavior, interface, quality, or constraint is needed? | A task or design decision                                          |
| Quality attribute    | How well must the system behave in a stated context?                    | “Fast,” “secure,” or “scalable” without a measure or review method |
| Acceptance criterion | What bounded, observable condition decides whether scoped work is met?  | The command that checks it                                         |
| Assumption           | What uncertain premise is temporarily being relied upon?                | A hidden fact or permanent requirement                             |
| Non-goal             | What adjacent outcome or behavior is deliberately excluded?             | Work silently forgotten                                            |
| Decision             | Which approach was selected, why, and with what consequences?           | The original need                                                  |
| Task                 | What bounded work changes the system or resolves uncertainty?           | Evidence that its criterion was met                                |
| Check                | What reproducible inspection, test, analysis, demonstration, or review? | Its dated result                                                   |
| Evidence             | What result occurred, where, when, under which version/environment?     | Proof beyond the represented scope                                 |

GOV.UK's service guidance usefully distinguishes a user's need and overall outcome from the
features used to deliver it, and treats unsupported stakeholder suggestions as assumptions to
validate. That guidance is authoritative for its own service context; this library adopts only the
general separation as a project default
([user needs](https://www.gov.uk/service-manual/user-research/start-by-learning-user-needs),
[service outcomes](https://www.gov.uk/service-manual/service-assessments/what-a-service-is),
verified 2026-07-31).

## Validation and verification

Use the distinction consistently:

- **Validation** asks whether the selected outcome and requirements fit the intended use, users, and
  operating context—“are we solving the right problem?”
- **Verification** asks whether an artifact or implementation satisfies its specified criteria—“did
  we satisfy the stated contract?”

NASA's Systems Engineering Handbook similarly separates product verification against requirements
or design from product validation in the intended environment. NASA SWE-052 separately requires
bidirectional traceability for particular NASA software classes and elements. That is a
domain-specific requirement, not a universal process mandate
([NASA Systems Engineering Handbook, revision 2](https://www.nasa.gov/wp-content/uploads/2018/09/nasa_systems_engineering_handbook_0.pdf),
[NASA SWE-052, revision D](https://swehb.nasa.gov/spaces/SWEHBVD/pages/102695427/SWE-052%2B-%2BBidirectional%2BTraceability),
verified 2026-07-31).

A test can verify specified behavior while the product still fails its users. User research can
validate a need while the implementation still violates its API contract. Keep both questions
visible.

## Frame the change before selecting the solution

For consequential work, establish:

1. **Problem and evidence** — affected actors, observed behavior, frequency/scale, source, and what
   remains unknown.
2. **Outcome** — the change in user, operational, safety, business, or system state that matters.
3. **Constraints** — law, policy, compatibility, data, safety, budget, deadline, platform, and
   project authority with source and applicability.
4. **Quality attributes** — ranked, contextual targets or explicit review methods.
5. **Non-goals** — adjacent outcomes and solution space intentionally excluded.
6. **Assumptions** — owner, consequence if false, validation method, and review/expiry trigger.
7. **Acceptance criteria** — observable boundaries for this increment.
8. **Candidate decisions and tasks** — only after the preceding intent is visible.

**Heuristic:** If the request names only a solution (“add Redis,” “use microservices,” “rewrite in
Rust”), ask what outcome, constraint, or measured deficit makes that solution relevant. Do not block
an obvious low-risk request merely to manufacture a product exercise.

## Write criteria that can disagree with the implementation

An acceptance criterion should be:

- **observable** — describes behavior, state, or a reviewable artifact;
- **bounded** — identifies actor/input, environment, time/version, and relevant boundary;
- **decidable** — states what result counts as met, unmet, or intentionally not evaluated;
- **solution-neutral where useful** — preserves design freedom unless the implementation is itself
  constrained;
- **risk-complete** — includes material negative, error, permission, recovery, compatibility, or
  accessibility behavior;
- **evidence-linked** — names a planned test, analysis, demonstration, inspection, measurement, or
  qualified review without embedding a transient result.

Bad:

> AC-001: Add a fast search endpoint with good tests.

Better:

> AC-001: For the versioned 100k-record fixture on the declared CI runner, authenticated exact-name
> searches return the authorized matching record and no cross-tenant record; p95 server time is at
> most 250 ms across the recorded workload. Evidence: contract test plus benchmark record.

The number is an example, not a default. The project should justify its own workload, environment, and
threshold. For subjective qualities, define the review population, scenario, rubric, decision
owner, and uncertainty instead of inventing fake precision.

## Stable identifiers and lifecycle

**Project default:** Assign stable identifiers when a criterion or relationship must survive
renaming, reordering, multiple tasks, releases, audits, or tools.

Suggested namespaces:

| Prefix | Meaning                  | Example   |
| ------ | ------------------------ | --------- |
| `OUT-` | outcome                  | `OUT-001` |
| `CON-` | authoritative constraint | `CON-004` |
| `REQ-` | functional requirement   | `REQ-012` |
| `QA-`  | quality requirement      | `QA-003`  |
| `AC-`  | acceptance criterion     | `AC-021`  |
| `ASM-` | assumption               | `ASM-002` |
| `NG-`  | non-goal                 | `NG-005`  |

Use a repository-defined grammar such as `^[A-Z][A-Z0-9]*-[0-9]{3,}$`. Do not renumber or reuse an
identifier after publication. Preserve `draft`, `accepted`, `superseded`, or `retired` state and
link replacements. Text may evolve through the owning change process; accepted historical
evidence continues to point to the version it evaluated.

Not every typo needs an ID. Introduce one when losing the relationship would make impact analysis,
handoff, review, or completion materially less reliable.

## The minimum trace graph

Use explicit typed relationships instead of copying the same requirement into every artifact:

| From                  | Relationship     | To                            | Question answered                                      |
| --------------------- | ---------------- | ----------------------------- | ------------------------------------------------------ |
| outcome/constraint    | `refined-by`     | requirement/criterion         | What makes the intent or limit actionable?             |
| requirement/criterion | `decided-by`     | ADR or decision               | Which non-obvious approach governs it?                 |
| requirement/criterion | `implemented-by` | task/change                   | Where is the bounded work?                             |
| criterion             | `verified-by`    | check/review                  | Which method could decide this criterion?              |
| check/review          | `evidenced-by`   | immutable result              | What actually happened for this version/environment?   |
| outcome/assumption    | `validated-by`   | research/operational evidence | What supports intended use or the relied-upon premise? |
| any versioned record  | `superseded-by`  | replacement                   | Which record now owns current intent?                  |

“Bidirectional” means a maintainer or tool can navigate both impact directions; it does not require
duplicating links in two files when one indexed relationship can answer both queries.

Review these conditions:

- an accepted criterion with no planned check;
- a completed task with no criterion or disposition;
- a passing check with no criterion or project quality floor;
- a requirement with no outcome, constraint, source, or derivation rationale;
- evidence without commit/version, environment, command/method, result, or important omissions;
- a changed requirement whose decisions, tasks, checks, docs, migration, or release consumers were
  not impact-reviewed.

An orphan is a question, not automatically a defect. Exploratory infrastructure, refactoring,
regulatory constraints, and emergent requirements can have legitimate roots; record the rationale.

## Change control without pretending requirements are fixed

An accepted baseline is a review point, not a waterfall promise. When intent changes:

1. preserve the prior identifier and version/state;
2. record the source and rationale for the change;
3. assess affected decisions, interfaces, data, tasks, tests, docs, releases, and operations;
4. update or disposition related criteria and evidence;
5. obtain the authority required by project policy;
6. link the superseding record and communicate material compatibility or migration effects.

The Agile Manifesto explicitly welcomes changing requirements. That principle does not make silent
scope changes safe; it makes change management and short feedback loops more important
([Agile principles](https://agilemanifesto.org/principles.html), verified 2026-07-31).

Security requirements deserve the same lifecycle rather than a late checklist. NIST SSDF 1.1
includes identifying, documenting, maintaining, and tracking security requirements and related
design decisions; apply its practices only where the project's SSDF scope or policy adopts them
([NIST SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final), verified 2026-07-31).

## Scenario playbooks

### New feature or discovery

- Start with problem evidence, affected actors, and desired outcome.
- Separate user need from stakeholder suggestion and implementation idea.
- Record unknowns as assumptions; validate the expensive or irreversible ones early.
- Define the thinnest outcome-bearing increment and its negative/quality criteria.

### Inherited system

- Treat observed behavior, tests, docs, schemas, and production evidence as potentially conflicting
  evidence—not automatic intent.
- Write characterization checks before risky change.
- Identify which behavior is contractual, accidental, defective, or still unknown.
- Link a newly accepted criterion to its authority and preserve incompatible historical evidence.

### Defect

- Record a discriminating reproduction and the source of expected behavior.
- Define the criterion as the corrected observable boundary, including a meaningful negative case.
- Link root cause and decision only when established; do not turn the first hypothesis into a
  requirement.
- Preserve a regression check or the strongest practical reproduction evidence.

### Migration or compatibility change

- State old, transitional, and target invariants plus supported producer/consumer versions.
- Define data preservation, concurrency, interruption, retry, rollback/roll-forward, and
  observability criteria.
- Link each compatibility criterion to its migration check and environment.
- Treat a successful script exit as execution evidence, not proof of recovered data or safe
  rollback.

### Research spike

- Frame a decision question, hypotheses, time/cost/data boundary, comparison method, and stopping
  rule.
- Acceptance means the promised experiment and decision evidence exist—not that a preferred
  technology won.
- Record inconclusive results, invalidated assumptions, and follow-up decisions explicitly.
- Do not convert a prototype's observed behavior into a production requirement without review.

## Compact record

Use this inline in an issue/task or link to an owned specification:

```text
Problem evidence:
Outcome IDs:
Constraint IDs and authority:
Requirements / quality IDs:
Acceptance criteria:
Assumptions and validation/expiry:
Non-goals:
Decisions:
Tasks:
Checks planned:
Evidence produced:
Uncovered criteria / residual risks:
Change owner and review trigger:
```

For a small change, most fields may be one line or explicitly not applicable. For high-consequence
work, the same IDs can point to schemas, hazard analyses, data maps, formal specifications, test
plans, release records, and qualified approvals owned by their domains.

## Evidence limits and failure modes

- Traceability shows recorded relationships; it does not establish that the relationships are
  correct, complete, current, or valuable.
- Passing every linked check verifies only represented criteria under recorded conditions.
- A criterion can be perfectly testable and still encode the wrong user outcome.
- A user story is one useful format, not the definition of a requirement.
- Coverage percentage is not requirements coverage unless the mapping and oracle are credible.
- A large matrix can become compliance theater. Scale relationship detail by consequence,
  uncertainty, lifetime, reversibility, and change frequency.
- Do not let a tool's schema become product authority. The project owns intent; tools preserve and
  query it.

## Meta-Question

Can a reviewer move from the observed problem and desired outcome to each consequential decision,
change, check, and dated result—and back—while still seeing assumptions, exclusions, and what the
evidence does not prove?
