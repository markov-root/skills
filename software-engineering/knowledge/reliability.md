---
knowledge:
  version: 1
  id: reliability
  summary: Set service objectives, budget capacity, design degraded modes, respond to incidents, recover, and learn causally so rigor matches consequence and operating capacity.
  routes: [deployment-operations, defect-diagnosis]
  sources: [src-reliability-standards]
---

# reliability.md — Reliability, Runbooks, and Incident Learning

> **Purpose:** Reference for deciding how much reliability engineering a given system needs and how
> to do it: service objectives, capacity, degraded modes, dependency failure, overload, operational
> readiness, incident response, recovery, and learning reviews. It is the routed owner for
> reliability targets and incident practice; observability owns the telemetry definition, and
> hosting/data own recovery mechanics.
>
> **Read this when:** setting an availability or latency target; deciding whether an outage was
> acceptable; planning for a dependency to fail or an overload; writing a runbook or an incident
> review; deciding how much rigor an incident deserves; asking "could we have prevented this?"
>
> **Do NOT** assume every system needs an SLO, a 24/7 on-call, or a formal incident program. Rigor is
> a budget you spend where consequence, service model, and operating capacity justify it.

---

## Epistemic position

**Project default:** Calibrate reliability rigor to (a) the consequence of failure, (b) the service
model, and (c) the operating capacity available to maintain the promise. A target or process that
cannot be sustained is worse than an honest, smaller one. Project instructions, contracts, and
applicable external constraints outrank this reference.

**Invariant (safety/privacy/integrity floor):** No reliability process or availability target may
silently trade away a safety, privacy, or data-integrity invariant. Where those floor constraints
bind, they are non-negotiable defaults that an outage or an availability push cannot justify; the
trade is decided explicitly by the responsible authority, never by default. Evidence of loss can
prove a violation; evidence cannot prove that a violation can never occur.

