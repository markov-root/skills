---
knowledge:
  version: 1
  id: observability
  summary: Design logs, metrics, traces, and alerts around answerable operational questions, bounded data, ownership, and response workflows.
  routes: [deployment-operations, defect-diagnosis]
---

# observability.md — Logs, Metrics, Traces, and Alerts

> **Purpose:** Reference for designing systems you can actually operate. Covers the three pillars (logs, metrics, traces), SLI/SLO/SLA, alerting philosophy, debugging in production, and the discipline that prevents an incident from being a mystery.
>
> **Read this when:** adding a feature whose failure mode is unclear; designing a new service; debugging something that "shouldn't be happening"; choosing what to log; writing an alert; reviewing on-call burden.
>
> **Do NOT** treat this as a tooling shopping list. The vendor changes. The discipline doesn't.

---

## The Premise

> _In production, telemetry and retained operational evidence constrain what you can establish._
> Missing evidence increases uncertainty; telemetry itself can also be incomplete, delayed, biased,
> sampled, or wrong.

Three corollaries:

1. **If you can't observe it, you can't operate it.** A bug that can't be reproduced and can't be observed in production is a permanent feature.
2. **Logs/metrics/traces are part of the system, not an afterthought.** They have an API contract, a cost, a retention policy, and a maintenance burden.
3. **Observability is what you do when monitoring fails.** Monitoring answers questions you knew to ask. Observability lets you ask questions you didn't anticipate.

---

## The Three Pillars

| Pillar      | Question it answers                                    | Cardinality tolerance                                                       | Retention typical      |
| ----------- | ------------------------------------------------------ | --------------------------------------------------------------------------- | ---------------------- |
| **Logs**    | What happened, in detail, at a single point?           | Potentially high; storage/query systems still require bounds and governance | Purpose-based          |
| **Metrics** | How many / how often / how long, over time?            | Low — every label combination is a time series                              | Long (months to years) |
| **Traces**  | Where did a single request go, and what took the time? | Sampled                                                                     | Short (days)           |

Choosing the wrong pillar is a common mistake:

- **High-cardinality "metric"** (e.g., a label per user ID) is actually log-shaped. It will blow up your metrics store.
- **A log line counted by `wc -l`** is a metric in disguise. Emit a counter.
- **A "log" with parent-child relationships across services** is a trace.

---

## Logs — Discipline

### Structure

| Rule                                                                                                               | Why                                                                               |
| ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| **Structured (JSON or logfmt)**, not free-text                                                                     | Greppable in production scale; aggregatable in tools                              |
| **One event per line**, with explicit fields                                                                       | Multi-line logs lose half their meaning when split                                |
| **Stable field names** (`user_id`, not sometimes `userId` sometimes `userID`)                                      | Aggregations only work on consistent fields                                       |
| **Timestamps in UTC, ISO 8601, with sub-second precision**                                                         | Correlation across boxes                                                          |
| **A `correlation_id` / `trace_id` on every line of a request**                                                     | Stitch the story together                                                         |
| **Levels mean something:** `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` — and they're for _operators_, not developers | A `WARN` means "look at me later"; an `ERROR` means "page someone if it persists" |
| **No PII / secrets in logs**                                                                                       | See [PRIVACY](privacy.md) and [SECURITY](security.md)                             |
| **Logger names map to module/package**                                                                             | You can raise the level of a noisy module without silencing the whole system      |

### What to log, what not to

**Log:**

- Request enter/exit at boundaries (with `correlation_id`, method, route template, status, duration, byte counts — **not** the body by default).
- State transitions ("order moved from `pending` to `paid`").
- Errors with full context (stack trace, request id, what was being attempted, what input — sanitised).
- Authentication and authorisation events (success and failure).
- Significant business events (payment, deletion, export, share).
- Operational events (startup, shutdown, config reload, migration applied, leader election).

**Do not log:**

- Inside tight loops without rate limiting.
- Whole request/response bodies.
- Successful happy paths in fine detail at `INFO`.
- Secrets, tokens, passwords, full PII, full payment card numbers, raw national IDs.
- "Debugging" lines that should have been deleted before commit.
- Anything just because you can.

### Log levels — what they really mean

| Level                | Meaning                                   | Operator action                             |
| -------------------- | ----------------------------------------- | ------------------------------------------- |
| `DEBUG`              | Development-time detail                   | Disabled in production                      |
| `INFO`               | Significant business or operational event | Read for context during investigation       |
| `WARN`               | Something is wrong but the system coped   | Read aggregated; investigate if rate climbs |
| `ERROR`              | A request failed; the system did not cope | Should correspond to a metric you alert on  |
| `FATAL` / `CRITICAL` | The process is going to die               | Should never recur normally; pages someone  |

