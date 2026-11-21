# Components, brand tokens, and when to go custom

## One library, every deck

Decks are assembled from the skill's component library: native charts, quote slides, timelines,
chains, comparisons, numbered cards, statistics in context, contents and section dividers, source
footers, and the rest.

- **The authoritative catalogue is the gallery,** not this file: `present components gallery`
  renders one slide per component and variant. Each component has a JSON Schema for its
  arguments, and `slides.yaml` is validated against it before anything renders.
- **One component per slide type.** Every chart slide uses the chart component, every quote the
  quote component, and so on, so similar items look identical in every deck.
- **Extend the library generically.** When a deck needs something the library lacks, add a
  general component (with a schema and a gallery entry) rather than drawing it inside one deck.

## What the library offers beyond the obvious (1.1.0–1.2.0)

- Single-module talks: `title_slide` with `speakers` and a `kicker`; one-row contents
  (`section_divider` without `parts`, with `descriptions`), re-shown before each section.
- `quote_slide`: `portrait_img` for a person (a photograph, credited in the footer), `org_logo`
  for an organisation.
- `agent_grid`: `legend`, and speech `bubbles` pointing at one agent's square.
- `chart_xy`: `band` series for uncertainty fans (±1σ/±2σ), drawn behind the lines.
- Preview before a version: `present deck build --dry-run --out <dir>` (full-size page PNGs).
- Known gaps (filed): date axes with `major=365.25` can label a year twice (start `lo` on the 2nd
  of January); `rail` blocks do not stop at the content bottom; `callout` width is estimated.

## Brand comes only from tokens

The library holds no colour, font, size or logo of its own. It reads them from the repository's
token file (`presentations.toml` `[brand] tokens`), which follows the `tokens` schema:

- `color.*`: ink, accent, context tints, grounds;
- `font.*`: display and body families, with their font files;
- `size.*`: type and spacing values;
- `logo.*`: logo roles mapped to files.

Without a token file, the skill's neutral defaults apply. A deck's receipt records the token
file's version and hash, so an old deck rebuilds with the brand it was built under. Changing a
brand value means editing the token file and bumping its version. It never means editing a
component. `[enforced: the component library's static check — no literals]`

The visuals theme (CSS custom properties) is generated from the same token file, so charts drawn
as HTML visuals and native slides share one palette.

## Declarative decks and the escape hatch

`src/slides.yaml` is an ordered list:

```yaml
- id: firefox-fixes                 # = the script heading
  component: chart_bar
  with: { data: data/fixes.csv, title: "…", source: C-12 }
  builds: [base, highlight]         # progressive reveal as duplicated slides
- id: org-intro
  use: library/slides/org-intro@latest
- id: one-off-diagram
  component: custom                 # escape hatch → src/custom.py
```

- **Quote text values, or use block style.** An unquoted comma inside a flow mapping
  (`with: { title: Fixes, by month }`) silently truncates the text, and no schema can catch it.
- `component: custom` dispatches to `src/custom.py`, and `present deck check` reports every use.
- **Promote a custom slide** into a library component when it is used in a second deck, or when
  a second slide in the same deck needs the same drawing. Promote it into the repository library
  (`library/slides/`) instead when it is a whole recurring slide (an organisation introduction, a
  recurring chart) rather than a reusable drawing; library slides are declarative, so express it
  with components first.

## Reuse without forking

Recurring slides and visuals live in the repository's `library/` and are pinned
(`use: library/slides/<id>@<selector>`, or a visual pin). They are never copied. An adaptation is
a new item that records `derived_from`.

- `present library promote <talk>/<module> --slide <id>` turns a talk slide into a library slide
  (1.0.0) and rewrites it to `use: …@latest`. `present library promote <talk>/visuals/<slug>`
  moves a visual and turns its pins into `library: {<slug>: <selector>}` in `deck.yaml`.
- Edit `library/slides/<id>/src/`, then `present library bump`. Talks pinning `@latest` change at
  their next build; pin an exact version to hold one still. The deck receipt records the version.
- Retire an item with `retired: true` (and a `retired_note`) in its `library-slide.yaml` or
  `library-visual.yaml`. `present validate` blocks talks that still pin it and warns about items
  no talk pins. `present library list` shows who pins what.
