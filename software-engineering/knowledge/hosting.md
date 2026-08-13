---
knowledge:
  version: 1
  id: hosting
  summary: Choose and operate hosting and deployment boundaries from availability, jurisdiction, security, portability, recovery, and cost constraints.
  routes: [deployment-operations]
---

# hosting.md — Hosting, Deployment, and Jurisdiction

> **Purpose:** Reference for choosing where to host, how to deploy, and which operational,
> contractual, and jurisdictional controls govern data. Covers self-hosting vs managed services,
> deployment strategies, rollback, disaster recovery, and provider exit.
>
> **House preference:** Minimize provider access and make location, jurisdiction, role, encryption,
> operations, contract, and exit explicit. Neither self-hosting nor a country name proves privacy,
> security, or reliability.
>
> **Read this when:** choosing infrastructure for a new project; reviewing where data lives; planning a deploy; designing rollback; recovering from an incident; auditing a third-party provider.
>
> **Legal note:** A data region, provider establishment, user location, contract, transfer mechanism,
> and disclosure law are distinct facts. Obtain current qualified review where legal exposure matters.

---

## The Premise

Hosting is two decisions in one:

1. **Operational:** how does this run, scale, recover, deploy?
2. **Legal / ethical:** under whose laws does the data live? Who can be compelled to disclose it? Who can change the terms unilaterally?

Vendor material often emphasizes operational features over legal and ethical consequences. Treat
both as first-class requirements: an operationally suitable service can still be unacceptable when
its roles, access, locations, contracts, transfers, or applicable law do not satisfy the workload.

---

## Jurisdiction and Provider Decision

Do not maintain a timeless country/vendor tier list. Provider ownership, subprocessors, product
terms, regions, adequacy/transfer mechanisms, surveillance law, and technical access change.

For each workload, record:

| Dimension             | Evidence                                                                           |
| --------------------- | ---------------------------------------------------------------------------------- |
| Data and purpose      | Categories/content/metadata, users, necessity, retention, recovery copies          |
| Roles                 | Controller/processor/subprocessor/recipient and actual purposes/means              |
| Locations             | Compute, storage, backups, support, telemetry, and administrative access           |
| Jurisdictions         | Provider establishment, user/data locations, disclosure/transfer exposure          |
| Access and encryption | Key holders, operator/support access, client-side/E2EE limits, metadata visibility |
| Contract              | DPA/terms, subprocessors, deletion, breach notice, audit, training/secondary use   |
| Operations            | Patch, identity/access, monitoring, incident, backup/restore, capacity, staffing   |
| Exit                  | Export format, egress/time/cost, key/data deletion, DNS/integration migration      |

Keep the resulting provider/country research in a dated source register. Re-verify before purchase,
renewal, new data categories, new region/transfer, ownership/subprocessor change, or architecture
commitment. See [privacy](privacy.md) for legal-role, DPIA, rights, and transfer analysis.

---

## Self-Hosted vs Managed — The Trade-off

| Self-hosted                   | Managed                                    |
| ----------------------------- | ------------------------------------------ |
| Full control over data        | Less to operate                            |
| Patch / upgrade burden on you | Provider handles                           |
| Hardware / IaaS cost          | Per-service cost (often higher per unit)   |
| Snowflake servers are a risk  | Provider's reliability is your reliability |
| Backup / DR is your problem   | Provider's claim to handle (verify)        |
| Direct operational control    | Contracted operational control             |

Self-hosting may improve control, but it also assigns patching, access, physical security, backups,
incident response, and availability to the project. Managed service may be safer or less safe
depending on evidence. A hybrid is often useful; choose each boundary from ranked requirements and
operational competence.

---

## Deployment Models

### Single VM / Server

Smallest setup. Application + DB + reverse proxy on one machine.

| Pro                       | Con                          |
| ------------------------- | ---------------------------- |
| Simple, cheap, observable | Single point of failure      |
| No network mysteries      | Doesn't scale horizontally   |
| Easy to understand        | Manual upgrades are downtime |

