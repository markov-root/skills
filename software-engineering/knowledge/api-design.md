---
knowledge:
  version: 1
  id: api-design
  summary: Design evolvable APIs and event contracts with explicit semantics, compatibility, idempotency, errors, and operational limits.
  routes: [api-event-contract]
  sources: [src-api-standards, src-api-contract-standards]
---

# api-design.md — Interface Design Reference

> **Purpose:** Reference for designing APIs that survive change — between services, between client and server, between you-today and you-in-three-years. Covers REST/GraphQL/gRPC choice, versioning, idempotency, pagination, errors, schemas, deprecation, and the things that hurt to change once shipped.
>
> **Read this when:** designing any interface that crosses a process boundary, a deployment boundary, a team boundary, or a release boundary; adding an endpoint; reviewing a breaking-change conversation.
>
> **Invariant (contract integrity):** Apply a protocol rule only inside the protocol and version
> that defines it. HTTP, library calls, local IPC, events, webhooks, batch files, and asynchronous
> jobs do not inherit one another's defaults.

---

## The Premise

> An API is a contract at the boundary where a consumer relies on observable behavior. Its lifetime,
> compatibility cost, and required ceremony depend on who controls producer and consumer, whether
> messages persist, and how independently each side deploys.

"Public" is not synonymous with "internet." An interface becomes expensive to change when an
independent consumer, stored message, released library/application, plugin host, or operational
workflow depends on it. A private helper compiled and released with its only caller is still an
interface, but usually has a cheaper atomic migration path.

### Claim classification

| Claim type          | Rule, scope, trade-off, and counterexample                                                                                                                                                                                                                                                                                                                                       |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Invariant**       | Preserve security, privacy, and data-integrity boundaries; make observable success, failure, side effects, and compatibility claims unambiguous enough for the actual consumer to act safely. Extra specification has a maintenance cost, so a private pure function need not adopt an HTTP error envelope.                                                                      |
| **Project default** | For independently deployed, released, or persisted contracts, keep an authoritative versioned definition, validate inputs at the trust boundary, and provide migration/evolution evidence proportional to consumer impact. A monorepo library with all callers changed atomically may rely on compiler and integration evidence instead of a multi-version compatibility window. |
| **Heuristic**       | Version prefixes, pagination, cursor style, timeouts, idempotency keys, rate limits, and schema-first workflows are candidate mechanisms. Select them from cardinality, latency, retry, transport, and consumer constraints; a bounded lookup, local function, or single-shot batch compiler may need none of them.                                                              |

Unless a passage is labeled otherwise, recommendations below are **project defaults** within the
named interface form; examples, anti-patterns, symptom tables, and mechanism comparisons are
**heuristics**. Protocol tables marked by an RFC are **standard/fact** claims only for that RFC's
scope and version.

---

## The Load-Bearing Rules

These are cross-boundary questions, not universal HTTP prescriptions:

| Question                    | Project default and exception                                                                                                                                                                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What is authoritative?**  | Name the declaration, schema, source signature, protocol/version, or language-native interface that owns the contract. A generated wire schema may be authoritative for a service; compiler-visible types and docstrings may own a library.                                                            |
| **What is compatible?**     | Define compatibility from real consumer behavior and the protocol's evolution rules. Adding an optional field is not automatically safe for closed unions, strict decoders, signatures, exhaustive matches, or read-modify-write clients. Changing meaning can break consumers without changing shape. |
| **What may repeat?**        | State retry and duplicate-effect semantics. Use natural idempotency, operation identity, deduplication, reconciliation, or an explicit non-retryable limitation as appropriate; a local in-memory mutation need not accept an HTTP idempotency key.                                                    |
| **What is bounded?**        | Bound work, payload, buffering, fan-out, or result size where resource exhaustion or starvation is plausible. A fixed three-item enum does not need pagination.                                                                                                                                        |
| **How does work stop?**     | For blocking, remote, streaming, or expensive work, define deadline/cancellation propagation and what remains committed. A cheap, bounded pure library call usually needs neither.                                                                                                                     |
| **How do failures travel?** | Give callers a stable discriminant and actionable context appropriate to the interface. HTTP commonly needs machine-readable errors; a CLI may use exit codes plus stderr; a typed library may use result/error types.                                                                                 |
| **Who authorizes?**         | Authenticate where identity is required and authorize every protected action at the component that owns the resource decision. A deliberately public health endpoint is a counterexample to universal authentication, not to deliberate access policy.                                                 |
| **How does it evolve?**     | Record consumers, compatibility matrix, deprecation/migration path, and evidence limits when old and new versions can coexist. Atomically released private callers can often migrate together.                                                                                                         |

