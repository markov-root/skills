---
knowledge:
  version: 1
  id: performance
  summary: Improve performance from measured workload bottlenecks, representative environments, explicit budgets, profiles, and before-and-after evidence.
  routes: [performance-work, resource-cost-change]
---

# performance.md — Performance and Scalability Reference

> **Purpose:** Reference for thinking about speed, capacity, and cost. Covers the discipline of measurement, the hierarchy of bottlenecks, Big-O literacy, caching, the role of the database, and the difference between _making something fast_ and _making the system handle more work_.
>
> **Read this when:** something is slow; something might become slow; deciding whether to optimise; reviewing a "performance fix"; sizing capacity for a new feature.
>
> **Do NOT** optimise without a measurement. The default outcome of guessing is slower code that's harder to read.

---

## The Premise

Two famous quotes, both right, both abused:

> _Premature optimisation is the root of all evil._ — Knuth (often quoted; the full quote includes "yet we should not pass up our opportunities in that critical 3%")

> _Make it work, make it right, make it fast._ — Kent Beck

Operational form:

1. **Don't optimise without a measurement.** The measurement tells you where to spend.
2. **Don't optimise the part that isn't the bottleneck.** Amdahl's Law: optimising a part that takes 10% of the time gives you at most a 10% improvement, no matter how clever.
3. **Don't keep optimising after the measurement says "good enough".** Performance work has its own complexity tax.

A senior reviewer's question is rarely "is this fast?" It is **"how do we know?"** and **"what was it before?"** and **"what's the budget?"**.

---

## Latency vs Throughput — Don't Conflate

| Property       | Question it answers                   | Improved by                                                          |
| -------------- | ------------------------------------- | -------------------------------------------------------------------- |
| **Latency**    | How long does _one_ request take?     | Faster algorithms, less waiting, fewer round trips, closer placement |
| **Throughput** | How many requests per second?         | Parallelism, batching, more capacity                                 |
| **Capacity**   | At what load does the system degrade? | All of the above plus load shedding                                  |

**These trade.** Batching improves throughput at the cost of latency. Caching improves latency until invalidation costs throughput. Adding parallelism improves throughput but each request may be slower due to contention. **Optimising the wrong one wastes work.**

---

## Tail Latency — The Number That Matters

The mean is a lie. **Users experience the tail.**

| Percentile   | What it represents              |
| ------------ | ------------------------------- |
| p50 (median) | "Typical" user — half are worse |
| p95          | 1 in 20 — visible to operators  |
| p99          | 1 in 100 — the user complaint   |
| p99.9        | The user who tweets             |
| max          | Worst case in the window        |

For systems composed of N sub-requests, the perceived latency is roughly the **max of the parts, not the mean**. A 99th-percentile dependency, called 10 times, produces a 99.9% chance the request is slow (because 1 - 0.99^10 ≈ 10%). **The tail amplifies in distributed systems.** Strategies:

- **Hedged requests:** issue a backup request after a timeout; take the first response.
- **Reduce fan-out:** fewer dependencies per request.
- **Fast-fail dependencies:** short timeouts; circuit breakers (see [ERROR_HANDLING](error-handling.md)).
- **Bound queues:** queuing is invisible latency.

---

## Measure First — The Tools

| Tool class                                                                                    | Use                                                                                                      |
| --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **Application metrics** (RED — rate, errors, duration; see [OBSERVABILITY](observability.md)) | "Is anything wrong?"                                                                                     |
| **Distributed tracing**                                                                       | "Where did this request spend its time?"                                                                 |
| **CPU profiler** (sampling, flamegraphs)                                                      | "Which function is hot?"                                                                                 |
| **Allocation profiler / heap dump**                                                           | "What's using memory? What's churning the GC?"                                                           |
| **Off-CPU profiler**                                                                          | "Where is time spent _waiting_?" (often more interesting than CPU)                                       |
| **Continuous profiling** in production                                                        | Detect regressions without staging                                                                       |
| **System metrics** (USE — utilisation, saturation, errors)                                    | "What's saturating? CPU, memory, disk, network, file descriptors?"                                       |
| **Database `EXPLAIN`**                                                                        | "Why is this query slow?"                                                                                |
| **`tcpdump` / `eBPF`**                                                                        | "Where in the kernel is the time going?"                                                                 |
| **Load testing** (`k6`, `wrk`, `vegeta`, `locust`)                                            | "What happens at N× current traffic?"                                                                    |
| **Chaos / fault injection**                                                                   | "How does latency behave when a dependency is slow?"                                                     |
| **Microbenchmarks**                                                                           | "Which of these implementations is faster, isolated?" — _only_ useful once you know the function matters |

