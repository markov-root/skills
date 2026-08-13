---
knowledge:
  version: 1
  id: error-handling
  summary: Design failure contracts, propagation, recovery, retries, and diagnostics so callers can act without losing causal information.
  routes: [api-event-contract, defect-diagnosis]
---

# error-handling.md — Errors, Failures, and Recovery

> **Purpose:** Reference for how to think about and handle errors — language-mechanism level (exceptions, return values, panics), boundary level (timeouts, retries), and system level (fallbacks, circuit breakers, graceful degradation).
>
> **Read this when:** writing anything that can fail (so: anything); reviewing error-handling code; debugging silent failures; designing a retry strategy; deciding what to log vs surface vs swallow.
>
> **Do NOT** wrap everything in `try/except` just to "be safe." That is how bugs become permanent.

---

## The Premise

Errors are not handled by mechanism first. They are handled by boundary: what failed, which fault
domain contains it, what the caller was promised, and what evidence the next layer needs.

There are three common categories of error. Conflating them is a common source of bad
error-handling code.

| Category                               | Examples                                                                                     | Default response                                                                                                                           |
| -------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Programmer errors (bugs)**           | Off-by-one, null deref, wrong type, broken invariant                                         | Fail the smallest safe fault domain, preserve evidence, and let supervision/restart policy recover; do not silently continue invalid state |
| **Expected operational errors**        | Bad input, file not found, validation failure, conflicting state, rate-limited, unauthorised | **Handle deliberately and locally.** They are part of the domain.                                                                          |
| **Environmental / transient failures** | Network blip, brief DB outage, dependency cold start                                         | **Retry with backoff, then surface.** Detached from the domain.                                                                            |

Bugs masquerading as transient failures (caught and retried) are the worst class — they go on forever, in production, while the metric stays green.

## Fault Domain and Caller Contract First

Before choosing exceptions, result values, retries, supervision, or fallback, name the decision
fields:

| Field                     | Question                                                                                         | Consequence                                                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Fault domain**          | What is the smallest unit that can fail without corrupting unrelated work?                        | A request, job, actor, process, tenant, shard, or whole service can have different isolation and restart policy.                          |
| **Recoverability**        | Can this layer correct the condition, compensate for it, retry safely, or only report it?         | Catch locally only when this layer can make a better decision than its caller.                                                            |
| **Caller contract**       | What did the caller reasonably expect: success, validation failure, timeout, partial result?      | The error shape should let the caller decide without parsing logs or transport details.                                                   |
| **Cancellation**          | If the caller stops waiting, what work continues, stops, rolls back, or needs reconciliation?     | Cancellation is not proof of remote rollback; see [concurrency](concurrency.md) for distributed delivery and ordering assumptions.        |
| **Partial progress**      | What state may already have changed before the failure surfaced?                                  | A safe response may require transaction rollback, compensation, status query, deduplication, or an explicit "unknown" outcome.            |
| **Supervision**           | Who observes unhandled failures and restarts, quarantines, drains, or escalates the fault domain? | Fire-and-forget work needs an owner; otherwise errors become log lines with no recovery path.                                              |
| **Evidence preservation** | What causal details must survive translation across layers?                                       | Preserve cause chains, stable codes, correlation IDs, sanitized inputs, dependency response metadata, and partial-progress markers.        |

**Project default:** Derive the handling strategy from these fields at every boundary. Scope:
service, batch, CLI, and worker code where failures cross ownership boundaries. Trade-off: a small
script may not need a full taxonomy; a counterexample is a one-off data-cleanup script where a clear
fatal error with input line number is more useful than a reusable error hierarchy.

---

## Errors as Values vs Exceptions

The language picks the mechanism. The discipline is the same.

| Mechanism                 | Languages                                                          | Strength                                                      | Weakness                                |
| ------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------- | --------------------------------------- |
| **Exceptions**            | Python, Java, C#, JS, Ruby, C++                                    | Errors propagate without ceremony; the happy path stays clean | Easy to lose; silent control-flow jumps |
| **Result types**          | Rust (`Result`), Go (return-value-pair), Haskell (`Either`), OCaml | Errors are in the type; callers must address them             | Verbose; cluttered happy path           |
| **Panics / fatal errors** | Go (`panic`), Rust (`panic!`), Python (`SystemExit`)               | Bugs visible immediately                                      | Should not be used for expected errors  |
| **Error codes**           | C                                                                  | Universal                                                     | Easy to ignore; no payload by default   |

