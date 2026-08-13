---
knowledge:
  version: 1
  id: configuration
  summary: Design configuration, secret, environment, and feature-flag contracts that are explicit, validated, observable, and safe to change.
  routes: [dependency-build-change, deployment-operations]
  sources: [src-config-standards]
---

# configuration.md — Configuration, Secrets, and Feature Flags

> **Purpose:** Reference for what to put in code, what to put in config, where config lives, how secrets are handled, how feature flags work, and how to keep "we changed a value" from being a multi-hour incident.
>
> **Read this when:** introducing a new config variable; reviewing how an environment differs from another; designing secrets handling; setting up a feature flag; auditing what's actually deployed.
>
> **Invariant (secret and policy integrity):** Do not embed production credentials or other
> non-public secret values in source or distributable artifacts. Do not let a lower-authority user,
> plugin, feature, or runtime override silently weaken a higher-authority safety, security, privacy,
> or organizational policy constraint.

---

## The Premise

> Configuration is an explicit input that selects behavior without editing the implementation.
> Which inputs should vary—and who is allowed to choose them—depends on the product form and
> lifecycle. A long-running service, reusable library, CLI, desktop/mobile application, plugin, and
> build tool need different boundaries.

### Claim classification

| Claim type          | Rule, scope, trade-off, and counterexample                                                                                                                                                                                                                                                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Invariant**       | Protect secrets, preserve higher-authority policy and safety constraints, validate before a value can cause unsafe or corrupt behavior, and report effective provenance without exposing sensitive values. Strict validation can reduce availability; an invalid optional theme preference may fall back safely while an invalid signing key must fail closed. |
| **Project default** | Make configuration type, authority, precedence, scope, lifecycle, and migration explicit; keep one reviewed artifact across equivalent service environments when practical. A mobile application may require signed per-platform builds, and a plugin may receive all configuration from its host.                                                             |
| **Heuristic**       | Environment variables, startup parsing, `.env.example`, restart-on-change, one-binary deployment, and config-as-code are useful patterns for some deployable processes. They are not universal interfaces for libraries, desktop/mobile settings, ephemeral CLIs, plugins, or build-time feature selection.                                                    |

Unless a passage is labeled otherwise, recommendations below are **project defaults** for the
product form and authority named by the section; option/tool tables, worked examples,
anti-patterns, and diagnostics are **heuristics**. The Twelve-Factor table summarizes that external
methodology and becomes project policy only when adopted.

Three operational rules:

1. **Prefer one reviewed artifact across equivalent deployment environments.** Compile-time targets
   are legitimate for mobile/desktop/platform capabilities, security hardening, or materially
   different products; make variants explicit, reproducible, and tested.
2. **Validate configuration before the affected capability serves work.** Required core config
   normally blocks readiness/startup. Invalid optional-feature config may keep the process up while
   disabling that feature and surfacing a health finding.
3. **Configuration has its own threat model.** It may contain secrets, grant capabilities, change
   routing/retention, or only control presentation. Classify it before selecting controls.

## Product Forms Change the Boundary

| Product form               | Typical authority and lifecycle                                                                                      | Counterexample to service-shaped guidance                                                                                                                                   |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Service/daemon**         | Deploy/operator policy plus runtime secret/config sources; validate before readiness, and expose revision/provenance | An optional isolated integration can remain disabled while the core service stays ready.                                                                                    |
| **Library/SDK**            | Caller supplies typed options or constructors; the host application owns environment and secrets                     | A reusable library should not read ambient environment variables at import time unless that is its explicit API.                                                            |
| **CLI/ephemeral tool**     | Command flags, config file, environment, stdin/credential helper, and policy; validate per invocation                | A one-shot formatter can use a repository file and flags without a startup health endpoint or dynamic config service.                                                       |
| **Desktop/mobile app**     | User settings, device/OS policy, signed build capabilities, managed configuration, and secure platform storage       | User preferences often change live and persist locally; “one binary for every target” may conflict with platform signing and entitlements.                                  |
| **Plugin/extension**       | Host-defined schema, capability grant, user/workspace settings, and host secret API                                  | The plugin must not invent precedence that bypasses host policy; an out-of-process plugin may receive environment values, but the host contract still owns their authority. |
| **Build-time tool/output** | Source/lock/toolchain inputs, target profile, feature set, and reproducible build metadata                           | Compile-time target selection is legitimate when it changes ABI, platform resources, dead-code elimination, or signed capabilities.                                         |

