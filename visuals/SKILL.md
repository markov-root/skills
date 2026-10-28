---
name: visuals
description: >-
  Produce slides, posters, figures, diagrams, and charts under a production
  contract. `render` captures a frame manifest in headless Chrome after a
  readiness signal into immutable versions with SHA-256 receipts; `bump`
  derives the next version. Unpublished renders can be probed by version and
  promoted with `publish`. `measure` reports selector-keyed geometry, glyph
  fonts, CSS paint composition, and unknowns. `check` evaluates selected
  advisory measurements and emits a contact sheet plus flagged crops. `probe`
  offers opt-in cold-reader checks at delivery size; `improve` drives bounded
  author-led revision against explicit brief criteria. `validate` separates four
  blocking conditions from advisory findings. `new` scaffolds a bare canvas;
  `index` derives portfolio status; `sources` and `data snapshot` hash-lock
  provenance; `image` delegates generation; `init` adopts a project. No command
  ranks designs. For raster generation use image-generation; for chart design
  use dataviz; for UI review use ux-engineering.
license: Apache-2.0
compatibility: >-
  Requires Python 3.11+ (stdlib only for the dispatcher); `uv` for the
  render-weight commands (`render`, `bump`, `improve`, `image`); Chrome or Chromium for
  the authored-render engine. The `image-generation` skill is an optional
  delegate, capability-detected and never a hard dependency.
metadata:
  version: "0.8.0"
---

# visuals

`visuals` owns the **production envelope** for explanatory graphics — slides,
posters, paper and textbook figures, README diagrams: project config, artifact
store, provenance receipts, deterministic rendering, and the contract layer that
holds them together. It deliberately owns **no opinion about what a graphic
draws**; scaffolds emit contract wiring only, and no command ranks, scores, or
grades a design.

## Status at this version (0.8.0)

Implemented: `bump`, `data`, `doctor`, `image`, `index`, `init`, `new`,
`render`, `publish`, `measure`, `check`, `probe`, `improve`, `sources`, `theme`,
`validate`, plus project-declared named styles and the `knowledge/` layer.
`probe` was exercised on a real reference visual and a public negative control.
`improve` was exercised on a public two-iteration before/after graphic. Both
commands are dry-run by default and dispatch fresh agents only with `--execute`.
The registry (`scripts/cli/registry.py`) exposes exactly what exists.

## Usage

```sh
scripts/visuals init                 # adopt a project: write visuals.toml, nothing else
scripts/visuals new <kind> <slug>    # bare contract wiring; optional --style <name>
scripts/visuals render <slug>        # readiness-signalled render into an immutable version
scripts/visuals render <slug> --unpublished  # keep latest on the prior version
scripts/visuals probe <slug> --version v0.0.2  # inspect that version's delivery previews
scripts/visuals publish <slug> v0.0.2 # verify recorded frames and promote to latest
scripts/visuals improve <slug>        # dry-run: cap, next iteration, call estimate
scripts/visuals improve <slug> --execute  # render and probe one iteration
scripts/visuals bump <slug> minor    # re-render at a derived next version
scripts/visuals validate             # four blocking conditions, advisory findings separately
scripts/visuals check <slug>         # project-selected advisory scene checks and looking ladder
scripts/visuals probe <slug>         # dry-run; --execute dispatches fresh agents and spends quota
scripts/visuals index                # derived portfolio status; never hand-maintained
scripts/visuals sources verify       # re-hash every declared asset; https provenance
scripts/visuals data snapshot <slug> --input ... --limitation ...
scripts/visuals image <slug> --prompt "..."   # dry-run; --execute is the paid call
scripts/visuals theme show <name>    # every resolved token WITH its resolution step
scripts/visuals doctor --json        # per-item readiness verdict
```

## What each command guarantees

`render` waits on an explicit readiness signal rather than a fixed time budget,
so a page that never becomes ready fails loudly naming the frame instead of
silently capturing a half-drawn canvas; the receipt records which path was
taken. `bump` derives the version string from the existing version directories —
it is never hand-supplied and never written in a second place.

When authoring a new visual, put at least one explicit `- Q: … | A: …` pair
under the brief's acceptance heading. Run `improve <slug>` to inspect the
dry-run plan, then `improve <slug> --execute` for one unpublished render and
cold-reader probe. Inspect every frame at full size and the final frame at
delivery size. Compare the output with the brief and the project's style
description, revise the source, and execute the next iteration. The project
sets `[improve].max_iterations` (default 3; 1–10); exhausting it reports
remaining disagreements and unknowns without failing. `--new-run` begins
another capped sequence while retaining earlier evidence. The command never
edits a master, ranks designs, or moves `latest`. Probe agreement is evidence,
not approval. `publish` checks the chosen version's receipt and frame hashes
before moving `latest` after review.

