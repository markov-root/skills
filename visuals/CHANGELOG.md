# Changelog

## 0.5.0 — 2026-10-28

- **New `knowledge/` layer (task 0018), discharging the obligation ADR 0002 created and ADR 0007
  unblocked.** Eight routed files — numbers and claims, composition, progressive builds, encoding
  and colour, annotation, axes and commentary, source credit, release check — carrying the
  transferable judgment the skill previously had none of. At 0.4.0 the skill had eleven commands and
  no answer to "how should this graphic be made"; the bare scaffold was 38 lines against a reference
  master of 1,062.
  **Nothing in it is executed, and no gate implements it** (ADR 0007 rule 2): the blocking set is
  still exactly the four ADR 0004 conditions, the advisory set is unchanged, and no command reads a
  knowledge file at runtime. **It ships no colour, typeface, or measurement** (ADR 0008 §2) — every
  rule names its level (core / medium / style) and its authority, which is either a row in
  `references/SOURCES.md` or an explicitly-marked _attributed example_ recording one named corpus's
  choice and binding nobody. `SOURCES.md` gains rows for WCAG 2.2 SC 1.4.1 and for the Creative
  Commons BY 4.0 licence's §3(a)(1) attribution conditions, both verified against the primary text.
- **New named styles (task 0019), implementing ADR 0008's style level.** A project declares
  `[styles.<name>]` tables carrying a prose description in `visuals.toml`; a visual names at most one
  with a `style:` line in its `BRIEF.md`, reusing the seam the scaffold already writes rather than
  adding a per-visual config file. An unknown style is an **advisory** finding naming the declared
  styles — the blocking set stays at four — and `index` gains a style column in both text and JSON.
  **Four non-goals, each with a guard test**: no inheritance, no resolution ladder, no bundled
  styles, no default style. Applied to the reference corpus, four declared families (line-chart,
  matrix, fact-slide, compositional) cover all 30 masters with zero style advisories, and the audit
  tool resolves all eleven of the mining report's practice-versus-standard contradictions into
  5 style-scope errors, 3 belonging at medium or core level, and 3 genuine disagreements that remain
  the portfolio owner's decision.
- **`new` can scaffold to a project's declared system (task 0021), implementing ADR 0007 rule 4.**
  A project may declare `[scaffold.<style>]` for a style it also declares, carrying stylesheet and
  script `includes`, a `readiness` choice (`ready`, `rendered`, `none`), a `footer` element with
  attributes, and an existing `canvas` profile. `new --style <name>` emits exactly that wiring —
  web-root-absolute includes preserved, project-relative ones resolved to the new master's depth —
  so a new graphic starts connected to its project's visual system instead of to a bare canvas.
  **The skill bundles no style, include, readiness value, or footer**, and `new` with no `--style`
  emits output **byte-identical to 0.4.0's**, guarded by a committed fixture test rather than by
  review — ADR 0007 names rule 4 as the one most likely to erode, so erosion now fails a check.
  A `--style` naming an undeclared style is a usage error listing what is declared, never a silent
  fall back to bare. Verified end to end on a scratch copy of the reference corpus: the scaffolded
  master rendered through the **readiness-signal** path with no unresolvable-reference warning and
  no hand-editing.
- **`init` discovery fixes (task 0020).** `init` now emits `web_root` when a master carries a
  root-absolute asset reference that does not resolve under the project root, and names which
  reference drove the choice — previously the first render after adopting a corpus that references a
  repository-root asset produced a degraded frame, and the operator had to already know about a key
  `init` never mentioned. Contract paths that discovery did not find are written and reported as
  explicitly unfound rather than silently inheriting the neutral scaffold's placeholders. `validate`
  prints `source-registry entries: not checked` instead of a measured-looking `0` when the
  `source-registry` advisory check did not run.
  Verified end to end: on a scratch copy of the reference corpus, `init` followed by `render` with
  **no hand-editing** reproduces a visual's five frames byte-identically to its committed version.

## 0.4.0 — 2026-09-23

- New `sources` and `data snapshot` commands (task 0008): attribution and dataset provenance.
  `sources` re-hashes every declared asset against its recorded digest, requires https provenance
  rather than prose, keeps the untransformed original of a transformed asset with a description of
  the transform, and scans SVG assets for five distinguishable kinds of active or external content.
  `add` computes digests itself and never accepts one from the caller, and writes nothing when the
  entry it was asked to add does not meet the contract. `data snapshot` records source identity,
  upstream URL, byte size, sha256, both timestamps, what the dataset measures, and a **required,
  non-waivable** `limitations` array — the corpus records limitations in 7 of 25 visuals (audit F9)
  and this makes the best-practised case the only case. A re-run over unchanged inputs is
  byte-identical apart from timestamps; a changed upstream digest is reported prominently rather
  than silently absorbed. Against the reference corpus, `sources verify` reproduces the audit F2
  prose-provenance finding, and `data snapshot` reproduces the corpus's own hand-written sha256 and
  byte count exactly. The source-registry contract now lives in one place with two consumers:
  `validate`'s advisory layer delegates to it rather than keeping a second copy.