---

## The Twelve-Factor Lens

**Heuristic with explicit scope:** The _Twelve-Factor App_ methodology is a useful lens for deployed
network services. Its environment, stateless-process, port-binding, and one-codebase assumptions do
not automatically govern libraries, embedded systems, desktop/mobile products, plugins, or build
tools.

| Factor                  | Operational form                                                       |
| ----------------------- | ---------------------------------------------------------------------- |
| **Codebase**            | One codebase, many deploys                                             |
| **Dependencies**        | Explicitly declared and isolated (see [DEPENDENCIES](dependencies.md)) |
| **Config**              | Stored in the environment, never the code                              |
| **Backing services**    | Treated as attached resources (URL + credential), swappable            |
| **Build, release, run** | Distinct stages; releases are immutable                                |
| **Processes**           | Stateless; share-nothing between instances                             |
| **Port binding**        | The app exports its service via a port                                 |
| **Concurrency**         | Scale out by process model                                             |
| **Disposability**       | Fast startup, graceful shutdown                                        |
| **Dev/prod parity**     | Same code, same backing services as much as feasible                   |
| **Logs**                | Treat as event streams; don't manage files                             |
| **Admin processes**     | One-off admin tasks run as one-off processes against the same release  |

Use the factors that match the product and deployment model; document the ones intentionally not
adopted.

---

## Configuration Types and Authorities

The same value can cross several lifecycles; classify the decision, not merely its serialization:

| Type                    | Examples                                                                             | Authority, validation, and counterexample                                                                                                                                                                                                       |
| ----------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Runtime**             | Pool size, timeout, log verbosity                                                    | Operator/application authority within policy bounds; validate before activation and record effective revision. A hard real-time embedded limit may be compiled and certified instead.                                                           |
| **Build**               | Target architecture, feature set, bundle ID, optimization profile                    | Build/release authority; pin inputs and emit provenance so artifacts are reproducible. A cosmetic default that users change at runtime does not belong here.                                                                                    |
| **Deploy**              | Endpoint/region, replica role, backing-service reference                             | Deployment controller/operator authority; coordinate compatibility and rollback. A library should receive this from its host instead of discovering deployment state.                                                                           |
| **User**                | Theme, locale, shortcuts, accessibility preferences                                  | Authenticated user/device authority, scoped to that user and bounded by policy. A user preference cannot disable required access control or retention.                                                                                          |
| **Policy**              | Allowed regions, minimum TLS posture, data retention bounds, enterprise restrictions | Organization/device/tenant authority; lower-precedence inputs may narrow but not silently relax enforced constraints. Local developer mode is not a counterexample for production policy.                                                       |
| **Feature**             | Rollout cohort, experiment, kill switch, entitlement                                 | Product/operations/authorization authority depending on flag kind; owner, evaluation scope, fallback, audit, and retirement/review trigger differ. Entitlement is not merely a UI toggle.                                                       |
| **Secret**              | Credentials, signing/decryption keys, tokens                                         | The credential issuer and authorized runtime own the value; configuration may carry a reference, not expose the secret. Public test fixtures and non-secret identifiers are counterexamples to classifying every token-shaped string as secret. |
| **Domain/content data** | Tax rule, model table, country policy, tenant limit                                  | Domain authority, versioning, effective dates, and audit may matter more than config mechanics. Frequently changing regulated business data may belong in governed storage, not a source constant.                                              |

A giant `.env`, settings object, or database table can hide these distinct authorities. Separate
them logically even when one transport carries several categories.

---

## Precedence and Authority Boundaries

**Example, not a universal order:** A service/CLI might resolve later entries over earlier ones:

1. **Compiled-in defaults** (safe defaults; fail closed on missing values only where a
   safety-, security-, privacy-, or integrity-impacting capability cannot operate safely without
   them).