**Anti-pattern:** `WARN` for things that aren't problems, `ERROR` for things that didn't fail. Both teach operators to ignore the level.

### Sampling

Once log volume gets serious:

- **Head-based sampling:** Decide at request start (cheap, predictable, but you miss rare-but-important traces).
- **Tail-based sampling:** Decide at request end based on outcome (keep all errors, sample the successes).
- Preserve errors, slow requests, or other rare outcomes through tail sampling or separate
  error/metric signals when policy and privacy permit. Head sampling alone cannot know the outcome
  at request start.

---

## Metrics — The Vocabulary

### The four instruments

| Type          | What it does                                             | When to use                                                                |
| ------------- | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Counter**   | Monotonically increases (per process); resets on restart | "How many things happened?" — requests, errors, bytes                      |
| **Gauge**     | Current value, up and down                               | "How big is the queue right now?" — connections, queue depth, memory       |
| **Histogram** | Distribution of values into buckets                      | "How long do requests take?" — latency, sizes                              |
| **Summary**   | Distribution with pre-computed quantiles                 | When histogram buckets are inadequate; rarely worth it — prefer histograms |

**Project default:** Use distributions/histograms for latency and size when tail behavior matters.
Means can still support capacity/cost calculations and statistical comparison; report the statistic
that answers the question, with bucket/aggregation limits understood.

### The two methods

For any component, instrument according to one of these:

| Method  | For                                  | Signals                                                                  |
| ------- | ------------------------------------ | ------------------------------------------------------------------------ |
| **RED** | Request-driven services              | **R**ate (req/s), **E**rrors (err/s or err%), **D**uration (p50/p95/p99) |
| **USE** | Resources (CPU, memory, disk, queue) | **U**tilisation, **S**aturation, **E**rrors                              |

Most services need both: RED on the public face, USE on internal resources.

### Labels (Cardinality)

Labels multiply. A metric with three labels of cardinality 10/100/1000 produces 1,000,000 time series. Each is a row in the time-series database. This is how observability bills go through the roof.

**Rules:**

- **Bounded cardinality** on every label. `route_template` (✓), `user_id` (✗), `query_string` (✗).
- **The metric describes a class of event**, not a specific instance. The instance belongs in logs or traces.
- **Predict the cartesian product** before adding a label. 10 × 10 × 10 × 10 × 10 = 100,000 series.

---

## Tracing — The Story of One Request

A trace is a tree of **spans**. Each span represents work done at one boundary: an HTTP handler, a database query, an outbound call, a queue publish.

| Span attribute       | Default                                                                               |
| -------------------- | ------------------------------------------------------------------------------------- |
| Name                 | The operation, not the URL (`POST /orders/:id/refund`, not `POST /orders/123/refund`) |
| Start, end, duration | All three                                                                             |
| Status               | OK / error                                                                            |
| Attributes           | Coarse context: HTTP method, status code, DB system, queue name                       |
| Events               | Significant points within the span — timestamped sub-events                           |

**Trace propagation:** every outbound call carries the trace ID (HTTP `traceparent` header, queue message metadata). Without propagation, traces stop at the first hop.

**Sampling:** Choose head, tail, or hybrid sampling from traffic, cost, privacy, and diagnostic
requirements. “Keep errors/slow traces” requires an outcome-aware tail decision or a separate
capture/signal; it cannot be guaranteed by ordinary head sampling. Record rates and policies.

**Anti-pattern:** spans for trivial code paths. Each span has overhead. Cover the boundaries (network, disk, database, queue, slow internal computation), not every function call.

---

## SLIs, SLOs, SLAs — Reliability as a Product Decision

| Term                              | Meaning                                                                                   |
| --------------------------------- | ----------------------------------------------------------------------------------------- |
| **SLI** — Service Level Indicator | A measurable property of the service ("fraction of requests served in < 300 ms with 2xx") |
| **SLO** — Service Level Objective | A target for that indicator over a window ("99.5% over a rolling 28 days")                |
| **SLA** — Service Level Agreement | A contractual promise, usually with consequences if missed                                |
| **Error budget**                  | The complement of the SLO. A 99.9% SLO buys you 0.1% of failure. Spend it deliberately.   |

### Choosing SLIs

The good ones are:

- Prefer user/outcome symptoms for paging. Add predictive cause alerts when an operator can act
  before impact (for example certificate expiry, disk exhaustion, or replication lag).
- **From the user's perspective.** A backend that's 100% up but inaccessible from the client is not "up".
- **Continuously measurable.** No "we'll check on Monday".

Common patterns:

- **Availability:** good requests ÷ total requests.
- **Latency:** fraction of requests under a threshold.
- **Quality:** fraction of responses that are correct/complete (when "200 OK" is not sufficient).
- **Freshness:** age of data at read time.
- **Throughput** (for batch): records processed within a deadline.

### SLOs you can keep

- Availability targets are product/risk decisions. User-facing reliability usually needs an error
  budget below 100%; a safety or integrity invariant may legitimately target zero violations while
  still acknowledging that evidence cannot prove perfection. Do not inherit arbitrary percentages
  from another project's scale.
- **Multi-window, multi-burn-rate alerts:** alert when 2% of the monthly budget burns in 1 hour, _and_ when 5% burns in 6 hours. Avoids both noise and lag.
- **Burned budget = engineering pause.** When the budget is spent, stop shipping risky changes until it recovers.

---

## Alerting — The Hardest Part

**Alerts cost humans.** Every alert that fires interrupts someone. The cost is measured in sleep, attention, and trust.

### The Two Laws

1. **Page on actionable urgent risk.** User symptoms are usually strongest; predictive cause signals
   are valid when they reliably precede harm and have an immediate runbook.
2. **Every alert must be actionable.** If the recipient cannot do something useful, the alert is misconfigured. Either fix the system to be self-healing, or change the alert.

### The Severity Ladder

| Severity                      | What it means                      | Where it goes                                                                  |
| ----------------------------- | ---------------------------------- | ------------------------------------------------------------------------------ |
| **Page**                      | Wake someone up                    | Phone. Reserved for user-visible breakage that needs immediate human attention |
| **Ticket / chat-room ping**   | Look at this within business hours | Slack, email, ticket queue                                                     |
| **Dashboard / weekly review** | Trend, not an event                | Nowhere in real time                                                           |

If a "page" never requires action at 3 AM that couldn't wait until 9 AM, it isn't a page.

### Anti-patterns

| Pattern                                      | Why it fails                                                                              |
| -------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Alert on every error log**                 | The first noisy bug trains operators to mute alerts                                       |
| **Alert on a single threshold crossing**     | One outlier shouldn't page; use a sustained-over-window condition                         |
| **Alert on the cause, page-by-cause**        | When the cause changes, alert misses; symptom alerts catch the next bug too               |
| **No runbook**                               | Now the on-call is figuring it out from scratch                                           |
| **No silence/snooze story**                  | During known maintenance, you'll either get spammed or operators will permanently silence |
| **Hand-rolled alert thresholds copy-pasted** | They drift; the world changed; the threshold didn't                                       |

### Every alert has a runbook

A runbook entry per alert:

- What does this mean, in plain language?
- What's the first command to run?
- What does "all good" look like once mitigated?
- What's the escalation if I'm stuck?
- What's the post-incident pointer (where the story gets written)?

If you can't write the runbook, you can't write the alert.

---

## Health Checks — The Different Kinds

| Check                 | Question                                      | Consequence of failure                                                                                      |
| --------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Liveness**          | Is the process running and responsive at all? | Restart it                                                                                                  |
| **Readiness**         | Can this instance serve traffic right now?    | Stop routing to it; keep it running                                                                         |
| **Startup**           | Has it finished initialising?                 | Don't kill it for liveness yet                                                                              |
| **Deep / dependency** | Can it reach its dependencies (DB, queue)?    | Diagnostic, not orchestration-driving — otherwise one DB blip cascades into every replica failing readiness |

Readiness answers whether routing this instance can serve its declared traffic. If no request can
succeed without the database, failing readiness may be correct; if the service can degrade or
readiness removal would amplify an outage, keep dependency state diagnostic. Test orchestrator and
recovery behavior rather than applying one rule to every topology.

---

## Tracing the Request: Correlation IDs

Every request gets a correlation ID at the edge (or carries one from upstream).

- **Pass it through** every internal call, every queue message, every database session variable.
- **Log it on every log line** for that request.
- **Return it to the client** in a response header so support can find the trace from a user complaint.

Without correlation IDs, every cross-service investigation is a fishing expedition by timestamp.

---

## What to Look at First — The Operator's Mental Model

When something is wrong, the order is roughly:

1. **Is the symptom user-visible?** (SLI dashboard.) If not, deprioritise.
2. **When did it start?** Look for change correlation: deploys, config changes, traffic shifts, dependency status.
3. **Where is it?** Localise: which endpoint, which region, which version, which tenant?
4. **What's saturating?** (USE on the suspect resource: CPU, memory, disk, network, queue depth, DB connections.)
5. **What are the errors?** (Top error messages by rate; new errors first.)
6. **Drill into one slow / failed request.** (Trace + logs by correlation ID.)
7. **Form a hypothesis. Test it cheaply.** Don't restart things hoping it works.

Recording this in your runbooks turns intuition into reproducible operations.

---

## Dashboards — Curate Like Code

| Rule                                                    | Reason                                                            |
| ------------------------------------------------------- | ----------------------------------------------------------------- |
| **A dashboard is a story.**                             | Top-of-funnel signal first; details below; not 40 random panels   |
| **Each panel answers one question.**                    | If you can't write the question above the panel, delete the panel |
| **Time alignment.**                                     | Every panel on the same time range, same step                     |
| **Annotations for deploys, config changes, incidents.** | Correlate without guesswork                                       |
| **Owned and reviewed.**                                 | A dashboard with no owner becomes wrong silently                  |
| **Versioned with the service.**                         | Dashboards-as-code (Grafana JSON, Terraform)                      |

---

## On-Call Hygiene

| Practice                                                    | Why                                                                                     |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Bounded rotations** (no permanent on-call for one person) | Sustainable; spreads operational knowledge                                              |
| **Runbooks per alert**                                      | See above                                                                               |
| **Risk-based post-incident review**                         | Review events with material impact, surprise, response friction, or reusable learning   |
| **Just-culture reviews**                                    | Examine system conditions and accountability without scapegoating or suppressing candor |
| **Track alert volume**                                      | If a person paged > N times per shift, the alerts are wrong, not the person             |
| **Operational toil tracked as work**                        | Otherwise it eats engineering capacity invisibly                                        |

An incident process should name commander/coordination, technical operations, communications,
evidence timeline, containment, recovery, and escalation roles proportionate to scale. A review
records contributing conditions, detection/response/recovery gaps, what worked, prioritized actions
with owners/dates, and a check that actions actually changed the system. “Root cause” may be plural
or systemic.

---

## Logs and Privacy

Logs contain personal data the moment the application processes personal data. Discipline:

- **Redact at the source.** Centralised redaction; never trust handlers.
- **Whitelist what you log,** not blacklist what you don't.
- **Short retention for personal data;** long retention for aggregated metrics.
- **Access-log access to logs.** Who reads the logs is also a security event.
- **Logs are subject to the right of erasure** (in principle). Hard to comply with retroactively; easier with short retention.

See [PRIVACY](privacy.md) for the operational form.

---

## Telemetry Contract and Pipeline

Telemetry is a versioned data product. Define:

- semantic names, units, resource/service identity, status/error meaning, and attribute ownership;
- cardinality/privacy budgets and allowed values;
- trace/log/metric correlation and exemplar strategy;
- clock source, timestamp precision, and expected skew;
- collection, buffering, retry, backpressure, drop, sampling, retention, and access behavior.

Prefer an adopted semantic convention (for example an applicable OpenTelemetry convention) over
inventing different names in each service. Pin/version it and test upgrades; standard attributes
still require correct project semantics.

Use exemplars or correlation IDs to connect an aggregate symptom to representative traces/logs
without putting high-cardinality identifiers in every metric label. Treat identifiers as
potentially personal or sensitive.

Test telemetry:

- schema/required fields and bounded labels;
- redaction on success and error paths;
- emitted counters/histograms for known fixture behavior;
- trace propagation across queues and background work;
- alert rules against recorded or synthetic series;
- collector outage, queue saturation, throttling, and recovery;
- dashboard queries after schema/version changes.

The telemetry path must not take down the product. Bound queues and memory, define drop priority,
expose exporter/collector loss, and decide whether an audit-critical event needs a separate durable
path. Async export can reduce request latency but does not make loss, ordering, or shutdown flush
free.

Wall clocks can jump and hosts can disagree. Use monotonic clocks for durations; preserve timezone
and synchronization evidence for cross-system event time; do not infer causality from timestamps
alone.

---

## Cost — Observability Is Not Free

