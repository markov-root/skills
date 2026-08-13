---
knowledge:
  version: 1
  id: testing
  summary: Choose test subjects, scenarios, oracles, environments, and proof boundaries from the risks and claims a change actually creates.
  routes:
    [
      test-strategy-evidence,
      inherited-repository,
      api-event-contract,
      refactor-rewrite,
      agent-facing-skill-tool,
    ]
  sources: [src-testing-foundations]
---

# Testing: Strategy, Evidence, and Proof Boundaries

> **Purpose:** Choose proportionate tests and interpret their results without claiming more than
> their scenarios, oracle, inputs, and environment establish.
>
> **Read this when:** changing observable behavior, fixing a defect, planning verification, deciding
> which checks block integration, or judging whether a test portfolio is credible.
>
> **Do not:** inherit a pyramid, coverage target, test count, or CI policy without relating it to the
> project's risks and quality priorities.

---

## The Evidence Contract

**Standard/fact:** Testing can reveal failures and increase confidence over exercised cases; passing
tests do not prove that a system is defect-free or correct for every input or environment. This is
the first testing principle in the
[ISTQB CTFL v4.0.1 syllabus](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf),
verified 2026-07-31. Re-verify when ISTQB supersedes that syllabus. ISTQB is a useful attributed
source, not project authority.

Interpret any test result through six questions:

1. **Subject:** Which implementation, configuration, dependency versions, and artifact were tested?
2. **Scenario/input:** Which example, generated domain, workload, state transition, or version pair
   was exercised, and how was it selected?
3. **Oracle:** What distinguished acceptable from unacceptable behavior, and who or what owns that
   expectation?
4. **Environment:** Which platform, topology, data, clock, network, privileges, and external systems
   shaped the observation?
5. **Observation/result:** What actually happened, with which seed, sample, duration, and artifacts?
6. **Boundary:** Which inputs, failure modes, environments, properties, and user outcomes remain
   untested or unresolved?