**Project default:** Establish a representative baseline before optimization and repeat the same
measurement after. Profilers and telemetry perturb timing and resource use; record tool, overhead,
environment, workload, and versions.

---

## Measurement Design and Queueing

Define the user/client-observed outcome, workload, concurrency/arrival process, dataset, cache state,
environment, warm-up, samples, and stopping rule. Report distributions, effect size, variance or
confidence interval, and failures—not only the fastest run or arithmetic mean.

- Separate cold start from steady state.
- Randomize/counterbalance before/after run order when shared infrastructure drifts.
- Watch coordinated omission: a closed-loop load generator can stop sending work while the system
  stalls and under-report the worst latency.
- Track throughput, latency, errors, saturation, and queue depth together.
- Preserve raw results or a reproducible summarized artifact for regression history.

Queueing connects utilization and latency. Little's Law (`L = λW`) relates average work in a stable
system, arrival/throughput rate, and average time in system under its assumptions. Near a saturated
resource, small load increases can cause large queue/latency growth; averages can hide burst and tail
effects. Measure arrival rate and queue wait separately from service time.

Load tests must have an authorized target, traffic/data safeguards, ramp/abort limits, monitoring,
and cleanup. Do not point an unconstrained benchmark at production or a third party.

---

## The Hierarchy of Latency

**Heuristic:** These orders of magnitude are illustrative, hardware/topology dependent, and should
not be used as benchmark evidence.

| Operation                                 | Order of magnitude                          |
| ----------------------------------------- | ------------------------------------------- |
| CPU L1 cache access                       | ~1 ns                                       |
| CPU L2 cache                              | ~3–4 ns                                     |
| L3 cache                                  | ~10–20 ns                                   |
| Main memory                               | ~100 ns                                     |
| SSD random read                           | ~100 µs                                     |
| HDD seek                                  | ~10 ms                                      |
| Same-DC network round trip                | ~0.5 ms                                     |
| Cross-continent network round trip        | ~150 ms                                     |
| Software-level lock contention under load | Microseconds to milliseconds, unpredictable |

**Implications:**

- A single network hop ≈ 5000× a memory access. Cutting one round trip is worth a lot of CPU optimisation.
- Disk is slow. Avoid synchronous disk I/O on the hot path.
- Cache locality matters at the inner-loop level for compute-bound work.

---

## Where Time Goes — The Common Bottlenecks, In Order

For most application code, the bottleneck is one of:

1. **Persistence and data access.** Frequently: slow queries; missing indexes; N+1; lock contention; connection pool exhaustion.
2. **The network.** Too many round trips; chatty protocols; serialisation overhead.
3. **External services.** A 200ms third party in your hot path.
4. **Serialisation / deserialisation.** Large JSON payloads parsed repeatedly.
5. **Lock contention.** Visible only at scale.
6. **Garbage collection / memory churn.** In managed runtimes.
7. **Actual CPU work.** Less common in typical request/response applications, but often dominant in
   media, compression, cryptography, simulation, analytics, and ML workloads.

**Starting hypothesis, not diagnosis:** for a conventional data-backed application, investigate
data access and network round trips early. For embedded, frontend-heavy, streaming, search,
media-processing, scientific, and ML systems, choose an order that matches the workload. In every
case, profile before changing code.

---

## Big-O Literacy — The Floor

The constant factor changes; the asymptotic class doesn't. Know these by heart:

| Class            | What it means                         | Examples                                |
| ---------------- | ------------------------------------- | --------------------------------------- |
| `O(1)`           | Independent of input size             | Hash lookup; array index                |
| `O(log n)`       | Doubles on doubling — slow growth     | Balanced tree search; binary search     |
| `O(n)`           | Linear in input                       | One pass over a list                    |
| `O(n log n)`     | The ceiling for comparison sort       | Mergesort, quicksort                    |
| `O(n²)`          | Quadratic — breaks at modest n        | Nested loops, naive substring search    |
| `O(2ⁿ)`, `O(n!)` | Exponential / factorial — breaks fast | Naive recursion, brute-force traversals |

