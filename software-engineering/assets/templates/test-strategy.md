# Experimental test strategy: TITLE

> **Status:** Experimental authoring aid. This is not an adopted metadata-v1 role. Task 0049 owns
> any promotion after at least two reviewed real uses.
>
> Replace every uppercase placeholder with reviewed project facts. Delete inapplicable sections
> explicitly or record the omission; never invent requirements, approval, evidence, dates, owners,
> environments, or results.

## Decision context

- Subject/artifact and version: SUBJECT
- Change/release boundary: BOUNDED CHANGE
- Owner: OWNER
- Reviewers/approvers required by project policy: REVIEWERS OR NONE
- Related outcomes/requirements/criteria: IDENTIFIERS
- Quality attributes and rank: RANKED ATTRIBUTES
- Strategy state: draft | reviewed | active | superseded
- Review/expiry trigger: TRIGGER

## Risk-to-evidence map

Add one row per material claim or failure mode. “Passing test” is not an evidence description.

| Criterion / claim | Failure mode and consequence | Exposure / uncertainty | Test family + level | Scenario / input-selection method | Oracle and authority | Environment / versions | Fixture or data provenance | Cadence and blocking policy | Owner | Result artifact | What this evidence cannot establish |
| ----------------- | ---------------------------- | ---------------------- | ------------------- | --------------------------------- | -------------------- | ---------------------- | -------------------------- | --------------------------- | ----- | --------------- | ----------------------------------- |
| CRITERION         | FAILURE                      | RISK                   | FAMILY + LEVEL      | SCENARIO                          | ORACLE               | ENVIRONMENT            | PROVENANCE                 | CADENCE / POLICY            | OWNER | ARTIFACT        | PROOF BOUNDARY                      |

## Change execution matrix

Record which evidence is required at each boundary. Use `not applicable` with a reason rather than
an empty cell.

| Boundary                | Required evidence | Unavailable / inconclusive behavior | Authorized override and expiry |
| ----------------------- | ----------------- | ----------------------------------- | ------------------------------ |
| Local / affected change | EVIDENCE          | BEHAVIOR                            | AUTHORITY OR NONE              |
| Integration / merge     | EVIDENCE          | BEHAVIOR                            | AUTHORITY OR NONE              |
| Release / migration     | EVIDENCE          | BEHAVIOR                            | AUTHORITY OR NONE              |
| Scheduled / production  | EVIDENCE          | BEHAVIOR                            | AUTHORITY OR NONE              |

## Environment and compatibility

- Supported environment/version matrix: MATRIX OR LINK
- Explicitly untested combinations: OMISSIONS
- External services, credentials, network, quotas, and timeouts: CONTRACT
- Production/test differences that affect interpretation: DIFFERENCES
- Test-impact selection and safe broader fallback: SELECTION / FALLBACK

## Oracles and fixtures

- Oracle sources and precedence: ORACLES
- Independent/differential oracle, if any: ORACLE OR NONE
- Fixture/data provenance, classification, access, retention, and disposal: DATA CONTRACT
- Generated inputs: domain, distribution/search, seed/corpus, shrink/minimization, and budget:
  GENERATION CONTRACT OR NOT APPLICABLE
- Snapshot/golden-baseline ownership and update review: BASELINE CONTRACT OR NOT APPLICABLE

## Statistical or stochastic protocol

If applicable, record population/workload, estimand/property, practical effect or tolerance, sample
size rationale, repetitions, warm-up, randomization/order, seeds, missing/outlier policy,
uncertainty interval or error-rate trade-off, and decision rule.

NOT APPLICABLE, OR PROTOCOL

## Failure, flake, and partial-result policy

- Result states preserved: passed | failed | flaky | inconclusive | unavailable | partial | other
- First-failure artifacts: ARTIFACTS
- Retry purpose and limit: DIAGNOSIS CONTRACT OR NONE
- Quarantine owner, tracking item, release-claim impact, review/expiry, and re-entry: POLICY
- Timeout, cancellation, resource exhaustion, and missing-tool behavior: POLICY

## Omitted evidence and residual risk

| Omission / assumption | Why it is omitted or uncertain | Consequence | Compensating evidence | Owner / revisit trigger |
| --------------------- | ------------------------------ | ----------- | --------------------- | ----------------------- |
| OMISSION              | REASON                         | CONSEQUENCE | EVIDENCE OR NONE      | OWNER / TRIGGER         |

## Results and interpretation

Populate only after execution.

| Evidence item | Subject/environment identity | Observation/result | Artifact/digest | Criterion informed | Limitations / disposition |
| ------------- | ---------------------------- | ------------------ | --------------- | ------------------ | ------------------------- |
| EVIDENCE      | IDENTITY                     | RESULT             | ARTIFACT        | CRITERION          | LIMIT / DISPOSITION       |

## Review

- Does every material risk have evidence, an explicit omission, or an authorized acceptance?
- Can each oracle discriminate the stated failure without merely copying the implementation?
- Are environment, version, data, generation, and statistical assumptions visible?
- Are blocking and override semantics owned by project/release authority?
- Do results state only what the represented scenarios establish?
- Are security, privacy, accessibility, operability, compatibility, and rollback evidence routed
  to their specialist owners where applicable?