**Discipline:**

- Reverse proxy in front (Caddy, nginx, Traefik) for TLS, routing.
- Systemd unit / supervisor / Docker Compose for process management.
- Automated backups (encrypted, off-site).
- Snapshot before any destructive operation.
- Image / IaC so the box can be rebuilt without ceremony.

### Container on a host

Docker / Podman Compose. Same machine, multiple processes.

| Pro                    | Con                                    |
| ---------------------- | -------------------------------------- |
| Reproducible packaging | Containers don't make you cloud-native |
| Easy local-prod parity | The host is still a SPOF               |

### Orchestrator (Kubernetes, Nomad, Docker Swarm)

For real horizontal scaling and self-healing.

| Pro                           | Con                                        |
| ----------------------------- | ------------------------------------------ |
| Self-healing; rolling deploys | Massive complexity tax                     |
| Standard tooling, ecosystem   | Operating it is a job                      |
| Multi-host                    | Easy to over-engineer for the actual scale |

**Default position:** **don't reach for Kubernetes** unless you have specific reasons. The complexity is real; the failure modes are unique; the operational burden often dwarfs the application's own. For most homelab / small-team projects, a single VM with Docker Compose is correct.

### Platform-as-a-Service

Heroku-likes; Render; Fly.io; Railway; Coolify (self-hostable); Dokku (self-hostable).

| Pro                 | Con                                     |
| ------------------- | --------------------------------------- |
| Push to deploy      | Lock-in to the platform's model         |
| Less ops overhead   | May not be in preferred jurisdiction    |
| Good for prototypes | Costs scale unfavourably at higher load |

A self-hosted PaaS can trade managed-platform operations for direct control; it still has
infrastructure-provider, software-supply-chain, administrator, and jurisdictional exposure.

### Serverless / Functions

Stateless functions; provider scales to zero.

| Pro                         | Con                                                      |
| --------------------------- | -------------------------------------------------------- |
| Usage-linked billing        | Cold starts; per-request overhead and cost variability   |
| Managed scaling             | Platform coupling and service limits                     |
| Good for sporadic workloads | Harder local parity, state design, and tail-latency work |
|                             | Region, operator access, contract, and law need review   |

---

## Deployment Strategies

### Recreate

Stop old, start new. **Downtime during deploy.** Simplest. Fine for low-traffic, internal tools, or where a brief unavailability is acceptable.

### Rolling

Replace instances one at a time. The next instance comes up before the previous goes down. Requires:

- Health checks (readiness vs liveness — see [OBSERVABILITY](observability.md)).
- Backward-compatible code (the old and new versions run together).
- Backward-compatible schema (no destructive migration mid-rollout).

### Blue / Green

Two complete environments; deploy to the idle one; flip traffic.

| Pro                                  | Con                                                                  |
| ------------------------------------ | -------------------------------------------------------------------- |
| Instant rollback (flip traffic back) | Double the resources during the deploy                               |
| Verifiable before flip               | Stateful systems (DB) are still shared, so schema discipline matters |

### Canary

Deploy new version to a small slice of traffic; observe; if metrics are good, expand.

| Pro                                  | Con                                        |
| ------------------------------------ | ------------------------------------------ |
| Catches problems before full rollout | More moving parts (routing, observability) |
| User impact is bounded               | Slower to fully roll out                   |

### Feature Flags as Deploy Strategy

(See [CONFIGURATION](configuration.md).) Deploy the code dark; turn the feature on for a subset of users at runtime. Combines well with canary — the code is everywhere, the feature is here.

**Project default where supported:** Separate artifact deployment from user exposure with tested
flags or gradual rollout. Embedded, mobile, desktop, regulated, or tightly coupled products may have
different release mechanics.

---

## Rollback — A First-Class Concern

Every deploy is followed by a possible rollback. Design accordingly.