**The trap:** working with small inputs and shipping `O(n²)` code that's "fast enough on my laptop". A 100× growth in input produces 10,000× more work. Production has 100× more.

**Specific antipatterns:**

- A nested loop where the inner loop walks a list — pull into a hash set; `O(n)` instead of `O(n²)`.
- Repeated linear search instead of building an index once.
- Recursive calls that re-solve the same subproblem — memoise.
- Building immutable strings by repeated concatenation can be quadratic in some runtimes/patterns;
  verify the implementation and use a builder/join when the path matters.

---

## Data Access Is a Common Bottleneck

(Cross-reference [DATA](data.md).) In conventional data-backed applications, persistence is a frequent
bottleneck and a productive early hypothesis. It is not a universal one. Confirm it with traces,
profiles, query plans, and resource measurements before optimising.

| Problem                                                     | Fix                                                                |
| ----------------------------------------------------------- | ------------------------------------------------------------------ |
| Missing index                                               | Read the query plan; add a composite or partial index              |
| Wrong index — used but not optimally                        | Look at columns / order / selectivity; check `EXPLAIN ANALYZE`     |
| N+1 queries                                                 | Batched fetches; joins; dataloader pattern                         |
| Over-fetching (`SELECT *`, full row when one column needed) | Project only what you need                                         |
| Under-fetching (multiple queries for related data)          | Single query with joins or `IN` lists                              |
| Long transactions                                           | Shorten; move external I/O out of the transaction                  |
| Lock contention                                             | Reduce hot rows; queue contention; partition; sharding             |
| Connection pool exhaustion                                  | Pool too small, query times too long, leaks (unclosed connections) |
| Sequential scans on large tables                            | Index or partition                                                 |
| Bloated tables / dead rows (Postgres)                       | Vacuum strategy; auto-vacuum tuning                                |

**Two-minute diagnostic:** in your slow path, count the queries (`pg_stat_statements`, ORM query log). If the count is high, fix that _before_ optimising anything else.

---

## Caching — The Most Common Tool, The Most Common Bug

Caching trades **freshness** for **latency** (and load). Both trade-offs need an answer.

### Levels of caching