## Interface Forms and Their Different Contracts

| Form                        | Load-bearing concerns                                                                                                                    | Common counterexample to HTTP-shaped advice                                                                           |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **HTTP request/response**   | Method/status/cache semantics, media negotiation, authentication/authorization, intermediaries, deadlines, bounded bodies/collections    | A fixed-size health response does not need pagination or a version prefix.                                            |
| **Library API**             | Type/ownership/lifetime, exceptions or result types, thread safety/reentrancy, semantic versioning and supported platform/runtime matrix | Reading process environment inside a reusable library hides inputs; a typed error need not be serialized as RFC 9457. |
| **Event/message**           | Schema evolution, delivery/ordering, duplicate effects, partition key, retention/replay, producer/consumer matrix                        | There may be no synchronous response or caller deadline to return.                                                    |
| **Local IPC**               | Peer identity/permissions, framing, version/capability handshake, cancellation, resource quotas, upgrade ordering                        | Locality does not remove trust concerns, but a stable OS-owned protocol may own version negotiation.                  |
| **Webhook**                 | Authenticity/integrity, replay defense, sender retry policy, acknowledgment deadline, receiver deduplication                             | The receiver cannot choose the sender's transport semantics; it must implement the documented provider contract.      |
| **Batch/file interchange**  | Atomicity, schema/version marker, validation report, partial-record policy, checkpoint/resume, provenance                                | A bounded one-shot compiler input may fail the whole file instead of returning a paginated partial response.          |
| **Asynchronous job/stream** | Accepted-versus-completed state, status/result retrieval, cancellation, progress, backpressure, partial results, retention               | `202 Accepted` is HTTP-specific; a queue or local task handle represents the same lifecycle differently.              |

---

## Choosing a Style

| Style                                          | Best at                                                                     | Worst at                                                                            |
| ---------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **REST (resource-oriented HTTP)**              | CRUD over resources; cacheability; broad tooling; public consumption        | Operations that aren't naturally resource-shaped; bulk; arbitrary queries           |
| **JSON-RPC / "HTTP RPC" / "REST-ish actions"** | Action-oriented operations; pragmatic                                       | Cacheability; resource conventions                                                  |
| **GraphQL**                                    | Client-driven queries; many client variants over the same data; aggregation | Caching; rate-limiting (cost analysis required); simple use cases — adds complexity |
| **gRPC / protobuf**                            | Internal service-to-service; strongly typed; streaming; performance         | Browser clients (needs gRPC-Web/Connect); human exploration                         |
| **WebSocket / SSE**                            | Server push, real-time                                                      | Stateless caches, simple request/response                                           |
| **Webhook**                                    | Push to third parties; events you originate                                 | Reliable delivery (consumers do strange things)                                     |
| **Message queue / event bus**                  | Decoupled consumers, ordering, durability                                   | Synchronous queries                                                                 |

**Heuristic for an ordinary external HTTP resource API:** REST-like JSON over HTTPS with an OpenAPI
description often has broad tooling and low consumer friction. GraphQL, RPC, streaming, or batch may
fit better when the query, type, latency, or delivery model demands it. The transport choice does
not decide the domain contract by itself.

## Cross-Paradigm Contract Dimensions

### Deadlines and cancellation

**Project default:** Remote, blocking, streaming, or expensive operations expose a bounded waiting
contract and propagate cancellation where the stack supports it. Document whether cancellation is
best-effort, whether committed effects remain, and how callers discover the final outcome. The
trade-off is implementation and cleanup complexity; a tiny in-process pure function or an
intentionally detached durable job is a counterexample.

Do not equate a client timeout with server cancellation. A client can stop waiting while the server
commits work. When that ambiguity matters, return an operation identity and support status lookup or
reconciliation.

### Partial results and completion

For batches, search, fan-out, and streams, define:

- whether success is all-or-nothing, best-effort, or threshold-based;
- item-level status/error representation and ordering;
- continuation/checkpoint semantics and whether retry repeats successful work;
- whether an incomplete result can be cached, persisted, or used for decisions; and
- how truncation, timeout, cancellation, and unavailable dependencies differ.

**Invariant (truthful completion):** Never label incomplete or truncated coverage as complete. A
transactional funds transfer may correctly reject partial success; a multi-source search may return
useful partial results when omissions are explicit.

### Capability negotiation

**Project default:** When peers can run different versions or optional features materially change
semantics, negotiate or declare capabilities instead of guessing from version strings. HTTP media
types/headers, an IPC handshake, a library feature probe, or an event schema registry may carry the
evidence. The cost is extra states to test; a tightly coupled atomic deployment can use one fixed
capability set.

