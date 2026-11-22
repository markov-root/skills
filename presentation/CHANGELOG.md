# Changelog

## 0.8.0 — 2026-11-22

Tasks 0024 and 0025, and the Japan pilot closed (tasks 0013, 0014).

### References (task 0024)

- Canonical references (portfolio ADR 0006 as amended; research ADR 0008 decision 5): the CLI
  parses and emits `literature:<ref>[@vN]` and `dataset:<id>[@<release>][.<table>][#<key>]`.
  The aliases `research:`, `lit:` (literature) and `data:` plus the old `/table` separator
  (dataset) are still read and are never emitted; `claims pin` writes canonical text; old receipts
  and snapshots read unchanged. Datasets resolve through the unified `research` CLI
  (`research dataset …`), falling back to a standalone `datasets` binary only when `research` is
  absent — until now a missing `datasets` binary degraded every `dataset:` reference to
  `capability_unavailable`. `present doctor` reports which backend serves the dataset surface.

### The takeaway rail is a choice (task 0025; components 1.5.0)

- The takeaway side rail is a per-slide choice, not a template (lesson 0008):
  `knowledge/deck-standard.md` states the rail-is-a-choice rule with its boundary — the rail only
  when it carries content the main area lacks; tables, lists and full-width diagrams take the full
  width; a one-line takeaway goes in the title or a line under the content; step slides keep a
  case panel that holds data. No knowledge file requires a side panel on every slide.
- Chart slides gain the rail-less full-width variant: `takeaway_below: true` (with no `rail`) on
  `chart_slide` / any chart component drops the panel and divider, spans the visual across the
  full content width, and puts the takeaway in a line under the content (or in the title, when
  `takeaway` is omitted). Schema key documented; gallery entry `chart-xy-wide`; slides that pass
  a `rail` are pixel-identical in geometry (proven by shape-level test).

## 0.7.2 — 2026-11-21

- New `knowledge/visuals.md`: how `presentation` and `visuals` work together, when a drawn visual is
  warranted (native first), the `present visual new|render|publish|show` path, deck pins and
  `@visual:` placement, versions, reuse through `library/`, and which skill checks what.
- Changelogs and a code comment name talks generically instead of naming specific talks.

## Unreleased (pilot, task 0013)

- Components 1.1.0 (additive; every 1.0.0 gallery slide unchanged): two presenters and a kicker
  on `title_slide`; one-row contents on `section_divider`; `portrait_img` on `quote_slide`;
  `legend` and speech `bubbles` on `agent_grid`; uncertainty `band` series on `chart_xy`.
  Contents labels shrink to fit instead of breaking a word.
- Components 1.2.0 (the maintainer's review of the pilot deck (v2.0.0); visible on every framed
  slide): compact one-line footers with full references in the speaker notes; the mark back in
  the left column with an `n / N` counter; section kickers above titles; a constant 0.32 in
  clearance above the footer; white label grounds; larger quote portraits and logos;
  `section_divider` `descriptions`. `knowledge/deck-standard.md` states the rules.
- `validate`: a version whose live input (the brand token file) changed after it was built gets
  `receipt_pin_since_changed` (info), not `receipt_pin_changed` (blocking): a token bump no
  longer fails every older deck version. Receipt-to-receipt pins stay blocking.
