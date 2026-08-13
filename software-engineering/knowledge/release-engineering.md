---
knowledge:
  version: 1
  id: release-engineering
  summary: Plan and review releases when source identity, artifact evidence, compatibility, migration, rollout, recovery, and support promises need one accountable record.
  routes: [deployment-operations, dependency-build-change]
  sources: [src-supply-chain-standards, src-release-standards]
---

# release-engineering.md — Release Identity, Compatibility, and Recovery

> **Purpose:** Reference for turning a change set into a named release with clear identity,
> compatibility promises, migration path, rollout evidence, recovery path, known limitations, and
> support boundaries.
>
> **Read this when:** cutting a library, service, CLI, application, schema, protocol, or deployment
> release; reviewing a release candidate; deciding whether a breaking change is ready to ship;
> writing rollback or forward-recovery instructions.
>
> **Do NOT** treat a tag, build number, or deployment event as the whole release. A release is the
> promise consumers and operators can rely on after that event.

---

## The Premise

> A release is a named transfer of risk from builders to consumers, operators, and support.

**Project default:** A release record should answer seven questions for the release's actual
product form: what source produced it, what artifacts were delivered, who can use it, how consumers
move to it, how it was verified, how it fails back or forward, and where support ends. The trade-off
is ceremony: a throwaway internal preview may need a lighter note, while a package, public API,
database migration, mobile application, or production service needs enough evidence for someone else
to operate it later.

**Heuristic:** If the release cannot be reconstructed as a decision from its tag, artifact registry,
CI result, changelog, migration plan, and incident/recovery notes, the release identity is probably
too weak. Counterexample: an emergency configuration disablement may intentionally record the
operator action and incident ticket instead of a new build artifact.

Canonical ownership still applies:

- Use [git and versioning](git-and-versioning.md) for commit history, tags, changelog discipline, and
  version-control operations.
- Use [API design](api-design.md) for wire semantics, API versioning, idempotency, errors,
  pagination, schema evolution, and deprecation protocol.
- Use [data](data.md) for durable-state integrity, database migration design, zero-downtime schema
  changes, backup, restore, and reconciliation.
- Use [dependencies](dependencies.md) for dependency provenance, SBOM generation, vulnerability
  triage, license hygiene, and package-manager behavior.
- Use [error handling](error-handling.md) for retries, timeouts, fallback, circuit breakers, and
  failure contracts.

This file owns the release-specific consequence: the release record ties those decisions together
and states what is true for this cut.

## Release Identity

**Project default:** A releasable unit should identify the source revision, build recipe, artifact
set, artifact digests, dependency resolution, and release notes in one place. The trade-off is that
some ecosystems already expose part of this through package metadata or deployment records; reuse
those records rather than copying them by hand, but link the release to them.

**Project default:** Record digests for each delivered artifact, not just for the release as a whole.
The trade-off is extra bookkeeping for multi-platform builds; the counterexample is a source-only
release where the source archive is the artifact and no compiled binary is distributed.

**Standard/fact (verified 2026-08-05):** SLSA v1.2 describes supply-chain security levels and
tracks, including source, build, provenance, and verification guidance. SLSA's provenance guidance
describes verifiable information about where, when, and how software artifacts were produced:
<https://slsa.dev/spec/v1.2/> and <https://slsa.dev/spec/v1.2/provenance>.

**Standard/fact (verified 2026-08-05):** The in-toto Attestation Framework specifies a format for
verifiable claims about how software is produced: <https://github.com/in-toto/attestation>. A release
record may reference in-toto attestations produced by the project tooling, but this prose record is
not itself an attestation.

**Project default:** A release record must not present a signature, provenance attestation, SLSA
level, or compliance claim unless an authorized issuer or tool produced that evidence. The scope is
release evidence integrity; the trade-off is that unsigned releases may look less mature, but a
truthful unsigned release is safer than a fabricated assurance. Counterexample: an internal nightly
build may intentionally record "no attestation produced" while preserving its CI run and artifact
digests.

**Heuristic:** The same source commit does not prove identical binaries. Toolchain versions, build
environment, dependency resolution, timestamps, platform targets, flags, and signing steps can change
outputs. Treat reproducible-build evidence as an explicit artifact of the build, not as an assumption
inferred from Git.

## Version and Compatibility Policy

**Standard/fact (verified 2026-08-05):** Semantic Versioning 2.0.0 defines major, minor, and patch
increments relative to a declared public API: <https://semver.org/>.

**Project default:** Version policy should name the compatibility surface, not only the number
format. The trade-off is precision: a library's source API, a CLI's flags and exit codes, and a
service's HTTP contract change differently. Counterexample: a private prototype with one deployer
may use date or build-number releases until external consumers depend on it.

