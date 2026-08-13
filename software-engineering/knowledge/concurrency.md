---
knowledge:
  version: 1
  id: concurrency
  summary: Reason about shared state, ordering, consistency, coordination, retries, and failure across concurrent and distributed execution.
  routes: [database-schema-migration, api-event-contract]
  sources: [src-concurrency-foundations]
---

# concurrency.md — Concurrency, Parallelism, and Distributed Coordination

> **Purpose:** Reference for thinking about overlapping work. Covers the difference between concurrency and parallelism, the failure modes that arise from each (races, deadlocks, livelocks, starvation), the primitives that fix them, and the distributed-systems consequences (CAP, consensus, ordering, duplicate delivery).
>
> **Read this when:** designing anything with more than one thread, more than one process, more than one request in flight, or more than one machine; debugging "it only happens sometimes"; reviewing a lock; choosing a queue or coordination service.
>
> **Do NOT** "add a lock to make it safe." Locks are a tool, not a defence. Most concurrency bugs are visible only at scale or under load and survive code review.

---

## The Premise

Most code is read in isolation, executed concurrently. The bugs that result are the hardest to reproduce, the hardest to test, and the ones that hurt the most in production. A senior reviewer's question is almost always: **what happens if two of these run at the same time?**

Two foundational distinctions:

|                 | Definition                                             | Example                                           |
| --------------- | ------------------------------------------------------ | ------------------------------------------------- |
| **Concurrency** | Multiple tasks make progress over the same time period | One thread, an event loop, juggling many requests |
| **Parallelism** | Multiple tasks execute literally at the same time      | Multiple CPU cores, multiple machines             |

Concurrency is about _structure_. Parallelism is about _execution_. A program can be concurrent without being parallel; it can be parallel without much concurrency. The bugs live mostly in the concurrent structure.

---

## The Four Canonical Failure Modes

| Name               | What it is                                                                                              | When to suspect                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| **Race condition** | The outcome depends on the _order_ in which concurrent operations happen, and that order isn't enforced | "Sometimes the count is wrong"; "it works in tests, fails under load" |
| **Deadlock**       | Two or more tasks each wait for a resource the other holds; none progresses                             | "It hangs and never times out"                                        |
| **Livelock**       | Tasks keep changing state to "fix" the other; none progresses                                           | "CPU is busy but nothing gets done"; retry storms                     |
| **Starvation**     | One task never gets the resource because others always win                                              | "Some requests are fast, a few wait forever"                          |

Two more, less famous but equally important:

| Name                   | What it is                                                                                                                                                |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Priority inversion** | A low-priority task holds a lock a high-priority task needs; an even higher priority task preempts the low-priority one, and the high-priority task waits |
| **Lost update**        | Two writers read the same value, each computes a new value, each writes back — the second overwrites the first                                            |

---

## Name the Execution Model First

Concurrent systems do not share one failure model. A useful review starts by naming the execution
model and the assumptions it gives you. Interleaving is central in shared-memory and async-task code;
distributed work adds delivery and partial-failure assumptions that a lock or event-loop rule cannot
settle.