Treat absence, unsupported, disabled-by-policy, and temporarily unavailable as distinct when the
caller chooses a different action for each.

### Backpressure and flow control

**Invariant (resource integrity):** A producer/consumer boundary that can outpace finite memory,
connections, threads, or downstream capacity needs an explicit bound or flow-control strategy.
Options include demand/credit, bounded queues, admission control, chunking, sampling, or deliberate
rejection. The trade-off is latency, throughput, or data loss; an offline bounded collection known
to fit memory is a real counterexample.

### Compatibility matrix and evidence

For independently changing producer/consumer versions, record the supported matrix (or range),
upgrade order, downgrade/rollback limits, and deprecation dates. Support claims should identify the
evidence population: schema-diff rules, compiler/type checks, consumer/provider contract tests,
recorded-message replay, canary traffic, or tested version pairs. Each proves only its represented
shape or scenario; no single green schema diff proves semantic compatibility.

---

## REST — The Operational Form

"REST" is a spectrum. The pragmatic, useful version (sometimes "REST level 2", sometimes "HTTP API"):

| Concept                           | HTTP form                                                                                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Resource                          | `/orders/{id}`, `/customers/{id}/addresses`                                                                                                 |
| Collection                        | `/orders`                                                                                                                                   |
| List                              | `GET /orders` (with pagination, filtering, sorting query parameters)                                                                        |
| Read                              | `GET /orders/{id}`                                                                                                                          |
| Create                            | `POST /orders` (server assigns ID) **or** `PUT /orders/{id}` (client assigns ID, idempotent)                                                |
| Replace                           | `PUT /orders/{id}`                                                                                                                          |
| Partial update                    | `PATCH /orders/{id}`; **Standard/fact (HTTP patch formats):** JSON Merge Patch (RFC 7396) and JSON Patch (RFC 6902) define distinct formats |
| Delete                            | `DELETE /orders/{id}`                                                                                                                       |
| Action (not naturally a resource) | `POST /orders/{id}/cancel`, `POST /orders/{id}:refund` — pragmatic; "purists" disagree, ignore them                                         |

### HTTP method semantics — the rules

| Method    | Safe? | Idempotent?                                                                        | Body?          |
| --------- | ----- | ---------------------------------------------------------------------------------- | -------------- |
| `GET`     | Yes   | Yes                                                                                | No             |
| `HEAD`    | Yes   | Yes                                                                                | No             |
| `OPTIONS` | Yes   | Yes                                                                                | (rarely)       |
| `PUT`     | No    | **Yes**                                                                            | Yes            |
| `DELETE`  | No    | **Yes** (deleting twice returns 404 the second time, but the _effect_ is the same) | (occasionally) |
| `POST`    | No    | **No** by default                                                                  | Yes            |
| `PATCH`   | No    | **No** by default (it can be; the spec doesn't promise)                            | Yes            |

**"Safe" = no observable server state change.** GET that "logs a view" violates this in spirit but is generally tolerated. GET that triggers anything else is wrong; use POST.

**“Idempotent”** means multiple identical requests have the same intended server effect as one.
That does not automatically make every implementation, response, audit event, or downstream side
effect retry-safe; design and test the complete effect chain.

### Status codes — the short list

| Code                | Meaning                | Use                                                                                                  |
| ------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------- |
| **200**             | OK                     | Successful read or update with a body                                                                |
| **201**             | Created                | Successful create — include `Location` header                                                        |
| **202**             | Accepted               | Async processing started; not done yet                                                               |
| **204**             | No Content             | Successful, nothing to return (delete, update with no body)                                          |
| **301**             | Moved Permanently      | Permanent-redirection semantics; cacheable by default unless applicable cache controls say otherwise |
| **302/303/307/308** | Other redirects        | Choose deliberately — 307/308 preserve method, 301/302 traditionally don't                           |
| **400**             | Bad Request            | Client sent malformed or invalid input                                                               |
| **401**             | Unauthorized           | **Authentication** is missing or wrong                                                               |
| **403**             | Forbidden              | **Authorisation** failed — authenticated but not allowed                                             |
| **404**             | Not Found              | Resource doesn't exist (or you don't get to know)                                                    |
| **405**             | Method Not Allowed     | Wrong verb on a valid resource                                                                       |
| **409**             | Conflict               | State conflict (duplicate, version mismatch, concurrent edit)                                        |
| **410**             | Gone                   | Used to exist, won't again — useful for tombstones                                                   |
| **412**             | Precondition Failed    | `If-Match` / `If-None-Match` failed (optimistic concurrency)                                         |
| **415**             | Unsupported Media Type | `Content-Type` we don't accept                                                                       |
| **422**             | Unprocessable Entity   | Syntactically valid, semantically wrong (often used for validation errors)                           |
| **429**             | Too Many Requests      | Rate-limited; `Retry-After` can communicate the selected retry contract                              |
| **500**             | Internal Server Error  | Server bug; client cannot do anything                                                                |
| **502**             | Bad Gateway            | Upstream returned garbage                                                                            |
| **503**             | Service Unavailable    | Temporarily overloaded or down; `Retry-After` is available when applicable                           |
| **504**             | Gateway Timeout        | Upstream timed out                                                                                   |

