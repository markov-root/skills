# Changelog

## 0.5.0 — 2026-08-16

C2 hardening from an adversarial red-team of 0.4.0 (audit 0020; contract ADR 0019).
Closes two HIGH and four MEDIUM findings in the evidence semantics around closure.
Breaking behavior changes under 0.x, hence MINOR.

- **Breaking — purpose-gated receipt consumption.** A receipt now authorizes only the
  matching transition: `resolved` requires a `resolution` receipt, `preserve` a
  `preservation` receipt, and `reopen` a `resolution` receipt. A wrong-purpose receipt
  is refused exactly like a missing one (previously any passing receipt closed an item).
- **Breaking — `resolved → open` refused via `triage`.** Reopening a resolved item must
  go through `reopen` (which requires a discriminating recurrence and a superseding
  receipt); the ungoverned `triage --status open` path is rejected. This also keeps the
  closeout reopen classification honest.
- **Changed — evidence-bound closeout.** `verified_outflow` counts only closures backed
  by a verified receipt (a resolved with a verified resolution receipt, or a preserve
  with a verified preservation receipt); legacy pre-C2 prose-only resolves are excluded
  and surfaced as `population.legacy_unverified_outflow`. A verified `preserve` now
  counts as verified outflow (fixing a deflated `verified_close_rate` for praised
  skills); `population.verified_resolved` / `verified_preserved` sub-counts added.
- **Fixed — verifier check hardening.** A check resolves only to an existing _regular
  file_ that is not the receipt itself (directories, self-reference, dangling/empty →
  `unverified`). A non-decodable/unreadable receipt now returns a typed
  `invalid verification receipt` (exit 1) instead of a raw traceback. (Binding a check
  to the artifact under verification remains deferred to C4.)
- **New — `doctor` sidecar/ledger reconciliation.** `doctor` flags any feedback whose
  `.status.json` asserts a closed/verified state the authoritative ledger does not back
  (a torn two-phase commit or an out-of-band edit).

## 0.4.0 — 2026-08-16

C2 verified-closure & closeout (SIP 0001 control C2; ADR 0018). Closure now
requires verification evidence, not a prose status flip — includes a breaking
rejection of evidence-free closure (MINOR under 0.x).

- **Breaking — evidence-bound closure.** `triage --status resolved` now requires a
  passing verification receipt via `--receipt-id`; a prose-only resolution is refused
  (`resolution receipt required`) and the item stays actionable. Illegal transitions
  (e.g. `planned→resolved`, `declined→fix_candidate`) are rejected
  (`illegal transition`). Rejection is atomic — no event or projection is written.
- **New — `verify` command.** `verify <skill> <id> --receipt PATH` validates a typed
  receipt (11 required fields; a missing field is a malformed receipt → exit 1) and
  records a `verification.recorded` event. It classifies verified/unverified WITHOUT
  executing the declared check (it resolves the check path and honors the recorded
  result), so the verifier carries no code-execution surface. A well-formed but
  unverifiable check (missing/misspelled/unrun/stale/failed) → `unverified` at exit 0.
- **New — `reopen` command.** `reopen <skill> <id> --recurrence <rid> --receipt-id
<rid>` returns a verified item to `open` (lifecycle_state=reopened), preserving the
  superseded receipt and recording the triggering recurrence; reopen is never
  inferred from text.
- **New — `closeout` command.** `closeout --skill <skill>` reports inflow, historical
  verified outflow, verified-close rate, reopen rate, oldest-open age,
  time-to-verification (count + median), and disjoint open/reopened id sets.
- **Breaking — preservation stats.** The insecure truthy-link `preserved_with_test`
  guard is removed; `stats` preservation now reports `declared_with_test` (a declared
  but unverified guard) and `verified_with_test` (a passing preservation receipt).
- **Idempotent/concurrent closure.** `triage --idempotency-key` dedupes a keyed
  transition to exactly one ledger event under concurrent resolution.

## 0.3.0 — 2026-08-15

C1 sealed-read & trust-boundary (SIP 0001 control C1; ADR 0017). Security-hardening
release — includes breaking read/privacy-contract changes (MINOR under 0.x).

- **Breaking — metadata-only reads.** `list` and `review` (text and JSON) now emit a
  body-free metadata view; note bodies and other free-text fields (`text`, `tags`,
  `links`, `resolution`, `privacy_review`) are omitted from the default agent-read
  path. Body access is only via an explicit, isolated `--body`/`--text` path that
  returns an opaque handle redeemable solely through a sandboxed inspection provider.
- **Breaking — operator-capability privacy review.** Record-time `--privacy-reviewed`
  no longer attests review (it is a deprecated, non-authorizing storage-admission
  input); agents/automation and CLI-string identities can no longer self-acknowledge.
  Review is a sealed `privacy.review.acknowledged` event bound to
  `(entry_sha256, findings_sha256, scanner_version)` and a one-use operator capability;
  the CLI fails closed when no capability is available.
- **Ledger-authoritative provenance.** The append-only event ledger is the sole
  authority; Markdown headers and `.status.json`/`.delivery.json` are reconciled
  projections. Any divergence is a blocking, content-free `doctor` integrity conflict.
- **Origin-authentic delivery.** `deliver` promotes only origin-verified, exact
  preauthorized bytes after a current privacy re-screen, with a TOCTOU reclose;
  tampered/missing/duplicate-origin records are blocked without a destination write.
- **Observable retention.** `retention --apply` now emits a content-free
  `observation.tombstoned` successor event (prior event id + note digest + corpus
  version) instead of silently truncating the ledger.
- **Internals.** The 4,458-line executable is now a thin shim over a stdlib-only
  `skill_feedback/` package (`model`/`storage`/`privacy`/`inventory`/`read_model`/
  `commands`) with an AST-enforced import boundary. (tasks: 0021; ADR 0017)

## 0.2.0 — 2026-08-02

- Remove retired adapter-publishing guidance from SKILL.md and onboarding output; adapters are now
  committed beside the skill in `scripts/` and installed by skills.sh as ordinary executables.

## 0.1.1 — 2026-08-02

- Resolve skill inventory from installed skills.sh dirs / `SKILLS_HOME/<name>/public` instead of the
  retired Skill Manager; honor an explicit Manager only when `SKILL_MANAGER_COMMAND` is set. Map
  feedback landing to the B-workspace `dev/docs/feedback` and read `public/SKILL.md` names. (task: 0018)

## 0.1.0 — 2026-08-02

- Relocate into the canonical Skills monorepo B-workspace (`Skill-Feedback/skill-feedback/`
  artifact + `Skill-Feedback/dev/` factory); no behavior change. (task: monorepo-relocation)