| Model                         | Ordering assumption                                                                                                             | Atomicity assumption                                                                                             | Memory / visibility assumption                                                                                           | Fairness assumption                                                                                                      | Cancellation assumption                                                                                                       | Resource-lifetime assumption                                                                                                      | Delivery assumption                                                                                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Shared-memory threads**     | Operations may be observed in different orders unless a lock, atomic ordering, or language happens-before edge constrains them. | Single machine instructions are not business transactions; atomic read-modify-write covers only the named object. | Threads share an address space, but compilers and CPUs may reorder visibility within the language memory model.           | Scheduler fairness is runtime/OS policy; a runnable thread may still starve behind priority, locks, or CPU saturation.   | Usually cooperative through flags/tokens plus blocking-call interruption limits; unsafe forced thread death can break invariants. | Ownership and cleanup depend on lexical scope, lock discipline, RAII/context managers, or explicit supervisor policy.             | Function calls are not delivered messages; external I/O still has the transport semantics of that boundary.                                                |
| **Async tasks / event loops** | Code between suspension points is locally sequential; tasks interleave at `await`, callbacks, timers, and event-loop turns.      | A non-awaiting block is only atomic with respect to tasks on the same loop, not with respect to threads, signals, or other processes. | State owned exclusively by one loop is visible in program order on that loop; shared objects crossing loops/workers need synchronization. | Event-loop fairness depends on yielding; CPU-bound or blocking work can starve unrelated tasks.                          | Cancellation is commonly cooperative and injected at suspension points; cleanup requires awaited cancellation/finalizers.         | Owner scopes make task errors, cancellation, and cleanup observable to the caller that created the work.                          | In-process task scheduling is not broker delivery; once work crosses a queue/socket, the documented delivery and acknowledgment contract controls.            |
| **Multiprocess / same host**  | Processes have independent schedulers; shared files, sockets, databases, and IPC define the ordering you can rely on.            | A syscall, filesystem rename, database transaction, or IPC operation may be atomic only within its documented scope. | Memory is isolated unless explicitly shared; shared memory segments need the same synchronization care as threads.         | OS scheduling and resource limits can favor one process; lock files and queues can starve without policy.                | Signals and process termination may interrupt work at boundaries that library cleanup code did not expect.                       | Orphaned child processes, descriptors, temp files, and locks need process-group, supervisor, or lease cleanup.                   | Local queues and IPC can still drop, duplicate, or reorder under restart or buffer overflow depending on their contract.                                    |
| **Distributed systems**       | There is no implicit global order; protocols supply per-key, per-partition, causal, or consensus-backed order when they say so. | A transaction, compare-and-swap, or consensus decision is atomic only inside its quorum/replica/transaction boundary. | Nodes do not share memory; caches and replicas expose stale, causal, or linearisable views according to the data contract. | Network, leader election, queues, and retry policy can indefinitely delay one actor even while the system serves others. | Caller cancellation may stop waiting, but it does not prove the remote operation stopped or rolled back.                         | Resource lifetime crosses leases, sessions, heartbeats, fencing tokens, durable records, and reconciliation jobs.                | Messages may be lost, delayed, duplicated, reordered, or acknowledged ambiguously unless a protocol states a narrower guarantee.                            |

**Project default:** Write down the model before choosing a primitive. Scope: design reviews for
code with overlapping work. Trade-off: this slows small reviews; a counterexample is a local CLI that
uses one short-lived worker thread and no shared state, where the model is obvious from the code.

### Model-specific review drills

- **Shared-memory:** Which variables are shared, which primitive establishes visibility/order for
  each invariant, and what happens if the scheduler switches at each synchronization boundary?
- **Async-task:** Which state survives across suspension points, which tasks own it, and what cleanup
  runs if cancellation arrives between two awaits?
- **Multiprocess:** Which external resources act as the shared state, and what contract makes a file,
  lock, IPC message, or database write atomic enough for this operation?
- **Distributed:** Which component owns delivery, ordering, deduplication, leases, and reconciliation?
  Link API idempotency/wire semantics to [API design](api-design.md); keep delivery and ordering
  assumptions here.

---

## Shared Mutable State — The Source of Many Bugs

**House preference:** Minimize shared mutable state and make the remaining ownership rule explicit.
Scope: ordinary application services where clarity and recoverability outrank maximal shared-memory
throughput. Trade-off: copying, message passing, or sharding can add latency and memory cost; a
counterexample is a high-throughput in-memory index where shared atomic state is the simpler,
measured design.

Common options:

| Option                                                       | What it buys                                                                 | Main cost / counterexample                                                                                                      |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **No shared state**                                          | Each task owns its memory; channels, queues, or messages expose boundaries.  | Serialization and queueing cost can dominate tiny hot paths.                                                                    |
| **Shared immutable state**                                   | Readers cannot race with mutation.                                           | Snapshot rebuilds can be too expensive for large, frequently updated structures.                                                |
| **Shared mutable state, isolated by ownership**              | One owner at a time; local reasoning remains possible.                       | Ownership transfer can be awkward when several operations need a consistent multi-object view.                                  |
| **Shared mutable state, protected by synchronization**       | Efficient for small critical sections and well-scoped invariants.            | Lock ordering, priority inversion, and memory-model details become part of the correctness argument.                            |
| **Shared mutable state without synchronization or ownership** | Sometimes appears to work in a single-threaded test.                         | If at least one concurrent access mutates observable state, the program lacks a portable correctness contract.                   |

