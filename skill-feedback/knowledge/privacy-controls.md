# Feedback privacy controls

## Contents

1. Conservative defaults
2. Data map
3. Captured event fields and purposes
4. Inspection, export, retention, and deletion
5. Boundaries and remaining policy choices
6. Proposed distributed-user model

## 1. Conservative defaults

- Local filesystem only; no network transport.
- Raw prompts, outputs, note bodies, and full command lines excluded from events.
- Content capture fixed to `false`.
- Automatic collection defaults to `off`; version 3 permits only explicit `manifest_opt_in`.
- Retention policy unset until the owner explicitly chooses bounded days or forever.
- Deletion and retention are plans unless `--apply` is present.
- Likely secrets in structured event fields are rejected before persistence.
- Qualitative observations and disposition notes receive a deterministic local privacy screen before
  CLI persistence. Likely secrets are rejected; likely identifiers require explicit review.
- Central directory mode `0700`; event, lock, configuration, and explicit export files mode `0600`.
- Session IDs stored as keyed HMAC-SHA256 pseudonyms.
- Note locations stored as portable relative references; undeliverable notes use a private outbox.
- Read-only commands do not create locks, change modes, or repair state.

`SKILL_FEEDBACK_HOME` is an explicit location override. Without it, a new Linux installation uses
`${XDG_STATE_HOME:-~/.local/state}/skill-feedback` (with the platform-local application-state
equivalent on macOS and Windows). If the legacy
`~/Skills/exported-data/skill-feedback` directory already exists, Feedback keeps using it so an
upgrade cannot silently split one ledger across two roots.

## 2. Data map

| Store | Contains | Location | Managed deletion |
| --- | --- | --- | --- |
| Qualitative notes | User/agent observation text and Markdown metadata | `<skill-repo>/docs/feedback/*.md` | No; repository owner manages it |
| Pending qualitative notes | Notes whose canonical skill source is read-only or unavailable | `$SKILL_FEEDBACK_HOME/note-outbox/<skill>/docs/feedback/*.md` | No automatic deletion; deliver/triage explicitly |
| Dispositions | Status, rationale, and task/test links | `<skill-repo>/docs/feedback/.status.json` | No; repository owner manages it |
| Delivery dispositions | Relative outbox/source locations, entry/note hashes, delivery time | `<skill-repo>/docs/feedback/.delivery.json` | No; repository owner manages it |
| Event ledger | Structured invocation, outcome, observation reference, and disposition events | `$SKILL_FEEDBACK_HOME/events.jsonl` | Yes |
| Privacy configuration | Content/automation gates, retention mode, and identifier/location policy | `$SKILL_FEEDBACK_HOME/privacy.json` | Direct local configuration |
| Session hash key | Random 32-byte key used only for local session pseudonyms | `$SKILL_FEEDBACK_HOME/session-hash.key` | Delete only if future session joins are no longer needed |
| Event lock | No user data | `$SKILL_FEEDBACK_HOME/.events.lock` | May remain after ledger deletion |
| Note lock | No user data | `$SKILL_FEEDBACK_HOME/.notes.lock` | May remain after note migration |
| Session-key lock | No user data | `$SKILL_FEEDBACK_HOME/.session-key.lock` | May remain after first key creation |
| Explicit exports | A selected copy of ledger events | Operator-selected path | No; operator manages each copy |

The CLI has no third-party processor and makes no network request. Filesystem backups, snapshots,
repository history, and copies made by other programs are outside its deletion boundary.

“Portable relative note location” means an event stores a reference such as
`docs/feedback/2026-07-29.md` together with `skill.name = "debate"`, rather than a user-home path to
that repository. The skill identity resolves the canonical checkout. A note that cannot reach a
writable source is additionally marked `delivery=pending`; its private outbox location is an
implementation detail rather than copied into the event as an absolute machine path.

## 3. Captured event fields and purposes

| Field group | Fields | Purpose |
| --- | --- | --- |
| Contract | `schema_version`, `event_id`, `event_type`, `occurred_at` | Parsing, uniqueness, ordering, and migration |
| Capability | `skill.name`, `skill.version`, `invocation_id` | Attribute results to a capability version and join lifecycle events |
| Runtime context | keyed `session.id`, `session.harness`, `task.class`, `tags` | Diagnose harness/task-specific behavior without storing raw session identity |
| Provenance | `actor.type`, `actor.id`, `source` | Distinguish user, agent, automation, and evaluation evidence |
| Privacy | `content_included`, `redacted` | Make content handling explicit on every event |
| Backend | `router`, `provider`, `model`, `effort` | Separate skill effects from interchangeable intelligence backends |
| Result | `outcome`, duration/cost/token/retry metrics, evidence references | Measure behavior, costs, and acceptance evidence |
| Observation | feedback ID, kind, signal, feature, impact, outcome, note hash/repo-relative path | Join a central event to a repository note without copying its body or machine path |
| Disposition | feedback ID, status, rationale hash, task/issue/commit/test links | Close the improvement loop without copying rationale content |