The oracle deserves special scrutiny. The
[test-oracle survey by Barr et al.](https://earlbarr.com/publications/testoracles.pdf) describes the
recurring difficulty of deciding whether observed behavior is correct when complete specifications
or automated oracles are unavailable. Verified 2026-07-31; re-verify before materially revising the
oracle taxonomy.

Use [requirements and traceability](requirements-and-traceability.md) to connect a test to the
acceptance criterion it informs. A link does not enlarge the test's proof boundary.

---

## Test Families and the Evidence They Supply

“Unit,” “integration,” and “end-to-end” describe scope or isolation. They do not say what claim the
test evaluates. Record both the **family** and the **level** when the distinction matters.

| Family                       | Observation it can support                                                                     | It does not establish by itself                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Executable example**       | Expected behavior for named examples                                                           | General behavior outside those examples                                                 |
| **Behavioral**               | Publicly observable response satisfies a stated oracle in represented scenarios                | Internal structure, every environment, or product usefulness                            |
| **Characterization**         | Current behavior is recorded so unintended change becomes visible                              | That current behavior is desired, safe, or specification-conformant                     |
| **Conformance**              | Subject satisfies exercised clauses/cases of an identified specification or contract           | Full conformance unless the governing scheme explicitly defines sufficient evidence     |
| **Contract/compatibility**   | Exercised producer/consumer versions agree on represented interactions                         | Unrepresented consumers, journeys, capacity, or deployment correctness                  |
| **Structural**               | A represented static or dynamic structure exists: branch reached, import forbidden, type valid | Semantic correctness or absence of defects                                              |
| **Property-based**           | An executable property survived generated examples from a stated domain/search process         | The property is the right specification or that every domain value ran                  |
| **Metamorphic/differential** | Related executions or independent implementations agree under stated relations                 | Truth when the relation, reference, or shared assumptions are wrong                     |
| **No-crash/robustness**      | No monitored crash, hang, sanitizer finding, or resource violation occurred in sampled runs    | Correct output, security, or safety for the explored inputs                             |
| **Mutation**                 | Tests detect selected synthetic changes under stated operators and exclusions                  | Real-defect detection rate or correctness; equivalent mutants complicate interpretation |
| **Statistical**              | A stated estimator, interval, hypothesis, or tolerance criterion holds for sampled runs        | Exact repeatability or behavior outside the population/model assumptions                |
| **Performance/load**         | A defined workload met a budget in a measured environment                                      | Other workloads/environments or causal attribution without a designed comparison        |
| **Recovery/fault**           | The subject preserves stated invariants under injected failures and recovery paths             | Resilience to unmodeled combinations or a production blast radius                       |
| **Acceptance/usability**     | Represented users or authorized reviewers found stated outcomes acceptable                     | Universal user value, accessibility, or technical correctness                           |

Static analysis, model checking, proof assistants, manual review, exploratory testing, production
telemetry, and user research may contribute other evidence. Do not relabel them all as tests or
collapse their assumptions and result classes.

---

## Build a Risk-to-Evidence Strategy

**Project default:** Start from consequential uncertainty, not from a preferred testing shape.

1. Identify the acceptance criterion, quality attribute, changed behavior, and material failure
   modes.
2. Rank consequence, likelihood/exposure, uncertainty, change frequency, and detectability using
   the project's own scale.
3. Choose the cheapest credible observation and oracle at the boundary where the failure would be
   visible.
4. Record environment, fixtures/data, versions, sampling, cadence, owner, and retained artifacts.
5. Decide which evidence blocks integration, release, or neither—and how unavailable or flaky
   results are handled.
6. Record omissions, assumptions, residual risk, and the trigger for broadening or retiring the
   strategy.

Use the experimental [test-strategy template](../assets/templates/test-strategy.md) when the
mapping is consequential or crosses several environments. It is an authoring aid, not an adopted
metadata-v1 role and not proof that the strategy is adequate.

### Portfolio shapes are heuristics

The test pyramid is one useful cost/granularity heuristic: many cheap narrow checks and fewer
expensive broad ones. It is not a law. The
[Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html), verified
2026-07-31, explicitly presents a metaphor and discusses granularity. Re-verify only before changing
the attribution.

- Pure logic or libraries may be dominated by narrow behavioral/property tests.
- CRUD, ETL, adapters, orchestration, infrastructure, and framework-heavy code often need more real
  seam or integration evidence.
- A small script may justify one CLI smoke test plus side-effect sentinels rather than a unit suite.
- Safety-, security-, data-, or compatibility-critical work may require several independent
  evidence families even when they are expensive.
- Generated code may be covered more credibly by testing the generator, schema, deterministic
  regeneration, compilation, and representative consumer use than by line-level generated tests.

**Diagnostic:** If this failure occurred in production, which observation would discriminate it
from success with the fewest unrelated causes?

---

## Selecting Scenarios and Inputs

Use the technique that matches the risk:

| Technique                | Useful for                                                         | Important limitation                                       |
| ------------------------ | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| Boundary values          | Empty, one, maximum, just-inside/outside, zero, negative, overflow | Requires a credible boundary model                         |
| Equivalence partitions   | Representative classes with expected equivalent behavior           | A wrong partition hides differences                        |
| State transitions/models | Legal/illegal transitions, temporal behavior, protocols            | Model omissions become test omissions                      |
| Decision tables/pairwise | Interacting conditions when the Cartesian product is impractical   | Pairwise misses higher-order interactions                  |
| Properties/invariants    | Parsers, serializers, transformations, algebraic/stateful behavior | A weak or false property is a weak or false oracle         |
| Fuzzing/generation       | Hostile, malformed, structured, or broad machine-generated input   | Search budget and instrumentation bound the explored space |
| Production-derived cases | Real distributions and previously observed failures                | Privacy, sampling bias, freshness, and retention apply     |
| Exploratory/manual       | Unknown unknowns, usability, perception, and oracle-poor behavior  | Session skill, charter, environment, and notes bound reuse |

Property-based tools execute generated examples; “should hold for all inputs” describes the
property, not an exhaustive run. Hypothesis' current
[documentation](https://hypothesis.readthedocs.io/en/latest/) makes the described domain and
generated-example mechanism explicit. Verified 2026-07-31; re-verify before tool-specific guidance
or a locked-major change.

Preserve minimal failing examples, seeds where meaningful, generator/tool versions, and the
original deterministic regression when a generated run finds a defect.

---

## Oracles and Assertions

Prefer an oracle independent enough to discriminate the failure:

- an acceptance criterion, protocol/specification clause, or approved decision;
- an independently implemented reference or simpler model;
- an invariant, metamorphic relation, or state-machine rule;
- a versioned producer/consumer contract;
- a human/domain decision when automation cannot responsibly decide;
- crash/sanitizer/resource monitors when the claim is explicitly robustness, not correctness.

Avoid an expected value copied from the implementation under test. A fake built from the same
misunderstanding as an adapter does not validate the real provider.

Arrange–Act–Assert and Given–When–Then are useful readability patterns, not required syntax.
Assertion count is not a quality metric:

- several assertions may describe one coherent postcondition or preserve an atomic diagnostic;
- one broad snapshot may hide many unrelated claims;
- split a test when scenarios, causes, ownership, or failure messages become clearer—not merely
  because it has more than one assertion.

Name tests for the behavior and condition they discriminate where the ecosystem permits it.

---

## Change, Rewrites, and Deletion

“Survives a rewrite” applies primarily to behavioral tests intended to protect a stable external
contract. It is not a universal admission test:

- characterization tests intentionally pin observed legacy behavior until a decision changes it;
- conformance tests may change when the governing specification changes;
- structural/architecture tests intentionally constrain implementation shape;
- performance tests may remain meaningful while their thresholds, workload, or environment evolve;
- migration and compatibility tests are often temporary but mandatory for the supported transition;
- generated-code tests may follow generator or schema boundaries rather than public runtime behavior.

When a test still passes after relevant production code is deleted, investigate before deleting
either one. The test may be tautological, may exercise another implementation, may be a
specification/example artifact, or may be guarding structure/configuration. Mutation testing can
diagnose whether selected synthetic faults are observed; it is not an automatic deletion oracle.

Delete or retire a test when its protected claim no longer exists, stronger evidence supersedes it,
or maintenance cost exceeds documented value. Preserve historical evidence when regulation,
incident learning, compatibility, or migration auditability requires it.

---

## Doubles, Fixtures, and Environments

Use a double according to the claim:

| Double    | Role                                                    | Common risk                                      |
| --------- | ------------------------------------------------------- | ------------------------------------------------ |
| Dummy     | Satisfies an unused parameter                           | Hides a now-used dependency                      |
| Stub      | Returns controlled responses                            | Encodes an unrealistic provider model            |
| Fake      | Implements a simpler working boundary                   | Drifts from production semantics                 |
| Mock      | Verifies an expected interaction                        | Couples tests to incidental call structure       |
| Spy       | Records interaction with a real or wrapped collaborator | Observation changes timing or behavior           |
| Simulator | Models environment/device/failure behavior              | Model-to-reality gap is mistaken for equivalence |

**Project default:** Put domain behavior behind a boundary the project owns. Test that behavior with
controlled doubles, and separately verify the adapter against a provider sandbox, conformance
suite, versioned recording, or controlled live system when compatibility risk warrants it.

Record fixture provenance and scenario-relevant differences. Treat test data as governed data:
classification, access, privacy, retention, and disposal still apply.

---

## Flakes, Randomness, and Statistical Behavior

A test is flaky when materially identical subject/input conditions can yield pass and fail. The
cause may be the test, product, environment, dependency, scheduler, clock, or undefined behavior.
Do not assume the test alone is wrong.

**Project default for required checks:**

- preserve the first failure and its environment/artifacts;
- use repeats to estimate or reproduce, not to erase the failure;
- quarantine only with owner, tracking item, impact on release claims, review/expiry, and a path
  back;
- distinguish deterministic replay, seeded generative search, expected stochastic variation, and
  uncontrolled nondeterminism;
- report `flaky`, `inconclusive`, `unavailable`, and `failed` distinctly when the runner permits it.

Google's published experience shows that flakes can retain value while imposing substantial
triage cost; it is an organizational example, not a universal threshold. See
[Flaky Tests at Google](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html),
verified 2026-07-31; re-verify before quoting current Google rates or policy.

For randomized/statistical systems, define the distribution or population, estimand/property,
sample size rationale, seeds, repetitions, tolerance or interval, false-positive/negative trade-off,
and decision rule. Exact repeatability may be unavailable or distort the production behavior being
tested. Deterministic modes can aid diagnosis while differing in performance or implementation;
record which mode produced the evidence.

Read [advanced testing](testing-advanced.md) for statistical, performance, visual, compatibility,
recovery, fault-injection, privacy, and long-running test-operation details.

---

## CI and Enforcement

Blocking is a project/release contract, not an intrinsic property of a tool.

| Decision                        | Calibrated rule                                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------------------- |
| Required pre-integration checks | Block when failure signal is trusted and the check protects an integration-critical property      |
| Advisory/new/noisy checks       | Report first; promote after false-positive, availability, ownership, and repair-path evidence     |
| Slow/broad suites               | Run at merge, release, schedule, or explicit risk trigger with a safe fallback                    |
| External/live checks            | Define network, credential, quota, timeout, unavailable, and environment-drift semantics          |
| Generated/statistical checks    | Preserve seed/sample/tool identity and distinguish failure from inconclusive or budget exhaustion |
| Emergency override              | Require authorized exception, recorded risk, compensating evidence, expiry, and follow-up         |

A red trusted required check should not be converted to green by silent retries. A repository may
allow an explicit reviewed override, non-blocking experiment, or degraded release path where its
authority and risk model permit it. One green CI run establishes only the checks and environments
that ran.

Preserve a fast local or affected-change loop. Test-impact selection is an optimization with
false-negative risk; broaden selection when build rules, shared fixtures, dependency graphs, or the
selector itself changes, and retain a full/release/scheduled fallback appropriate to the project.

---

## Inherited Systems and High-Risk Changes

**Project default:** Establish the smallest credible safety net before a risky behavior-preserving
change. That may be characterization tests, production replay, a golden master, shadow comparison,
state/data invariants, rollback rehearsal, or manual observations. “Never refactor without tests”
is too narrow when the code cannot yet run in a harness or when another evidence form is stronger.

For a defect:

1. Preserve a minimal reproducer or the strongest available evidence.
2. Add a discriminating regression test when practical.
3. Show that it fails for the defect and passes for the intended behavior when that causal check is
   safe and feasible.
4. Exercise nearby boundary/state classes according to consequence and recurrence risk.
5. Record what the regression does not cover.

For high-consequence security, authorization, financial, migration, safety, or data-integrity
changes, seek independent evidence families and qualified review as applicable. More tests of one
oracle do not compensate for a wrong oracle.

---

## When Testing Is Sufficient for This Change

Stop for the current decision when:

- applicable acceptance criteria and critical risks have proportionate evidence;
- subject, scenarios, oracle, environment, and result artifacts are identifiable;
- material omissions, inconclusive results, assumptions, and residual risks are visible;
- required project gates and authorized reviews are satisfied;
- another test is less valuable than the next risk-reduction activity.

Do not stop merely because coverage reached a number, every function has a test, snapshots were
updated, CI is green, or no sampled input failed.

## Meta-Question

What exact claim does this test result support for this subject, scenario/input process, oracle, and
environment—and what important claim remains outside that boundary?

---

_See [advanced testing](testing-advanced.md) for specialized evidence domains._
_See [requirements and traceability](requirements-and-traceability.md) for acceptance-to-evidence
relationships._
_See [performance](performance.md) and the Performance Engineering capability for measured
performance work._