**Heuristic:** Treat atomic types and lock-free structures as synchronization, not as a magic
exception to the shared-state problem. They may be the right primitive for counters, flags, and
specialized queues; a counterexample is using several independent atomics to represent one business
invariant without a protocol that makes the combined state coherent.

---

## Synchronisation Primitives — A Map

| Primitive                               | What it is                                              | Use when                                                                             |
| --------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| **Mutex / Lock**                        | Only one holder at a time                               | Short critical sections; "no two of these at once"                                   |
| **Read-write lock (RW lock)**           | Many readers or one writer                              | Read-heavy access patterns; long critical sections — measure before assuming it wins |
| **Semaphore**                           | A counter; allows N holders                             | Resource pools (e.g., "at most 10 outbound connections")                             |
| **Condition variable**                  | Wait until another thread signals                       | Producer/consumer; waiting on a predicate                                            |
| **Barrier**                             | All N tasks wait until all reach this point             | Phased computation                                                                   |
| **Atomic operations**                   | Single-instruction read-modify-write                    | Counters, flags, lock-free queues                                                    |
| **Channels**                            | Typed message passing between goroutines/tasks          | When you want to _communicate_, not share memory                                     |
| **Actors / mailboxes**                  | A single-threaded object processing a queue of messages | Encapsulated state, sequential local reasoning                                       |
| **STM (software transactional memory)** | Optimistic atomic blocks                                | Rarely available; powerful where it is                                               |
| **Futures / Promises**                  | "This value, eventually"                                | Composing asynchronous work                                                          |

**Heuristic:** If you find yourself reaching for a mutex, first ask whether you can remove or
isolate the sharing. A lock remains the clearest correct tool for many small critical sections.

---

## Locks — Discipline

When you must lock:

| Rule                                                                             | Why                                                                                                          |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Hold the lock for the shortest possible time**                                 | Long critical sections create contention and increase deadlock probability                                   |
| **Avoid uncontrolled callouts from inside a lock** (I/O or callbacks)            | The callee may acquire another lock or block indefinitely; a tightly specified non-blocking call can be safe |
| **Consistent lock ordering** — a global, documented total order across all locks | Out-of-order acquisition is the canonical cause of deadlock                                                  |
| **Use try-lock/deadlines when ordering cannot be guaranteed**                    | Bounds waiting and surfaces contention; a timeout does not by itself diagnose deadlock                       |
| **Each lock protects a specific set of state** — document what                   | A lock with no documented invariant is a lock no one trusts                                                  |
| **Don't lock around the entire object** if only one field is shared              | Coarse locks turn into bottlenecks                                                                           |
| **Prefer immutable snapshots plus a language-supported atomic publication step** | Readers can see a whole old or new snapshot when the memory model and primitive guarantee safe publication   |
| **Avoid recursive (reentrant) locks**                                            | They make hidden ordering bugs survive longer                                                                |
| **Avoid releasing a lock you didn't acquire**                                    | Some languages allow it; most invariants don't survive it                                                    |

### Lock-free is not "lock fast"

Lock-free / wait-free data structures are not faster; they are different. They avoid the failure modes of blocking (deadlock, priority inversion) but require careful reasoning about memory models. **Project default:** for production application code, use existing implementations (`AtomicLong`, `ConcurrentHashMap`, lock-free queues from a battle-tested library). Build your own only when implementing concurrency primitives is the assignment: for example, a runtime/library team, safety-critical work with reviewed bespoke requirements, or education/research where the implementation is the point.

---

## Memory Model — The Hard Truth

Modern CPUs and compilers reorder reads and writes. Threads do not see a single linear history of memory operations. **Reads and writes that look adjacent in the source may execute and become visible in different orders.**