| Lever                                | Effect                                         |
| ------------------------------------ | ---------------------------------------------- |
| **Cardinality discipline on labels** | Often the single biggest cost lever            |
| **Sampling**                         | Logs and traces; almost never metrics          |
| **Retention tiering**                | Recent in hot storage, older compressed / cold |
| **Aggregation at the source**        | Send a counter, not 1000 events                |
| **Drop noisy debug at ingest**       | Don't transport then drop                      |

When the bill arrives, the questions are: which label exploded, which service is the noisiest, what retention is justified?

---

## Tooling — Categories, Not Vendors

Vendor names and capabilities change. Match the category to the need; choose specific tools per
[PRIVACY](privacy.md) (data flow/provider analysis) and [DEPENDENCIES](dependencies.md) (supply
chain).

| Category                | Examples                                                             |
| ----------------------- | -------------------------------------------------------------------- |
| Metrics — store + query | Prometheus, VictoriaMetrics, Mimir, M3                               |
| Metrics — push gateway  | Prometheus pushgateway (with care), OpenTelemetry Collector          |
| Logs — collection       | Vector, Fluent Bit, OpenTelemetry Collector                          |
| Logs — storage + query  | Loki, OpenSearch, ClickHouse-based stacks                            |
| Traces                  | Jaeger, Tempo, OpenTelemetry-compatible backends                     |
| Dashboards              | Grafana                                                              |
| Synthetic / uptime      | Self-hosted (Uptime Kuma, Blackbox exporter), EU-hosted alternatives |
| Error tracking          | GlitchTip, Sentry self-hosted, EU-region Sentry                      |
| Profiling (continuous)  | Pyroscope, Parca                                                     |

**The instrumentation API:** OpenTelemetry is the lingua franca. Instrument the application against OpenTelemetry; swap backends without rewriting the application.

---

## Anti-Patterns

| Pattern                                                               | Why it fails                                                                               |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **No logs, only metrics**                                             | When the alert fires, there's no context to investigate                                    |
| **No metrics, only logs**                                             | You can't see trends; alerts become regex over log streams                                 |
| **No traces in a distributed system**                                 | Every cross-service investigation is timestamp archaeology                                 |
| **Every variable as a metric label**                                  | Cardinality explosion; the bill                                                            |
| **`print()` statements that survived to production**                  | Unstructured, unsearchable, unscoped                                                       |
| **Logger initialised at module top with the file name as the logger** | Fine, but ignoring inheritance — silencing one module also silences peers if names are off |
| **Errors swallowed with `except: pass`**                              | The metric stays green; the user sees a bug; you find out from Twitter                     |
| **Latency reported as average only**                                  | Hides the tail; the tail is the user complaint                                             |
| **Health check that fails when a non-critical dependency is down**    | Cascading false outage                                                                     |
| **A single "errors" counter without labels**                          | You know something is wrong; you don't know what                                           |
| **Time-series with `path=/orders/123` as a label**                    | Per-instance label; cardinality death                                                      |
| **Dashboard built once, never reviewed**                              | The metric was renamed; the panel is silently 0 forever                                    |

---

## Diagnostic Framework

| Symptom                                                      | Likely cause                                                                                        |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| "It works locally, fails in prod"                            | An environment-specific factor not surfaced in logs/metrics — config, network, secret, scale        |
| Alerts fire constantly                                       | Threshold too tight; not symptom-based; or system genuinely broken — read the metric, not the alert |
| Alerts never fire and yet incidents happen                   | Wrong SLI; missing instrumentation at the failure boundary                                          |
| Cannot tell from logs which user was affected                | Missing correlation ID                                                                              |
| Cannot tell from metrics where a slow request spent its time | Missing traces                                                                                      |
| Cost spiking                                                 | Cardinality explosion, usually one label one service                                                |
| Logs full of secrets after an audit                          | Redaction was per-call; should be in the logger                                                     |

---

## Meta-Question

Observability is the answer to: _when the system misbehaves and we can't reproduce it, what do we have to figure out why?_ Build for the question you don't know to ask yet.

A useful internal benchmark: **time-to-first-clue**. From "the alert fires" to "I know which subsystem, which version, which user/tenant, what the actual error was" — how long? Anything over a few minutes is an investment opportunity.

---

_See [SECURITY](security.md) for what to log and what to never log._
_See [PRIVACY](privacy.md) for retention and redaction obligations._
_See [ARCHITECTURE](architecture.md) for where cross-cutting instrumentation lives._
_See [PERFORMANCE](performance.md) for the metrics that turn into capacity decisions._
_See [DEBUGGING](debugging.md) for the operational use of observability._