**Anti-pattern:** Returning `200` with `{"success": false}`. The HTTP layer is _part_ of the API. Clients (and load balancers, and proxies) read status codes.

**Anti-pattern:** Returning `404` for both "doesn't exist" and "you don't have access". Sometimes that's the right call (don't leak existence), but make it deliberate.

---

## Idempotency — A Mutation Discipline

Networks retry. Without idempotency:

- The user clicks "Pay" once. The browser retries. They're charged twice.
- A queue redelivers the message. The order is created twice.
- A webhook is retried by the sender. The integration creates duplicate records.

**The pattern:** the client generates a unique key per intended operation (`Idempotency-Key: 5f1a4...`). The server stores the result of the first request keyed by `(client, key)` and returns it on retry.

| Requirement                                                           | Detail                                                                                             |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Key generated by the client                                           | Per intended operation, not per HTTP attempt                                                       |
| Key uniqueness scoped to the client and a documented retention window | Avoid collisions; size retention from retry horizon, consequence, storage, and privacy obligations |
| First request executes; result stored with the key                    | Atomically with the operation                                                                      |
| Subsequent request with the same key and intent                       | Return/reconcile the original result according to the documented response-retention contract       |
| Same key with different intent                                        | Reject as a conflict using the API's stable error contract                                         |

HTTP defines idempotent semantics for `PUT` and `DELETE`, but the implementation must preserve them
across downstream effects. An idempotency key can still be useful for operation identity, concurrent
creation, or response replay. `POST` and non-idempotent `PATCH` operations need an explicit retry
contract when duplication matters; not every POST universally needs a key.

---

## Errors — Actionable at the Consumer Boundary

**Project default for independently consumed wire protocols:** provide a stable machine-readable
error discriminant plus safe human context. A typed library may use its language's result/error
model; a CLI may use documented exit codes and stderr; a batch format may emit per-record findings.
The common invariant is that callers can distinguish the states for which they take different
actions without parsing incidental prose.

Bad:

```json
{ "error": "Something went wrong" }
```

**Standard/fact (HTTP error format):** RFC 9457 defines Problem Details for HTTP APIs. An API may
adopt that format and define documented extensions, for example:

```json
{
  "type": "https://example.com/probs/insufficient-funds",
  "title": "Insufficient funds",
  "status": 422,
  "detail": "Account 12345 has balance 5.00; required 10.00.",
  "instance": "/transfers/abc-123",
  "code": "INSUFFICIENT_FUNDS",
  "errors": [
    {
      "field": "amount",
      "code": "TOO_LARGE",
      "message": "Amount exceeds balance"
    }
  ]
}
```

| Field      | Purpose                                                                              |
| ---------- | ------------------------------------------------------------------------------------ |
| `type`     | A URL the developer can read to understand this error class. Stable across versions. |
| `title`    | Human-readable summary.                                                              |
| `status`   | Mirror of the HTTP status — convenience for client logging.                          |
| `detail`   | Specific to this occurrence. Safe to show to a developer.                            |
| `instance` | A URL or correlation id pointing at this specific occurrence.                        |
| `code`     | Stable machine string. Clients switch on this.                                       |
| `errors[]` | Field-level validation errors.                                                       |

**HTTP project default:**

- **Error `code` strings are part of the contract.** Renaming is breaking.
- **Invariant (confidentiality):** Do not expose stack traces, queries, secrets, or sensitive
  internal identifiers across an untrusted boundary. A local developer-only diagnostic channel can
  deliberately carry richer details.
- Include a correlation/operation ID when an operator or caller needs to reconcile the failure; a
  pure validation library need not invent distributed tracing.
- Keep a consistent envelope within a negotiated media type/version; different transports can have
  different native error forms.

---

## Versioning — Choose an Evolution Boundary Deliberately