### Discipline regardless of mechanism

- **Errors should be part of the signature or documented boundary contract.** Scope: public
  functions, service boundaries, and reusable modules. Trade-off: tiny private helpers can inherit a
  caller's contract; a counterexample is a parser whose callers need stable failure variants.
- **Catch only what this layer can act on.** Recover, translate, compensate, add context, or attach
  the error to a supervisor. Otherwise propagate it.
- **Narrow the type of error.** Catch `IOError`, not `Exception`, when the recovery path only applies
  to I/O. Broad catches are sometimes justified at process/request boundaries to translate unknown
  failures into safe responses.
- **Narrow the scope of the catch.** Wrap the smallest expression whose failure has the same
  recovery path. A counterexample is a transaction block where several statements deliberately share
  one rollback contract.
- **Bare `except:` / `catch (Throwable)` is a boundary-only tool in rare runtimes.** It can catch
  interrupts, fatal errors, assertion failures, or memory exhaustion; ordinary recovery code should
  not make those look like domain failures.

---

## The Anti-Patterns, By Name

| Pattern                                                               | Why it fails                                                                                                                 |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **The empty catch** (`except: pass`, `catch (e) {}`)                  | The bug now exists forever and produces no signal                                                                            |
| **Log-and-swallow**                                                   | The error is visible only to log readers; callers proceed as if all is well                                                  |
| **Generic catch-all-at-top-level**                                    | All real errors look identical; specific recovery is impossible                                                              |
| **Returning `null`/`-1`/`""` for failure**                            | The caller forgets to check, exactly once                                                                                    |
| **Returning the error as the value** (HTTP 200 with `{"error": ...}`) | Layers above can't tell apart success from failure                                                                           |
| **Re-throwing as a different type with no context**                   | The stack trace is the only diagnostic, and now it points at the rethrow site                                                |
| **`try: ... except: raise`**                                          | Adds nothing; delete it                                                                                                      |
| **`try` blocks that span 200 lines**                                  | Multiple unrelated failures lumped together; "what failed where" is unknowable                                               |
| **Catching only to log "shouldn't happen"**                           | If it shouldn't happen, let it propagate; if it can happen, handle it specifically                                           |
| **Catch in the constructor, leave the object in an invalid state**    | Now a half-built object haunts the system                                                                                    |
| **Defensive programming everywhere**                                  | Trust boundaries, internal calls — protect the former, trust the latter; otherwise the code becomes a checking ritual        |
| **Stringly-typed error matching**                                     | `if "not found" in str(e)` — breaks the day the message rewords                                                              |
| **`if (success)` after every call**                                   | The reason exceptions exist. Use the language. (Unless your language is Go, in which case: yes, every call. It's the trade.) |

---

## Fail Fast

**Validate at boundaries; trust internally.** Once data is inside a trust zone, it has been validated and you don't re-validate it everywhere.

| Where                                                          | Validate                                                                                  |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Public API request                                             | Schema + business rules; reject early with a structured error                             |
| CLI input                                                      | Same                                                                                      |
| File / format parse                                            | Reject malformed input with location                                                      |
| Configuration load                                             | Reject at startup; **do not** start with bad config                                       |
| Subprocess / external call return                              | Treat as untrusted boundary input                                                         |
| Internal function calls between modules in the same trust zone | Express preconditions in types/contracts; use invariant checks appropriate to consequence |

Assertions can be useful checked documentation for developer assumptions. They are not the same as
input validation or a production integrity/security control:

- Input validation rejects user data gracefully with a structured error.
- A failed invariant should stop or isolate the affected operation/fault domain and preserve
  diagnostic evidence.

Some languages/runtimes can disable assertions (for example Python `-O`). Do not rely on such
assertions for security, authorization, data integrity, resource limits, or required runtime
validation. Use an unconditional check and explicit failure type for those contracts.

---

## Error Messages — Audience and Form

| Audience                 | Form                                                                                                             |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **End user**             | "We couldn't reach the payment provider. Please try again." Short, actionable, no stack, no IDs they don't need. |
| **Developer (logs)**     | Full stack, full context, correlation ID, what was being attempted, the input (sanitised)                        |
| **Operator (alerts)**    | Symptom + a runbook pointer ("See `runbook://payments/upstream-down`")                                           |
| **API client (machine)** | Stable error code + human-readable message + structured fields; see [API_DESIGN](api-design.md) error format     |

**The same exception goes to multiple audiences. Format at the edge, not at the throw site.**

---

## Context — The Stack Is Not Enough

A stack trace tells you _where_ the error happened. It does not tell you _what was being attempted_.

Patterns to add context as the error propagates:

- **Wrap, don't replace.** Add context; preserve the cause. Python: `raise X("context") from e`. Go: `fmt.Errorf("doing X: %w", err)`. Rust: `.context("doing X")` (anyhow). Java: chain the cause.
- **Add the relevant identifiers** at each layer (`user_id=...`, `order_id=...`).
- **Include the operation,** not just the data ("while applying refund to order 123").

The result, when read top-to-bottom: a narrative from "what we were trying to do" down to "the syscall that returned an errno". That narrative is what makes incidents short.

---

## Where to Catch — Boundaries and Fault Domains

For every `try`, ask:

1. **What specific failure are you protecting against?** If you cannot name the failure, the catch is
   probably hiding uncertainty rather than handling it.
2. **Which fault domain owns the consequence?** A failed request, failed batch item, failed worker,
   and corrupted process image should not receive the same treatment.
3. **What will this layer do that the caller or supervisor could not do better?** Valid answers
   include recover, compensate, translate, attach context, record partial progress, or initiate a
   supervised shutdown.
4. **What partial progress already happened?** If the answer is unknown, say so in the result or
   preserve enough evidence for reconciliation.
5. **What evidence would be lost by catching here?** Preserve the cause chain and correlation
   context before translation.

**Project default:** Catch close to the source when recovery is local; catch at an ownership boundary
when translating unknown failures into a safe response; avoid middle-layer catch blocks whose only
job is "just in case." Scope: application and service code. Trade-off: some frameworks require
adapter-level wrapping to normalize third-party exceptions; a counterexample is a persistence
adapter that converts vendor-specific unique-constraint errors into a domain conflict while
preserving the original cause.

## Cancellation, Partial Progress, and Supervision

Cancellation is a caller signal, not a complete failure policy.

| Concern              | Guidance                                                                                                                                      |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Caller cancellation** | Stop spending resources for a caller that no longer wants the result when the operation can be abandoned safely.                              |
| **Remote ambiguity** | If a downstream call was sent, cancellation or timeout may leave the outcome unknown; expose "unknown/pending" or reconcile instead of guessing. |
| **Partial writes**   | Prefer atomic transactions where the boundary supports them; otherwise record progress markers and compensating actions deliberately.           |
| **Cleanup**          | Use language-supported scoped cleanup for local resources and supervisor-managed cleanup for owned tasks/processes.                            |
| **Supervision**      | Owned background work has a place to report errors, cancellation, retries, shutdown, and resource cleanup.                                      |
| **Evidence**         | Record operation IDs, attempt numbers, dependency status, timeout/cancellation reason, and last known durable state.                           |

**Heuristic:** Treat "timed out" as "the caller stopped waiting" until the dependency contract proves
more. Scope: remote calls, queues, and distributed transactions. Trade-off: conservative ambiguity
adds status checks or reconciliation jobs; a counterexample is a local pure computation cancelled
before it mutates external state.

---

## Retries — Cheap to Add, Easy to Get Wrong

**Project default:** For remote calls, jobs, and dependency clients, retry only when all are true.
[API design](api-design.md) owns idempotency keys and duplicate-effect wire semantics; the
error-handling consequence is that retries without such a contract can multiply side effects and load.

- The operation is inherently idempotent or duplicate effects are controlled by an idempotency key,
  transaction, deduplication record, or status reconciliation.
- The failure is retryable under the dependency's contract and enough caller deadline/budget remains.
- Retry ownership is coordinated. Independent retries at several layers multiply load.

### The pattern

**Example:** These are starting points for ordinary user-facing remote calls with a finite caller
deadline, not inherited requirements. Batch repair jobs, long-lived streams, money movement, and
vendor-specific rate limits can need different budgets.

| Element                        | Starting point                                                                                                                                                   |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Number of attempts             | A small bounded number; keep the whole retry budget inside the caller deadline                                                                                    |
| Base delay                     | Long enough for the dependency to recover and short enough to preserve useful caller budget                                                                       |
| Backoff                        | Exponential or dependency-specified; for example 200ms → 400ms → 800ms → 1.6s when that fits the deadline                                                        |
| **Jitter**                     | Add randomness to avoid synchronised retry storms (a herd of clients retrying at exactly t+1s)                                                                   |
| Total cap                      | Bound the total time spent retrying — a deadline, not just an attempt count                                                                                      |
| Retry only on retryable errors | Follow the operation/dependency contract: some 5xx are permanent for the request; some 4xx (for example 408/409/425/429 in defined workflows) can be conditional |
| Duplicate-effect control       | See [API design](api-design.md); use when the operation is not inherently idempotent                                                                             |
| Retry evidence                 | Emit retry metrics/log fields when operators need to distinguish transient recovery from dependency degradation; a local CLI may only need a final error message  |

Honor a valid `Retry-After` within the caller's deadline, policy, and safety limits.

### Anti-patterns

- Retrying a status/exception without a documented or reasoned transient condition.
- Retrying a side effect without duplicate-effect control.
- Retries at multiple layers without coordination.
- Infinite retries with no cap. ("Eventually succeed" is not a real plan.)
- Same delay every time. Synchronised retries DDoS the recovering service.
- Retrying inside a transaction.

---

## Circuit Breaker

When a dependency is down, hammering it doesn't help. The circuit breaker:

| State         | Behaviour                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------- |
| **Closed**    | All calls pass through; failures are counted                                                            |
| **Open**      | Calls fail immediately without trying — for a cooldown window                                           |
| **Half-open** | After cooldown, a small number of probe calls are allowed; success closes the circuit, failure re-opens |

**Use a circuit breaker when:**

- A downstream's failures are slow (timeout-bound) — open circuit prevents resource exhaustion.
- Repeated calls during an outage cause cascading harm (DB connection pool, threads).
- You have a fallback (cached result, degraded response).

No fallback is required for a circuit breaker to be useful: fast failure can protect pools, reduce
cascades, and give a dependency time to recover. Do not add one where ordinary deadlines,
concurrency limits, and load shedding already give clearer behavior, or where stateful half-open
probing creates more risk than it removes.

---

## Timeouts — The Unsung Hero

**Project default:** Give every remote or potentially blocking operation a finite deadline unless an
explicit long-lived streaming/wait contract supplies cancellation, heartbeats, and resource bounds.

| Reason                                                                           | Detail                                                                                                     |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Without a timeout, a hung dependency becomes a hung pool of yours                | Threads, connections, file descriptors — all finite                                                        |
| Each attempt fits the **remaining caller deadline** plus cleanup/response budget | A simplistic “shorter than upstream” rule ignores fan-out, retries, queues, and legitimate background work |
| Timeouts are **bounded by an end-to-end deadline**, not only per-call values     | Budget queueing, attempts, backoff, work, rollback, and response within it                                 |
| **Connect timeout** and **read timeout** are different                           | Some libraries default one to zero (infinite); check                                                       |
| **Whole-request deadline** propagated to every downstream                        | "Deadline propagation" — some frameworks and instrumentation libraries support carrying deadline context    |

**Diagnostic:** If you've ever seen a request that hung "forever", a timeout was missing somewhere.

---

## Fallback and Graceful Degradation

When the primary path fails, what's the secondary? Categories:

| Pattern              | Example                                                                             |
| -------------------- | ----------------------------------------------------------------------------------- |
| **Stale cache**      | "Couldn't reach the rate API; using the rate from 4 hours ago"                      |
| **Default value**    | "Couldn't reach the personalisation service; showing default recommendations"       |
| **Read-only mode**   | "Couldn't reach the write database; the site still serves reads"                    |
| **Queue for later**  | "Couldn't send the email now; queued for retry"                                     |
| **Partial response** | "Couldn't reach the comments service; showing the post without comments"            |
| **Polite failure**   | "We can't do this right now. Please try again." (with a correlation ID for support) |

**Discipline:**

- Fallbacks should be explicit. "Silently use stale data" is a bug if the user expects fresh.
- Fallbacks should be observable. Metric per fallback path; if it triggers often, the dependency is degraded.
- Fallbacks should not mask the primary failure. The primary alert still fires.

---

## Bulkheads

A failure in one part shouldn't drain resources from another.

| Pattern                                                 | Detail                                                        |
| ------------------------------------------------------- | ------------------------------------------------------------- |
| **Separate thread / connection pools** per dependency   | One bad dependency can't exhaust the pool the others use      |
| **Separate queues** per priority class                  | Low-priority work can fail without affecting high-priority    |
| **Separate replicas / processes** per high-risk feature | A new feature with unknown failure modes runs on its own pool |

The image: a ship with watertight compartments. One floods; the ship doesn't sink.

---

## Duplicate-Effect Control for Retry Safety

API idempotency and wire-level form belong to [API design](api-design.md). Database mechanics belong
to [data](data.md), and delivery/ordering assumptions belong to [concurrency](concurrency.md).

The error-handling consequence is retry safety: before retrying a side effect, the caller should know
whether duplicate effects are impossible, tolerated, deduplicated, compensated, or reconciled. Scope:
remote calls, message handlers, jobs, and dependency clients. Trade-off: durable deduplication and
reconciliation add storage and workflow complexity; a counterexample is a local pure read operation
where repeating the call has no externally visible effect.

---

## Error Handling at System Boundaries

### Inbound (you are the server)

| Layer              | Default                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------- |
| **Edge / gateway** | Translate every uncaught exception to a structured error; do not expose raw stack traces to untrusted clients. Internal/dev-only surfaces may show them behind access controls |
| **Validation**     | Reject early with field-level errors (see [API_DESIGN](api-design.md))                      |
| **Business logic** | Throw domain-specific errors with stable codes                                              |
| **Persistence**    | Catch DB-driver exceptions, translate to domain errors                                      |
| **Logging**        | Errors include correlation ID, user/tenant context (sanitised), what was attempted          |
| **Alerting**       | Rate-based: alert when error rate exceeds threshold over window — not on single occurrences |

### Outbound (you are the client)

| Layer                                       | Default                                                                       |
| ------------------------------------------- | ----------------------------------------------------------------------------- |
| **Deadline/cancellation**                   | Finite and propagated for blocking/remote work; explicit streaming exceptions |
| **Retry**                                   | Contract-defined transient failures; duplicate-safe; backoff/jitter; capped   |
| **Circuit breaker**                         | Where fast-fail materially protects resources or recovery                     |
| **Fallback**                                | Explicit, observable, alerting                                                |
| **Translate failures into domain language** | "RateAPIUnavailable", not "ConnectionResetError"                              |

---

## Language-Specific Notes

### Python

- `except Exception` is broad enough; `except:` (bare) catches `KeyboardInterrupt` — don't.
- Use `raise X from e` to chain causes. Read tracebacks; they are excellent.
- `contextlib.suppress(SpecificError)` is cleaner than `try: ... except SpecificError: pass`.
- `logging.exception()` inside an `except` block includes the stack trace; `logging.error()` doesn't.
- Custom exceptions subclass the right base (`ValueError` for bad input, `LookupError` for missing keys) so callers can catch broadly when appropriate.

### Go

- Don't ignore returned errors. `golangci-lint` with `errcheck` enforces this.
- Wrap with `fmt.Errorf("...: %w", err)` so callers can `errors.Is` / `errors.As`.
- `panic` is for "this code path should be unreachable" — and recovered only at goroutine boundaries.
- `defer` for cleanup; don't put cleanup in the happy path only.

### JavaScript / TypeScript

- `try { await x } catch (e)` — `e` is typed `unknown` in TS; narrow before using.
- **Project default:** At the process boundary, handle promise rejections explicitly; unhandled rejection is a process-level event in Node (`unhandledRejection`).
- `async` functions throw via promise rejection; calling without `await` and without `.catch()` is a silent error.
- Beware `Promise.all` rejecting on first failure; use `Promise.allSettled` when you want all results.

### Rust

- The type system carries error handling; `Result<T, E>` is the idiom.
- `?` propagates; `unwrap()`/`expect()` panic — use only when "impossible state, panic is correct".
- `thiserror` for libraries (typed errors); `anyhow` for applications (`anyhow::Result<T>`).

### Java / Kotlin

- Checked exceptions are controversial; pragmatic answer: convert checked to unchecked at the boundary, retain semantic information.
- Don't catch `Throwable` or `Exception` broadly.
- `try-with-resources` for closing; same in Kotlin (`use { }`).

---

## Resource Cleanup — On Every Path

For resources owned by the current fault domain, cleanup should be tied to scope so success,
failure, cancellation, and early return take the same release path. Counterexample: a durable job
record intentionally outlives the process and is cleaned by a supervisor or reconciler rather than a
local `finally` block.

Mechanism by language:

| Language    | Mechanism                          |
| ----------- | ---------------------------------- |
| Python      | `with` (context managers)          |
| Java/Kotlin | `try-with-resources`, Kotlin `use` |
| C#          | `using`                            |
| Go          | `defer`                            |
| Rust        | RAII via `Drop`                    |
| JS          | `finally`                          |
| C++         | RAII via destructors               |

**Anti-pattern:** Resource acquired in `try`, released after the `try` block. If the body throws
after acquisition but before the release, the resource leaks. Prefer the language's scoped mechanism
when the resource lifetime is local to the operation.

---

## Diagnostic Framework

| Symptom                                                      | Likely cause                                                                                          |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Bug occurred and produced no signal                          | Caught and swallowed somewhere                                                                        |
| Stack trace points at a wrapper, not the cause               | Lost the cause when rewrapping                                                                        |
| Single failure cascades to everything                        | Missing timeout / circuit breaker / bulkhead                                                          |
| Same operation succeeds sometimes, fails others              | Real transient — or — race condition (see [CONCURRENCY](concurrency.md))                              |
| Retry storm took out the dependency that was just recovering | No jitter; synchronised retries                                                                       |
| User sees a 500; logs show the actual error                  | Server leaked an internal error — translate at the boundary                                           |
| "Works on dev, fails in prod"                                | Different timeout / different network / different secrets — fail-fast at startup would have caught it |
| Errors are vague: "something went wrong"                     | No error code discipline; clients can't switch on outcome                                             |
| A logged-error rate that climbs slowly                       | A new bug that doesn't fire alerts; rates need thresholds                                             |
| An exception type is `Exception` everywhere                  | No domain error taxonomy; the type system isn't carrying weight                                       |

---

## Meta-Question

Error handling is the answer to: _when this fails, who learns, who recovers, and what does the next person debugging this need to see?_ If "no one learns" or "no one can recover from this exception", you have not handled the error — you have hidden it.

The shortest path to robustness is honesty: do not continue from corrupted state. Fail or isolate
the smallest safe fault domain, let a tested supervisor/restart policy handle process recovery, and
surface enough context for the next layer to decide. In embedded, safety-critical, batch, or
multi-tenant systems, “crash” without fault-domain analysis can be the larger failure.

---

_See [API_DESIGN](api-design.md) for error envelopes at the wire._
_See [OBSERVABILITY](observability.md) for the metrics and alerts behind "error rate"._
_See [ARCHITECTURE](architecture.md) for where failure boundaries sit in the system shape._
_See [CONCURRENCY](concurrency.md) for the race-condition flavour of "intermittent failure"._
_See [DATA](data.md) for transaction rollback and isolation._
