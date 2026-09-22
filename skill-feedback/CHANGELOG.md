# Changelog

## 0.8.1 — 2026-09-06

- Declare the optional skill-feedback PATH command for Manager ownership and document verified PATH preference with a location-independent bundled fallback.


## 0.8.0 — 2026-08-25

C5 prospective evaluation and readiness control. Adds the evidence contracts needed to evaluate a
candidate policy without turning incomplete historical data into causal claims.

- **New — prospective decision and outcome records.** `decision.logged` freezes the candidate set,
  eligibility, assignment mechanism, propensity, policy identity, and pre-action stratum before a
  choice; `decision.outcome` attaches a later observed result without backfilling policy context.
- **New — computable readiness and bounded acquisition.** `readiness` reports explicit gates for
  decision logging, assignment overlap, and outcome coverage. An insufficient gate links an owned,
  budgeted acquisition task instead of waiting indefinitely.
- **New — immutable as-of evaluation.** `evaluate --as-of` produces a versioned manifest with a
  stable ledger digest; pinned manifests cannot be silently overwritten, and later data creates a
  new version.
- **New — estimator safety gates.** Unsupported propensity, overlap, outcome, temporal, integrity,
  or censoring conditions force abstention and prediction-audit output. Causal claims are emitted
  only when the predeclared estimator's requirements pass.
- **New — frozen decision profiles.** Task-specific hard constraints, a primary comparison rule,
  secondary thresholds, abstention, Pareto and sensitivity reporting, and a named human tie-break
  replace universal weighted scores and post-hoc promotion rules.
- **Changed — retention and integrity reconciliation.** Content-free tombstones distinguish
  post-deletion censoring from original missingness, invalidate affected evaluation populations,
  and exclude origin-conflicted or unverified records.
- **New — authorized pilot dry-runs.** Maintainer-approved pilot records capture population,
  exclusions, assignment, budget, monitoring, stopping, ownership, kill switch, rollback, and the
  analysis plan before assignment. Seeded dry-runs verify mechanics without counting as evidence.
- **New — learner-acquisition artifacts.** Readiness always emits owned plans for the separately
  gated 0007 label corpus and 0008 decision/overlap evidence. Both learner statuses remain blocked;
  producing a plan authorizes acquisition work only.

## 0.7.0 — 2026-08-22

C4 honest evidence classes (SIP 0001 control C4; task 0024; ADR 0021). Makes aggregation
honest about _where evidence came from_ so an acting agent's own praise can never drive a
score, a deterministic process check is never relabelled as user preference, a fabricated
evidence reference cannot manufacture strength, and privacy-correlated label loss is
surfaced rather than pooled away. Adds fields and a verifier binding, hence MINOR under 0.x.

- **New — typed evidence verification at record time.** Each `--evidence` reference is
  resolved when recorded (`test:` filesystem+AST with no import/exec, `invocation:` ledger
  cardinality, `commit:` git object db; `task:`/`user:` declared-but-conservative; untyped
  → unverified) into a content-free `{reference, type, result, resolver_version}` receipt.
  No artifact bytes are ever stored.
- **New — source-stratified, eligibility-gated `stats`.** Each group exposes
  `source_distribution` (raw per-source counts + rate + per-source eligible + `classified_as`),
  `eligible_aggregates` (preservation / recommendation / user_preference / outcome /
  failure_prediction), and `evidence_verification` tallies. A versioned source-tier matrix
  decides eligibility: `agent_judgment`/`automation` are raw-only and never score; an
  observation scores only with an eligible source tier AND a verified evidence receipt AND
  the use-case condition. Raw counts stay visibly distinct from eligible counts, in JSON and
  in a human source-stratified block.
- **New — non-ignorable privacy missingness.** `privacy_missingness` reports per task-class
  label coverage from content-free screening-outcome / label-available fields; a stratum
  below coverage abstains and never borrows a better-observed stratum's result.
- **Changed — verifier artifact-binding (closes the C2 R3-1 residual).** `verify` records a
  `check_digest` and an `artifact_binding` (`bound`/`unbound`/`conflicting`): a receipt that
  pins `artifact_digest` is bound iff it matches the check's current content, conflicting on
  mismatch (which downgrades to unverified). Legacy receipts stay verified but `unbound`.
  `closeout` adds `verified_and_bound_outflow` — the artifact-attested subset. **Residual:**
  digest binding cannot prove the check exercises the artifact without executing it (which
  the verifier deliberately never does); the bound metric is advisory, not proof.

## 0.6.0 — 2026-08-22

C3 representative capture (SIP 0001 control C3; task 0023; ADR 0020). Makes captured
feedback representative — a trustworthy denominator and an honest use↔feedback join —
instead of a missing-not-at-random pile of notes. Adds fields and changes default
`stats` output (suppression), hence MINOR under 0.x.

- **New — activation receipts.** Content-free `activation.receipt` (capture mechanism +
  decision episode) and `activation.closeout` (`feedback_id` / `no_noteworthy_feedback`
  / `aborted` / `unable_to_report`) event types record every skill consultation,
  including pure-text ones, without prompts, outputs, or note bodies.
- **Changed — explicit-handle-only linkage.** An observation links to an invocation
  only when `--invocation` resolves to exactly one `invocation.started`; an absent,
  invalid, or ambiguous handle stays unlinked with a visible diagnostic. Linkage is
  never inferred from proximity, name, or active-invocation count.
- **New — honest units.** `stats` reports `capability_executions`,
  `decision_episodes`, and `executions_per_episode`; process outcomes are never
  treated as task reward.
- **Changed — comparison-readiness gate.** Per-use `rates_per_100_uses` and
  cross-skill ordering are **suppressed** unless a group meets the versioned
  activation- and link-coverage policy; each group reports `comparison_readiness`
  with its failed dimensions. `stats --allow-partial-descriptive` emits a labelled
  `non_comparable` view instead.
- **New — representativeness strata.** Per group `observation_link_rate`,
  `observations.linked_to_invocation`, and a `capture_mechanisms` stratum
  (`automatic` / `manual-start` / `note-only` / `unknown`); top-level
  `activation_receipts` completion vs MNAR dropout by harness and closeout.
- Rollout is advisory-first: closeout is recorded, never a blocking gate. Binding the
  verification check to the artifact (the C2 D4 residual) remains C4's job.

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