- New `index` command (task 0009): portfolio status derived from the store on disk, replacing the
  hand-maintained status prose the corpus keeps in `VISUALS-BRIEF.md` and a 38 KB `HANDOFF.md`
  (audit F5, F6). One row per visual including nested families, with current version, disk-counted
  frames, content-based staleness, per-visual finding counts, and the consumer join in **both**
  directions. **Staleness never consults mtime**: it compares theme token digests, git-anchored
  input content, and per-frame artifact hashes, and where no baseline exists it reports `unknown`
  and names every missing instrument rather than guessing. Anomalies are rows with named causes and
  a completed run exits 0 — a status view, not a gate (ADR 0004), with a drift-guard test asserting
  no score, rank, or grade key can ever appear in the output.
- New `image` command (task 0014): the generative delegate. Carries no provider knowledge and
  delegates to the `image-generation` skill (ADR 0006), which is capability-detected and never a
  hard dependency — when absent the command exits 3 naming every location checked, never a
  traceback and never a silent no-op. **Dry-run by default**; the paid call is behind `--execute`.
  A generated artifact enters the same immutable store as an authored render and is distinguishable
  from one by its receipt alone, with no measurement vocabulary applied to a stochastic engine
  (ADR 0003). Delegate detection constants now live in one module shared with `doctor`.
- Fixed: a uv-backend command (`render`, `bump`, `image`) printed a raw `FileNotFoundError`
  traceback when `uv` itself was absent from PATH. An absent prerequisite is now exit 3 with a named
  cause, which is the contract `doctor` exists to report. Latent since 0.2.0.
- Fixed: `SKILL.md`'s body still claimed only `doctor` and `theme` were implemented, three commands
  and two releases after that stopped being true.

## 0.3.0 — 2026-09-23

- New `validate` command (task 0007): exactly four blocking conditions, guarded by a test that
  enumerates the blocking set and fails if its size changes — the drift guard for ADR 0004.
  Project-selected advisory checks that never affect the exit code, and which reports the checks it
  did **not** run, so a quiet report is distinguishable from a narrow one. Source-registry re-hashing
  with https-provenance and SVG active-content scanning; both-direction consumer-manifest
  reconciliation; every finding names what would make it pass. Against the reference corpus it
  reports a classified superset of that corpus's own validator — all 17 of its HTML errors plus 6
  masters its single-level glob never reached (audit F2, F6).
- New `new` command (task 0006): opinion-free scaffolding. Contract wiring at the correct relative
  depth including nested families (the corpus hardcodes `../../`, audit F2/F6), a form-not-example
  `BRIEF.md`, a project shared stylesheet derived once from the single token source and never
  rewritten, and a `--force` that fills only absent files and never overwrites. The rendered scaffold
  is a bare canvas with a source-credit band and one identifying string: two scaffolds of different
  kinds are byte-identical apart from the selected canvas profile (ADR 0004, audit F8).
- Fixed: the `init` scaffold emitted `theme = "default"`, a name resolving nowhere, so a fresh
  init-only project could not be scaffolded. It now names the bundled `neutral` theme, and a test
  asserts the scaffold's theme reference actually resolves.

## 0.2.0 — 2026-09-23

- New `render` and `bump` commands (task 0005): readiness-signalled authored
  rendering into immutable versioned output — per-frame SHA-256 receipts,
  automatic 640px previews and contact sheet, `latest` repointed only after
  every frame succeeds, two-pass determinism check. A page that implements the
  readiness signal but never fires it fails loudly and names the frame, rather
  than silently capturing a half-rendered page on a timeout; the receipt records
  which path was taken. `bump patch|minor|major` derives the version from the
  existing directories — it is never hand-supplied (audit F5).
- New `init` command (task 0003): adopt a project by writing `visuals.toml`
  (canvas profiles, contract paths, pre-render hooks) and nothing else. Geometry
  and contract only — no key may express a colour, type scale, or layout
  (ADR 0004). Verified against the reference corpus: 1702 files checksummed
  before and after, zero modified.
- New `theme` command (task 0004): four-step theme resolution per ADR 0005 with
  per-token resolution-step reporting; bundled brand-neutral default theme;
  derived CSS block and machine-readable palette generated from the single
  token source; `theme check` — independent palette validator (CIEDE2000
  adjacent-pair distance, WCAG 2.2 contrast), advisory and never blocking
  (ADR 0004). Threshold provenance in `references/SOURCES.md`.

## 0.1.1 — 2026-09-22

- `doctor` also capability-detects the `image-generation` delegate as a PATH command; uv re-exec routing proven by fixture test. (task 0002 follow-up)

## 0.1.0 — 2026-09-19

- First release: `visuals` CLI skeleton — single static command registry, weight-routed dispatcher, working `doctor` with per-item readiness verdicts (task 0002).