2. **Config files** (per environment).
3. **Environment variables.**
4. **Command-line flags.**
5. **Authorized runtime overrides** (admin interface, feature-flag service).

**Project default:** Document precedence per key/category, conflict behavior, merge-versus-replace
semantics, and provenance. Precedence cannot by itself grant authority: a command-line flag supplied
by an untrusted plugin must not override host policy, and a user setting may override an application
default without overriding device management. Secrets may use reference resolution rather than the
ordinary scalar merge chain.

Counterexamples are legitimate: CSS-like layered preferences may merge; Kubernetes-style objects
may use server-side ownership; a build may reject conflicting sources rather than pick a winner.

---

## Environment Variables — One Process Boundary

Environment variables are a common process/service deployment boundary, not a universal
configuration format. Structured files, platform settings, managed configuration services, mobile
profiles, command-line flags, and OS key stores can better preserve types, hierarchy, atomic update,
or user ownership.

### Naming

| Convention                                         | Example                                                                           |
| -------------------------------------------------- | --------------------------------------------------------------------------------- |
| `SCREAMING_SNAKE_CASE`                             | `DATABASE_URL`, `LOG_LEVEL`                                                       |
| Namespaced prefix per app                          | `MYAPP_DATABASE_URL`, not just `DATABASE_URL`                                     |
| `_URL` for connection strings                      | `DATABASE_URL=postgres://...`                                                     |
| `_FILE` suffix for paths to a file with the secret | `DATABASE_PASSWORD_FILE=/var/run/secrets/db-password` (Docker / Kubernetes idiom) |
| `_ENABLED` / `_DISABLED` for booleans              | `FEATURE_NEW_CHECKOUT_ENABLED=true`                                               |
| `_TIMEOUT_MS` / `_TIMEOUT_S` — include the unit    | `HTTP_TIMEOUT_MS=5000`, not `HTTP_TIMEOUT=5000`                                   |

### `.env` and `.env.example` when adopted

- **Project default for repositories that use dotenv-style local configuration:** keep real local
  secret-bearing `.env` files untracked, and commit or generate a non-secret example/schema that
  lists the supported variables. A library, host-managed plugin, desktop settings UI, or build tool
  with no environment-variable interface should not add `.env.example` ceremony.
- The example/schema can list each variable with:
  - A comment describing what it is.
  - A safe default (or `REQUIRED` if there is none).
  - Indication of whether it's a secret.
- Update the authoritative example/schema with the interface change, or generate it deterministically.
- Tooling can load local values (`direnv`, `dotenv`, language-specific loaders); avoid exposing
  secret values through shell history or copied command transcripts.

---

## Validate Before the Value Can Cause Harm

Validation phase depends on the consumer:

| Consumer       | Validation boundary                                                                                                                      |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Service/daemon | Parse core config before readiness; optional isolated capabilities may fail closed and report degraded/unavailable state.                |
| Library        | Validate typed options at construction or the operation that first requires them; avoid import-time reads of ambient process config.     |
| CLI            | Parse and validate per invocation before side effects; allow help/version and unrelated subcommands without requiring irrelevant config. |
| Desktop/mobile | Validate managed policy and security-critical values before use; user preferences may be repaired/defaulted with a visible explanation.  |
| Plugin         | Let the host validate schema/capabilities, then re-check trust-boundary invariants inside the plugin.                                    |
| Build-time     | Validate at configuration/build planning before producing an artifact; record the effective inputs in build provenance.                  |

For a service, a common sequence is:

1. Parse the configuration required for the capabilities being activated.
2. **Type-validate** (URL is a URL; port is 1–65535; timeout is positive).
3. **Semantic-validate local invariants** where it's cheap (can we read the signing key file? Are
   mutually dependent settings coherent?).
4. Refuse readiness/startup when required core values are invalid. For an optional isolated
   capability, fail it closed, expose the finding, and keep unrelated service only when that degraded
   mode is explicitly designed and tested.
5. Expose the redacted effective configuration revision and provenance. Logging every value can
   itself leak or create noisy, stale evidence.

**Heuristic:** For a service, deployment/startup is usually cheaper than discovering invalid core
config during a user request. Eagerly requiring unrelated optional integration credentials can make
an otherwise healthy service unavailable, so validate by activation boundary.

