---
knowledge:
  version: 1
  id: data
  summary: Evolve data models, persistence, indexes, and migrations with explicit invariants, compatibility, rollback, privacy, and integrity evidence.
  routes: [database-schema-migration]
  sources: [src-data-platform]
---

# data.md — Data, Schema, and Persistence Reference

> **Purpose:** Reference for designing, evolving, and operating durable state. Covers schema design,
> ACID, isolation, indexing, migrations, transactions, integrity, encoding, and reconciliation
> across systems of record.
>
> **Read this when:** designing a schema; adding a column; writing a query that touches more than one row; reviewing a migration; debugging an "impossible" data state; integrating a new data store.
>
> **Do NOT** assume that "the framework handles it." ORMs hide enough of the truth to be dangerous when you don't understand what they generate.

---

## The Premise

The database outlives the code. Every other layer of the stack will be replaced two or three times before the schema is. **Decisions made at the schema level are the most expensive ones to reverse.** Treat them accordingly.

Three rules that everything else descends from:

1. **Name the authority for each datum and invariant.** An owned relational database may be
   authoritative for durable application state; an event log, external system, ledger, object
   store, or federated domain may own other truth. Caches and projections declare freshness and
   reconciliation semantics.
2. **Enforce invariants at every capable boundary.** Put database-expressible invariants in
   constraints/transactions; retain application/workflow controls for cross-service, temporal,
   authorization, and external-system invariants.
3. **Data outlasts the developer.** Optimise the schema for the people who will read it in five years, not for the convenience of today's framework.

---

## Choosing the Storage Engine

| Engine class                                             | Use when                                                                                                                                     | Reject when                                                                          |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| **Relational (Postgres, MySQL, SQLite)**                 | Anything with relationships, transactions, or analytical queries. **Default.**                                                               | Single-key lookups at planet scale                                                   |
| **Document (MongoDB, CouchDB)**                          | Aggregate/document access, schema evolution, distribution, and consistency model fit the workload                                            | Selecting “flexibility” without query, integrity, migration, and operations evidence |
| **Key-value / coordination store**                       | Cache, sessions, counters, configuration, coordination, or durable key-value workloads when its documented persistence/consistency fits      | Assuming all products in the category share durability semantics                     |
| **Wide-column (Cassandra, ScyllaDB)**                    | Massive write throughput; known access patterns; eventual consistency is acceptable                                                          | You want SQL ergonomics                                                              |
| **Time-series (TimescaleDB, InfluxDB, VictoriaMetrics)** | Append-only metrics/events with time-based queries                                                                                           | Anything that isn't time-series                                                      |
| **Graph (Neo4j, JanusGraph)**                            | The questions are inherently graph-shaped (paths, cycles, reachability)                                                                      | A few foreign keys                                                                   |
| **Search/index engine**                                  | Full-text, faceted, ranked search; sometimes an authoritative corpus when durability, backup, and mutation semantics are explicitly designed | Treating a rebuildable index as authoritative accidentally                           |
| **Object store (S3-compatible)**                         | Blobs, files, immutable artefacts                                                                                                            | Metadata-only data                                                                   |
| **Embedded (SQLite, DuckDB, libmdbx)**                   | Single-process, low-ops, small-to-medium dataset, no concurrent writers from multiple machines                                               | Multi-writer or distributed                                                          |

**The default for a conventional server-side relational application is Postgres.** It is mature,
well documented, and operationally well understood. It supports SQL, JSON, full-text search, and
extension ecosystems for workloads such as time-series and vectors. Treat that as a strong prior,
not a statistic: embedded/offline, analytical, search-first, streaming, graph, and extreme-scale
access patterns may justify another engine. State the workload evidence that overrides the default.

---

## Relational Schema Design — The Discipline

### Normalisation, in plain English