**Project default:** A release should include a compatibility matrix when support varies by runtime,
platform, dependency range, operating system, browser, client version, schema version, protocol
version, region, feature flag, or deployment environment. The trade-off is maintenance cost; a
single-platform internal daemon may only need "Linux amd64 on the production base image."

**Heuristic:** "Compatible" means "an existing supported consumer keeps working within the documented
contract," not "the tests passed for the producer." Counterexample: a major-version preview may
state that compatibility is intentionally broken and only migration tooling is supported.

Compatibility matrix rows usually need:

| Dimension | Release-specific question |
| --- | --- |
| Producer version | Which version, tag, image, package, schema, or protocol is being released? |
| Consumer version | Which clients, callers, plugins, extensions, migrations, or operators are supported? |
| Runtime/platform | Which OS, architecture, language runtime, database, browser, device, or hosting target applies? |
| Data/protocol | Which schema, event, API, file format, wire format, or storage version is accepted and produced? |
| Dependency range | Which direct and critical transitive dependency versions are supported or excluded? |
| Support window | How long is this line patched, and what receives security-only fixes? |
| Escape hatch | Which flag, config, downgrade, forward fix, or manual step reduces blast radius? |

## Product Forms

**Project default:** Release review should match the product form because compatibility, migration,
verification, and recovery differ. The trade-off is that a single release may span several forms; in
that case, review each material form instead of averaging the risk.

### Library Release

| Question | Release review |
| --- | --- |
| Compatibility | What is the public API: source signatures, binary ABI, type-level behavior, plugin hooks, config keys, supported runtimes, and dependency ranges? |
| Migration | Which callers need code changes, dependency-range updates, feature flags, or deprecation cleanup before upgrading? |
| Verification | Which unit, integration, ABI/API, supported-runtime, dependency-range, and downstream smoke checks establish the compatibility claim? |
| Rollback/recovery | Can consumers pin the previous version, and are package contents immutable under the ecosystem's rules? If a bad version escaped, is the recovery a yanked release, a patched forward release, an advisory, or all three? |

**Project default:** Published library versions should be immutable after release because consumers
and lockfiles use version identity as a cache and trust boundary. The trade-off is that fixing a bad
artifact requires a new version or ecosystem-specific yank; a private registry with controlled
consumers may allow replacement during a documented pre-release window.

### Service Release

| Question | Release review |
| --- | --- |
| Compatibility | Which API versions, events, webhooks, auth scopes, rate limits, config keys, and operational dependencies remain supported? |
| Migration | Which clients, workers, jobs, caches, secrets, queues, or data stores need sequencing before or after rollout? |
| Verification | Which contract tests, integration checks, health checks, observability queries, synthetic transactions, and canary criteria were run? |
| Rollback/recovery | Is rollback safe after writes occur, or is the recovery path roll forward, disable a feature flag, drain a queue, replay events, or run a compensating migration? |

**Project default:** A service release should separate deploy success from release success. The
trade-off is delayed confidence: a deployment can become technically live before canary metrics,
client behavior, and support signals prove the release acceptable. Counterexample: an offline batch
service with no live traffic may use job completion and output reconciliation as the release signal.

### CLI Release

| Question | Release review |
| --- | --- |
| Compatibility | Which commands, flags, environment variables, config files, stdin/stdout/stderr formats, exit codes, shell completions, and scripting assumptions are supported? |
| Migration | Which scripts, CI jobs, aliases, config paths, and automation consumers need changes? |
| Verification | Which golden-output, exit-code, packaging, installer, upgrade, downgrade, and platform smoke tests were run? |
| Rollback/recovery | Can users reinstall or pin the previous binary/package, and does the installer preserve config and cache state across downgrade? |

**Heuristic:** CLI compatibility is often broken by text changes that look harmless. Human-readable
output may still be a machine contract when users parse it. Counterexample: an explicitly documented
interactive-only progress message can change without a compatibility promise.

### Application Release

| Question | Release review |
| --- | --- |
| Compatibility | Which user workflows, saved state, local files, browser/device versions, OS versions, integrations, and accessibility expectations remain supported? |
| Migration | What happens to existing sessions, local storage, preferences, offline data, uploads, or in-progress work? |
| Verification | Which end-to-end, accessibility, upgrade, install, smoke, observability, and support-readiness checks establish release fitness? |
| Rollback/recovery | Can the previous application version read the new state, or does recovery require a server-side flag, data repair, app-store phased release halt, or forward patch? |