Separate invalid configuration from unavailable dependencies. For required core service
capabilities, malformed settings, missing required secret references, and unreadable required local
inputs are startup/readiness failures. Optional or later-activated capabilities follow their
declared activation boundary and may remain disabled with an explicit finding. A temporarily
unreachable database or queue is normally a readiness/retry concern: use bounded backoff and expose
the state through readiness or deep health checks. Do not turn one dependency blip into a restart
cascade. See [OBSERVABILITY](observability.md).

**Tools:** Pydantic Settings (Python), `viper` (Go), `config` (Node), `figment` (Rust), language-stdlib options.

---

## Secrets — Specific Handling

(Cross-reference [SECURITY](security.md).)

### Secret reference and delivery examples

**Examples, not a universal storage policy:** The selected security policy owns the storage and
delivery mechanism; configuration represents its value or reference at the appropriate activation
boundary.

| Location                                                                                       | When                                                                                                                                    |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **OS keyring / `pass`**                                                                        | Local development                                                                                                                       |
| **`.env` files**, gitignored, distinct per developer                                           | Local development, when keyring is impractical                                                                                          |
| **Cloud secret manager** (Vault, AWS Secrets Manager, GCP Secret Manager, Doppler, Infisical)  | Production                                                                                                                              |
| **Encrypted payload in the repository; decryption key held outside it** (for example SOPS/age) | Release/deploy-time decryption with explicit key custody; this need not make the application depend on a runtime secret-manager service |
| **Kubernetes Secret API object**                                                               | In-cluster delivery under the cluster's configured access and encryption-at-rest policy                                                 |

**Standard/fact (Kubernetes Secret representation):** Kubernetes API Secret `data` values are
base64-encoded; encoding is not encryption. Actual confidentiality depends on the selected cluster
encryption-at-rest, access-control, delivery, and node/runtime controls.

### Configuration boundary for secrets

**Invariant (configuration confidentiality):** A configuration interface may carry a secret value
or reference only through an authorized boundary, and its effective-config/provenance surfaces must
not expose the value. Public keys and deliberately non-secret test fixtures are outside this scope.

Configuration-specific responsibilities are to:

- document the reference shape, issuer/store authority, activation point, redaction behavior, and
  version/revision needed for rollout;
- distinguish missing reference, denied access, unreadable material, revoked/expired credential,
  and temporarily unavailable provider when callers act differently;
- validate required secret references at the affected capability's activation boundary, while an
  optional integration may remain disabled with an explicit finding; and
- expose safe provenance such as reference/revision identity without serializing the secret value.

[SECURITY](security.md) canonically owns secret storage selection, credential lifecycle and
rotation, delivery channels, exposure/incident response, and secret-scanning controls. This
configuration reference does not duplicate those policies; it defines how their selected mechanism
appears as a typed, precedence-aware, redacted configuration input.

---

## Configuration as Code — When and When Not

Config files committed to the repo, versioned, reviewed in PRs.

| Use config-as-code when             | Use a runtime service when                 |
| ----------------------------------- | ------------------------------------------ |
| Change cadence is low               | Change cadence is high                     |
| Audit trail is important            | Audit trail is provided by the service     |
| Changes correlate with code changes | Changes are independent                    |
| Reviewers want to see the diff      | Operators change settings without a deploy |

**Mixed approach:** the config schema lives in the repo (versioned, reviewed); the values for low-cadence items live in the repo (per env); high-cadence items reference a runtime service.

---

## Feature Flags — A First-Class Concept

A feature flag is a runtime switch that turns a feature on or off without a deploy.

### Categories — different cadences, different lifetimes

| Type                         | Lifetime                      | Examples                                            |
| ---------------------------- | ----------------------------- | --------------------------------------------------- |
| **Release toggle**           | Days to weeks; remove after   | "New checkout flow" gated until rolled out          |
| **Experiment toggle**        | Weeks; analysed, then removed | A/B test, gradual rollout                           |
| **Ops toggle / kill switch** | Indefinite                    | "Disable the recommendations service" when degraded |
| **Permission toggle**        | Indefinite                    | "Beta user can use feature X"                       |