| Normal form | What it forbids                                             | When to relax                                                                                                    |
| ----------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **1NF**     | A cell containing multiple values                           | Almost never                                                                                                     |
| **2NF**     | Non-key columns that depend on only part of a composite key | Almost never                                                                                                     |
| **3NF**     | Non-key columns that depend on other non-key columns        | When read patterns make a join unbearable — and even then, denormalise the _projection_, not the source of truth |
| **BCNF**    | Edge cases of 3NF involving overlapping candidate keys      | Often. Most schemas stop here.                                                                                   |

**Default: design to 3NF.** Denormalise _deliberately_, with a written reason and a way to keep the duplicate in sync (trigger, materialised view, application-level invariant with a test).

### Naming

Names are the second most permanent thing about the database (after data). Make them precise.

| Convention                                                                                        | Why                                                                 |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `snake_case` for tables and columns                                                               | SQL is case-insensitive in most dialects; mixed case forces quoting |
| Plural for tables (`users`), singular for columns (`user_id`)                                     | Consistent with `SELECT user_id FROM users`                         |
| `_id` suffix for foreign keys                                                                     | Self-documenting                                                    |
| `_at` suffix for timestamps (`created_at`, `deleted_at`)                                          | Disambiguates from booleans                                         |
| `is_` prefix for booleans (`is_active`)                                                           | Same                                                                |
| Avoid reserved words (`user`, `order`, `type`, `group`)                                           | Mandatory quoting; subtle bugs across drivers                       |
| Avoid generic `data`, `info`, `details`, or `metadata` unless the domain truly names that concept | Generic names hide semantics and ownership                          |
| Domain language, not technical jargon                                                             | `customer`, not `entity_type_3`                                     |

### Types — pick the narrowest correct one

| Need           | Use                                                                                                                                                               | Avoid                                                            |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Integer ID     | `bigint` (`int8`)                                                                                                                                                 | `int` — 32-bit ceilings happen sooner than you'd think           |
| Money          | `numeric(p, s)` with explicit precision; or integer minor units (cents)                                                                                           | `float`, `double`, `real` — floating point cannot represent 0.10 |
| Instant        | An offset/instant-capable type such as Postgres `timestamptz`                                                                                                     | A timezone-free timestamp for a globally ordered instant         |
| Date (no time) | `date`                                                                                                                                                            | `timestamptz` set to midnight — what time zone's midnight?       |
| Text           | `text` (in Postgres; no length penalty)                                                                                                                           | `varchar(n)` unless `n` is a real domain constraint              |
| Boolean        | `boolean`                                                                                                                                                         | `int` 0/1, `char(1)` Y/N — both lose meaning                     |
| Enum-like      | Foreign key to a lookup table, or a `CHECK` constraint, or a native `enum` (with awareness of how hard enums are to evolve)                                       | Free-text strings parsed by the application                      |
| JSON           | A typed schema when fields are relationally queried; Postgres `jsonb` for appropriate semi-structured/indexed documents; `json` when lexical preservation matters | Stringified JSON with no validation or migration plan            |
| Binary blob    | Object storage for independently served/large objects; database binary types when transactional locality, scale, and backup/replication costs support it          | Choosing either location without lifecycle and recovery evidence |
| UUID           | `uuid` native type; UUIDv7 if you want time-ordered (better locality than v4)                                                                                     | UUID stored as text                                              |

### Time, time zones, and the worst bugs

- **Project default for an instant:** Store an unambiguous instant/offset (for example,
  `timestamptz`) and render in the user's zone.
- **Civil schedules need civil data:** Store the intended local date/time, IANA time-zone ID, and
  recurrence/business rules; derive occurrences with an explicit timezone-database version/policy.
  UTC alone cannot preserve “09:00 Europe/Oslo every Monday” across daylight-saving changes.
- **`now()` vs `clock_timestamp()` vs `statement_timestamp()`** — know the difference. `now()` is fixed for the whole transaction.
- **Don't subtract dates and assume days.** Daylight saving, leap seconds, calendar reform — use date arithmetic functions.
- **Wall-clock vs monotonic clock.** Durations between events should use monotonic time; wall clocks jump.