| Layer                      | Latency | Invalidation difficulty                                  |
| -------------------------- | ------- | -------------------------------------------------------- |
| Browser cache              | Instant | Hard (you don't control it)                              |
| CDN                        | ~10 ms  | Per-key purge or short TTL                               |
| Reverse proxy              | ~ms     | Local control                                            |
| Application-process memory | µs      | Lost on restart                                          |
| Distributed cache (Redis)  | ms      | Centralised, evictable                                   |
| Database query cache       | depends | Often disabled in modern DBs; query plans cached instead |
| Materialised view          | depends | Refresh policy                                           |

### The strategies

| Pattern                          | Description                                                 |
| -------------------------------- | ----------------------------------------------------------- |
| **Cache-aside**                  | App checks cache; on miss, reads source; populates cache    |
| **Read-through / write-through** | Cache library handles reads/writes against the source       |
| **Write-behind**                 | Cache writes async to the source — risk: data loss on crash |
| **Refresh-ahead**                | Refresh popular keys before they expire                     |
| **Stale-while-revalidate**       | Serve stale immediately; refresh in background              |

### The hard parts

- **Invalidation.** "When does the cache get the new value?" Prefer short TTL over complex invalidation. Complex invalidation is where the bugs live.
- **Stampede.** When N requests miss simultaneously and all hit the source. Defences: single-flight, probabilistic early expiry, brief in-cache lock.
- **Negative caching.** Cache "not found" too, with a short TTL — otherwise a missing key is a slow query every request.
- **Cache as source of truth.** Wrong. If losing the cache is bad, it's not a cache.
- **Cardinality blow-up.** "Cache per user per page per locale per device" — you've quadrupled cache size.
- **Cache poisoning.** Untrusted input shapes a key; an attacker can prime the cache with garbage. Validate before caching.
- **Hidden coupling.** A change in the source's shape breaks readers who depend on the cached shape; cache layouts are an API too.

**Rule:** if a cache is masking a database problem, fix the database problem too. The cache hides it; the cache will miss eventually.

---

## Avoiding Work — Often the Best Optimisation

Faster than doing it faster: not doing it at all.

| Technique                                      | Detail                                                                                               |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Memoise / cache**                            | Don't recompute what you already computed                                                            |
| **Lazy evaluation**                            | Defer until needed; some values are needed never                                                     |
| **Skip if unchanged** (ETags, `Last-Modified`) | "If you haven't changed, I don't want a response body"                                               |
| **Bulk operations**                            | One DB round trip with 1000 rows beats 1000 round trips with one row each                            |
| **Precompute**                                 | Materialised views, summary tables, daily roll-ups                                                   |
| **Approximate**                                | HyperLogLog for distinct counts, Count-Min Sketch for frequencies — when exact answers aren't needed |
| **Cancel**                                     | When the user has gone, stop the work                                                                |
| **Sample**                                     | Don't process every event if a 1% sample answers the question                                        |

---

## Scaling — Vertical, Horizontal, and the Distinction

| Axis                       | What it does   | When applicable                                                                         |
| -------------------------- | -------------- | --------------------------------------------------------------------------------------- |
| **Vertical (scale up)**    | Bigger machine | Database master; latency-sensitive single-process; simplest answer for low/medium scale |
| **Horizontal (scale out)** | More machines  | Stateless workers; sharded data; read replicas                                          |

Horizontal scaling requires state to be partitioned, replicated, shared, or routed consistently—not
necessarily absent. Local sessions, caches, files, and ownership can work with affinity or sharding,
but they change failover, rebalancing, and capacity behavior.

### Statelessness, in practice

| State                  | Where it should live                                                        |
| ---------------------- | --------------------------------------------------------------------------- |
| Authentication session | Shared session store or signed token (JWT/PASETO)                           |
| Application config     | Read at startup; immutable after                                            |
| User-specific cache    | Distributed cache, keyed by user                                            |
| Locks                  | Distributed lock service (with caveats — see [CONCURRENCY](concurrency.md)) |
| Files                  | Object storage, not local disk                                              |
| Logs/metrics           | Shipped out; not on local disk                                              |

### Sharding

Splitting the data across instances by some key. Common shard keys: user ID, tenant ID, geographic region. The key choice is **architecturally significant** — repartitioning is expensive.

**Choose the key carefully:**

- Distributes load evenly (no hot shards).
- Maps to the most common access pattern (queries within a shard are fast; cross-shard queries are painful).
- Doesn't change for an entity over time.

**Cross-shard joins** are the cost. Either denormalise to avoid them or accept the latency hit.

### Read replicas

For read-heavy workloads: many readers, one writer. Implications:

- **Read-your-writes:** the replica may not have your write yet. Route just-after-write reads to primary, or design the UI to tolerate it.
- **Replica lag is a metric.** Monitor it. Alert on it.
- **Failover semantics.** What happens if a replica dies? Promotes to primary? Loses uncommitted writes?

---

## Connection Pools, Thread Pools, and Why They Fail

Pools are bounded resources. They run out. When they do, everything queues behind the pool.

| Pool                              | Failure mode                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **DB connection pool**            | Long queries hold connections; new requests wait; thread/request pool fills behind them; cascading hang |
| **Thread pool**                   | Each request takes a thread; if all are blocked on I/O, no new work runs                                |
| **HTTP client pool**              | Same; outbound calls stack up                                                                           |
| **File descriptor / socket pool** | Process-level limit; reached, accept fails                                                              |

**Heuristic:** Low CPU with high latency often indicates waiting: I/O, locks, queues, dependency
latency, throttling, scheduler pauses, or an unobserved constrained resource. Measure rather than
assuming a pool is responsible.

**Discipline:**

- **Size pools deliberately.** Default "10" is rarely right. Profile.
- **Timeouts on every wait.** A pool that can wait forever is a pool that hangs forever.
- **Avoid synchronous I/O on the same threads that serve requests.** Async runtimes mitigate; sync runtimes amplify.
- **Don't hold pool resources longer than needed.** Acquire late, release early.

---

## Memory — A Distinct Concern

Slow can mean **paging**, **GC pause**, **OOM**, or **swap**. Each is a different bug.

| Symptom                                          | Possible cause                                        |
| ------------------------------------------------ | ----------------------------------------------------- |
| Periodic spikes in latency                       | GC pauses; checkpointing; cron jobs                   |
| Memory grows linearly forever                    | Leak — references retained somewhere                  |
| Memory grows then OOMs                           | Same, or an unbounded cache / queue / buffer          |
| Latency drops after a deploy and slowly degrades | Heap fragmenting; pool warm-up; cache wearing in      |
| CPU at 100%, work not getting done               | GC thrashing — heap too small relative to working set |

**Tools:**

- Heap dump on OOM (`-XX:+HeapDumpOnOutOfMemoryError`, `tracemalloc`, `pprof`).
- Continuous heap profiling.
- Memory metrics (RSS, heap used, GC pause time).

**Anti-patterns:**

- Unbounded collections (logs, history, queues, caches).
- Holding closures over large objects (one byte of `self`, ten megabytes of context).
- Concatenating strings in a loop in languages where strings are immutable.
- Reading whole files into memory when a stream works.

---

## Algorithmic Performance Gotchas

| Pattern                                                   | Trap                                                                                                                    |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Sorting a stream**                                      | `sort` requires materialising the whole stream; doesn't compose with infinite/large data                                |
| **`in` on a list**                                        | Linear scan; convert to set if used many times                                                                          |
| **Repeated immutable string concatenation in a hot loop** | Can be quadratic or allocation-heavy depending on runtime/optimization; benchmark and use a builder/join when warranted |
| **Recursion on user input depth**                         | Stack overflow; convert to iteration or tail-call                                                                       |
| **`O(n*m)` data joins in application code**               | Move to the database — joins are what databases do                                                                      |
| **Regex backtracking on adversarial input**               | Catastrophic regex performance; use a linear-time engine or rewrite                                                     |
| **Sorting then taking top-K**                             | Use a heap (`O(n log k)`), not full sort (`O(n log n)`)                                                                 |
| **Re-compiling regex / re-parsing JSON inside a loop**    | Hoist out of the loop                                                                                                   |
| **Repeated allocation in hot paths**                      | First reduce allocation; pool/reuse only with ownership, reset, memory-retention, and contention evidence               |
| **Blocking telemetry in hot path**                        | Batch/async export where loss, shutdown flush, queue bounds, and backpressure are explicitly designed                   |

---

## Frontend Performance — Some of It Lives in the Browser

If the project ships HTML/JS/CSS:

| Concern                       | Defence                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| **First contentful paint**    | Server-side rendering; critical-path CSS; defer non-essential JS                                       |
| **Largest contentful paint**  | Optimise hero images; preload the LCP element                                                          |
| **Cumulative layout shift**   | Width/height on images and embeds; reserve space for late-arriving content                             |
| **Interaction to next paint** | Avoid long tasks on the main thread; chunk work; use `requestIdleCallback` / web workers               |
| **Bundle size**               | Tree-shaking, code-splitting, lazy-load by route, don't ship dev dependencies                          |
| **Image weight**              | Modern formats (WebP, AVIF); responsive `srcset`; proper compression; lazy loading                     |
| **Font weight**               | Self-host; subset; `font-display: swap`; preload                                                       |
| **Network round trips**       | HTTP/2, HTTP/3; combine API calls where sensible; resource hints (`preconnect`, `preload`, `prefetch`) |
| **Caching**                   | Long-cache hashed assets; short-cache HTML; service workers for offline                                |

**Measurement:** combine privacy-governed real-user evidence with reproducible lab runs across the
supported device/network matrix. Include keyboard/screen-reader responsiveness, zoom/reflow, reduced
motion, input latency, and assistive-technology overhead where applicable; an optimization that
breaks accessibility is a regression.

---

## Capacity Planning — Before The Outage

| Question                           | Answer needed                                                                            |
| ---------------------------------- | ---------------------------------------------------------------------------------------- |
| What's the current load?           | Requests/sec, bytes/sec, DB queries/sec at peak                                          |
| What's the headroom?               | At what multiple of current does something break? (Run a load test — once.)              |
| What constrains safe capacity?     | Identify saturated resources, queues, dependencies, and interacting limits from evidence |
| How fast does load grow?           | Linear in users? Quadratic in features?                                                  |
| What's the deploy / recovery time? | If load doubles overnight, how long to provision?                                        |
| What's the dependency capacity?    | Their limits become your limits                                                          |

**Two non-obvious truths:**

- **Headroom matters more than current utilisation.** Running at 80% with no headroom is more dangerous than 50% with a known scaling story.
- **Capacity comes in steps.** Sharding, adding a tier, switching a database engine — none of these are 10-minute changes. Plan ahead of the cliff.
- Capacity choices also change monetary cost, energy, carbon, and hardware demand. Track total and
  per-useful-outcome impact using [cost and sustainability](cost-and-sustainability.md); do not move
  work to clients or another service and call it eliminated.

---

## Anti-Patterns

| Pattern                                             | Why it fails                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------------ |
| **"It feels slow"**                                 | Not a measurement — quantify before optimising                                 |
| **Optimising the part not on the critical path**    | Amdahl: bounded improvement                                                    |
| **"Add a cache to fix it"**                         | Often masks a bug; complicates invalidation; doesn't help cold-start           |
| **Rewriting in a faster language**                  | Often the bottleneck is not the language; profile first                        |
| **Adding parallelism without measuring contention** | More threads + a shared lock = same speed, more bugs                           |
| **Microbenchmarks that don't reflect reality**      | JIT warm-up, branch prediction, cache effects — easy to mismeasure             |
| **Increasing pool sizes "to handle more"**          | Hides the real problem (slow downstream / long transactions)                   |
| **Loading "just in case" data eagerly**             | Bigger response, slower path, all to avoid one extra request that may not come |
| **Premature horizontal scaling**                    | Distributed systems are far more expensive than vertical scaling               |
| **Optimising for the average, ignoring the tail**   | The tail is the user complaint                                                 |
| **No load test before launch**                      | Production becomes the load test                                               |
| **"Performance is the SRE team's job"**             | Performance is determined at design time; SREs can patch, not fix              |

---

## Performance Budgets

A budget makes "is it fast enough?" decidable. Set them up-front, per surface:

| Surface               | Example budget                                 |
| --------------------- | ---------------------------------------------- |
| Public API endpoint   | p99 < 300ms, p999 < 1s, error rate < 0.1%      |
| Internal service call | p99 < 50ms                                     |
| Page load (LCP)       | < 2.5s on mid-tier mobile                      |
| Background job        | Completes within X minutes; X% of jobs succeed |
| Database query        | < 100ms for read; < 500ms for write            |

The budget tells you when to optimise and when to stop. **Without a budget, you can't tell "good enough" from "needs more work" except by feeling.**

See SLI/SLO in [OBSERVABILITY](observability.md) — the same idea, framed as reliability.

---

## Diagnostic Framework

| Symptom                                | First questions                                                                           |
| -------------------------------------- | ----------------------------------------------------------------------------------------- |
| Slow page / API call                   | Trace it. Where does the time go?                                                         |
| Slow query                             | `EXPLAIN ANALYZE`. Look for sequential scans, large row estimates wrong, missing indexes. |
| Tail latency much worse than median    | Where does the tail come from? GC, dependency, lock contention, pool exhaustion?          |
| Latency grows with load                | Bottleneck has serial component or a saturating resource.                                 |
| Latency stable but throughput plateaus | Bottleneck is throughput-bound (CPU, network, DB writes).                                 |
| CPU low, slow anyway                   | Waiting somewhere — lock, I/O, pool, dependency.                                          |
| Memory grows over time                 | Leak; unbounded structure; cache without eviction.                                        |
| Latency varies wildly                  | Garbage collection; noisy neighbour; dependency variability; queueing.                    |
| Performance was fine, now isn't        | Bisect — what changed? Code, data volume, dependency?                                     |
| Local fast, production slow            | Cold caches, network latency to the DB, real concurrency, real data sizes.                |
| New replica is slower than the others  | JIT warm-up, cold cache, hardware variation, NUMA.                                        |

---

## Meta-Question

Performance is the answer to: _under realistic load, with realistic data, does this meet the user's latency, the operator's cost, and the company's growth curve?_ Anything else is bench racing.

**The decision procedure:** measure, identify the currently material constraint or set of interacting
constraints, change one causal factor, remeasure, and stop when the system meets its budget. The
limiting resource can shift, and distributed queues or coordinated omission can hide more than one.

The fastest code is the code that doesn't run.

---

_See [DATA](data.md) for the database-side detail — indexes, isolation, query planning._
_See [OBSERVABILITY](observability.md) for the metrics that make "is it fast?" answerable._
_See [ARCHITECTURE](architecture.md) for caching layers and source-of-truth design._
_See [CONCURRENCY](concurrency.md) for backpressure, lock contention, and parallel scaling._
_See [ERROR_HANDLING](error-handling.md) for timeouts and the tail-latency consequences of dependency variability._
