---
knowledge:
  version: 1
  id: testing-advanced
  summary: Select advanced evidence for compatibility, generated or hostile inputs, recovery, stochastic behavior, visual output, privacy, and test operations.
  routes: [test-strategy-evidence, user-facing-interaction]
  sources: [src-advanced-testing]
---

# Advanced Testing and Test Operations

> **Purpose:** Design credible evidence for compatibility, hostile/generated input, migrations,
> recovery, partial failure, privacy, performance statistics, visual output, stochastic systems,
> and long-lived test operations.
>
> **Read this when:** an ordinary behavioral suite does not represent a material failure dimension.

---

## Extend the Core Evidence Contract

The [core testing reference](testing.md) requires subject, scenario/input selection, oracle,
environment, observation/result, and proof boundary. Specialized evidence adds fields rather than
relaxing those:

- generation/search method, seed/corpus, shrink/minimization, and budget;
- workload, warm-up, order, sample size, distribution, variance, interval, and effect threshold;
- producer/consumer/schema versions and supported compatibility direction;
- injected fault, injection boundary, abort condition, recovery invariant, and reconciliation;
- browser/device/assistive-technology/rendering stack;
- test-data provenance, classification, access, retention, and deletion;
- runner/tool/version/configuration plus missing, timeout, inconclusive, and partial-result states.

Use the experimental [test-strategy template](../assets/templates/test-strategy.md) when these
dimensions affect acceptance or release. It remains an authoring aid pending Task 0049's practice
gate.

---

## Compatibility and Conformance

Define supported browser, device, OS, architecture, locale, timezone, database, protocol,
dependency, producer, consumer, and stored-data versions from actual contracts and users.

- Exercise critical paths on every supported tier.
- Use risk-based or pairwise combinations when the Cartesian product is impractical.
- Include unknown fields, missing optional fields, enum evolution, rolling deploys, and
  downgrade/rollback behavior when the contract permits them.
- Record unverified combinations and the release/scheduled fallback.
- Test accessibility with relevant browser, platform, and assistive-technology combinations;
  browser-only coverage is not accessibility evidence.