### Encoding and collation

- **UTF-8 everywhere.** Database, connection, application, file system.
- **Use `text` collation explicitly** (`COLLATE "C"` for byte-order; ICU collations for language-aware sorting). Default `en_US.UTF-8` is a frequent source of surprise behaviour in indexes.
- **Normalise Unicode at the boundary.** Different code-point sequences can compare unequal even when they look identical (`é` as one code point vs. two).
- **Be deliberate about case folding.** "Steve" and "steve" — equal? Asked at every layer.

---

## Constraints Are Documentation That Enforces Itself

Use, in order of strength:

1. **`NOT NULL`** — every column. Nullable should be the exception with a reason.
2. **`UNIQUE`** — on natural keys and combinations that must be unique.
3. **`FOREIGN KEY`** — every reference, with explicit `ON DELETE` semantics.
4. **`CHECK`** — for invariants the type can't express (`age >= 0`, `status IN ('active','suspended','deleted')`, `start <= end`).
5. **`EXCLUSION` constraints** (Postgres) — for "no two overlapping reservations".
6. **Generated columns** — for derived values you want to query/index without trusting the application.

**`ON DELETE` matters.** `RESTRICT`, `CASCADE`, `SET NULL`, `SET DEFAULT`, `NO ACTION` — pick deliberately. The default in most ORMs is `NO ACTION`, which is rarely what you want.

**Null is not a value.** It's "unknown". `NULL = NULL` is `NULL`, not `true`. `NOT IN (..., NULL, ...)` is always empty. Treat null with suspicion; eliminate it where you can.

---

## ACID — Know What You're Buying

| Letter          | Means                                                                                                                   | Bought you what                                                     |
| --------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| **A**tomicity   | A transaction is all-or-nothing                                                                                         | Partial failures don't leave half-written state                     |
| **C**onsistency | A committed transaction takes the database from one valid state to another according to declared constraints/invariants | Application and schema rules—not the letter C alone—define validity |
| **I**solation   | Concurrent transactions appear sequential at the chosen isolation level                                                 | Concurrent writers don't corrupt each other (depending on level)    |
| **D**urability  | Committed data survives a crash                                                                                         | Power loss doesn't lose committed data                              |

ACID is per-transaction. **Most application bugs are isolation bugs masquerading as logic bugs.**

---

## Isolation Levels — The Land Mine

Most databases default to a level weaker than developers assume. **Read this section before designing anything with concurrent writers.**

| Level               | Allows                                                                 | Postgres default               | MySQL InnoDB default   |
| ------------------- | ---------------------------------------------------------------------- | ------------------------------ | ---------------------- |
| Read uncommitted    | Dirty reads                                                            | —                              | —                      |
| **Read committed**  | Non-repeatable reads, phantom reads                                    | ✓                              | —                      |
| **Repeatable read** | Phantom reads (in standard); none of the others in Postgres (snapshot) | (available)                    | ✓                      |
| **Serializable**    | Nothing                                                                | (available; cheap-ish via SSI) | (available; expensive) |

**Phenomena to recognise by name:**

| Name                    | What it is                                                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dirty read**          | Read uncommitted data; might roll back                                                                                                         |
| **Non-repeatable read** | Same query, same transaction, different answer because someone committed                                                                       |
| **Phantom read**        | A `WHERE` clause matches more rows on re-query                                                                                                 |
| **Lost update**         | Two transactions read, then write, and the later overwrites the earlier without seeing it                                                      |
| **Write skew**          | Two transactions read overlapping data, write disjoint data, and the _combination_ violates a constraint that each transaction alone preserves |

**The write-skew trap** is the one most often missed:

> Two on-call doctors are scheduled. Each transaction reads "there are two on-call doctors", then each independently sets `is_oncall = false` for one of them. The constraint "at least one doctor is on-call" is violated even though each transaction saw a consistent snapshot.