**Project default:** Application releases should record known user-visible limitations and support
scripts because support absorbs ambiguity first. The trade-off is exposing imperfection; a limited
release with clear boundaries is easier to operate than a broad promise support cannot honor.
Counterexample: a short-lived internal tool may record limitations in the ticket instead of public
release notes.

### Schema Release

| Question | Release review |
| --- | --- |
| Compatibility | Which writers, readers, backfills, replicas, analytical jobs, exports, and old application versions can coexist with the new schema? |
| Migration | Is the path expand, backfill, dual-read/write, cut over, contract, and cleanup? Which step is reversible? |
| Verification | Which migration dry run, row-count, invariant, performance, backup/restore, reconciliation, and old/new binary checks were run? |
| Rollback/recovery | If rollback cannot undo data shape changes safely, what forward repair, restore point, queue pause, or compensating migration is approved? |

**Project default:** Schema releases should treat rollback as a data-safety question, not a deploy
button. The trade-off is slower release sequencing; counterexample: adding an unused nullable column
may be reversible by dropping it if no released writer can populate it.

### Protocol Release

| Question | Release review |
| --- | --- |
| Compatibility | Which wire versions, negotiation rules, encodings, error codes, ordering guarantees, security properties, and tolerated unknown fields apply? |
| Migration | How do old and new peers discover capabilities, downgrade, reject unsupported messages, or run in mixed-version clusters? |
| Verification | Which conformance, fuzz, compatibility, replay, interop, downgrade, and security checks were run against old and new peers? |
| Rollback/recovery | Can peers negotiate the old protocol, or does recovery require blocking a peer version, disabling a capability, rotating keys, or replaying messages? |

**Project default:** Protocol releases should document negotiation and rejection behavior before
shipping because mixed-version peers are normal during rollout. The trade-off is more design work
up front; a single-process embedded protocol may not need negotiation until independent peers exist.

## Deprecation and Migration

**Project default:** Deprecation should state what is deprecated, who is affected, the replacement,
the first warning release, the earliest removal release/date, detection signals, and support path.
The trade-off is carrying old behavior longer; counterexample: a security vulnerability may require
accelerated removal with an advisory and compensating support plan.

**Project default:** Migration instructions should be executable by the consumer who owns the work.
The trade-off is more documentation and examples; counterexample: a managed service migration may
only need an operator-run plan plus customer-visible compatibility notes.

Migration evidence often includes:

- the old-to-new version path and whether skipping versions is supported;
- data backup, restore, and reconciliation references from [data](data.md);
- API or event contract changes from [API design](api-design.md);
- dependency and package-manager changes from [dependencies](dependencies.md);
- operator failure and retry behavior from [error handling](error-handling.md);
- version, tag, and changelog references from [git and versioning](git-and-versioning.md).

## Rollout and Recovery

**Project default:** Staged rollout should define stages, gates, observations, stop conditions, and
who can advance or halt the release. The trade-off is slower delivery; counterexample: a local-only
library release to a package registry may not have staged runtime traffic and instead relies on
pre-release testing plus post-release monitoring.

**Project default:** Recovery should choose rollback, roll forward, disablement, repair, or restore
based on state changes already made. The trade-off is that rollback is simpler to explain, while
forward recovery is often safer after durable writes or protocol negotiation. Counterexample: a pure
static asset release behind immutable filenames may roll back by repointing a CDN alias.

**Heuristic:** A release is not recoverable until the team can name the first irreversible step.
Examples include a destructive migration, an externally visible API removal, a package publication
that consumers mirror, a key rotation, a message-format change, or an app-store binary approval.

Recovery questions:

| Area | Release-specific question |
| --- | --- |
| Trigger | What observation stops rollout or starts recovery? |
| Authority | Who can decide rollback, forward fix, feature disablement, or restore? |
| State | What data, messages, cache, secrets, or external side effects changed? |
| Compatibility | Can old and new versions coexist during recovery? |
| Time | How long can the system remain in the mixed or degraded state? |
| Evidence | Which logs, traces, checks, support signals, and incident records prove recovery worked? |
| Communication | Who needs notice: users, customers, operators, support, maintainers, downstream packages, or regulators? |

## Release Evidence

**Project default:** Release evidence should be referenced from primary systems instead of rewritten
into release notes by hand. The trade-off is link dependence; counterexample: long-term-support or
regulated releases may need an archived evidence bundle because CI logs and dashboards expire.

Evidence can include:

| Evidence | Source of truth |
| --- | --- |
| Source identity | Commit, tag, branch policy, reviewed merge, changelog entry |
| Artifact identity | Registry coordinates, image digest, package checksum, installer hash, archive hash |
| Build context | Build workflow, runner image, toolchain versions, dependency lock/resolution |
| Provenance/attestation | SLSA/in-toto artifact produced by an authorized issuer, if adopted |
| Dependency inventory | SPDX or CycloneDX SBOM generated by project-native tooling |
| Checks | CI run, release-candidate test report, manual verification note, migration dry run |
| Rollout | Canary/stage gates, deployment record, feature flag state, monitoring window |
| Limitations | Known issues, unsupported paths, exclusions, support escalation notes |
| Recovery | Rollback/forward plan, restore point, incident link, verified recovery check |

**Standard/fact (verified 2026-08-05):** SPDX is an international open standard for software
package data exchange, and the SPDX site lists the current specification documents:
<https://spdx.dev/use/specifications/>.

**Standard/fact (verified 2026-08-05):** CycloneDX is a BOM standard whose specification represents
components, services, dependencies, compositions, vulnerabilities, and related supply-chain
information: <https://cyclonedx.org/specification/overview/>.

**Project default:** Use the ecosystem's native release and package tooling as the source of truth
when it already records package coordinates, digests, signatures, provenance, yanking, immutability,
or support metadata. The trade-off is ecosystem coupling; counterexample: a cross-ecosystem release
may need a product-level release record that links npm, PyPI, container, and installer artifacts.

## Known Limitations and Support Boundaries

**Project default:** Release notes should separate known limitations from support boundaries.
Limitations describe what is imperfect in this release; support boundaries describe what the project
will and will not help consumers operate. The trade-off is more explicit expectation-setting;
counterexample: a fully internal release may record both in the deployment ticket if the same team
builds, consumes, and supports it.

Support boundaries usually answer:

- Which release lines receive security fixes, bug fixes, migrations, or documentation updates?
- Which platforms, runtimes, regions, dependency versions, data stores, protocols, or clients are out
  of support?
- Which upgrade paths are tested, best-effort, or unsupported?
- Which known limitations are accepted temporarily, and what event reopens them?
- Which failures are product support issues versus local integration, unsupported modification, or
  third-party dependency issues?

## Release Record Template

**Project default:** The release record should be small enough to complete for every material release
and concrete enough to audit later. The trade-off is that highly regulated products may require a
separate controlled release package; a small internal service may link to the deployment record and
fill only the fields that materially differ.

**Project default:** The template records release evidence; it does not manufacture attestation.
Leave fields as `not produced`, `not applicable`, or `unknown` with a reason when evidence is absent.
The trade-off is visible incompleteness; counterexample: a release gated by policy may reject
`unknown` for required security evidence.

```yaml
release:
  product:
    name:
    form: library | service | cli | application | schema | protocol | other
    release_id:
    version_policy:
    support_boundary:

  source:
    repository:
    commit:
    tag:
    reviewed_change:
    changelog_or_release_notes:

  artifacts:
    - name:
      type:
      location:
      digest_algorithm:
      digest:
      platform_or_runtime:
      package_coordinates:

  provenance_and_inventory:
    build_record:
    attestations:
      - type:
        issuer:
        subject_artifact:
        location:
        verification_status:
    sbom:
      format: SPDX | CycloneDX | ecosystem-native | not produced
      location:
      generator:

  compatibility:
    supported_consumers:
    supported_platforms:
    supported_dependency_ranges:
    supported_schema_or_protocol_versions:
    compatibility_exclusions:

  migrations:
    required:
    path:
    reversible_steps:
    irreversible_steps:
    backup_or_restore_point:
    consumer_actions:

  checks:
    automated:
    manual:
    migration_dry_run:
    rollout_gates:
    evidence_links:

  limitations:
    known_issues:
    unsupported_paths:
    temporary_exceptions:
    recheck_trigger:

  recovery:
    rollback_available:
    forward_recovery:
    feature_disablement:
    data_repair_or_restore:
    stop_conditions:
    recovery_verification:
```

## Diagnostic Framework

For a release candidate, ask:

1. What exact source and artifact identities will consumers receive?
2. Which compatibility promises are being made, and where are the counterexamples documented?
3. Which product forms are present, and has each one answered compatibility, migration,
   verification, and rollback or forward-recovery questions?
4. Which migrations or protocol changes create irreversible state?
5. Which checks prove only build success, and which prove consumer-operable release success?
6. Which limitations and support boundaries are known before release?
7. Which evidence is primary, which is copied, and which is absent?
8. Which external attestations, SBOMs, signatures, or compliance claims were actually produced by an
   authorized issuer or tool?

## Meta-Question

If this release fails after consumers start depending on it, what identity, evidence, compatibility
promise, migration path, and recovery decision will let someone else understand and repair it?
