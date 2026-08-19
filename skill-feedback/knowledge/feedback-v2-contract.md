# Feedback v2 emission contract

## Contents

1. Ownership and storage
2. Common envelope
3. Event types
4. Observation semantics
5. Lifecycle and automatic coverage
6. Privacy and retention
7. Consumer rules

## 1. Ownership and storage

Feedback owns the emission interface and ledger. Skills identify themselves and their feature; they
do not implement storage.

Two stores serve different change rates:

| Store | Contents | Reason |
| --- | --- | --- |
| `<skill-repo>/docs/feedback/` | Selective human-readable observations and dispositions | Maintainer action and version control |
| `$SKILL_FEEDBACK_HOME/note-outbox/` | Pending notes for read-only/unresolved sources | Preserve evidence without claiming delivery |
| `$SKILL_FEEDBACK_HOME/events.jsonl` | Invocation, outcome, observation, and disposition events | Cross-skill analysis without dirtying repos |

Verified outbox promotion is recorded in `<skill-repo>/docs/feedback/.delivery.json` with relative
locations and entry/note hashes. The original observation event remains immutable and describes its
historical pending state.

## 2. Common envelope

Every event contains:

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | Integer event schema version |
| `event_id` | yes | Globally unique event identifier |
| `event_type` | yes | One of the types below |
| `occurred_at` | yes | UTC RFC 3339 timestamp |
| `skill.name` | yes | Stable skill name (SKILL.md `name` / installed folder) |
| `skill.version` | no | Commit, release, or content identifier |
| `invocation_id` | event-dependent | Joins a use across start, finish, and observations |
| `session.id` | no | Stable keyed pseudonym of the harness session identifier |
| `session.harness` | no | `claude`, `codex`, `opencode`, or another harness |
| `actor.type` | yes | `agent`, `user`, `automation`, or `system` |
| `source` | yes | Provenance class for the event |
| `task.class` | no | Privacy-safe workload class |
| `tags` | yes | String list, possibly empty |
| `privacy` | yes | Content-inclusion and redaction facts |
| `payload` | yes | Event-specific object |

Unknown values are `null` or omitted according to the schema; never invent model, provider, cost, or
user confirmation.

## 3. Event types

### `invocation.started`

Required payload:

- `feature`: capability/command used, or `null`.
- `backend`: requested router, provider, model, and effort when known.

Optional payload:

- alternatives considered;
- command name, never ambient secrets or full arguments;
- task fingerprint derived from an explicitly safe representation.

### `invocation.finished`

Required payload:

- `outcome`: `success`, `partial`, `failure`, `abandoned`, or `unknown`.
- `backend`: actual router/provider/model facts when known.
- `metrics`: duration, cost, token counts, retries, and cache facts when known.
- `evidence`: references to tests, artifacts, or results.

Do not infer success only from exit code when the domain has stronger acceptance evidence.

### `observation.recorded`

Required payload:

- `feedback_id`;
- `kind`: `praise`, `friction`, `bug`, `wish`, or `idea`;
- `signal`: `positive`, `negative`, or `mixed`;
- `feature`;
- `impact`: `low`, `medium`, `high`, or `unknown`;
- `outcome`;
- `evidence`;
- `note_sha256`, portable relative `note_file`, and optional `delivery`, not note content by default.

### `disposition.changed`

Required payload:

- `feedback_id`;
- `status`: `open`, `observed`, `preserve`, `planned`, `resolved`, `declined`, or `duplicate`;
- rationale;
- structured links to a task, issue, commit, test, or duplicate when known.

## 4. Observation semantics

- Record every invocation automatically only after safe instrumentation exists.
- Record qualitative observations selectively.
- Use praise for noteworthy value, not generic completion.
- Name the exact feature and observable benefit.
- Keep signal, outcome, cost, latency, safety, and quality separate; do not prematurely create one
  scalar reward.
- Treat explicit user confirmation, deterministic evidence, independent evaluation, and agent
  judgment as distinct sources.
- Promote important praise to `preserve` and link the behavior to a regression guard.

## 5. Lifecycle and automatic coverage

Current implementation exposes the central contract, explicit emission
commands, Feedback-owned CLI adapters, and coverage derived from the discovered
installed-skill/filesystem inventory. Inventory failure is an explicit
unavailable state and cannot pass coverage or onboarding checks. The installer
(skills.sh) publishes adapters as ordinary executable targets. Remaining
full-portfolio coverage requires:

- harness adapters for pure-text skill activation;
- representative paid/resumable pilots;
- measured latency and interactive process-behavior evidence for each unusual command class.

Never say “every skill automatically emits” until those adapters pass their acceptance tests.

The Feedback skill can receive qualitative meta-feedback by using `skill-feedback` as the target
skill. Its own executable is intentionally self-exempt to avoid recursion.

## 6. Privacy and retention

- Content capture defaults off.
- Avoid full command lines because they may contain prompts, paths, or secrets.
- Evidence is a reference, not automatic file ingestion.
- Structured values matching common secret forms are rejected before persistence.
- Qualitative observation and disposition prose is screened before CLI persistence. Likely secrets
  are rejected; likely identifiers require explicit review. Portfolio audit also covers parsed
  manual and legacy notes without returning their prose.
- Privacy findings are remediated by semantic generalization, not automatic match deletion. Preserve
  the feedback ID and actionable causal meaning; record content-free hash lineage for an authorized
  historical rewrite under ADR 0011.
- Central storage is local and private to the Unix user.
- Raw session IDs are transformed with a local keyed HMAC before persistence.
- Note locations are portable relative references; pending outbox locations are explicitly marked.
- `doctor`, `export`, `retention`, and targeted `delete` make storage inspectable and erasable.
- Retention and deletion are dry-run-first and require `--apply` to rewrite the ledger.
- An explicit retention policy plus `manifest_opt_in` mode is required before automatic collection
  can become active.
- Preserve the ability to delete telemetry without deleting curated qualitative feedback.

See [privacy-controls.md](privacy-controls.md) for the data map, commands, boundaries, and remaining
policy choices. ADR 0010 records the qualitative scanner's detection and semantic limits; ADR 0011
records the historical privacy-remediation exception.

## 7. Consumer rules

- Usage events provide denominators; qualitative notes provide explanations.
- Compare capability versions separately from backend versions.
- Do not attribute backend quality to the skill or skill utility to the backend without an
  appropriate comparison.
- Run learned recommendations in shadow mode before allowing them to change routing.
- Preserve deterministic safety and policy gates regardless of learned scores.