Cure: use **`SELECT ... FOR UPDATE`** to lock the read rows, or run the transaction at **serializable** isolation, or compute the invariant with an exclusion constraint.

### The decision

- **Default:** Use `READ COMMITTED`. Explicitly use `SELECT ... FOR UPDATE` (or `FOR SHARE`) for read-modify-write patterns.
- **When the invariant can't be expressed by row locks** (write skew across rows): use `SERIALIZABLE` for the affected transactions.
- **Don't mix.** Pick a level for a logical operation and document it.

---

## Transactions — Practical Discipline

| Rule                                                     | Reason                                                                                                   |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Keep transactions **short**                              | Long transactions hold locks, bloat the WAL, block VACUUM, and accumulate visibility metadata            |
| **No external I/O inside a transaction**                 | HTTP call, email send, file upload — the transaction's lifespan is now bounded by an unrelated system's  |
| **The outbox pattern** for "write to DB and then notify" | Insert the message in the same transaction as the write; a separate worker reads the outbox and delivers |
| Use **savepoints** for nested logical units              | Postgres has no nested transactions; savepoints are the substitute                                       |
| **Idempotent** application code where retries can happen | Deadlock detection will roll some transactions back; the application must be able to retry safely        |
| Avoid **`SELECT * `** in transactions                    | Schema additions break callers; explicit column lists are safer                                          |

---

## Indexes — Costs, Not Just Benefits

Every index is a write-amplification cost. Every write to the table updates every index on the table. **Indexes are not free.**

| Index need                                | Index type                                        |
| ----------------------------------------- | ------------------------------------------------- |
| Equality on one column                    | B-tree                                            |
| Range on one column (`>`, `<`, `BETWEEN`) | B-tree                                            |
| Multi-column with leftmost-prefix queries | Composite B-tree (column order matters)           |
| Full-text search                          | GIN with `tsvector`, or a dedicated search engine |
| JSON containment, array overlap           | GIN                                               |
| Geospatial                                | GiST / SP-GiST (PostGIS)                          |
| Approximate / similarity (vectors)        | HNSW, IVFFlat (pgvector)                          |
| Exclusion constraint                      | GiST                                              |

**Anti-patterns:**

- Indexing every column "just in case." The query planner can't tell the useful indexes from the rubbish.
- Indexing low-cardinality columns (`gender`, `is_deleted`) without a partial index condition.
- Composite indexes in the wrong column order. Match actual query predicates and ordering: leading
  equality constraints commonly come first, then the first range/order requirement; verify with the
  database's planner and production-shaped data rather than a generic “most selective first” rule.
- Ignoring `EXPLAIN (ANALYZE, BUFFERS)`. You can't tune what you can't see.

**Partial indexes** are underused — `CREATE INDEX ... WHERE is_active` indexes only the rows you care about, smaller and faster.

**Covering indexes** (`INCLUDE` columns) avoid heap fetches for read-heavy queries.

---

## The N+1 Query Problem

A single page renders. For each of N items shown, the ORM emits one extra query. You discover the bug in production at scale.

**Symptoms:**

- Slow lists, fast detail pages.
- Query count rises with result size.

**Fixes:**

- ORM-specific eager loading (`joinedload`, `prefetch_related`, `includes`).
- Explicit SQL with a join.
- Batch loader pattern (e.g., DataLoader) for N independent fetches.

**Anti-pattern:** Add a cache to mask the N+1. The N+1 will return as soon as the cache misses.

---

## Migrations — Schema Change Without Downtime

The schema lives in production. Changes happen while users are connected. Discipline:

| Pattern                                                                                     | When                                                                                                                                              |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Forward-oriented production migrations**                                                  | Prefer roll-forward and expand/migrate/contract; reversible migrations still matter for packaged, embedded, or explicitly rollback-driven systems |
| **Expand → migrate → contract**                                                             | Add a new column nullable; backfill in batches; switch writers to the new column; switch readers; drop the old column. Three deploys, not one.    |
| **Online migration tools** (`pg-online-schema-change`, `gh-ost`, `pt-online-schema-change`) | Tables larger than what a `LOCK TABLE` can hold                                                                                                   |
| **Background backfill** with batches and rate limits                                        | Don't lock the table; don't saturate I/O                                                                                                          |
| **`CONCURRENTLY`** on Postgres indexes                                                      | Build indexes without blocking writes                                                                                                             |
| **Renames in two steps**                                                                    | Add a new column with the new name, dual-write, drop the old                                                                                      |
| **Default values added in two steps** (older Postgres)                                      | New tables get the default; old rows backfilled separately                                                                                        |
| **Migration incompatible with deployed code**                                               | Design an expand/backfill/contract sequence so old and new versions remain compatible through the actual rollout and rollback window              |

**Locking gotchas (Postgres):**

- `ALTER TABLE ADD COLUMN` with a constant default in modern Postgres is fast; with a function-based default it rewrites the table.
- Adding `NOT NULL` is version- and data-dependent. On supported PostgreSQL versions, add
  `CHECK (column IS NOT NULL) NOT VALID`, validate it, then use `ALTER COLUMN ... SET NOT NULL`;
  a validated proof can avoid the full verification scan. Measure lock acquisition and duration
  on production-like data. `NOT VALID` does not apply directly to a `NOT NULL` constraint. Verify
  the sequence against the deployed version's
  [PostgreSQL `ALTER TABLE` documentation](https://www.postgresql.org/docs/current/sql-altertable.html).
- `CREATE INDEX` (without `CONCURRENTLY`) locks writes.
- `VACUUM FULL` rewrites and exclusively locks; use `pg_repack` instead.

---

## Soft Delete — Retention Semantics, Not Deletion

`deleted_at TIMESTAMPTZ NULL` everywhere is tempting. The consequences:

| Cost                                         | Reality                                                             |
| -------------------------------------------- | ------------------------------------------------------------------- |
| Every query needs `WHERE deleted_at IS NULL` | The day someone forgets, deleted users see deleted data             |
| Foreign keys still point to deleted rows     | `ON DELETE` semantics become a maze                                 |
| Uniqueness constraints break                 | `UNIQUE(email)` fails because the deleted user still owns the email |
| Right to erasure (GDPR)                      | Soft-deleted ≠ deleted. Compliance bug.                             |

**When soft delete can be right:** When reversible deactivation is a named product/records
requirement with authorization, uniqueness, visibility, retention, and eventual disposition
designed explicitly. Personal data may still be retained where a valid purpose/legal basis applies;
the row must not be represented as erased. Otherwise:

- **Hard delete** for personal data, on schedule.
- **Tombstone table** for "we used to know this thing existed" without keeping its contents.
- **Archive table** for "we need history" — explicit, separate, with its own access controls.

See [PRIVACY](privacy.md) for the retention discipline.

---

## Money — A Worked Example of "Don't Wing It"

Floating point is a bug factory for money:

```
>>> 0.1 + 0.2
0.30000000000000004
```

**Use one of:**

- **`numeric(p, s)`** with explicit precision (e.g., `numeric(19, 4)` for general use).
- **Integer minor units** (cents as `bigint`). Cheap, fast, no precision drama. Track the currency separately.
- **A money library** (e.g., `dinero.js`, `money` types in Java). Never raw floats.

**Currency is part of the value.** "100" without "EUR" or "USD" is a bug waiting to happen.

**Rounding rules.** Half-up vs banker's rounding vs truncate matters at scale; pick one, document it, test it.

---

## Replication, HA, and CAP

- **Single primary, async replicas:** the workhorse. Reads can lag (eventual consistency on replicas).
- **Sync replication:** stronger guarantee, latency cost on writes.
- **Multi-primary:** conflict resolution is now your problem.
- **Distributed SQL (CockroachDB, Spanner, YugabyteDB):** strong consistency across regions, but with latency and operational complexity. Justify the cost.
- **CAP theorem:** under network partition, you choose between consistency and availability for that subset of operations. For most business systems, partitions are rare, and the question is really "what's the latency and operational cost of strong consistency?"

**Eventual consistency:** the read replica may be stale. Either route reads needing strong consistency to the primary, or design the UI to tolerate "it might take a moment to show up".

---

## Caching the Database — and Its Many Bugs

| Concern                | Default                                                                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Where the cache lives  | As close to the consumer as possible (in-process > local Redis > remote Redis > CDN)                                                          |
| Invalidation           | The hardest part. Prefer short TTLs over complex invalidation.                                                                                |
| Stampede               | When the cache expires, N requests miss simultaneously and overwhelm the source. Use `singleflight` / probabilistic early expiration / locks. |
| Negative caching       | Cache "not found" too, with shorter TTL — otherwise a missing item is a slow query every time                                                 |
| Stale-while-revalidate | Serve stale, refresh in background — when the staleness is acceptable                                                                         |
| Cache the right shape  | Cache what's expensive to compute, not what's cheap                                                                                           |

**Rule:** A cache hides bugs. Run with the cache disabled occasionally to surface them.

---

## Encoding and Internationalisation

| Concern                                     | Default                                                                                                                                 |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Database, connection, table, column charset | UTF-8                                                                                                                                   |
| Collation                                   | Document explicit collation per text column where it matters                                                                            |
| Sort order                                  | Locale-aware (ICU) for human-facing sorts; `C` collation for byte-order indexes                                                         |
| Case folding                                | Pick a strategy; same everywhere (DB, app, search)                                                                                      |
| Names, addresses, languages                 | Allow full Unicode; don't reject non-ASCII; don't enforce English name conventions                                                      |
| Phone numbers                               | Store in E.164 format (`+CCNNNN...`); use a library (`libphonenumber`)                                                                  |
| Emails                                      | Allow internationalised emails (IDN, `local-part@xn--...`) where the threat model permits; otherwise pick a sane subset and document it |

**Falsehoods programmers believe about names, addresses, time zones, dates, languages** — read the lists. Twice.

---

## Backups — A Backup You Haven't Restored Is a Hope

| Discipline                         | Detail                                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Schedule**                       | Frequency matches the recovery point objective (RPO). Daily isn't good enough for high-value writes.   |
| **PITR (point-in-time recovery)**  | WAL archiving on write-heavy systems                                                                   |
| **Encrypted at rest**              | The backup is a copy of all your secrets too                                                           |
| **Off-site**                       | A backup in the same DC as the primary is a copy, not a backup                                         |
| **Tested**                         | Restore on a schedule. An untested backup provides artifact evidence, not demonstrated recoverability. |
| **Documented runbook**             | At 3 AM you don't want to be reading manuals                                                           |
| **Retention aligned with privacy** | See [PRIVACY](privacy.md) — backups containing personal data are subject to retention rules            |
| **Distinct credentials**           | The application cannot delete backups                                                                  |

**Rule:** A backup that took 12 hours to restore is a 12-hour outage you signed up for.

---

## Data Integrity Beyond Constraints

| Tool                                                                                                        | Use                                                  |
| ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Checksums** on important files / blobs                                                                    | Detect bit rot in object storage                     |
| **Append-only / hash-chained ledgers** for audit-critical state                                             | Tamper evidence                                      |
| **Application-level invariant checks** (a daily job that verifies "no order has total ≠ sum of line items") | Catch logic bugs early                               |
| **Database-level row counts and aggregates** monitored                                                      | Sudden drops are bug signals                         |
| **Replicas read randomly to spot-check the primary**                                                        | The replica catches some kinds of primary corruption |

---

## Schema Documentation

**Project default:** Document non-obvious units, ownership, semantics, sensitivity, and invariants
near the schema or in generated schema documentation. Database comments are effective where the
platform preserves and exposes them; do not duplicate obvious names.

For every table:

- What is it for? (One sentence.)
- What is the primary key, and what does it mean? (Surrogate vs. natural.)
- What writes here? What reads here?
- What's the retention policy?

ERDs and schema diagrams help, but only if they're regenerated from the schema, not maintained by hand.

---

## ORMs — The Trade-off

ORMs trade **understanding of generated SQL** for **velocity on common cases**. The trade is fine as long as:

- You read the generated SQL on every non-trivial query (turn on query logging in dev).
- You know how to drop into raw SQL when needed and how the ORM expects you to.
- You understand the unit of work / session lifecycle, lazy loading rules, and N+1 risks.
- You don't reach for ORM features (single-table inheritance, polymorphic associations) that hide the underlying schema cost.

**Anti-pattern:** Letting the ORM design the schema. The ORM's defaults are convenient for the application, not for the database.

---

## When You Are Not Using SQL

For non-SQL data stores, the principles still apply:

- **Indexes:** What queries does the system support efficiently? What's the cost of each index?
- **Schema:** "Schemaless" means the schema is in every reader's head, in inconsistent forms. Maintain a schema document.
- **Consistency:** What does this store promise? Eventual? Read-your-writes? Linearisable?
- **Transactions:** What's atomic? At what granularity? Document-level? Multi-key transactions?
- **Backups:** Same discipline.
- **Migrations:** Even schemaless stores need migrations as the implicit schema evolves.

---

## Diagnostic Framework

| Symptom                        | Likely cause                                                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| "It worked yesterday"          | A migration ran; a default changed; an index was dropped; check the change log                                            |
| Slow query                     | Missing index; bad plan; bloat; N+1; lock waits — read `EXPLAIN`                                                          |
| Deadlocks                      | Inconsistent lock ordering across transactions; long transactions                                                         |
| Data is "missing"              | Soft delete; replication lag; cache; wrong tenant filter; case folding                                                    |
| Mysterious nulls               | A column was added; a constraint was relaxed; a value is `NULL` because the JOIN didn't match                             |
| Duplicate rows                 | Missing `UNIQUE` constraint; idempotency bug; retry without idempotency key                                               |
| Phantom rows                   | Retry that succeeded the second time without idempotency                                                                  |
| Slow writes after good reads   | Index thrashing; over-indexed table                                                                                       |
| `serialization_failure` errors | Working as intended — retry the transaction                                                                               |
| Storage growing unbounded      | Bloat (Postgres); soft-delete accumulation; missing retention                                                             |
| "It corrupted the data"        | Investigate races, missing/incorrect invariants, migration defects, storage faults, and external-authority reconciliation |

---

## Meta-Question

The data layer should make invalid durable states hard or impossible within its authority. Put
database-expressible invariants in the database and test the application/workflow/reconciliation
controls for invariants that cross stores, services, time, authorization, or external systems.

## Primary Source

**Standard/fact (verified 2026-07-30):** PostgreSQL's current multicolumn-index documentation
describes leading-column and inequality behavior; other engines differ. Source:
[PostgreSQL multicolumn indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html).
Re-verify against the deployed engine/version and query plan.

When in doubt: put the rule in the database. The database is patient and exact. The application is fast and forgetful.

---

_See [ARCHITECTURE](architecture.md) for transaction boundaries and source-of-truth design._
_See [PRIVACY](privacy.md) for retention and erasure obligations._
_See [SECURITY](security.md) for SQL injection, encryption at rest, and access control._
_See [PERFORMANCE](performance.md) for caching, N+1 detection, and query optimisation._
_See [CONCURRENCY](concurrency.md) for the cross-process race conditions that mirror isolation phenomena._