**Project default:** Before independent consumers exist, decide how compatible additive change,
deprecation, and incompatible replacement will be represented. An explicit `v1` prefix is only one
mechanism; a library package version, event type, media type, capability handshake, or atomic
producer/consumer release may own the boundary instead.

| Strategy                     | Form                                   | Trade-off                                                                                                 |
| ---------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **URL**                      | `/v1/orders`                           | Visible and straightforward; duplicates routes across active versions                                     |
| **Media type**               | `Accept: application/vnd.acme.v1+json` | Uses HTTP negotiation; requires tooling and cache behavior to handle it                                   |
| **Header**                   | `X-API-Version: 2024-08-15`            | Stripe-style date versioning — fine grained, requires good tooling                                        |
| **Query parameter**          | `?v=2`                                 | Discouraged — caches and shareable URLs get confused                                                      |
| **No explicit wire version** | `/orders`                              | Can work with compatibility/deprecation negotiated another way; risky when consumers evolve independently |

### When to bump the version

**Heuristic:** Do not create a parallel version until an incompatible contract requires it;
maintaining every active version costs implementation, documentation, support, and test capacity.
This does not mean postponing the evolution policy itself.

| Change                                     | Breaking?                                                                                | Need a new version?                                                         |
| ------------------------------------------ | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Add a new optional request field           | Usually additive only when old producers may omit it and validators/defaults permit that | Usually no; verify protocol/schema rules and consumers                      |
| Add a new response field                   | Depends on unknown-field, signing, exhaustive-match, and read-modify-write behavior      | Usually no for an established extension point; verify consumers             |
| Remove a request field                     | Yes                                                                                      | Yes, or deprecate                                                           |
| Remove a response field                    | Yes                                                                                      | Yes, or deprecate                                                           |
| Rename a field                             | Yes                                                                                      | Yes — emit both for a deprecation window                                    |
| Change a field's type (string → int)       | Yes                                                                                      | Yes                                                                         |
| Change the meaning of a field's value      | Yes — _especially_ — silent corruption                                                   | Yes                                                                         |
| Tighten validation                         | **Possibly** — clients that used to succeed now fail                                     | Treat as breaking                                                           |
| Loosen validation                          | Possibly — may broaden accepted meaning or weaken a security/integrity constraint        | Review semantics; a new version may be unnecessary but evidence is required |
| Change error codes for existing conditions | Yes                                                                                      | Yes                                                                         |

### Deprecation — the protocol

1. Announce the deprecation through the channels the consumers use, with the applicable date.
   **Standard/fact (HTTP only):** For HTTP APIs that use these fields, RFC 9745 defines the
   `Deprecation` header field and RFC 8594 defines the `Sunset` header field.
2. Continue supporting the old behavior for a window derived from consumer inventory, upgrade
   capability, contractual notice, risk, and observed migration; no universal release count fits.
3. Log usage server-side. Reach out to users still on the old behaviour.
4. Retire on the announced date using the interface's documented terminal behavior. For an HTTP
   resource that is intentionally gone, `410 Gone` with migration details is one available response.

**Anti-pattern:** Sunset by stealth. Removing without warning. Users discover it through outages.

---

## The Tolerant Reader

**Project default:** Clients may ignore unknown additive fields when the protocol defines them as
extensions. Security-sensitive envelopes, signatures/canonicalization, commands, and closed unions
may require strict rejection.

- If your client deserialises into a strict struct that errors on unknown fields, you have made adding fields a breaking change for yourself.
- Choose strictness per field and version. Preserve unknown data when a read-modify-write client
  could otherwise delete it; validate semantically required and security-sensitive input.

---

## Pagination

| Strategy                                           | When to use                                            | Risks                                                                                   |
| -------------------------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| **Offset / limit** (`?offset=200&limit=50`)        | Small, stable datasets                                 | Skipped or duplicated items when data changes between pages; O(n) cost on large offsets |
| **Page / page_size** (`?page=5&page_size=50`)      | Same as offset; nicer for UIs that show "page 5 of 47" | Same risks                                                                              |
| **Cursor / opaque token** (`?cursor=abc&limit=50`) | Large or shifting datasets                             | Cursor is opaque to the client by contract — don't decode it                            |
| **Time-based** (`?since=2025-01-01T00:00:00Z`)     | Event streams, append-only logs                        | "Same timestamp" tiebreakers needed                                                     |
| **Keyset / seek** (`WHERE id > last_id`)           | Large datasets where you control both ends             | Requires a unique, sorted key                                                           |

**Heuristic:** Cursor/keyset pagination is often a good fit for large or changing collections;
offset/page forms can be simpler and more useful for small stable datasets or page-oriented UIs. A
bounded collection may be returned whole. When a cursor contract is selected, commonly return:

- The items.
- The cursor for the next page (`next_cursor`, or `null` if done).
- Optionally, a previous cursor for back-paging.
- **Don't** return a total count unless you actually need to compute it — it's often expensive and rarely useful.

**Project default:** Bound client-selected work from the service's measured capacity and payload
budget. The limit is project evidence, not a universal number; an already fixed-size result does not
need another cap.

---

## Filtering, Sorting, Field Selection

| Concern                 | Pattern                                                                                       |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| Filter                  | `?status=active&created_after=2024-01-01` — explicit per field                                |
| Generic filter language | Hard to get right; consider `RSQL`, `SCIM filter`, or GraphQL if you really need this         |
| Sort                    | `?sort=-created_at,name` (`-` for descending)                                                 |
| Sparse fieldsets        | `?fields=id,name,email` — server returns only those fields                                    |
| Expansion               | `?expand=customer,items` — server inlines related resources (carefully — N+1, response bloat) |

**Project default:** Validate client-controlled filter and sort expressions against the documented
grammar and authorization policy. Reject or explicitly ignore unknowns according to the versioned
extension contract; silent accidental behavior becomes a consumer dependency.

---

## Bulk and Async

| Pattern                                      | Use                                                                                     |
| -------------------------------------------- | --------------------------------------------------------------------------------------- |
| Multiple items in one POST                   | When the natural unit is a batch (CSV import)                                           |
| One item per request, parallelised by client | When each item is independent and HTTP/2 multiplexing is available                      |
| `202 Accepted` + status URL                  | When the operation takes long enough that the client shouldn't hold open the connection |
| Result polling                               | The status URL returns `pending` / `running` / `succeeded` / `failed`                   |
| Result webhook                               | The server pushes when done — see "Webhooks"                                            |
| Result streaming (SSE, chunked)              | When the result is incremental                                                          |

**Project default for HTTP 202 polling APIs:** Consider `Retry-After` when the server can provide a
useful polling delay, and return an operation/correlation identifier when clients need status or
support reconciliation. Queue, stream, library-task, and batch contracts use their native flow and
identity mechanisms instead.

---

## Caching

HTTP caching is **part of the API**. Use it deliberately.

| Header                                | Use                                                                                                            |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `Cache-Control`                       | `public`, `private`, `no-store`, `max-age=N`, `stale-while-revalidate=N`                                       |
| `ETag`                                | Entity tag; may be strong or prefixed `W/` for weak semantics. Use with `If-None-Match` for conditional reads. |
| `Last-Modified` / `If-Modified-Since` | Time-based validator whose precision and clock semantics may be weaker than a suitable ETag.                   |
| `Vary`                                | Tell caches what dimensions to key on (e.g., `Accept-Language`)                                                |

**Project default for HTTP conditional writes:** Clients can send `If-Match: <etag>` on
`PUT`/`PATCH`/`DELETE`, with `412 Precondition Failed` on a failed precondition. This can prevent
lost updates when validators represent the intended state and every relevant write path correctly
generates and enforces them.

---

## Authentication and Authorisation at the API Layer

| Mechanism                                                                      | When                                                                                                          |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| **Session cookie** (server-side, opaque)                                       | Same-origin web clients                                                                                       |
| **OAuth 2.0/OIDC with current security guidance** (JWT or opaque access token) | Delegated/federated access where the selected profiles and client types fit                                   |
| **API keys**                                                                   | Simple application identity or metering; authorization scope, rotation, and leakage risk still require design |
| **mTLS**                                                                       | Server-to-server, strong authentication, internal mesh                                                        |
| **Signed requests (HMAC of body + timestamp)**                                 | Webhook senders proving they're the real provider                                                             |

Discipline (cross-reference [SECURITY](security.md)):

- **Invariant for protected operations:** Authorize the requested action against the affected
  resource/tenant at the decision-owning component. Tokens prove claims, not entitlement.
- **Short-lived access tokens; rotation via refresh tokens.**
- **Scoped tokens** — read-only vs write, narrow audiences.
- **Invariant for bearer credentials:** Do not place secrets in URL components that routine logs,
  referrers, history, or intermediaries expose.
- Configure browser cross-origin policy explicitly; credentialed requests require an allowed origin
  rather than a wildcard under the applicable CORS protocol.

---

## Rate Limiting