**The trap:** temporary release/experiment flags becoming permanent. Every flag has an owner and a
kind. Temporary flags have an expiry/removal condition; permanent operational, permission, safety,
or product-policy flags have a review cadence and documented combinations instead.

### Discipline

- **Invariant:** Define a fail-safe fallback per flag kind and threat model. “Same as before,”
  fail-closed, last-known-good, or an operator-controlled safe state may each be correct; an
  authorization entitlement must not default open because the flag service is unreachable.
- Keep evaluation latency and availability inside the caller's budget. An in-process snapshot/cache
  or streamed update is common; a remote evaluation may be valid when the product accepts that
  dependency and bounds failure.
- Test critical states and transitions. Use pairwise/risk-based combinations for many flags and
  retain targeted full matrices for safety-critical interactions; the complete Cartesian product
  is often infeasible.
- Make effective flag revision/evaluation observable to authorized operators and affected users
  where appropriate without exposing cohort or personal data.
- Audit changes whose authority or consequence warrants it: who/what changed which revision, when,
  and under what approval/expiry.
- **Sensitive flags are gated.** Kill switches don't need the same gating as marketing toggles, but neither is "anyone with the dashboard URL".

### Tools — categories, not vendors

| Category                     | Examples                                                                   |
| ---------------------------- | -------------------------------------------------------------------------- |
| **Self-hosted, open source** | Unleash, GrowthBook, Flagsmith (self-hosted), Bucketeer, Flipt             |
| **Hosted service**           | Select through the dated provider/transfer method in [PRIVACY](privacy.md) |
| **Simple env-var flags**     | When the system is small and flag count is small — no service needed       |

---

## Environments — Dev, Staging, Production, and the Others

| Environment                | Purpose                                                                                                                |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Local development**      | Each developer's machine; can be wrong; can break                                                                      |
| **Continuous integration** | Automated verification environment; often ephemeral, with synthetic/minimized data and explicitly governed credentials |
| **Preview / ephemeral**    | Per-branch, throwaway, for review of in-progress work                                                                  |
| **Staging**                | Production-like; ideally with synthetic or anonymised production-like data                                             |
| **Production**             | Real users; real data; real consequences                                                                               |
| **DR / failover region**   | Hot standby; periodically exercised                                                                                    |

**Discipline:**

- Preserve semantic parity for behaviors the test claims. Lightweight local substitutes are valid
  for fast feedback when controlled integration tests exercise the production service/version and
  known differences are documented.
- Scope credentials to the environment/trust boundary where compromise or revocation should not
  cross; a shared public key or non-secret identifier is different.
- Use production data outside production only under an explicit privacy/security authority,
  minimization, access, retention, and deletion contract; prefer synthetic or safely transformed
  data where it establishes the needed evidence ([PRIVACY](privacy.md)).
- **Project default:** Isolate mutable databases and write authority across production and
  non-production. A governed read-only replica or sanitized snapshot can be valid; sharing the live
  write database makes tests, privacy, and blast radius unsafe.
- **The fewer differences, the fewer "works in staging, fails in prod" mysteries.**

---

## Configuration Schemas

Config without a schema is a guessing game.

| Tool                                                                    | Use                                                                      |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Typed config classes** (Pydantic, dataclasses, structs, case classes) | Self-documenting; validated on load                                      |
| **JSON Schema / OpenAPI for config**                                    | Especially when external systems supply config                           |
| **Generated `.env.example` from the schema**                            | One source of truth                                                      |
| **Generated documentation** of externally supported settings            | What it is, authority, default, allowed values, type, version, and owner |

**Project default:** Every supported setting should answer what it does, type/units, authority,
scope, default or required status, sensitivity, precedence, owner, and lifecycle. Evidence from a
schema establishes structural validity only; migration tests, policy tests, and runtime
observations establish different claims. Internal compile constants need proportionate
documentation rather than a user-facing configuration catalog.

---

## Hot Reload vs Restart

