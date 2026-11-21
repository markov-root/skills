# Component library changelog

`COMPONENTS_VERSION` in `components.py`. Every release that changes how a component draws
carries the `present components diff` summary against the previous release's gallery (task 0016).
An unexplained visible change fails the dev suite.

## 1.4.0 — 2026-11-12

The maintainer's round-5 review of the pilot deck (v2.3.0.)

- **`SOURCES` table footer:** a caps `SOURCES` label, then one equidistant cell per source (at
  least four cells, so positions repeat from slide to slide), hairline ticks between cells; labels
  stay italic, muted and hyperlinked. New primitive `cell_row(...)`: the one table-of-cells system,
  shared with legends.
- **Legends are tables:** `legend_line` places items in equidistant cells (the widest item's width),
  wrapping by whole cells; `legend_rows` counts the same grid. `_swatch` is the shared swatch drawer.
- **Palette restored (round 4 over-corrected):** new roles `BLUE` (`brand`), `BRAND_GREY`
  (`brand_grey`), `BLACK` (`black`), each falling back to an older token file's ink/muted. Default
  series inks: black/navy, brand blue, brand grey and their shades; orange stays the one highlight.
- **`sunrise(n, role)`:** n colours sampled end to end from the token score ramp (OKLab), `fill` as
  is, `line` deepened for use on white; for slides that genuinely need many colours.

Gallery diff: every framed slide with sources changes (footer table); charts with legends change
(cell grid); see `present components diff`.

## 1.3.0 — 2026-11-12

The maintainer's review of the pilot deck (v2.2.0.)

- **Footer format:** `Hendrycks et al., Jan 2023; METR, Nov 2025`. There is no "Sources:" prefix;
  labels are italic, in the muted grey, and separated by `; `. `cx.src` / `cx.dataset` and the YAML
  source objects accept `short` (e.g. "Hendrycks et al., Jan 2023").
- **Orange is the highlight only:** structural accents use `SOFT`, a gradation of the ink.
  Affected: the takeaway rule, the quote glyph and rule, the term kicker, the section kicker and
  the speech-bubble caption.
- **More room under the title:** content starts at 1.18 in (was 1.0).
- `title_slide`: the title is set at 54 pt (was 36). `speakers` entries may be
  `{name, role, photo}`; the photo is drawn as a circle beside the name.

Gallery diff: every framed slide changes (content top, footer); see `present components diff`.

## 1.2.0 — 2026-11-12

The maintainer's review of the pilot deck (v2.0.0) (pilot, task 0013). Visible on every framed slide.

- **Compact sourcing:** the footer is one line of short, linked labels (`Publisher, Mon YYYY`;
  datasets `Publisher data to Mon YYYY`); the full references (title, date, URL) are written to
  the speaker notes. `Source` gains `.short`; `kit.set_sources` / `set_notes` keep notes and
  references together. A source is cited once, in the footer, never again inline.
- **Frame:** the mark sits in the left column again (top), and every framed slide carries its
  position `n / N` at the foot of that column (`frame.finish`).
- **Section kickers:** after a one-row contents slide, each slide shows `NN · Section` in the
  accent above its title (the deck build adds it; `frame.section_kicker`).
- **Spacing:** the content area ends at 6.62 in (was 6.78), leaving a constant 0.32 in above the
  footer hairline on every slide.
- **Label grounds** use the `surface` role (the slide's own white), not `background` (a grey).
- `section_divider`: `descriptions`, one short line per item, set inside its box.
- `quote_slide`: larger portraits (1.45 in) and quote logos.

Gallery diff: every framed slide changed (frame mark, counter, footer, content bottom); see
`present components diff` between the 1.1.0 and 1.2.0 galleries.

## 1.1.0 — 2026-11-12

Single-module talks and the pilot briefing (presentation task 0013, the pilot). Every change is
additive: a deck that declares none of the new arguments draws exactly as under 1.0.0.

- `title_slide`: `module_n` is optional; `kicker` replaces the "Module N of M" label;
  `speakers: ["Name · Role", …]` sets several presenters side by side.
- `section_divider`: `parts` and `part_on` are optional; a talk with one agenda shows one row.
- `quote_slide`: `portrait_img` (a person's photograph, drawn as a circle) instead of `org_logo`
  for people; organisations keep their logo.
- `agent_grid`: `legend` under the grid; `bubbles` — speech bubbles whose tails point at one
  agent's square, which is ringed in the accent (new primitive `speech_bubble`).
- `chart_xy`: a series with `band: [(x, lo, hi)]` draws a filled uncertainty band behind the
  lines (new primitive `band_shape`).

Gallery diff: 23 same · 0 changed · 5 added · 0 removed (added: title-speakers, contents-single,
quote-portrait, agent-grid-bubbles, chart-xy-band).

## 1.0.0 — 2026-11-10

- First release: the consumer's first deck library, copied and tokenised (task 0015). Every
  colour, font, size and logo comes through `brand.py` by semantic role. With that consumer's
  tokens, the 17-component gallery's 128 package parts are byte-identical to the frozen legacy
  library's output (`dev/tools/legacy_identity.py`).
- Catalogue (declarable from `slides.yaml`): chart_xy, chart_line, chart_bar, chain, compare,
  cards, stat_in_context, term, timeline, agent_grid, pipeline, screenshot, quote_slide,
  title_slide, one_thing, section_divider, walk_slides. Primitives (text, label, box, rule, line,
  dot, logo, annotate, region, value_label, callout, legend_line, rail, panel_lead, takeaway,
  halo, texture) are for `custom.py`.
- Retired (left in the legacy library, talk-specific): `lifecycle`, `ladder`; the team-template
  helpers `tiles`, `highlight_tiles`, `set_tiles`, `drop_caption_sources`, `flatten`.
- `title_slide` no longer carries speaker, date or event defaults; they are talk content.
- Gallery: `gallery` built from the neutral tokens, sha256 of the slide XML recorded by task 0016.
