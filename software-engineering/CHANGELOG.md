# Changelog

This changelog records changes to the installable `software-engineering` Agent Skill artifact.

## 0.13.2 — 2026-11-21

- `scripts/reviewers/ocr_usage.py` keeps a ledger of every OCR run from OCR's own session files (time, model, prompt/completion/cache tokens, comments), plus the Codex weekly usage reading when it is fresh; OCR itself does not report plan percentages. Step 7 also says confirmed out-of-scope OCR findings become task records.
- Document role policy accepts `id_prefix_digits: 0` for unnumbered, slug-named roles and makes a role's `index` optional (absent means no registration findings); `document new` and `backfill` derive slug identities for unnumbered roles. The ~/Skills portfolio manifest now treats skill knowledge and reference pages this way (part of task 0144).
- `inspect` no longer crashes on a manifest whose document role declares no index (found by the CLI review before 0.13.2 was pushed).

## 0.13.1 — 2026-11-21

- The open-code-review adapter allowlists only `chatgpt` (the ChatGPT-plan sign-in) by default; API-key providers such as `anthropic`, `openai` and `openrouter` are refused unless a project passes `--allow-provider`. SKILL.md names the approved provider and rules out Claude subscription credentials for OCR (task 0140).
- Step 7 now routes to OCR's own skills, `open-code-review-delegate` (default; host model, no extra egress) and `open-code-review` (native, approved provider), and states where this skill overrides them: no self-installing `ocr`, no silently dropped findings, fixes only within scope.
- Live OCR pilot fixes (five reviews of this release's commits): the adapter accepts ocr's real `complete` status and keeps reviews with omissions partial even when they have findings; the launcher never writes to a predictable temp path and refuses `requires-python` bounds it cannot evaluate; the gate allows when a related transcript is unreadable and ignores markers written by the 0.12 detector; `inspect` and `doctor` tolerate an undecodable or dangling installed copy (tasks 0140, 0102, 0118, 0135).

## 0.13.0 — 2026-11-21

Self-audit release (audit 0014). Fixes first; every item has a regression test that failed before the change.

**Gate and hooks**
- The pre-edit consultation gate counts only structured tool calls (the Skill tool with `software-engineering`, or a Bash call running the engineering CLI). Its own block message, prose and tool results no longer satisfy it. It recognises subagent and parent transcripts, matches extensions case-insensitively (adds `.ipynb`, `.tf`, CI YAML, `Dockerfile.*`), sanitises session ids, and shares one file-class source across all hook dialects. An absent or unreadable transcript now allows (fail-open) instead of blocking (task 0118).
- `install-hooks --apply` writes through symlinked settings files and preserves their mode (task 0131).

**Lifecycle and CLI**
- `start` without `--paths` scopes the run to the whole project instead of guaranteeing a failed `finish`; a failed `finish` can be re-run after fixing the problem; `--project-root` help and errors name the real root (task 0123).
- Exit codes are truthful: internal errors exit 70 (`--debug` shows the traceback) instead of posing as invalid policy (2), baseline incompatibility (5) or a failed check (1); unmapped statuses fail closed (task 0124).
- Human output names each failing check with its exit code and output tail, and prints why `inspect` was unavailable (task 0119).
- `inspect` shows the running skill version and path; `doctor` warns when another installed copy, or `ENGINEERING_SOURCE_ROOT`, has a different version (task 0135).
- A bundled launcher, `scripts/engineering`, now fronts every invocation (and the PATH command, via `assets/cli.json`). It runs `uv run --script` as before. When the uv cache is read-only and uv fails before Python starts, it reuses the newest cached environment whose packages exactly match `engineering.py.lock`; it never creates a temporary cache or installs anything. `ENGINEERING_PYTHON` selects a prepared interpreter explicitly. A command that started is never re-run, and its stderr is always passed through (task 0102; the most-reported friction, 49 of 140 recent notes).
- Bytecode is cached under `$XDG_CACHE_HOME/software-engineering/pycache` (never inside the skill), cutting warm `--help`/`--version` from ~0.76 s to ~0.33 s (task 0134).
- `start` tolerates non-UTF-8 untracked filenames and dirty symlinks that point outside the repository (task 0133).

**Documents**
- `document validate [PATH ...]` validates explicit files, keeps the cross-document findings they take part in, and reports skipped scope (task 0120).
- `document validate` ratchets against `--base REF`, defaulting to the merge base with the default branch, so records broken in committed changes block on a clean checkout or in CI. Inherited findings stay advisory and are counted. Without a discoverable base it reports a strict all-documents fallback (task 0125).
- Non-draft records that still contain declared template placeholders (`owner: OWNER`, unfilled sections, the quality-bar comment) are reported; an open task may keep the completion-evidence placeholder until it claims `done` (task 0126).
- Task states are shared between `query` and `validate`; `superseded` is recognised and a terminal `declined` state requires `details.rationale` (task 0121).
- `document new` keeps backslashes, `$`, `&` and other special characters in titles literally instead of crashing (task 0122), and reserves numeric ids atomically so parallel allocations in one checkout get distinct ids (task 0129).
- Commands run from a nested directory use the nearest ancestor `engineering.yaml` (stopping at the Git root) and report the climb; an empty task glob is a warning instead of a silent zero-task success (task 0136).

**Publication**
- The pre-publication privacy scan covers commit messages and author/committer names, attributes removed-file lines correctly, and applies tracked-path hygiene to every nested skill root (task 0128).

**Review and guidance**
- Step 7 routes agents to open-code-review (`ocr`) as a second reader: `ocr delegate rule` (no model call) by default, a full `ocr review` only with an approved provider passed explicitly. `scripts/reviewers/ocr_adapter.py` records OCR findings in `finish` through the reviewer contract and refuses providers outside its allowlist (task 0140, live verification pending).
- Lighter path for work that ships no code; repository instructions win over this skill's tools; remove-the-dependency and mutation-table testing recipes (task 0139).

**Usage trend since the previous releases** (task 0143): `finish` runs recorded across adopted repositories fell from 49 (Aug) to 13 (Sep), 2 (Oct) and 0 (Nov); 26 of 64 finishes hit the empty-scope trap fixed above. All 140 feedback notes from 2026-09-09 to 2026-11-21 are dispositioned (112 planned, 9 fix candidates, 18 declined, 1 earlier).

## 0.12.0 — 2026-11-19

- A v2 docs project may set `docs_root: .` (equal to its root), so record folders sit directly in `docs/{adr,tasks,...}` instead of a nested `docs/records/`. docs_root must still resolve inside the project root, and project and docs roots still must not overlap.
- `document validate` no longer demands a new `updated` date for a record whose only change is a pure staged rename (git `R100`); the moved file stays in the changed set, so its other findings still block. JSON `changed_paths` gains `rename_only`.
- `documentation-structure` guidance now matches the allocator: every record role is `NNNN-slug.md`, provenance lives in frontmatter `relationships` rather than `adr-`/`audit-`/`task-` filename prefixes or date prefixes, and the one-current-handoff rule names the validator findings that enforce it.

## 0.11.3 — 2026-09-09

- Report document-validation change-set paths, effective date and fallback policy; unavailable discovery exits 3 while retaining findings. Preserve advisory-only success exits and guard run sealing against discovery failures, including nested-project fingerprints (task 0105).
- Route selected practices to observable application evidence and scoped specialist tools, with version-aware documentation fallback and no mechanical-work ceremony (partial task 0111; behavioral evaluation remains unexecuted).
- Calibrate record worthiness and scope-aware decision authority, separating scheduling, implementation and acceptance while preserving project taxonomies (task 0110).
- Clarify conditional launch prerequisites and preserve shared-cache policy in development verification; no temporary-cache fallback or new provisioning mode is introduced (partial task 0102).
- Clarify independent storage, audience, and release-payload judgments; preserve useful public contributor records and scoped private operational records (task 0100).
- Render existing error details and next-command hints in the generic human CLI fallback (task 0103). JSON output, exit codes, and explicitly supplied human output are unchanged.

## 0.11.2 — 2026-09-06

- Prefer a verified PATH launcher; resolve portable fallback scripts from the loaded SKILL.md location without assuming an installation directory.

## 0.11.1 — 2026-09-06

- Declare optional CLI entry points for skill-manager PATH exposure; portable invocation stays available.

## 0.11.0 — 2026-08-23

- **Per-role content-quality standards folded into authoring guidance and role templates (task
  0109, advisory only).** The cross-vendor debate (research 0013) produced a per-role standard for
  what makes the _content_ of each of the 17 document roles good — telos, content-quality
  properties, a discriminating test, and an exemplar/anti-example. Three new knowledge records ship
  that standard, one per role kind:
  - [`documentation-record-content-standards.md`](knowledge/documentation-record-content-standards.md)
    — the seven record roles (task, ADR, audit, research, lesson, handoff, plan).
  - [`documentation-living-content-standards.md`](knowledge/documentation-living-content-standards.md)
    — the eight living roles (specification, knowledge, reference, standard, guide, roadmap,
    changelog, runbook).
  - [`documentation-meta-content-standards.md`](knowledge/documentation-meta-content-standards.md)
    — the two meta-roles (index, template).
    All three route under `documentation-repository-organization` and are linked from the knowledge
    INDEX. The 17 role templates' quality-bar comments now carry a plain-text pointer to the
    matching standard (naming the skill knowledge file and section, not a relative markdown link) as a
    removable authoring prompt — not a gate: a record still allocates and validates after the entire
    comment is removed (covered by a fixture that truly strips the block). No enforcement machinery,
    schema, reviewer, or classifier changed.

## 0.10.1 — 2026-08-19

- **Publication scan: "no dependency manifests" is no longer misreported as scanner failure.**
  When `osv-scanner` is installed but the scanned tree contains no OSV-recognized manifest or
  lockfile, the tool prints `No package sources found` and exits non-zero. `inspect publication`
  previously mapped that non-zero exit to `dependency-vulnerabilities: unavailable` with blocking
  `dependency.scope-*` risks — indistinguishable from a genuine tool/network failure. It now
  classifies the "no package sources" sentinel as `not_applicable` (the same terminal state as a
  zero-package result), so self-contained skills with inline/PEP723 dependencies scan cleanly.

## 0.10.0 — 2026-08-18

- **Agent-scale ticketing and records substrate (ADR 0025, epic 0090).** The
  documentation/ticketing system becomes agent-schedulable — additively and opt-in. All new
  guardrails are **off by default** and activate only when a project sets `agent_scheduling.enabled`
  in its `engineering.yaml`; every existing record and single-project/v1 behavior is unchanged.
  - **Scheduling graph.** Task frontmatter gains optional `depends_on`, `parent`, `touches`, `size`,
    and `priority` fields. `engineering task graph` projects the declared dependency DAG read-only
    (topological order, derived ready-set, waves, cycle/orphan detection) suitable for a generated
    `tasks/README.md`. `engineering task next` gives an advisory, read-only next-ready suggestion
    ordered by `priority`/`size` — it never claims, locks, dispatches, or mutates state (concurrency
    is harness-owned; the CLI makes no mutual-exclusion guarantee).
  - **State predicates.** Optional `in_progress` task state plus a derived predicate layer
    (`is_open`/`is_started`/`is_blocked`/`is_terminal_success`/`is_terminal_noop`/`needs_review`)
    with defaults for existing states; unmapped states resolve to `unknown`, never invalid.
  - **Record lint.** `engineering record lint --mode structure|quality-review` generalizes the
    `done_task_evidence` gate to per-role required-structure/provenance (blocking only under the
    profile) and advisory quality-review prompts (never block).
  - **Advisory task-size gate.** Under the profile, oversize smells (many acceptance criteria; broad
    touched-directory span) warn and prompt vertical-slice decomposition, with an `atomic_large`
    exception (rationale + rollback/verify plan + checkpoints) and per-project-tunable thresholds. It
    never hard-blocks; the decidable invariants (done-without-evidence, dependency cycle,
    acceptance-criterion-without-check) remain enforced by existing mechanisms.
  - **`plan` record role.** A seventh record role (execution-plan / progress log: created-at-start,
    updated-per-checkpoint, closed-at-done) is added to the closed vocabulary, template, and
    profile-gated allocator, with per-role template quality bars documented in
    `knowledge/documentation-structure.md`.

## 0.9.0 — 2026-08-15

- **Multi-project document governance (manifest v2, ADR 0024, task 0089).** One git-root
  `engineering.yaml` can now govern multiple projects' `dev/docs` record populations, not only a
  single project's. A version-dispatched schema adds `docs.currency.projects[]`, each declaring its
  own record-role `include`/`index`, `required_current_truth`, `done_task_evidence`, and
  `task_inventory` (with per-project planning). `document new/backfill/validate/query/currency/index/
graph/trace/explain` gain a `--project <id>` selector and infer the project from
  `--project-root`/path when unambiguous; allocation, validation, currency, query, and the index
  cache are project-scoped and boundary-contained (records bounded by the project's `docs_root`, the
  source register by the workspace root, and global living/meta roles by the repository root). The
  index cache is namespaced per project (`.engineering/projects/<id>/document-index-v1.json`).
  Aggregate verbs (`docs`, `doctor`, `finish`) run one global living/meta pass plus per-project
  record passes, project-tagged and deduped. Relationship targets for the six record roles resolve
  per project (a dangling `task:0002` in one project is not satisfied by another project's record),
  while living/meta identities remain global. **Fully backward-compatible:** a v1 manifest and every
  existing single-project record and behavior are byte-for-byte unchanged, guarded by a v1
  byte-parity golden harness across all eleven document verbs.

## 0.8.1 — 2026-08-15

- **Tier-gate role-specific body validators (follow-up to 0.8.0).** `document validate` now applies
  the task acceptance-criterion checks (`criterion-id-missing`, `criteria-mismatch`) and the research
  source-reconciliation check only at `full` tier, consistent with `required_sections`. Historical
  (core-tier) records no longer need criterion IDs or reconciled sources; new (`contract_tier: full`)
  records keep the strict checks. Closes a gap where core-tier record backfill still reported
  `criterion-id-missing`.

## 0.8.0 — 2026-08-15

- **Tiered record-document compliance (ADR 0023).** `document validate` now distinguishes a `core`
  and `full` compliance tier for record roles via the optional `engineering_document.contract_tier`
  field (absent ⇒ `core`). At `core` tier a record is **not** required to carry the fixed role body
  sections or a reconstructed multi-step transition path. Both tiers still enforce the v2 core, the
  extension identity, the role/state enum, id uniqueness, index registration, legal asserted edges,
  transition connectivity, final-state agreement, dates, and supersession consistency. `document new`
  mints records at `full` tier (the six record templates carry `contract_tier: full`), so new records
  keep the strict standard; living/meta roles are unchanged. This makes the historical-corpus
  compliance sweep (task 0088) non-invasive — records need only core + extension, not body rewrites.

## 0.7.7 — 2026-08-14

Bug-fix batch resolving accumulated skill-feedback (2026-07-28..08-14):

- **`--version` single source.** `engineering --version` and in-process
  `scripts.cli.main(["--version"])` now derive the version from the colocated `SKILL.md` instead of a
  hardcoded `0.1.0` literal in `cli/parser.py`, eliminating version drift.
- **`explain` scalar rendering.** Scalar string fields (e.g. limits) render as a single line instead
  of one character per bullet; genuine multi-entry sequences still render as a list.
- **Portable-invocation cache fallback.** The documented `uv run` invocation selects a writable temp
  `UV_CACHE_DIR` only when the default cache is not writable (the common sandbox first-run failure),
  preserving the normal warm-cache path.
- **`--project-root` honored exactly.** `inspect`, `document`, `start`, and `finish` treat an explicit
  `--project-root` as the exact traversal boundary with no ancestor/git-root substitution via a new
  shared `policy/project_root.py` resolver; a canonical-path difference is reported (`root_resolution`)
  and warned rather than silently promoted.
- **`finish` concurrency & scoping.** An unrelated concurrent HEAD advance is recorded as
  `head_advance=benign` and no longer invalidates a run; only committed changes overlapping the run's
  declared paths are incompatible (`declared_paths`), reported with exact git-diff and
  replacement-run recovery commands. Check/fitness/reviewer/document-validation selection is scoped to
  declared paths, so unrelated pre-existing findings are no longer aggregated.
- **Publication scan scoping.** Active publication/security/privacy traversal is confined to the exact
  root; gitleaks and privacy-history scans run only when the supplied root is itself the Git top level,
  preventing an enclosing-monorepo history scan.
- **Actionable pre-adoption diagnostics.** Missing/invalid manifests and missing
  `docs.currency.roles` now name the exact field and the exact next command; manifest-less
  `document roles` returns the bundled template contracts (`adopted=false`) and `document validate`
  performs bounded read-only Markdown/link checks without creating `.engineering` state.
- **Backfill numeric IDs.** For prefix-configured roles, `document backfill` derives the ID from the
  numeric filename prefix instead of a title slug (failing closed on invalid filenames), and refuses a
  legacy body `- Status:` line that contradicts frontmatter, preserving the byte-preservation contract.

## 0.7.6 — 2026-08-13

- Retargeted the shipped JSON Schema `$id`s to the durable public
  `https://github.com/markov-root/skills/schemas/...` namespace ahead of the skill's first public
  release (previously a non-public placeholder namespace). Identifier-only change: schema shape,
  `$ref` resolution, and validation behavior are unchanged, and all `$id`/`$ref`s remain internally
  consistent. (439 dev tests green.)

## 0.7.5 — 2026-08-09

- Passive `inspect` now flags **manifest-declared concrete paths that do not exist** under the
  project root, closing the gap that let a stale manifest report "valid" while its checks were
  silently unrunnable. `manifest_observation` gained an additive `path_findings` list (each entry:
  `field`, `name`, `path`, `kind`, `reason`) covering `checks.*.cwd`, `fitness[].references`,
  `docs.currency.roles[].index`, and `project.documents`; the human line appends
  "(N declared path(s) missing)" when non-empty. Only concrete fields are checked — glob fields
  (`applies_to`, `include`, `classifiers`, `paths.*`) are never existence-checked, and manifest
  `status` is unchanged (drift is reported, not treated as invalidity). (task 0085)

## 0.7.4 — 2026-08-08

- Corrected `knowledge/agent-skills.md`: it taught the **retired Skill Manager** workflow
  (`skill.toml` manifest, `skill install`/`sync`/`doctor`, a single installer owning both skill
  placement and MCP configuration) as canonical. Rewrote the cross-harness portability section, the
  tool-backed `#1` distribution step, the repository/template layout, the install stanza, the
  `debate` example, and the wiring/meta checklists to the current two-plane model: **Vercel `skills`
  (skills.sh)** places skill folders and **MCPM (mcpm.sh)** provisions MCP servers, with standalone
  CLIs installed via their own package manager. Also framed the PATH adapter as optional convenience
  over the portable skill-relative `uv run --script` invocation. The two surviving
  `skill.toml`/Skill-Manager mentions are explicit "retired — do not use" callouts. The knowledge
  record `version` (a pinned contract field) is unchanged, and the guidance-fitness corpus baseline
  is unchanged (0 blocking, 12 advisory, 92 candidate). Reported as software-engineering friction
  during the `dedup` skill migration.
- `inspect` and `document query` now report **observation-root promotion**. When `--project-root`
  points at a nested workspace with no `engineering.yaml` of its own and the resolved root walks
  upward (e.g. to a monorepo Git root), both commands surface it: a new additive
  `root_resolution` JSON block (`requested`, `resolved`, `promoted`, `requested_has_manifest`) and,
  when promoted, a prominent human line/banner stating the report and tasks belong to the resolved
  root, not the requested directory. This prevents a nested skill being silently treated as adopting
  an enclosing repository's manifest/tasks. No key was removed and behavior at a real project root is
  unchanged. Reported as software-engineering friction during the `dedup` skill migration.

## 0.7.3 — 2026-08-08

- `inspect` and `document query` now reject a `--project-root` that points at an existing regular
  file, with an actionable error naming the parent directory, instead of silently resolving to the
  file's parent and mapping the wider directory. Passing a nested directory within the project still
  resolves upward as before, and a nonexistent path is still rejected. Hardening only in the
  observation path (`discover_observation_root`); the adopted lifecycle (`start`/`finish`/`document`
  authoring) is unchanged.

## 0.7.2 — 2026-08-07

- Added `engineering init [--apply]`, preview-first generation of a starter `engineering.yaml` from
  non-authoritative review candidates (`suggest-manifest`). Preview is the default (byte-for-byte
  golden-covered); `--apply` writes only when absent and never overwrites existing policy; the
  generated manifest is schema-validated before an atomic write, and `core_outcome` is an explicit
  review placeholder rather than an invented approval fact. The `init` surface is no longer reserved.
  (task: 0053, partial — `engineering migrate` remains deferred)

## 0.7.1 — 2026-08-07

- Added `engineering install-hooks --harness claude|codex|opencode [--hook consult|lifecycle]`, an
  opt-in convenience installer that idempotently wires the shipped hook scripts into a harness's
  runtime config. It defaults to a dry-run diff and requires `--apply` to write; merges rather than
  clobbers (JSON `settings.json`, marker-delimited TOML `config.toml`, or a dedicated OpenCode plugin
  file); `--uninstall` removes only its own entries; and a malformed or foreign target is refused
  with no partial write. It never enables a hook by default and never writes outside the named
  harness config. (task: 0082)

## 0.7.0 — 2026-08-06

- Added `scripts/se-lifecycle-hook.sh`, a warn/record-only lifecycle hook (the non-blocking sibling
  of the consult gate). It reminds about `engineering start` on an edit with no active run and about
  `engineering finish` on a session-end with an unfinished run; it always exits 0, never edits files,
  never invokes the CLI (reentrancy-safe), throttles to once per session/kind, and records only
  paths/run-ids locally. Install recipes for Claude Code, Codex, and OpenCode, plus pre-registered
  pilot thresholds and disposition, are in `references/lifecycle-hooks.md`. (task: 0055)

## 0.6.0 — 2026-08-06

- Added `engineering knowledge fitness`, a bounded guidance-quality fitness command over the
  authored knowledge corpus. Deterministic routed-file structure, canonical-ownership, and source
  contracts are reported as blocking; source freshness/due signals are advisory; and normative
  scoping, duplication, and conflict are lexical review candidates. Each finding carries a
  per-finding proof limit, and the command never grades prose truth or emits a universal score.
  Current corpus baseline: 0 blocking, 12 advisory, 92 candidate. (task: 0051)
- Added model-behavior red-team specifications (`routing/guidance-behavior-scenarios.json`) covering
  project-authority-over-house-preference, counterexample refusal of dogmatic design heuristics,
  named omissions, verification-claim honesty, and minimal routing. These are behavior specs with an
  explicit non-evaluation limit and stochastic-limitation note, never a blocking deterministic gate.
  (task: 0051)
- Added versioned minimal-correct routing fixtures (`knowledge-routing-v2.json`) proving that naive
  route-intersection loading is genuinely over-broad and that a smallest-correct selection excludes
  decoys, bound to the production selector and on-disk corpus. (task: 0051)

## 0.5.0 — 2026-08-05

- Added three routed knowledge references: `release-engineering` (release identity, compatibility,
  deprecation, rollout, recovery, and a non-attestation release-record template), `reliability`
  (objectives, capacity, degraded modes, runbook + blameless-but-causal incident-review templates),
  and `build-reproducibility` (repeatable/reproducible/hermetic/verified builds, declared inputs,
  provenance, and evidence boundaries). Tasks 0044, 0045, 0046.
- Recalibrated four references as multi-paradigm decision lenses: `principles` (OO material reframed
  as one lens, coupling/cohesion presented as gradients with counterexamples, added
  information-hiding/change-amplification/locality/type-driven/temporal-coupling/socio-technical
  lenses), `code-review`, `api-design` + `configuration` (first-order rules no longer contradicted by
  later exceptions), and `concurrency` + `error-handling` + `debugging` (execution-model separation,
  evidence-with-provenance, contributing-conditions incident learning). Tasks 0037, 0039, 0040, 0041.
- Registered the external standards these references cite (SLSA, in-toto, SPDX, CycloneDX, SemVer,
  ISO/IEC 25010, several RFCs, OpenAPI, AsyncAPI, Twelve-Factor, Kubernetes, Conventional Comments) in
  `references/SOURCES.md` and wired each file's `sources:` frontmatter; added release, reliability,
  and build-reproducibility owners to the epistemic-contract canonical-ownership table.
- Added `engineering document list` and `document show` over adopted roles, backed by a stale-checked
  generated document index cache that graph and trace projections also reuse. (task: 0071)
- Made research `derived-from -> source:src-*` references reconciled with the research source
  register so traces can walk task to ADR to research to source. (task: 0072)

## 0.4.0 — 2026-08-04

- Added `engineering document backfill PATH`, an atomic in-place v2-core migration for existing
  Markdown. It retains existing metadata and record extensions, preserves body bytes exactly,
  reuses the authoring identity primitives, and requires reviewed role/title/summary inputs for
  documents without frontmatter.
- Broadened the portfolio currency registry to nine living roles in addition to the six record
  roles, while retaining advisory backlog findings under the changed-path ratchet.
- Corrected the backlog arithmetic: 440 historical non-conformant documents comprised 46 partial,
  48 v1, and 346 frontmatter-free documents; the earlier 394 figure omitted the partial class.

## 0.3.0 — 2026-08-04

- Added the schema-version-2 flat queryable document core and a dual reader that preserves legacy
  v1 records. Expanded the closed vocabulary to sixteen roles: six lifecycle-backed records retain
  `engineering_document`, while ten living/meta roles use the flat core only.
- Added ten living/meta templates, upgraded the six record templates to v2, generalized
  `engineering document new` across all sixteen roles, restored the repository's real role paths,
  and added guards against empty role globs or missing role templates.
- Preserved the version-1 graph contract on `RECORD_ROLES`, made `document validate` exit according
  to severity and `ci_blocking`, and added a local changed-path ratchet: changed findings block while
  untouched migration backlog remains advisory. A clean CI checkout still needs the tracked
  merge-base follow-up for true go-forward enforcement.

## 0.2.0 — 2026-08-02

- Added `scripts/se-consult-gate.sh`: a harness-neutral PreToolUse gate that makes consulting this
  skill NON-OPTIONAL before editing code/build files (converts the AGENTS.md "always-on by policy"
  into "always-on by mechanism"). Detects consultation from the session transcript (Skill invocation
  or `engineering.py` run), caches per session, and blocks an un-consulted code edit; fail-open by
  construction (only the positive block path is non-allow). Claude Code (exit 2 + stderr) and Codex
  (`--json` deny) dialects; OpenCode via a plugin. Install recipes: `references/enforcement-hooks.md`.

## 0.1.1 — 2026-08-02

- Relocated to the standardized `software-engineering/public/` artifact with a sibling `dev/`
  factory; installed artifact behavior is unchanged. (adr: portfolio 0001)
- Bundled `THIRD_PARTY_NOTICES.md` inside the artifact so notices ship with the published skill.

## 0.1.0 — 2026-08-01

- Added a self-contained PEP 723 runtime with one resource authority, adjacent lock, explicit
  offline behavior, and direct/copied/symlinked/relocated execution proof. (task: 0077)
- Consolidated typed Markdown validation, authoring, currency, graph, and query behavior under one
  document domain with bounded summary/status projections. (tasks: 0075, 0078)
- Decomposed passive and active repository inspection into a cohesive domain and added fail-closed
  private-path publication hygiene for Agent Skill repositories. (task: 0076)
- Replaced the monolithic dispatcher and duplicate catalog with thin command adapters over one
  typed registry while preserving the accepted public CLI contract. (task: 0074)
- Moved 32 authored best-practice bodies into a strict, selectively routed `knowledge/` corpus with
  a deterministic compact index and no legacy flat catalog. (task: 0080)
- Canonicalized factual provenance as one validated row per unique HTTPS source with explicit
  knowledge ownership, relationship groups, review dates, statuses, and refresh triggers.
- Removed Skill Manager manifests, wrappers, runtime assumptions, and product-named package
  dependencies from the installable artifact. (tasks: 0073, 0077)
