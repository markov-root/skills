# Deck standard

Decks are native, editable presentation files built from one component library (`components.md`)
and used identically in every deck. Similar items look the same everywhere.

## Built, never hand-edited

- A deck is built: `present deck build` turns `src/slides.yaml` and its pinned inputs into a new
  version. Change the inputs, then build again. Never edit a built file by hand.
  `[enforced: present validate — receipts]`
- **Builds are duplicated slides, not animations,** so they survive every viewer and PDF. Each
  click adds one element in the order the script speaks, and keeps the earlier ones. Geometry is
  fixed across a build: nothing moves when an element appears.
- **Speaker notes come from the script.** Each slide's notes are the script section with the same
  slide ID, plus its `note` annotations.

## Native first; an HTML visual only for what the deck cannot draw

- Every chart is a native chart, and every diagram (chains, timelines, step boxes, flows,
  comparisons, grids) is native shapes and text from the component library.
- An HTML visual from the `visuals` skill is used **only for what native shapes cannot draw**:
  illustrations, hand-drawn sketches and genuinely complex diagrams. It is pinned into the deck as
  an image.
- Other raster images: real photographs, screenshots of a source document, and logos.
- A rendered chart or diagram that a component could draw natively is a regression, not a shortcut.
- A map may render its geometry as an image. Its labels and legend stay native text.
- Do not build what cannot be done well. A slide that cannot be made good is deleted, not
  approximated.

## One sourcing rule

- Sources appear only in the slide's footer: **one line** of short labels in one position on every
  slide, `Sources: Publisher, Mon YYYY · …` (a dataset as `Publisher data to Mon YYYY`), each
  label hyperlinked to the exact page. The full references (publisher, title, day, URL) go to the
  slide's speaker notes, written by the library (components 1.2.0). Since 1.2.0, decided by the
  maintainer: three-line footers were unreadable.
- **Cite once.** A source in the footer is never repeated inline ("(Verizon, 2026)" in a rail is a
  defect). Attribution that is part of the claim ("METR found …") is not a citation.
- Keep a slide to the few sources its claims need, so the footer stays on one line.
- Never put a source inside a chart or image, and never as a caption.
- Nothing on a slide is unsourced except the speaker's own framing.
- A talk keeps one source register (`research/sources.yaml`: key, publisher, title, short, date,
  URL, slides) that every footer is taken from.

## Layout constants every slide shares (components 1.2.0)

- The frame: the brand mark at the top of the left column and the slide's position `n / N`
  at its foot; the title band with, after a one-row contents slide, the section as a small accent
  kicker above the title.
- Nothing comes within 0.32 in of the footer hairline (the content bottom). Cut lines before
  shrinking type; nothing may look cramped.
- Label and callout grounds are the slide's own colour (or a halo), never a visible tint.

## Order and navigation

- **Order:** title → two-level contents → the one-thing slide (the module's single takeaway) →
  section 1. Nothing else before section 1.
- **Two-level contents:** the day's or talk's agenda, with the current module's parts beneath it,
  and the current item highlighted. The same slide is repeated before **every** sub-section, with
  the current part highlighted.
- When the story changes, rebuild the whole deck around it (opening, order, payoff), not just the
  middle.

## Density and type scale

A slide carries the point **and** its context: the main visual, an annotation where it explains,
and a side panel holding the takeaway as its lead sentence plus two to four small ordered facts
that appear with the builds. Oversized type and one-element slides are a failure, not a cleaner
version.

| Element (native slide, 13.33 in wide) | Size |
| --- | --- |
| body | 11–14 pt |
| labels | 9–11 pt |
| side-panel headline | 20–24 pt |
| hero number | ≤ 40 pt |
| statement slide | ≤ 28 pt |
| footer source | 9 pt |

| Element (rendered visual, 1920 px wide) | Size |
| --- | --- |
| ticks and axis text | 17–20 px |
| annotations and legend | 13–18 px |
| side-panel explanation | 19–20 px |
| side-panel hero value | 70–74 px (secondary values 50–56 px) |

- **At most four items per build** in a list-like layout (rows, cards, steps). More items become a
  second iteration of the same layout.
- **No lone huge numbers.** A number lives in a chart, a comparison or a panel with its context:
  what, when, and compared with what.
- **Every chart states its takeaway** as the side panel's lead sentence. The plot gets the full
  plot area.
- **Slides are memory triggers.** The side panel lists the sentences the speaker will say, in
  order, shortened from the script's own wording. It adds no new claims.

## Charts

- Muted context (light tints) and one strong accent on the element the slide is about. Series are
  dual-encoded by colour and texture (solid, hatch, back-hatch, dots, faded), never by colour alone.
- Legend at the bottom of the plot, without a box. Dotted light grid, no y-axis line, value labels
  on bars, curved leader lines where a label does not fit, a halo behind numbers over textures.
- A shaded region is a light tint plus a 45° hatch, labelled inside the region, never an opaque
  box.
- Model comparisons show every other model in grey behind the highlighted series, with provider
  logos beside model labels.
- Every number comes from a recorded dataset release or a ledger row.

## Quotes and logos

- **Quote slide:**
  - the quoter's logo and a large quote-mark glyph;
  - the quote in italics;
  - one attribution line: name · role · organisation · date.

  A non-English quote shows the translation as the main text, with the original smaller
  underneath, both in quotation marks. There are no numbered context cards. Attributed official
  advice also gets the quote-slide treatment.
- **Logos** are monochrome in the brand's ink colour, trimmed to their ink, and sized by equal area
  for each placement type (quote, row, label), so a wordmark and a square mark read as the same
  size. A deck never sets its own logo size.

## Visual language

- No drop shadows, no outlined boxes, no coloured left-border callout cards, no decorative icons.
  Icons only label a step.
- One deliberate visual per slide.
- Generated illustrations show the technical concept or the data's consequence, never a metaphor
  or story scene, and match the talk's seriousness.

## Review at full size

Render every slide and look at each one at full size, never only at a contact sheet. Fix anything
you would not show the most senior person in the room.