**Standard/fact:** ISO/IEC 25010:2023 includes reliability as a product-quality characteristic and
breaks it into sub-characteristics such as availability, fault tolerance, and recoverability (the
2023 revision reorganizes some 2011-era sub-characteristic names, so verify the current terminology
before a conformance claim). It is a vocabulary and checklist aid, not a mandate to adopt every
sub-characteristic, and this reference is not a conformance claim
([ISO 25010](https://www.iso.org/standard/78176.html), verified 2026-08-05).

This reference is engineering guidance, not a claim that any particular process or target is
required. There is no universal availability number.

---

## Calibrate rigor before choosing targets

Ask three questions before any reliability machinery:

| Question                          | What it changes                                                                                    |
| --------------------------------- | -------------------------------------------------------------------------------------------------- |
| **Consequence of failure**        | What loses if the system is slow or down: money, safety, trust, data, compliance, availability of another system that depends on it? |
| **Service model**                 | Is it a user-facing service, an internal batch job, a local developer tool, a library, or an embedded/offline component? How much do failure modes and recovery windows differ? |
| **Operating capacity**            | How many people and how many hours can actually maintain the promise, monitor it, and respond?     |

**Heuristic:** Service traits drive the shape of rigor:

| Service model       | Typical reliability shape                                                                                     | But watch out for                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| User-facing service | SLO/error budget, symptom alerting, readiness checks, incident response, rolling deploy                       | Over-instrumentation and alert fatigue before there is an audience to justify it   |
| Internal batch job  | Deadline/throughput objective, retry + idempotency, failure isolation, re-run/recovery path, dead-lettering   | Treating a batch like an interactive SLO; missing that a failed run may be a data-integrity event |
| Local developer tool / CLI | Fast, honest failure; clear errors; idempotent re-runs; no hidden background work                     | Silent partial writes; non-reproducible commands; hiding failure behind a non-zero-but-ignored exit code |
| Library / plugin    | Replaceable interface, fail-fast with clear contracts; caller controls retries/timeouts/backpressure          | The library hiding retries or swallowing errors and surprising callers (see [error handling](error-handling.md)) |
| Embedded / offline  | Deterministic behavior, bounded resources, graceful degradation, crash-safe state                                | Assuming network or wall-clock synchronization that the environment cannot guarantee |

**Counterexample to "always need an SLO":** a short-lived local conversion tool with no users, no
persistent state, and no external consumers can legitimately have no SLO at all; the honest
reliability artifact is a clear error and a deterministic, idempotent re-run. Conversely, a small
command-line tool that silently corrupts a user's file has an integrity problem that no SLO fixes.
The SLO is not the unit of reliability; consequence is.

---

## Service objectives: SLI/SLO/error budget as product decisions

[Observability](observability.md) defines SLI/SLO/SLA vocabulary. This reference owns the decision
method. Key judgments:

- **Choose SLIs from the user/outcome perspective**, continuously measurable, and add predictive
  cause signals only where an operator can act before impact.
- **An availability target is a risk and cost decision**, not arithmetic. A 99.99% SLO implies cost
  and process that a 99% SLO does not. Do not inherit someone else's percentage; justify your own.
- **Treat tolerance as a decision, not a default:** SLI/SLO/error-budget vocabulary and burn rules
  are defined in [observability](observability.md); the reliability-specific consequence here is
  deciding the budget is a **binding control on change** — when it is spent, slow or pause risky
  releases — and committing to honor it. A budget you never honor is theater.
- **Integrity/safety objectives can target zero violations** even while acknowledging that evidence
  cannot prove perfection; that is different from targeting 99.99% uptime.

**Heuristic:** For a single team with no dedicated ops and a modest user base, a lightweight
two-signal setup (one user-outcome availability/latency SLI + one resource signal) is usually enough
to start; grow the portfolio from what the review actually used, not from a template.

---

## Capacity, dependency failure, and overload

Reliability is as much about the edges of capacity as about the happy path.

### Dependency failure

Treat every outbound dependency (a database, queue, cache, API, DNS, clock, or another service) as a
component that will fail, and answer three questions per dependency:

1. **What is the blast radius if it fails?** Is availability, latency, correctness, or freshness hit — and for which users or downstream consumers?
2. **Does it have to block, or can the system degrade?** A global cache can often be bypassed; an order store cannot. The answer varies by request and feature, not by "the database is critical."
3. **What happens to in-flight work and queued data?** Retries need idempotency and backoff (see [error handling](error-handling.md)); queues need dead-letter and replay policy.

**Heuristic:** Isolate failure so a dependency problem cannot cascade into a system-wide one:
bulkheads (separate thread pools/processes per dependency class), timeouts with sane coupling,
bounded queue depths, and fresh-config fallbacks. A readiness check that fails whenever any
non-critical dependency is down converts a small dependency blip into a full outage (see
[observability](observability.md) on health checks).

### Overload and degraded modes

When load exceeds capacity, the system must decide *what* degrades rather than degrading randomly:

| Mechanism                | What it does                                                              | Trade-off / counterexample                                              |
| ------------------------ | ------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **Backpressure**         | A fast producer waits for a slow consumer                                | Can deadlock or pile up if the consumer never recovers; needs timeouts  |
| **Load shedding**        | Drop/queue some work to protect the rest                                 | Dropping the *wrong* work (e.g. a safety-critical call) is worse; pick the class of work to shed deliberately |
| **Bulkhead / isolation** | Limit one dependency's resource use so it cannot starve others           | Overpartitioning wastes capacity and adds complexity                    |
| **Degraded mode**        | Serve a reduced but still valuable response (fresh-from-cache, read-only) | Shipping a broken "fallback" that lies to users is worse than failing loudly |
| **Circuit breaker**      | Stop calling a failing dependency for a cooldown                          | A breaker that trips on a transient blip can amplify an outage; tune and test it |

**Counterexample to "just shed load":** if the overloaded path is the only path a regulated or
safety-relevant action can take, shedding it silently may violate the integrity floor. The honest
option may be to queue with explicit acknowledgment and a bounded deadline, or to refuse loudly with
a clear error, not to pretend the action succeeded.

**Invariant (integrity):** Degraded modes and error paths must not silently claim success. If a
batch write is throttled, a cache fallback is stale, or a background job was dropped, the observable
signals and the user-facing message must say so; silent success is a data-integrity violation even
when the happy-path metrics look green.

---

## Operational readiness

Readiness means the team can actually operate the system's failure modes before they arrive. The
minimum operational record per consequential system:

- **Runbooks per likely alert/failure** (see template below), written by the people who would execute them.
- **Playbooks for the big-failure classes**: dependency outage, overload, data-corruption suspicion, node loss, credential expiration, config error.
- **Drills for the expensive/reversible** operations: restore, failover, rollback, cert/config rotation. A drill that has never been run is a hope.
- **Change correlation discipline**: deploys and config changes are the most common triggers; keep enough version/config/rollback evidence to correlate an outage to a change (see [git and versioning](git-and-versioning.md)).

**Heuristic:** Exercise artifacts at a frequency derived from change rate, consequence, and
recovery complexity. Tabletop reviews, restore drills, and failover drills test different claims;
record which was exercised and the result rather than claiming "we tested recovery" generically.

---

## Incident response

**Project default:** An incident process should be proportionate to scale, and at a minimum the
evidence timeline and containment-before-root-cause discipline are **invariant** wherever harm can
be ongoing — no process may abandon those in the name of speed. Beyond that, five properties are the
default target:

1. **A defined coordination point** (even if "the person who notices it").
2. **Communication that happens while working** — not only in the report afterward.
3. **An evidence timeline** — what happened, when, with version/config/environment context, captured as it unfolds.
4. **Containment before root cause** — stop/limit harm first; understand later.
5. **Safe abort/rollback** — the ability to revert the recent change or disable the degraded path quickly, tested in advance.

**Emergency/solo-exception:** a solo maintainer or a seconds-critical emergency may compress 1 and 2
into a single person and a working log note, and may fall back to minimal evidence when the primary
containment action cannot wait — but even then, incident learning still requires that the timeline
and the containment action be reconstructed and recorded once the dust settles, rather than lost.

**Safe rollback is not free:** rolling back code while a schema migration or config change is
partially applied can corrupt state. The [expand/migrate/contract](data.md) discipline and forward-
and backward-compatible contracts (see [hosting](hosting.md)) are what make rollback safe. A
rollback that fails is worse than the original incident.

### Runbook template

One runbook per alert/failure class. When a check is added, its runbook is part of the check.

```text
# Runbook: <alert/condition name>
- Owner: <person or team>            // authority to run and escalate it
- Trigger: <what the alert/symptom is>
- Severity/impact: <what and who it affects; consequence class>

## Evaluate
- <first 2–3 commands/checks to confirm the condition is real and bound it>
- What "all good" / "not actually an incident" looks like

## Contain
- <first safe action to stop harm: disable feature flag, shed load, cut traffic, rollback?>
- Safe abort/rollback steps (and what to NOT do)

## Mitigate / recover
- <ordered steps, with validation after each>
- Validation: <how you confirm recovery worked, not just that a command exited 0>

## Escalate
- <when to hand off, to whom, what evidence to bring>

## Evidence & follow-up
- <timeline links, metrics, logs/traces by correlation id>
- <pointer to where the incident review will be logged>
```

**Heuristic:** If you cannot write the runbook, you cannot safely run the alert. Writing it usually
reveals the alert or the readiness gap.

---

## Incident review: blameless but causally rigorous learning

The goal of a review is a better picture of the system and a shorter, safer recovery next time — not
assignment of fault and not a generic "we'll be more careful."

**Reconcile "root cause" with conditions:** Most consequential incidents have several contributing
technical and organizational conditions that had to line up; "root cause" is often plural or
systemic, and a single named cause can be a simplification that hides the fix. Prefer a
conditions/timeline analysis: what was the intent, what was the change, what were the detecting and
response gaps, what worked, and what would have prevented or shortened this.

**Scope reviews by materiality and learning value:** Review events with material impact, surprising
failure, painful response, or reusable learning. Do not hold full formal reviews for every
transient blip — but do record every incident's disposition and any one-line lesson so nothing is
silently lost.

### Incident-review template

```text
# Incident review: <ID/title>
- Severity / outcome: <consequence class; what and who was affected>
- Duration / window: <from first symptom to recovery; timeline>

## Timeline (evidence)
- <chronological evidence: detection, changes, escalating signals, containment, recovery>
- <version/config/environment for each relevant stage>

## Contributing conditions (not a single "root cause")
- Technical conditions ...
- Organizational/process conditions ...
- Detection / response / recovery gaps ...
- What worked / went well ...

## Impact and integrity check
- <data, safety, privacy, or integrity exposure; was the integrity floor met? evidence?>

## Actions (prioritized, owned, dated)
- <each action: what, why it reduces recurrence or recovery time, owner, date>
- <a step to verify that the action actually changed the system>

## Evidence limits
- <what the review cannot establish; unknowns; unresolved hypotheses>
```

**Invariant (just culture):** A review must separate individual accountability from systemic
conditions without suppressing candor or manufacturing a scapegoat. Punishing honest incident
reporting destroys the evidence the whole program depends on; the review itself must never be a
weapon.

**Counterexample to "blame the process, never the person":** in rare cases of deliberate,
malicious, or repeatedly reckless action, individual accountability is appropriate; just culture
means handling those deliberately, not refusing ever to do so — and not pointing fingers at someone
whose only error was following a flawed system.

---

## Data recovery and disaster recovery

Cross-references [hosting](hosting.md) and [data](data.md). The reliability-relevant decisions:

- **RPO/RTO are product decisions** ("how much data can we lose, how long can we be down"), and they
  determine backup/replication/recovery architecture, not the other way around.
- **A backup is not proven until it is restored.** Schedule restore exercises; "we have backups"
  is a claim about hopes until an actual restore has been run end-to-end.
- **Data corruption is a distinct class** from data loss: loss protection does not protect against
  silently-corrupted bytes. Detect via checksums, invariants, and anomaly signals; keep enough
  history to recover a pre-corruption point.
- **Failure-domain separation** for recovery copies: credentials, accounts, and physical/regional
  failure domains should not all share one point of failure with the primary.

**Counterexample to "more redundancy is always better":** synchronous replication to a second
region imposes extra latency and cost and can introduce its own failure modes; the correct choice is
set by the genuine RPO/RTO requirement, not by a default preference for more copies.

---

## Scenario notes

### Batch job

- A failed batch run is often an integrity or freshness event, not just an availability one.
- Design for **idempotent, resumable re-runs** and a bounded window: checkpoints, replay, dead-letter
  handling, and a definition of "the run is complete" that includes a validation step.
- Distinguish **retryable** (transient) from **non-retryable** (permanent input/config) failures;
  retrying the latter is how a batch can double-post or loop.

### Local tool / CLI

- The reliable failure mode is **loud, early, and informative**, with a non-zero exit code and no
  silent partial writes; atomic write-then-rename and a clear "what to do next" are the substance.
- Idempotent re-runs matter here too; a tool that corrupts on the second run is unreliable even
  though it "completed" the first time.

### Service

- The reliability surface is SLO/error budget, symptom alerting, readiness/liveness, change
  correlation, rollback, and incident review — but sized to consequence and operating capacity.
- Watch for **cascading failure** across dependencies and across services; the fix is usually
  isolation and explicit degradation, not more replicas alone.

---

## Anti-patterns

| Pattern                                                                  | Why it fails                                                                              |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| **Inherited availability percentage**                                    | Copies another project's cost/risk trade-off without its justification                    |
| **SLO with no honored error budget**                                     | Theater; changes keep shipping through a "spent" budget                                    |
| **Readiness fails on any dependency blip**                               | One small outage becomes a full outage                                                     |
| **Silent degraded mode** (stale cache/read-only presented as fresh)      | Integrity violation; operators and users believe the happy path held                       |
| **Retrying non-retryable batch failures**                                | Double-posting, loops, wasted capacity                                                     |
| **"Root cause" hunt for one name**                                       | Hides the systemic/causal conditions that actually need fixing                             |
| **Reviewing every blip formally / reviewing nothing**                    | Either process-fatigue or silent unlearned incidents                                       |
| **Blame-oriented review**                                                 | Suppresses future reporting; kills the evidence base                                       |
| **Rollback tested never / rollback that corrupts**                       | Recovery action worsens the incident                                                       |
| **"We have backups" with no restore drill**                              | A claim about hopes, not a capability                                                      |
| **No runbook on the paging alert**                                       | The on-call reconstructs everything from scratch at 3 AM                                   |
| **Degrading the integrity floor to meet an uptime target**               | Equality of an availability number with a safety/data-integrity breach                     |

---

## Diagnostic framework

| Symptom                                                              | Likely cause / first thing to check                                                        |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| "It was fine until the deploy/config change"                         | Change correlation; roll back or disable the change and watch                              |
| One dependency outage took everything down                           | Readiness/liveness coupling; bulkheads; missing degradation for non-critical dependencies |
| Alerts fire but a runbook doesn't exist                              | Add the runbook when the alert is added; otherwise it is noise                             |
| Same incident keeps recurring                                        | Review produced no verified action, or the action was never proven to change the system   |
| Error budget spent but releases continue                             | The budget is not a control; make it one or drop it                                        |
| Batch "succeeded" but data is wrong                                  | Silent partial writes / non-idempotent re-run; add validation + idempotency checks        |
| "We have backups" but restore takes days                             | RPO/RTO never specified; restore path never exercised                                     |
| Incident reviews find only "human error"                            | Single-cause attribution; dig for systemic conditions and response gaps                   |

---

## Meta-Question

Are the objectives, capacity boundaries, and incident practice all sized to *this* system's
consequence, service model, and operating capacity — and does the safest, most reversible action
available degrade cleanly, honest about what it no longer guarantees?

---

_See [OBSERVABILITY](observability.md) for SLI/SLO/SLA definition and telemetry._
_See [ERROR HANDLING](error-handling.md) for retries, timeouts, and circuit breakers._
_See [CONCURRENCY](concurrency.md) for backpressure and queue/dead-letter semantics._
_See [HOSTING](hosting.md) for deployment/DR/rollback and provider failure domains._
_See [DATA](data.md) for backup/restore/replication and schema migration._
_See [PERFORMANCE](performance.md) for the measurements that become capacity targets._
_See [DEBUGGING](debugging.md) for reproducing and localizing a production defect._