Without a synchronisation primitive that establishes a happens-before relationship:

- A thread that writes `flag = true` and then reads `value` may see writes to `value` that happened _before_ the flag was set — or not — depending on the architecture and compiler.
- "I checked, then I acted" without a lock or atomic primitive **does not establish that the check is still true when you act.** This is TOCTOU at the memory level.

Each language has a memory model. Read it once for the language you use. Default rule: use synchronisation primitives correctly, and let the runtime guarantee ordering.

---

## Common Mistakes (and What They Look Like)

| Mistake                                                     | Example                                                                                       | Fix                                                                                   |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Check-then-act**                                          | `if not exists(x): create(x)` between two callers                                             | Atomic upsert; unique constraint at the database; lock around the whole operation     |
| **Read-modify-write**                                       | `counter = counter + 1` from multiple threads                                                 | Atomic increment; mutex; database `UPDATE counter = counter + 1`                      |
| **Iterating a collection while another thread modifies it** | `ConcurrentModificationException`                                                             | Snapshot; copy-on-write; explicit lock                                                |
| **Double-checked locking, broken**                          | "Check without lock, then lock, then check again, then init" — without proper volatile/atomic | Use the language's idiom (e.g., `lazy` in Kotlin, `Lazy<T>` in C#, `sync.Once` in Go) |
| **Reading uninitialised data**                              | A constructor publishes `this` before finishing — another thread sees a half-built object     | Don't leak `this` from a constructor; final/immutable fields where possible           |
| **Spinning without a barrier**                              | `while not done: pass` may never see `done = true` from another thread                        | Atomic / volatile / synchronisation primitive                                         |
| **`time.sleep` to wait for an event**                       | The window is arbitrary and wrong                                                             | Condition variable, channel, or future                                                |
| **Cancellation ignored**                                    | A long task continues after the user / caller has gone                                        | Cooperative cancellation; check the cancellation token at safe points                 |
| **Resource leaked on exception inside a parallel region**   | One thread fails; others run to completion; cleanup never happens                             | Structured concurrency (see below)                                                    |
| **`async` function called without `await` or supervision**  | Background work may outlive its owner and discard errors                                      | Await it or register it with an explicit supervised task scope                        |

---

## Patterns That Make Concurrency Safer

### Structured concurrency

> Concurrent tasks have a lexical scope. They are spawned inside a block. The block does not exit until every spawned task has exited.

| Language | Idiom                                                  |
| -------- | ------------------------------------------------------ |
| Python   | `asyncio.TaskGroup`, `trio.Nursery`                    |
| Kotlin   | `coroutineScope { }`                                   |
| Swift    | `TaskGroup`                                            |
| Java     | Project Loom's `StructuredTaskScope`                   |
| Rust     | `async-std` / `tokio::task::JoinSet`, `futures::join!` |

Benefits:

- Errors in any task propagate to the scope.
- Cancellation cascades.
- Resource lifetimes are tied to scope.
- "Where did this background task come from?" becomes "the enclosing scope".

**Anti-pattern:** fire-and-forget. A task whose lifetime exceeds the scope that created it is an orphan; orphans don't surface their errors, and no one supervises them.

### Channels and message passing

**Heuristic:** Prefer communication patterns that transfer ownership or serialize access over shared
mutable state. Message passing is one common way to do that.

| Property                           | Benefit                                      |
| ---------------------------------- | -------------------------------------------- |
| One owner at a time (the receiver) | Eliminates shared-state races                |
| Buffered or unbuffered             | Bounded buffers provide natural backpressure |
| Select / multiplexing              | "Whichever channel is ready" without locks   |
| Done channels                      | Cancellation by closing                      |

### Actor model

One object, one mailbox, one logical thread of execution. The actor processes messages serially. External callers send messages; they never call methods directly. Internal state is private and accessed only by the actor.

Works well for: stateful entities (a connection, a session, a game character), event-driven workflows.

Watch out for: actor-graph deadlocks; "back-and-forth" between two actors that build a synchronous dependency.