| Requirement                                 | Detail                                                                                     |
| ------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Forward-compatible**                      | A new version produces data the previous version can read                                  |
| **Backward-compatible**                     | A new version reads data the previous version produced                                     |
| **Schema compatibility window is explicit** | Old/new code and transitional schema work through the actual rollout and rollback sequence |
| **Configuration changes are versioned**     | Bad config rollback is the same as code rollback                                           |
| **The deploy tool supports rollback**       | One command; not "rebuild from scratch"                                                    |
| **Rolled back deploys are tested**          | Before production. A rollback that fails is worse than the original deploy.                |

**The expand-migrate-contract pattern** (see [DATA](data.md)) is the schema-side discipline that makes rollback possible.

---

## Immutable Infrastructure

| Principle                        | Detail                                                                                 |
| -------------------------------- | -------------------------------------------------------------------------------------- |
| **Servers are cattle, not pets** | Don't SSH in and fix things; rebuild from declarative configuration                    |
| **Configuration as code**        | Terraform, OpenTofu, Pulumi, Ansible, NixOS — pick one                                 |
| **Built once, deployed many**    | The artefact (container image, binary, VM image) is the same in staging and production |
| **Snapshots before changes**     | One command to roll back the world                                                     |

**The benefit:** reviewed declarations and rebuilds can reduce configuration drift and make it
detectable. They do not eliminate runtime, data, secret, provider, or emergency-change drift;
compare declared and effective state and test the rebuild path.

---

## DNS, Domains, and Email Reputation

| Concern                                    | Default                                                                                          |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| **Domain registration**                    | Current ownership, jurisdiction, recovery, registry lock, DNSSEC, support, and exit are reviewed |
| **DNSSEC**                                 | Enabled where supported                                                                          |
| **DNS provider for authoritative records** | Redundancy, security, API/change control, jurisdiction, support, and export fit the risk         |
| **DNS resolver for the application**       | Privacy, integrity, availability, caching, policy, and operational ownership are explicit        |
| **TLS certificates**                       | Let's Encrypt or Buypass; automate renewal                                                       |
| **Email sending domain**                   | SPF + DKIM + DMARC configured from day one                                                       |
| **Reverse DNS**                            | PTR records match for any IP that sends mail                                                     |
| **Anti-abuse contact**                     | Listed in WHOIS / abuse.net                                                                      |

---

## Backups — Not a Suggestion

Cross-references [DATA](data.md). The hosting-specific points:

| Discipline                                 | Detail                                                                                                                                    |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **Failure-domain separation**              | Keep recovery copies outside the primary account/credential/fault domain; another provider/region may be warranted by the disaster model. |
| **Encrypted before leaving**               | The backup is a copy of all your secrets too                                                                                              |
| **Verified by restore**                    | Schedule restore drills. A backup you've never restored is a hope, not a backup.                                                          |
| **Retention aligned with privacy**         | See [PRIVACY](privacy.md) retention discipline                                                                                            |
| **Distinct credentials**                   | Application's DB user cannot delete backups                                                                                               |
| **Immutable / append-only where possible** | Ransomware insurance                                                                                                                      |
| **Tested for restorable end-to-end**       | The bytes are not enough; the restore procedure must be exercised                                                                         |

---

## Disaster Recovery

A real DR plan answers four questions:

| Question                                        | Term                                                                 |
| ----------------------------------------------- | -------------------------------------------------------------------- |
| How much data can we lose?                      | **RPO** — Recovery Point Objective                                   |
| How long can we be down?                        | **RTO** — Recovery Time Objective                                    |
| What disasters do we cover?                     | Single-machine? Single-region? Single-provider? Single-jurisdiction? |
| Who triggers, who executes, who decides "done"? | Roles, runbooks, drills                                              |

| RTO / RPO         | Approach                                                            |
| ----------------- | ------------------------------------------------------------------- |
| Hours / Day       | Daily off-site backup; manual restore                               |
| Minutes / Minutes | Asynchronous replication; warm standby                              |
| Seconds / Seconds | Synchronous replication; hot standby with automated failover        |
| Zero / Zero       | Multi-region active-active; pay for the privilege; rarely necessary |