| Approach                                                            | When                                                                                          |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Restart/recreate on change**                                      | Common service default when restart cost and rollout semantics are acceptable                 |
| **Hot reload (SIGHUP, watcher, settings update)**                   | Long restart cost, interactive user preference, or operational setting that needs live change |
| **External runtime config** (feature flags, dynamic config service) | When change cadence exceeds deploy cadence                                                    |

For a coherent multi-key revision, the trap is partial activation: half the application sees the
new config, half sees the old. **Project default:**

- Reload atomically.
- Re-validate before swapping in.
- Surface what was reloaded, when, by whom.

---

## Distribution, Versioning, and Drift

For configuration shared across processes or regions, define:

- authoritative source, schema/version, signer/approver, and immutable revision ID;
- delivery consistency and propagation deadline;
- startup/cache behavior when the source is unavailable;
- atomic activation boundary and mixed-version compatibility;
- rollback to a known revision;
- secret/reference resolution without leaking values;
- audit trail and emergency-change path.

Instances should expose the effective revision and provenance without exposing secrets. Detect drift
between declared, distributed, and effective state; do not assume a successful control-plane write
means every consumer applied it.

Treat schema evolution like a data/API migration. Add readable defaults, deploy readers that
understand old/new forms, migrate producers, then remove old fields after evidence. Test rollback
and partial rollout. A dynamic configuration change needs the same causal review as a code change
when it can alter authorization, routing, retention, safety, or data integrity.

### Authority and evidence limits

| Claim                           | Authority and evidence boundary                                                                                                                                                                                                        |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **“Valid configuration”**       | The declared schema/policy owner defines validity. Parser/schema success proves represented shape and local constraints, not dependency reachability, authorization, or safe behavior.                                                 |
| **“Compatible migration”**      | The producer/consumer and rollout authorities define supported old/new combinations. Test each claimed matrix edge, rollback direction, and partial rollout that matters; one successful latest-version startup proves only that case. |
| **“Secret available”**          | The issuer/store policy and runtime identity define access. A syntactically valid secret reference does not prove authorization, freshness, revocation status, or that the value stayed out of logs.                                   |
| **“Applied everywhere”**        | The distribution/control plane supplies revision and delivery evidence; consumers supply effective-revision/health evidence. A successful write at the source proves neither propagation nor activation.                               |
| **“Safe feature/policy state”** | The feature owner plus security/privacy/domain policy defines allowed combinations. Schema validity cannot prove authorization, experiment ethics, or safe fallback.                                                                   |

When evidence is unavailable, report the exact population or lifecycle phase not observed rather
than broadening a structural validation pass into operational confidence.

---

## What Belongs Where — A Worked Example

For a payment processing service:

| Item                                 | Where it lives                                                                                                                | Why                                         |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Service name "payments"              | Code                                                                                                                          | Doesn't change per environment              |
| DB connection string                 | Env var `DATABASE_URL`                                                                                                        | Differs per environment                     |
| DB connection pool size              | Env var `DATABASE_POOL_SIZE` with default                                                                                     | Operational tunable                         |
| API key for payment provider         | Secret manager, fetched at startup                                                                                            | Sensitive                                   |
| Tax rates per country                | Database (with versioned migrations)                                                                                          | Business data; reviewers should see changes |
| Country list                         | Static file in repo                                                                                                           | Rarely changes; benefit from review         |
| Feature flag "use new checkout"      | Feature flag service                                                                                                          | High change cadence                         |
| Per-customer rate limit              | Database                                                                                                                      | Changes per customer                        |
| Kill switch "disable webhooks"       | Feature flag service                                                                                                          | Operators need to flip quickly              |
| Log level                            | Governed runtime setting; any request-scoped diagnostic override requires authorization, bounds, audit, redaction, and expiry | Operational/security-sensitive              |
| Service-to-service auth secret       | Secret manager                                                                                                                | Sensitive                                   |
| Default page size for paginated APIs | Env var with default, sane out of the box                                                                                     | Tunable                                     |

---

## Backing Services as Configuration

> A backing service is anything the app talks to over the network: databases, queues, caches, search, email, third-party APIs.

**External methodology summary (Twelve-Factor backing services):** A twelve-factor app treats
backing services as attached resources selected through configuration. That service-oriented lens
does not make every backing implementation interchangeable or govern libraries and applications
that do not adopt Twelve-Factor.