### Immutability + reference swap

Build a new immutable snapshot and publish it with the language/runtime's atomic or synchronized
primitive. When that primitive establishes the required memory ordering, readers see a whole old or
new snapshot rather than a partially initialized value. An ordinary assignment is not a portable
safe-publication guarantee.

### Single-threaded by design

A single event loop can serialize access to state owned exclusively by that loop. It does not remove
shared state by construction: coroutines interleave at suspension points, callbacks can retain
mutable objects, native workers may run concurrently, and multiple processes still coordinate
external state. Node.js, Python's asyncio, and Redis use variants of this model.

Caveats:

- A blocking call freezes everything. Discipline: anything CPU-bound goes to a worker pool; anything blocking gets an async equivalent.
- A single instance is a single machine's worth of throughput. Distribute via sharding.

---

## Distributed Concurrency — Beyond One Machine

Once tasks run on different machines, the problems multiply.

### What changes

- Messages can be lost, delayed, duplicated, reordered.
- Machines crash mid-operation.
- Clocks disagree (don't trust wall-clock timestamps for ordering across machines).
- Networks partition (nodes can't reach each other but are still up).
- "Did it happen?" is rarely answerable definitively.

### CAP — pick two, but in practice it's nuanced

| Property                          | Meaning                                                                            |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| **Consistency** (linearisability) | Every read sees the most recent committed write                                    |
| **Availability**                  | Every request to a non-failing node eventually completes with a non-error response |
| **Partition tolerance**           | The system keeps working when the network partitions                               |

The honest reading: **during a partition, you choose between consistency and availability for the partitioned subset.** Simplified review frame: CP-oriented operations may reject, stall, or degrade requests they cannot validate; AP-oriented operations may answer from reachable replicas and expose stale or divergent data. Real systems vary by operation, quorum, conflict resolution, client session guarantees, and failure mode.

This is a per-operation, per-subsystem choice — not a system-wide flag. A bank might accept stale reads of marketing copy but require linearisable writes to balances.

### PACELC — the more useful frame

> During a partition (P), trade availability (A) for consistency (C). Else (E), trade latency (L) for consistency (C).

This recognises that even without a partition, strong consistency has a latency cost (waiting for replicas). Most systems make different trade-offs in the partition case vs the normal case.

### Consistency models — the spectrum

| Model                     | Meaning                                                                                                          |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Linearisable**          | There exists a single global order; every read sees the most recent write                                        |
| **Sequential**            | Operations fit one total order that preserves each process's program order; the order need not respect real time |
| **Causal**                | Causally related operations are ordered consistently                                                             |
| **Read-your-writes**      | A client sees its own writes; might not see others                                                               |
| **Eventually consistent** | Given no new writes, all replicas converge — eventually                                                          |

**Heuristic:** When reviewing an unspecified "distributed" database, assume the operation is not
linearisable until the documentation says which operations, isolation modes, quorum settings, and
deployment topology provide that guarantee. Scope: replicated, sharded, or multi-region data stores.
Exceptions include single-node deployments and explicitly documented strongly consistent operations.
Read the docs.

### Time and clocks

| Concept                                    | Use                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------- |
| **Wall clock** (`now()`)                   | Display, scheduling against external deadlines                                  |
| **Monotonic clock**                        | Measuring durations within one process                                          |
| **Logical clock** (Lamport, vector clocks) | Ordering events across machines without trusting wall clocks                    |
| **HLC** (Hybrid Logical Clocks)            | Modern: monotonic + wall, combined                                              |
| **NTP / PTP**                              | Keep wall clocks within milliseconds — but not for ordering critical operations |

**Don't use wall-clock comparisons across machines for ordering.** Even with NTP, clocks drift, leap seconds happen, and one machine's "now" is not another's.

### Delivery ambiguity and duplicate effects

API idempotency and wire-level semantics belong to [API design](api-design.md). The concurrency
consequence is narrower: any transport whose acknowledgment can be lost may redeliver work, and the
broker's documented delivery and ordering assumptions become part of the consumer review.

“Exactly once” is not one property. For distributed-safety review, distinguish message delivery,
handler execution, state transition, and externally observable effect. Some systems provide
exactly-once processing within a bounded transactional domain under stated assumptions; they cannot
extend that guarantee across an uncoordinated external side effect merely by naming it exactly-once.

### Consensus and coordination

When two nodes must agree on a fact (who's the leader, what's the value, did the transaction commit),
use a reviewed consensus implementation. **Project default:** application teams should not invent a
new consensus protocol unless the project scope is distributed-systems implementation or research.

- **Example:** **Raft-style coordination services** — often a practical default for leader-based
  coordination when an existing service fits the operational model.
- **Example:** **Paxos** / Multi-Paxos — a family of consensus protocols with many production and
  research variants.
- **Example:** **ZooKeeper-style coordination** — another existing coordination-service pattern.

**Project default:** Most application teams should use an existing coordination service or database
coordination primitive instead of running consensus logic inside application code. **Examples:**
etcd-style, Consul-style, ZooKeeper-style, or database-provided coordination, when their documented
failure model fits the operation.

### Distributed locks — the dragons

Distributed locks are tempting and dangerous:

- They depend on liveness of the lock service.
- They require fencing tokens — a monotonically increasing number the lock service returns, that the resource being protected checks. Without fencing, a paused-then-resumed lock holder can corrupt state after losing the lock.
- "Lock service is just Redis" works for advisory locks; for correctness-critical operations, use a
  system whose documented failure model fits the invariant, such as a coordination service or
  database primitive with fencing support.

**Better alternatives:** make the operation idempotent; serialise through a single owner; use optimistic concurrency with a version number.

### The two-generals problem

**Example:** In the classic two-generals scenario, two parties try to agree using messages that may be
lost. If acknowledgments can also be lost, another acknowledgment only moves the uncertainty. Practical
consequences:

- "Send a message; wait for ack" does not guarantee delivery. The ack itself can be lost.
- "Did the payment go through?" cannot always be answered from the caller's side. Ambiguous external
  side effects often need reconciliation, duplicate-effect control, and out-of-band confirmation.

---

## Backpressure — The Concurrency Hygiene You Forget

If a producer is faster than a consumer indefinitely, _something_ fails — memory, queue, latency, all of them. Backpressure is the mechanism that propagates "slow down" upstream.

| Strategy                      | Detail                                                                           |
| ----------------------------- | -------------------------------------------------------------------------------- |
| **Bounded queues**            | Block (or fail) the producer when the queue is full                              |
| **Reactive streams / `Flow`** | Built-in request/credit signalling between producer and consumer                 |
| **HTTP 429 / 503**            | Backpressure at the boundary                                                     |
| **Token buckets**             | Limit producer rate                                                              |
| **Drop / shed**               | When backpressure can't propagate (UDP, fire-and-forget logs), drop deliberately |

**Anti-pattern:** unbounded queues. They "smooth bursts" until they crash the process with OOM. A queue that never fills is a queue that's the wrong size.

---

## Async I/O Gotchas

| Gotcha                                                   | Detail                                                                                  |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Blocking call in an async function**                   | Freezes the event loop; everything stalls. Use the async variant or a worker thread     |
| **CPU-bound work in async code**                         | Same: starves I/O. Offload                                                              |
| **Forgetting to `await`**                                | The "function" returns a coroutine/future, not the value; silent bug                    |
| **Mixing sync and async in inconsistent layers**         | Convoluted bridging code; deadlocks via `loop.run_until_complete` inside a running loop |
| **Cancellation not awaited or not propagated**           | Background tasks continue after the requesting client has left                          |
| **Exception inside a fire-and-forget task**              | Disappears unless explicitly handled                                                    |
| **`async with`** not used where `with` would be wrong    | Synchronous context manager in async code                                               |
| **Shared state inside async code is still shared state** | The event loop interleaves tasks at every `await`                                       |

---

## Testing for Concurrency

Concurrency bugs are the hardest to test. Strategies:

| Strategy                                                                                           | Strength                              | Weakness                                    |
| -------------------------------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------- |
| **Property-based tests with concurrency** (e.g., `loom` in Rust, `Jepsen` for distributed systems) | Explores interleavings systematically | Setup cost; specific to the property tested |
| **Stress tests**                                                                                   | Catches bugs that need contention     | Non-deterministic; "flaky"                  |
| **Race detectors** (`go race`, `tsan`)                                                             | Catches data races at runtime         | Doesn't catch logical races                 |
| **Linters and type systems** (`Send`/`Sync` in Rust, `@GuardedBy` in Java)                         | Static guarantees                     | Limited to what the language models         |
| **Deterministic schedulers** (FoundationDB-style)                                                  | Reproducible runs                     | Requires architectural commitment           |
| **Fault injection** (kill nodes, drop packets, pause processes)                                    | Validates resilience                  | Hard to integrate into normal testing       |

**Project default:** Prefer a deterministic regression test or model that discriminates old and new
behavior. Some concurrency defects are probabilistic, hardware-specific, or too expensive to force;
then use repeated/stress evidence with seeds and rates, static/model checking where possible, and a
clear statement of what the evidence cannot establish.

---

## Diagnostic Framework

| Symptom                                     | Likely cause                                                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| "Sometimes the count is wrong"              | Read-modify-write without atomic / lock                                                                            |
| "It hangs forever"                          | Deadlock, missing timeout, dropped message                                                                         |
| "Tests pass, production hangs"              | Race or deadlock only visible under contention                                                                     |
| "Two of the same record exist"              | Check-then-act race; missing unique constraint                                                                     |
| "A user got someone else's data"            | State leaked across requests via a shared mutable variable (module-global, singleton, thread-local in wrong place) |
| "Background task didn't run"                | Fire-and-forget swallowed the error                                                                                |
| "Errors are silently lost in async code"    | Unhandled rejection / un-awaited future                                                                            |
| "Slow under load only"                      | Lock contention; resource pool saturation                                                                          |
| "Memory grows unbounded"                    | Unbounded queue; leak in a background task; cancellation not propagated                                            |
| "We can't reproduce it"                     | Real concurrency bug — pursue with race detector / property test                                                   |
| "It only happens on multi-core"             | True parallelism unveiled a hidden race                                                                            |
| "After deploy, duplicate webhooks fire"     | At-least-once delivery + non-idempotent consumer                                                                   |
| "Wrong order of events"                     | Ordering assumed but not enforced (no fencing token, no sequence number)                                           |
| Performance degrades as a thread pool grows | Lock contention dominates; serial bottleneck somewhere                                                             |

---

## Meta-Question

Concurrency is the answer to: _what assumptions about order, exclusivity, and visibility am I making, and which primitive enforces each?_ If you can name the primitive, you have a chance. If you can't, you have a race.

**House preference:** Minimize shared mutable state and make ownership/synchronization visible. Shared
state is sometimes the simplest correct design; its invariant and enforcement mechanism should be
reviewable.

## Primary Sources

**Standard/fact (verified 2026-07-30):**

- CAP terminology follows Gilbert and Lynch's
  [formalization of Brewer's conjecture](https://pld.cs.luc.edu/database/gilbert_lynch_brewer_proof.pdf).
- Sequential consistency follows Lamport's definition in
  [How to Make a Multiprocessor Computer That Correctly Executes Multiprocess Programs](https://lamport.org/pubs/lamport-how-to-make.pdf).

Re-verify terminology against the actual datastore or protocol contract before selecting a
consistency or delivery model; product labels such as “strong” or “exactly once” are not sufficient.

---

_See [DATA](data.md) for the database-level concurrency story (isolation levels, write skew, deadlocks)._
_See [ARCHITECTURE](architecture.md) for sync-vs-async communication choice._
_See [ERROR_HANDLING](error-handling.md) for timeouts, retries, and retry duplicate-effect control._
_See [API_DESIGN](api-design.md) for API idempotency and wire semantics._
_See [PERFORMANCE](performance.md) for the impact of contention and the role of bounded resources._
_See [OBSERVABILITY](observability.md) for tracing across async boundaries._