- `deck build` warns `content_into_footer_clearance` for any shape that ends below the content
  bottom (advisory; found by the pilot's builders, who each wrote their own bounds script).
- `deck build --dry-run --out DIR` keeps a preview (pptx, PDF, contact sheet, full-size page
  PNGs) outside the repository; before, a dry run could not be looked at.

## 0.7.1 — 2026-11-20

- Deck data snapshots accept both datasets exit conventions for an incomplete page: a
  `datasets select` that exits 8 (contract 0.4) or exits 0 with `meta.complete: false`
  (contract 0.5, research-datasets ADR 0008) is refused as `data_too_large`, so a truncated
  table is never snapshotted as if whole.

## 0.7.0 — 2026-11-11

- Visuals integration (task 0009): `present visual new|render|publish|show` delegate to the
  visuals CLI from `<talk>/visuals/`; `deck.yaml` `visuals:` pins (local or cross-talk) resolve to
  exact versions in the receipt; `@visual:<key>[/<frame>]` places a frame; approval refuses
  unpublished visuals; the visuals theme is generated from the token roles.
- Repository library (task 0019): `library list|show|bump|promote`; `use:` / `library:` pins
  resolved to exact versions; `library-item` schema with `retired`/`derived_from`; validate
  reports `library_pin_retired`, `library_pin_unresolved` (blocking) and `library_unused`.
- The improvement loop (task 0020): `present lesson new|route|list`, lessons in
  `<talk>/docs/lessons/` routed once to their owner through skill-feedback or as a consumer task;
  `talk status` shows open lessons; `knowledge/feedback-loop.md`.
- Per-leaf feedback (task 0021): a content-free event naming the command that ran, tagged
  `present-leaf`; `doctor` reports the adapter and collection state.
- Typed references (task 0022): `research:`/`dataset:` sources resolved by `claims check`
  (`source_unresolved`, `source_newer_available`); `present claims pin`; `dataset:` deck data
  snapshotted into `src/data/` with release and sha256, so rebuilds need no datasets CLI.

## 0.6.1 — 2026-11-10

- Fix: derived monochrome logos were cached inside the consumer's `logos/navy/` folder, so a
  gallery or build left untracked files in the repository. They now go only to the per-user cache
  (`~/.cache/present/logos/<token-hash>/`).

## 0.6.0 — 2026-11-10

- Component library 1.0.0 behind brand tokens: 17 declarable components with argument schemas,
  colours by semantic role (tokens `roles`), a neutral token set. (task 0015)
- `present components gallery|diff`: rendered gallery, per-component pixel diff with crops,
  deterministic renders, a release fingerprint check. (task 0016)
- `present deck new|import|build|approve|show|check`: pinned script and tokens in receipts, notes
  from the resolved script version, PDF and contact sheet, external imports. (task 0008)
- Declarative decks: `slides.yaml` with `@role`/`@data:`/`@date:` values, overlays, `reveal`,
  `custom.py` and `build.py` escape hatches, validation that names the slide and field. (task 0017)

## 0.5.1 — 2026-11-10

- `scripts/present` is now a `skill-feedback` adapter (portfolio ADR 0006): every invocation
  records a content-free start/finish event when collection is enabled. The real launcher moved
  to `scripts/cli/present`; the public name is unchanged. `SKILL_FEEDBACK_DISABLE=1` bypasses it.

## 0.5.0 — 2026-11-10

- The knowledge layer: `knowledge/` (protocol, artifact contract, script format, script standard,
  claims, deck standard, components) consolidating the scattered conventions, briefs and agent
  memory into one brand-neutral copy; `SKILL.md` rewritten as the router;
  `references/SOURCES.md`. (task 0012)

## 0.4.0 — 2026-11-10

- `present validate`: the standard-1 contract (layout, schemas, receipts, latest, approvals,
  spoken-words-only scripts, claims gate, one current handoff, absolute paths, symlink loops) and
  loose legacy checks scoped to files changed since a talk was listed. (task 0010)
- `present delivery record|list`: immutable records of what latest was, with approval state and
  receipt digests; `--materialize` outside the repository. (task 0011)

## 0.3.0 — 2026-11-10

- Stand-off annotations: TextQuoteSelector-style resolution (exact, then normalised, with
  prefix/suffix disambiguation), ambiguity and orphan reporting with deterministic re-anchor
  suggestions; `present script annotate`. (task 0018)
- The advisory claims check: a tolerant ledger parser that reports every row it cannot read by
  line, number/quotation/name detectors measured on a real script, high/medium/low concerns,
  licensed spans, `blocking_tiers`; `present claims check|list`, with `--ledger`/`--script` for
  legacy files. (task 0006)
- The script kind: `present script new|check|bump|show|approve`; versions hold `script.md`,
  `speaking.md`, `notes.md` and resolved annotations; approval records concern counts; writing's
  `revoice_check.py` runs as the preservation layer when installed. (task 0007)

## 0.2.0 — 2026-11-10

- `present talk new|list|status|readme`: scaffold a standard-1 talk (staged, renamed into place,
  never overwriting; records allocated through `engineering` when installed), list talks with
  legacy and unclassified folders, flag past talks with no delivery record, and regenerate marked
  README blocks. (task 0004)
- The artifact store: immutable `vX.Y.Z/` versions with SHA-256 receipts, `latest` moved by
  atomic rename, an `.incomplete` crash marker, guards (including the `m2-design` loop), verify,
  and approvals bound to the receipt digest. (task 0005)

## 0.1.0 — 2026-11-10

- First artifact: JSON Schemas for the presentation standard, the `present` launcher with the
  command-result envelope, `doctor`, `explain` and `schema list|check`; the remaining command surface is declared
  and exits 3. (tasks 0002, 0003)