| Choice                                  | Detail                                                                                                                       |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Where to count**                      | Select principal, token/client, tenant, source/network, operation, or resource dimensions from the threat and fairness model |
| **Algorithm**                           | Token bucket (allows bursts), leaky bucket (smooth), sliding window                                                          |
| **Response on limit hit**               | `429 Too Many Requests` + `Retry-After`                                                                                      |
| **Headers on success**                  | **Standard/fact (HTTP):** RFC 9331 defines `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset` fields            |
| **Different limits per endpoint class** | Auth endpoints stricter; read endpoints looser                                                                               |
| **Distinct quotas vs rate limits**      | Rate = per minute; quota = per month                                                                                         |

**Anti-pattern:** Rate limiting only on the public edge but not internally. A compromised internal service can DoS the database.

---

## Schemas — The Contract in Code

| Style        | Schema language                                                                                                                           |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| REST         | **Standard/fact (OpenAPI Specification 3.1):** an HTTP API description format                                                             |
| GraphQL      | The GraphQL SDL                                                                                                                           |
| gRPC         | Protobuf                                                                                                                                  |
| Async events | **Standard/fact (AsyncAPI Specification):** an asynchronous API description; payload schemas can use the selected supported schema format |

**Discipline:**

- **Project default:** Keep one authoritative, versioned schema and diff it. Schema-first and
  code-first generation can both work when the generated artifact is deterministic, reviewed, and
  tested against implementations/consumers.
- Keep the authoritative schema or declaration under governed version control; it may live in the
  producer repository, an interface repository, or a language package according to ownership.
- Make incompatible diffs visible and require the approval/migration path adopted by the project.
  A diff tool enforces only the compatibility rules it models.
- Generate reference documentation where the schema can own it; preserve prose examples and
  rationale that generation cannot supply without creating a second field-level authority.
- Use consumer/provider contract tests, recorded-message replay, compiler checks, or version-pair
  integration tests according to the interface. Passing evidence covers only represented consumers
  and scenarios.

---

## Webhooks — You Are Now the Server's Client

If your system sends webhooks:

| Concern               | Project default and scope                                                                                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Signing**           | A documented, versioned signature scheme over exact bytes or a precisely specified canonical form; algorithm/key rotation and replay binding                               |
| **Replay protection** | Bind signature/authentication to freshness and operation identity according to the sender's documented clock/window contract; no universal window fits every delivery path |
| **Duplicate effects** | Give deliveries an event/operation identity and document receiver deduplication or another reconciliation strategy when retries can repeat harmful effects                 |
| **Retries**           | Exponential backoff for non-2xx; configurable retry policy; dead-letter for permanent failures                                                                             |
| **Versioning**        | Event types versioned; deprecation policy mirrors REST                                                                                                                     |
| **Documentation**     | Schema, example payload, retry behaviour, signing recipe                                                                                                                   |
| **Test endpoint**     | Let receivers verify their handler without business consequences                                                                                                           |

If your system _receives_ webhooks:

- Verify authenticity/integrity using the sender's documented mechanism and protect replay; where
  no signature exists, use an equivalent authenticated channel/control or accept the risk explicitly.
- Respond within the sender's deadline. Asynchronous processing is a strong default for durable
  workflows; a bounded synchronous handler can be valid when its contract and retry effects are safe.
- Handle duplicate delivery according to the sender's retry semantics and the receiver effect.
- Accept unknown fields only where the schema defines an extension point; reject unknown commands,
  signed/canonicalized fields, or closed unions when safety requires it.

---

## Async Events — The Schema is The Contract

Persisted or independently consumed events can outlive emitters and consumers. **Project defaults:**

- Define an event identity and evolution mechanism (for example a versioned type or schema subject)
  when incompatible forms may coexist.
- Prefer protocol-compatible additive evolution; verify optionality, defaults, unknown-field
  behavior, closed unions, and read-modify-write preservation before calling a field addition safe.
- Provide one governed schema discovery point when multiple producers/consumers need it; a
  single-process transient event may rely on compiler-visible types instead of a registry.
- When a state change and event publication must share an integrity boundary, use an outbox,
  broker/database transaction, reconciliation, or another design whose failure states are explicit.
- Implement the broker's documented delivery semantics. At-least-once is common; consumers then
  need idempotency, deduplication, transactions, or reconciliation appropriate to each effect.
- Route poison/unprocessable events to a visible bounded failure path—dead-letter storage,
  quarantine, rejection metrics, or explicit discard policy—appropriate to data sensitivity and
  retention obligations.

---

## Anti-Patterns