Unknown facts remain null. Evidence values are references, not automatic file ingestion.

## 4. Inspection, export, retention, and deletion

```bash
# Inspect schema, permissions, content/secret findings, and the automatic-collection gate:
skill-feedback doctor --json
skill-feedback doctor --fix-permissions

# Audit human-readable observations and disposition rationales without returning their prose:
skill-feedback privacy-check
skill-feedback privacy-check debate --json
skill-feedback privacy-check debate --acknowledge ID \
  --note "Reviewed for local storage"       # preview
skill-feedback privacy-check debate --acknowledge ID \
  --note "Reviewed for local storage" --apply

# Export all or a conjunctively filtered subset:
skill-feedback export --skill debate --after 2026-07-01T00:00:00Z
skill-feedback export --session SESSION --out session.jsonl

# Explicitly retain all minimized events:
skill-feedback retention --forever

# Permit commands that execute through Feedback-owned source adapters:
skill-feedback collection --manifest-opt-in

# Disable every automatic wrapper without editing manifests:
skill-feedback collection --off

# Or configure bounded retention; this writes policy and shows a deletion plan:
skill-feedback retention --days 90 --json

# Apply the configured policy explicitly:
skill-feedback retention --apply

# Targeted deletion is also a plan first:
skill-feedback delete --invocation USE_ID --json
skill-feedback delete --invocation USE_ID --apply

# Upgrade legacy raw session IDs and absolute note paths:
skill-feedback doctor --migrate-privacy

# Preview or explicitly apply pending-note promotion:
skill-feedback deliver
skill-feedback deliver debate --apply
```

Selectors are conjunctive across categories and disjunctive within a repeated category. `--before`
is exclusive; `--after` is inclusive. Deletion rewrites the ledger atomically while holding the same
interprocess lock used by appenders.

Shared reads use an existing readable lock when present and otherwise make a
best-effort read; they never manufacture a lock as a side effect. First-use session-key
publication uses its own private lock plus atomic replacement, so concurrent
processes cannot observe different or partially written keys. `doctor` reports
permission drift during ordinary inspection and changes it only with an
explicit repair/migration option.

Delivery copies qualitative content only from the private local outbox to the resolved local
repository. It writes no note content to the event ledger or a network service. `--apply` verifies
the canonical note, disposition, and hashes before pruning the matching outbox blocks.

Retention configuration does not schedule itself. A future timer, cron job, or wrapper must invoke
`retention --apply`; that integration must be independently observable.

Automatic collection remains doubly opt-in: privacy mode plus a command-level Skill Installer
manifest entry. `SKILL_FEEDBACK_DISABLE=1` and `SKILL_FEEDBACK_DISABLE_SKILLS=name,...` are
environment-scoped emergency/diagnostic opt-outs.

## 5. Boundaries and remaining policy choices

- Secret detection recognizes common key/token forms and assignments. It cannot prove a value is
  non-sensitive.
- Qualitative screening recognizes common credential forms and likely identifiers such as email,
  user-home paths, IP addresses, internal hostnames, SSH remotes, URL queries, and explicitly
  labelled contact/person fields. It cannot reliably classify arbitrary proper names or infer when
  otherwise innocuous prose identifies someone. Prefer generalized prose; use
  `--privacy-reviewed` only after a real review.
- Direct manual Markdown edits cannot be screened before the write. `privacy-check` and `doctor`
  detect them afterward.
- A finding is a request for semantic review, not an instruction to delete the matched substring.
  Preserve the capability, behavior, causal condition, and intended fix while generalizing sensitive
  context. Privacy is the narrow exception to raw-note immutability: preserve the stable feedback ID
  and record content-free old/new hash lineage under
  ADR 0011 (allow-semantic-privacy-redaction-with-hash-lineage).
- Historical acknowledgement is stored without changing the observation or lifecycle status. It is
  valid only for the exact scanner version, entry hash, and finding hash. Likely secrets remain
  non-overridable.
- Deleting ledger events does not delete qualitative notes, Git history, previous exports, or
  backups.
- Exporting to stdout may place data in terminal capture or caller logs; prefer an explicit private
  file when that threat matters.
- Session pseudonyms remain stable within this store so events can be joined, but cannot be resolved
  without the local hash key.
- Forever retention increases the consequences of an undetected future sensitive field. Schema
  review, secret screening, doctor checks, and targeted deletion therefore remain required.

## 6. Proposed distributed-user model

The current repository-backed qualitative-note layout is the accepted Feedback v2 behavior for the
owner's maintainer checkout. It is not yet the proposed default for colleagues or public
installations.

ADR 0009 (local-private-and-explicit-decentralized-sharing) preserves a deferred
proposal for local-private,
one-item-per-file qualitative storage for distributed users and a separate, explicit
preview/bundle/submit flow. Sharing would copy a minimized, approved payload and maintain a remote
receipt; it would not move the original note, upload event history, or make a lifecycle disposition.
Task 0011 holds the implementation and verification work. No network transport or automatic sharing
exists today. Task 0011 should be resumed only after the local-owner workflow and its Installer
integration are stable.