**Project default:** exercise the DR plan at a frequency derived from change rate, consequence,
RTO/RPO, regulation, and recovery complexity. Tabletop, restore, and failover exercises test
different claims; record which was exercised and the result.

---

## Anti-Patterns

| Pattern                                                         | Why it fails                                                                            |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Data region treated as the whole legal/privacy analysis**     | Provider role/establishment, access, contract, transfer, and disclosure law also matter |
| **Trust solely in contractual promises** about data handling    | Verify; reality matters more than paperwork                                             |
| **Manual deploys without rollback story**                       | The first bad deploy is a long outage                                                   |
| **Pet servers** that nobody documents                           | Bus factor goes to zero                                                                 |
| **No backups**                                                  | Inevitable data loss                                                                    |
| **Backups never tested**                                        | Same outcome, with extra surprise                                                       |
| **One provider, no exit plan**                                  | Provider failure = your failure; rate hike = forced migration                           |
| **Hand-edited production config**                               | Drift; irreproducibility                                                                |
| **Public S3-compatible buckets**                                | The default privacy incident                                                            |
| **TLS configured once, never rotated**                          | Some day the cert expires; alert and automate                                           |
| **DNS as an afterthought**                                      | Email delivery, security, and reputation depend on it                                   |
| **No DR plan** until the disaster                               | Plan in calm; execute in calm; survive in chaos                                         |
| **Choosing an orchestrator without a requirement it satisfies** | Operational burden can exceed the measured benefit                                      |
| **"Serverless" without cost modelling**                         | Surprising bills at scale                                                               |
| **Lift-and-shift to cloud with no architectural changes**       | Pays cloud prices for non-cloud properties                                              |

---

## Diagnostic Framework

| Symptom                                               | First steps                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Don't know where data physically lives                | Inventory it; this is also a [PRIVACY](privacy.md) requirement                                   |
| Don't know who can access or be compelled to disclose | Review provider role/establishment, operator/key access, contract, locations, and applicable law |
| Deploys are scary                                     | Improve observability; build rollback; smaller deploys, more often                               |
| Production is a snowflake                             | Build IaC; rebuild a copy in staging; iterate until matches                                      |
| Backups never tested                                  | Schedule a restore drill this week                                                               |
| Outage cascaded across services                       | Bulkhead by provider; design for graceful degradation                                            |
| Bill keeps growing                                    | Tag every resource; weekly review; sunset unused                                                 |
| Provider raises prices                                | Have an exit plan: data export, alternative chosen, rough migration path                         |
| Transfer mechanism or disclosure law changes          | Invoke the dated provider/transfer contingency and obtain current qualified review               |

---

## Meta-Question

Hosting is the answer to: _where and how does the system run, who can access or alter it, which
contracts and laws apply, and how will it recover or exit?_ Evaluate total lifecycle cost and
reversibility rather than inferring long-term value from initial price.

The healthiest hosting posture:

- Minimize operator access and failure domains; prefer user-controlled encryption where product and
  recovery requirements support it.
- Evaluate hosted services through the dated role/location/jurisdiction/contract/operations method
  in [privacy](privacy.md).
- **Reproducible infrastructure** from code.
- **Tested backups** and a practised DR plan.
- An exit or accepted-continuity plan for dependencies whose loss, change, or price could exceed the
  project's tolerance.

---

_See [PRIVACY](privacy.md) for data-subject rights, retention, provider roles, and transfer analysis._
_See [SECURITY](security.md) for operations security and patching._
_See [DATA](data.md) for backups, replication, and schema migration discipline._
_See [OBSERVABILITY](observability.md) for the metrics that turn deploys into supervised events._
_See [CONFIGURATION](configuration.md) for the environments and the secrets behind hosting._
_See [DEPENDENCIES](dependencies.md) for the supply-chain analogue to provider jurisdiction._