| Pattern                                                                      | Why it fails                                                                                                                  |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **`200 OK` for every response**                                              | The HTTP layer is part of the API; intermediaries get confused                                                                |
| **Verbs in URLs except for explicit actions** (`/getOrders`, `/createOrder`) | The HTTP method is the verb                                                                                                   |
| **Plural / singular inconsistency** (`/orders` next to `/customer/123`)      | Cognitive cost; SDK code generators choke                                                                                     |
| **Free-text error strings**                                                  | Clients regex over them, then break when you reword                                                                           |
| **Returning HTML in a JSON API on error**                                    | Yes, this happens; clients explode                                                                                            |
| **Sequential IDs treated as authorization**                                  | Guessability is not access control; exposure may reveal scale or enumeration and needs a deliberate threat-model decision     |
| **Nullable everywhere**                                                      | Hides domain truth; every field is a tri-state ("present", "explicit null", "absent")                                         |
| **Massive responses**                                                        | The endpoint that returns every field of every related resource; clients become coupled to internals                          |
| **Inconsistent date formats**                                                | `created_at`, `createdAt`, `creation_time`, sometimes ISO, sometimes Unix seconds                                             |
| **Ambiguous time values**                                                    | Use an instant/offset for events; use local civil time plus IANA zone and recurrence semantics for schedules                  |
| **Booleans named negatively** (`is_disabled`, `not_archived`)                | Cognitive load multiplies; pair with negation                                                                                 |
| **GET with side effects**                                                    | Caches will replay; safety violated                                                                                           |
| **UI-shaped API without an ownership boundary**                              | A deliberate backend-for-frontend can be valid; accidental coupling makes reuse/versioning harder                             |
| **No deprecation policy**                                                    | Breaking changes ship by accident                                                                                             |
| **No evolution policy before independent consumers**                         | The first incompatible change becomes an outage or improvised migration; an explicit `v1` prefix is not the only valid policy |
| **GraphQL without a cost model / depth limit**                               | One client query takes down the database                                                                                      |

---

## The Public-vs-Internal Distinction Is Smaller Than You Think

Migration cost rises when:

- A second team consumes them.
- A mobile app consumes them and you can't force-upgrade.
- A customer integrates against them, even via a partner.
- They are recorded somewhere persistent (events in storage, replayed at recovery).

**Project default:** Apply rigor according to independent consumers, deployment coupling, persistence,
blast radius, and migration cost. A private in-process interface and a stored cross-team event do
not need the same ceremony; both need an explicit contract proportionate to how they can fail.

## Protocol Status Sources

**Standard/fact (repository-verified 2026-07-30; re-verify before relying on current status):**

- [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110) defines HTTP validators, including strong and
  weak entity tags.
- [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) defines Problem Details for HTTP APIs; extensions
  such as a project `code` field remain that API's contract.

Re-verify drafts, security BCPs, and protocol/library versions before implementation.

---

## Diagnostic Framework

| Symptom                                               | Likely cause                                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------ |
| "We can't change anything without breaking clients"   | No tolerant reader; no versioning policy; no deprecation channel                     |
| Different endpoints return different error shapes     | No central error contract                                                            |
| Clients re-implement the same workflow over and over  | Resources missing — domain operation isn't represented as a resource or named action |
| Duplicate writes after retries                        | Missing idempotency                                                                  |
| Lost updates between concurrent edits                 | Missing optimistic concurrency (`ETag` / `If-Match`)                                 |
| Slow lists, OOM on large datasets                     | No bounded pagination                                                                |
| Clients hammer the API; latency degrades for everyone | No rate limits                                                                       |
| Surprising behaviour after an "additive" change       | Field meaning changed, not just field presence                                       |
| "We don't know who's using which endpoint"            | No usage metrics per endpoint per consumer                                           |
| One slow downstream takes the API down                | No timeouts; no circuit breaker                                                      |
| API is now the database's serialisation format        | Endpoint per UI need; presentation logic coupled                                     |

---

## Meta-Question

An API is a promise at a consumer boundary. Ask of each observable behavior: **who relies on this,
what evidence says old and new participants interoperate, and what migration would retract or change
the promise?** If retraction requires coordinated upgrades, stored-data conversion, or third-party
action, treat it as a consequential decision; if producer and sole caller compile and release
atomically, use proportionate ceremony.

---

_See [ARCHITECTURE](architecture.md) for synchronous-vs-async choice and service boundaries._
_See [SECURITY](security.md) for auth, input validation, rate limiting in depth._
_See [PRIVACY](privacy.md) for what to return and what to suppress._
_See [ERROR_HANDLING](error-handling.md) for the domain-level error story behind the wire format._
_See [OBSERVABILITY](observability.md) for correlation IDs and per-endpoint metrics._
_See [GIT_AND_VERSIONING](git-and-versioning.md) for the deprecation discipline at the code level._