`new` without `--style` emits the same bare files as 0.4.0. A project may add
`[scaffold.<name>]` for a declared `[styles.<name>]`, specifying stylesheet and
script includes, a readiness choice (`ready`, `rendered`, or `none`), a footer
element with attributes, and an existing canvas profile. `new --style <name>`
emits only that declared wiring, resolving project-relative includes from the
new master and preserving web-root-absolute paths. The skill bundles no style
or scaffold wiring and applies no default style.

`validate` separates **exactly four** blocking conditions (content clipped
outside the canvas, a missing or dangling `latest`, an absent receipt, a
malformed output name) from advisory findings, which report and never affect the
exit code; the project chooses which optional advisory checks run, and the report names
the checks that did **not** run so a quiet report is distinguishable from a
narrow one. Adding a fifth blocking condition requires a decision record.

`index` derives portfolio status from the store on disk: per-visual version,
disk-counted frames, content-based staleness (**mtime is never consulted**), and
the consumer join in both directions. Projects may declare `[styles.<name>]`
tables with a prose `description` in `visuals.toml`; a visual may name one with
`style: <name>` in its `BRIEF.md`. Missing style is valid. `validate` reports an
unknown style as an advisory, and `index` shows the declared style in its text
and JSON columns. Styles have no default, inheritance, or bundled definitions.
Where no content baseline exists it says
`unknown` and names what is missing rather than guessing. It is a status view,
not a gate — a completed run exits `0` however many anomalies it reports.

`sources` re-hashes every declared asset against its recorded digest, requires
https provenance rather than prose, keeps the untransformed original of a
transformed asset alongside a description of the transform, and scans SVG assets
for five kinds of active or external content. `data snapshot` records source
identity, upstream URL, byte size, sha256, timestamps, and a **required,
non-waivable** `limitations` array; a re-run over unchanged inputs is
byte-identical apart from timestamps, and a changed upstream digest is reported
rather than silently absorbed.

`image` delegates to the `image-generation` skill and carries no provider
knowledge. It is **dry-run by default** — the paid call is behind `--execute` —
and when the delegate is absent it exits `3` naming every location checked,
never a traceback and never a silent no-op. A generated artifact is
distinguishable from an authored render by its receipt alone.

`theme` resolves a theme through four steps — a project config reference (path
or inline table), the project's `themes/` directory, the user registry
`~/.config/visuals/themes/` (read only, never written), and the bundled
brand-neutral default — and reports every token with the step that supplied it.
Derived CSS and the machine-readable palette are generated from the single token
source. `theme check` validates the chart palette (CIEDE2000 adjacent-pair
distance, WCAG 2.2 contrast) with thresholds cited in `references/SOURCES.md`;
findings are advisory and never block.

`doctor` exits `0` when the authored-render engine can run and `3` when a
required component is absent. It never exits `0` on an unusable environment.

## Knowledge — read when you are producing the graphic, not filing it

The commands above own the envelope. [`knowledge/INDEX.md`](knowledge/INDEX.md)
carries the transferable judgment about making the graphic itself: composition,
staged builds, encoding and legend, annotation, axes and commentary, source
credit, and a release check. **Route through the index; do not read it all.**

Three things about it are load-bearing:

- **Nothing in it is executed or enforced.** No command reads a knowledge file
  at runtime, and no gate implements a rule stated there. A gate that enforced
  one would be a defect to report (ADR 0007).
- **Your project outranks it.** Where a project states a rule, the project wins.
  The knowledge is the default for a project that has not decided and the
  vocabulary for one that is deciding.
- **It ships no colour, typeface, or measurement.** Every rule names its level
  — core, medium, or style — and its authority: either an external standard with
  a row in [`references/SOURCES.md`](references/SOURCES.md), or an _attributed
  example_ recording one named corpus's choice, which binds nobody (ADR 0008).

If you are putting any figure on a graphic, read
[`knowledge/numbers-and-claims.md`](knowledge/numbers-and-claims.md) first.

## Exit-code contract

`0` ok · `1` blocking condition · `2` usage · `3` unavailable. The version is
read from this file's `metadata.version` at runtime and exists nowhere else.
