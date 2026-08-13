---
knowledge:
  version: 1
  id: cost-and-sustainability
  summary: Evaluate resource cost and environmental impact with workload-specific measurements, system boundaries, trade-offs, and explicit uncertainty.
  routes: [resource-cost-change, performance-work]
  sources: [src-sustainability-standards]
---

# Cost and Sustainability Engineering

> **Purpose:** Make monetary cost, resource efficiency, energy, carbon, and hardware lifecycle
> explicit quality attributes without greenwashing or false precision.
>
> **Read this when:** architecture changes workload shape, compute, storage, data transfer,
> retention, model/provider use, scaling, deployment region, or hardware demand.

---

## Define the Outcome and Boundary

Cost and environmental impact are properties of a service delivered over a defined boundary and
time period—not of a language or cloud label in isolation.

Define:

- functional unit, such as per successful request, active user, processed record, or training run;
- included client, network, compute, storage, redundancy, build, and embodied-hardware boundaries;
- workload volume, geography, utilization, availability, retention, and recovery requirements;
- monetary budget and resource/carbon metric;
- measurement uncertainty, data source, owner, and review cadence.

Do not improve an intensity metric by making the product fail more often or shifting impact outside
the measurement boundary.

## Measure Before Claiming

**Standard/fact (verified 2026-07-30):** ISO/IEC 21031:2024 defines the Software Carbon Intensity
(SCI) specification as a methodology for calculating a rate of carbon emissions for a software
system. Source: [ISO/IEC 21031:2024](https://www.iso.org/standard/86612.html). Re-verify before
making a standards-conformance claim.

SCI or another model can structure evidence; its result is only as credible as workload,
utilization, energy, carbon-intensity, embodied-emissions, and boundary data. Report estimates and
uncertainty as estimates.

## Reduction Order

**Project default:** Prefer eliminating unnecessary work before making the same work marginally
more efficient.

1. Remove unused features, duplicate processing, needless polling, and unnecessary data.
2. Reduce work per useful outcome through algorithms, batching, caching, compression, and locality.
3. Improve utilization and right-size capacity without violating resilience headroom.
4. Shift flexible work in time or location only when privacy, latency, reliability, and verified
   energy/carbon data permit.
5. Extend hardware life and reduce churn where security/support/performance remain adequate.

Rebound effects matter: a cheaper operation may be invoked more often. Track total impact alongside
per-unit intensity.

## Architecture Questions

- Does the design multiply network hops, replicas, indexes, or serialization?
- Are caches reducing origin work or adding invalidation, memory, and stale unused data?
- Can event-driven work replace high-frequency polling?
- Can data be filtered or aggregated near its source?
- Does retention match product, recovery, legal, and audit need?
- Are model size, precision, context, and invocation frequency proportionate to the task?
- Does autoscaling preserve utilization while retaining tested failure headroom?
- Is multi-region redundancy justified by the recovery and availability objective?

## Storage, Transfer, and Retention

Classify hot, warm, cold, archival, and disposable data. Measure copies across primary stores,
indexes, analytics, logs, backups, exports, and test environments. Compression and deduplication
trade CPU for storage/transfer; benchmark the actual workload.

Deletion must respect legal hold, recovery, security, and privacy obligations. “Keep forever because
storage is cheap” externalizes operational, breach, discovery, and environmental costs.

## Cost as an Operability Signal

Track unit cost and total cost with usage and reliability:

- cost per successful outcome;
- idle versus utilized capacity;
- storage and egress growth;
- failed/retried work;
- cost by tenant/workload without exposing sensitive labels;
- forecast error and budget anomaly.

A sudden cost change can indicate a retry storm, cardinality explosion, leak, abuse, or traffic
shift. Alerts need enough context to distinguish growth from waste.

## Trade-Offs and Guardrails

Do not trade away accessibility, security, privacy, correctness, or recovery merely to improve an
environmental or monetary metric. Make the conflict visible and choose against ranked project
quality attributes.

**Heuristic:** Optimize the dominant measured resource or cost driver, then remeasure the whole
system. Local efficiency can shift work to clients, networks, operators, or another service.

## Claims

Avoid “green,” “carbon neutral,” “zero impact,” or comparative claims without a defined boundary,
method, date, evidence, and treatment of offsets. Separate measured reductions from purchased
compensation and from provider marketing.

## Meta-Question

What useful outcome are we delivering, what resources and lifecycle impacts does it require, and
which measured change reduces total cost or impact without violating a higher-ranked constraint?