Consumer-driven contract tests cover represented interactions and known consumers. Pact's
[maintainer documentation](https://docs.pact.io/) explicitly distinguishes those examples from a
complete provider specification and from unrepresented consumer behavior. Verified 2026-07-31;
re-verify before Pact-specific adoption or version claims.

Conformance language belongs to the governing standard or certification scheme. Do not infer “fully
conformant” from passing selected clauses.

---

## Property-Based, Fuzz, Differential, and Metamorphic Testing

Use structure-aware generation for parsers, protocols, serializers, file formats, compilers,
stateful APIs, and trust boundaries. Record the accepted/rejected input domain, oracle, resource
limits, corpus/seeds, tool version, and stopping condition.

- **Property-based:** searches generated examples for a violation of an executable property.
- **Fuzz/no-crash:** searches for monitored failures such as crashes, hangs, sanitizer findings, or
  resource violations. Add a semantic oracle before claiming correct output.
- **Differential:** compares implementations/versions; agreement can reflect shared dependencies,
  specifications, or mistakes.
- **Metamorphic:** checks expected relations between transformed executions when a complete oracle
  is unavailable.
- **Grammar/model-based:** generates legal and illegal sequences from an explicit language or state
  model; model omissions remain omissions.

LLVM describes libFuzzer as coverage-guided and corpus-based; it also documents target and
applicability constraints. See the current
[libFuzzer documentation](https://llvm.org/docs/LibFuzzer.html), verified 2026-07-31. Re-verify
before tool-specific adoption because active development and recommended engines can change.

Preserve minimized failures as deterministic regressions when feasible. A run that exhausts its
time/example budget without finding a failure is bounded no-failure evidence, not exhaustive proof.

---

## Mutation and Coverage Diagnostics

Coverage says that represented structure executed; mutation analysis asks whether tests detect
selected synthetic changes. Neither decides whether the oracle or requirements are correct.

Use mutation analysis when:

- a critical module has high structural coverage but unclear assertion sensitivity;
- deleting or weakening behavior appears not to affect tests;
- comparing two test strategies against a stable operator set;
- a language/tool has credible operators and the runtime budget is acceptable.

Record operator/tool version, excluded code, timeouts, survived/killed/invalid/equivalent-or-unknown
mutants, selection, and baseline. Equivalent mutants and unrealistic operators limit interpretation.
The Jia and Harman
[mutation-testing survey](https://www.researchgate.net/publication/220069671_An_Analysis_and_Survey_of_the_Development_of_Mutation_Testing)
describes mutation adequacy as fault-based test-set evidence. Verified 2026-07-31; re-verify before
making a research-state claim or choosing an operator model.

Do not delete defensive code solely to reach a coverage target. SQLite's maintained
[testing account](https://www.sqlite.org/testing.html) documents both an unusually intensive
coverage regime and tensions with defensive/fuzz testing; it explicitly says its cost may not fit a
typical application. Verified 2026-07-31; re-verify before quoting current SQLite practices.

---

## Migrations, Rollback, Backup, and Recovery

For durable-state transitions, test applicable combinations:

- old code with old and transitional schema;
- new code with transitional and final schema;
- expand/backfill/contract during concurrent reads and writes;
- restart/resume after partial migration;
- rollback or forward-recovery at each declared point;
- retry/idempotency and duplicate delivery;
- production-shaped volume, skew, invalid historical rows, and time budget;
- backups restored in isolation with keys and external dependencies;
- recovery-point and recovery-time objectives.

A successful backup job proves artifact production, not recoverability. A migration happy-path unit
test does not represent rolling deployment, partial progress, operational duration, or rollback.
Record destructive-test containment and restoration of the test environment.

---

## Fault Injection and Degraded Modes

Inject plausible failures at a controlled boundary:

- timeout, cancellation, reset, malformed response, duplicate/reordered message;
- process crash/restart and partial write;
- exhausted pool, disk, quota, memory, file descriptors, or queue;
- dependency, zone/region, or network loss;
- clock skew, stale cache, expired credentials, and telemetry failure.

Verify the stated degraded behavior, invariant preservation, recovery, and reconciliation—not only
that an error was returned. Start with deterministic local/staging experiments. Production
experiments require explicit authority, blast radius, observability, abort conditions, owner,
incident coordination, and rollback.

---

## Statistical, Stochastic, and Performance Evidence

Before interpreting repeated measurements, define:

- population/workload and environment;
- estimand or property, oracle, practical effect/tolerance, and decision rule;
- sample size rationale, repetitions, warm-up, independence/correlation assumptions;
- randomization/counterbalancing, seeds, and run order;
- outlier/missing-data policy chosen before results;
- uncertainty interval or error-rate trade-off where applicable;
- cold/warm cache and client/server separation;
- profiler/telemetry overhead and environmental interference.

NIST's [Statistical Education Project](https://www.nist.gov/programs-projects/statistical-education-project)
routes engineers to experiment design and statistical methods for supportable conclusions. Verified
2026-07-31; re-verify before adopting a specific method or threshold. Use qualified statistical
review where consequence or model complexity warrants it.

For performance, a deterministic service budget may be more actionable than a tiny statistically
significant difference. Report effect size and user/capacity relevance. Use the Performance
Engineering capability for baselines, comparisons, profiles, and normalized measurement evidence;
this knowledge file owns only the test-strategy boundary.

Stochastic systems may require distributional, invariant, metamorphic, calibration, or
domain-reviewed oracles. A fixed seed supports replay but does not represent all seeds; an
uncontrolled seed impedes diagnosis. Record both purposes explicitly.

---

## Visual, Accessibility, and Human-Oracle Tests

Visual diffs can protect stable user-relevant rendering. Control and record font, viewport,
animation, clock, data, browser, OS, GPU, scale, and antialiasing where practical. Thresholds are
project decisions: accommodate known noise without hiding material change.

Baseline updates are product changes when the image is the oracle. Review them; do not approve
automatically because a renderer changed. Visual snapshots do not replace semantic, keyboard,
responsive, localization, contrast, zoom, or screen-reader evidence.

When humans supply the oracle, record the question/charter, participant or reviewer qualification
without unnecessary personal data, environment, decision scale, disagreements, and unresolved
cases.

---

## Privacy, Security, and Test Data

Verify applicable collection minimization, authorization and tenant isolation, redaction,
retention/hold transitions, and deletion/export/correction flows across logs, caches, replicas,
indexes, analytics, exports, and backups.

Synthetic data can contain copied secrets or identifiable combinations. Govern fixtures with
provenance, classification, least access, retention, and disposal. Do not send production personal
data to a test processor or model without project authority and the required privacy/security
review.

Security scanners and adversarial tests cover selected vulnerability classes, rules, versions, and
paths. Preserve tool/database currency and missing-tool states; a clean scan is not a security or
compliance certificate.

---

## Test Selection, Flake Operations, and Release Claims

Impact selection and historical prioritization optimize feedback but introduce false-negative risk.
Record why tests were omitted; broaden when dependency/build rules, shared fixtures, common
configuration, generated code, or the selector changes; retain a safe full/release/scheduled
fallback.

A flake quarantine requires:

- owner, tracking item, first-seen evidence, and estimated frequency/environment;
- preserved first-failure and repeat artifacts;
- explicit exclusion from affected integration/release claims;
- review/expiry and a path back into the required suite;
- separate states for product nondeterminism, test defect, infrastructure, dependency, and unknown.

Retries may estimate frequency or obtain diagnostics. They must not silently overwrite the first
failure or turn a required red result into evidence of an unqualified pass.

Release evidence should name which tests and versions ran, unavailable/inconclusive/quarantined
results, environment identity, accepted exceptions, and residual risk. A strategy document, green
dashboard, or large test count does not itself establish release fitness.

## Meta-Question

Which material failure dimension is absent from the ordinary suite, and what bounded observation,
oracle, environment, and result would reduce that uncertainty without overstating proof?