**Implications:**

- Tests can run against a local SQLite or in-memory equivalent — only if the application doesn't depend on Postgres-specific features.
- Swapping a real backing service for a fake (in tests, in dev) is a config change.
- Disaster recovery to a different region is a config change, not a code change.

---

## Anti-Patterns

| Pattern                                                             | Why it fails                                                                                                                     |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Implicit `if env == "production"` behavior fork**                 | Environment labels hide the real capability/policy and create paths exercised only in one deployment                             |
| **Secret or sensitive deploy values committed in plaintext**        | "Just for the demo" becomes history and may be distributed                                                                       |
| **Secrets in CI/CD logs**                                           | A grep over CI history yields keys                                                                                               |
| **Required config discovered only after irreversible side effects** | Failure arrives too late; libraries and optional features may still validate at their activation boundary                        |
| **Config schema implicit**                                          | Variables drift, defaults differ between services, "what does this var do?" becomes archaeology                                  |
| **`.env` shared via chat / email / drive**                          | Auditability gone; rotation impossible                                                                                           |
| **One credential shared across independent trust boundaries**       | Convenience expands compromise and revocation blast radius                                                                       |
| **Hard-coded deployment/user-specific URLs, paths, hostnames**      | The variable boundary is scattered; protocol constants and embedded targets can legitimately be code                             |
| **One giant `config.py` with everything**                           | No structure; no ownership; one file is changed for every kind of change                                                         |
| **Feature flags that never get removed**                            | The codebase has paths for every combination; testing matrix explodes                                                            |
| **Unreviewed fallback for flags**                                   | Default-on, default-off, or last-known state can each violate safety, availability, or entitlement unless selected per flag kind |
| **Hot reload that doesn't re-validate**                             | A bad config goes live silently                                                                                                  |
| **Accidental build-time bake of deploy-only values**                | Creates unnecessary artifact variants; target/ABI/signing/platform inputs are legitimate build configuration                     |
| **Per-environment branches** in git                                 | The "configuration" includes "which branch we're on" — terrifying                                                                |

---

## Diagnostic Framework

| Symptom                                                 | Likely cause                                                                  |
| ------------------------------------------------------- | ----------------------------------------------------------------------------- |
| "Works in dev, fails in prod"                           | Config divergence — different value, missing var, different format            |
| "Was working, now isn't"                                | Recent config change; rotated secret; expired token                           |
| Boot succeeds but feature fails mid-flight              | Lazy config load — promote to startup validation                              |
| Logs show "[env] using default for X"                   | Var didn't load; required var is missing                                      |
| Secret leaked in logs / error message                   | No redaction in logger; widen redaction now                                   |
| Config diff between two instances                       | They're not running the same release; one didn't pick up the change           |
| Feature flag flipped but nothing happened               | Cache TTL; flag service unreachable (defaulted off); wrong evaluation context |
| Different behaviour for different users in the same env | Feature flag, per-tenant config, or stale per-instance cache                  |
| "Nobody knows what this env var does"                   | No schema; document every var, with owner                                     |

---

## Meta-Question

Configuration answers: _which behavior may vary, at what lifecycle phase, under whose authority,
with what precedence, validation, provenance, migration, and rollback?_ Rebuilding is wrong for an
operator-tuned service value but correct for a target ABI or signed mobile entitlement. Manual
change can be acceptable for a one-off local tool but not for a fleet-wide safety control without
audit and convergence evidence.

A healthy configuration contract makes its effective non-secret state and authority obvious when
it matters. Validate at the activation boundary, expose redacted provenance, design revocation and
migration, and retire or periodically review temporary state according to its lifecycle.

---

_See [SECURITY](security.md) for secret management in the threat model._
_See [PRIVACY](privacy.md) for provider, location, access, contract, and transfer analysis._
_See [DEPENDENCIES](dependencies.md) for pinning build tools and runtime versions — also configuration._
_See [ARCHITECTURE](architecture.md) for backing services as ports/adapters._
_See [OBSERVABILITY](observability.md) for logging the effective config and auditing flag changes._
