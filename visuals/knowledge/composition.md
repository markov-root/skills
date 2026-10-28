# Composition

Choosing a canvas, deciding what owns the title, and arranging a graphic against its commentary.

---

## 1. The canvas is a consequence of where it is read `[medium]`

**Rule.** Decide the medium first; the canvas follows from it. The question is not "what size should
this be" but "what will be around it when someone reads it".

| Medium                   | What the medium already provides           | What the graphic must therefore not do                      |
| ------------------------ | ------------------------------------------ | ----------------------------------------------------------- |
| Presentation slide       | A title, a speaker, a fixed aspect, a deck | Repeat the title; assume the reader can zoom; rely on hover |
| Paper or textbook figure | A numbered caption carrying the detail     | Restate the caption; assume colour printing                 |
| README or docs diagram   | Surrounding prose, a scrollable width      | Assume a fixed width; assume a light background             |
| Poster                   | Nothing — it is read standing up, alone    | Assume any context; assume a close reading distance         |

The single most consequential consequence is **who owns the title**, below.

## 2. Settle title ownership before you draw `[medium]`

**Rule.** Exactly one of the graphic and its container carries the title. Decide which, record it in
the brief, and build to it.

A graphic that titles itself inside a container that also titles it produces a duplicate the reader
reads as an error. A graphic that titles nothing, placed in a container that titles nothing, ships
untitled. Both failures are invisible until the graphic is placed, which is why this is a decision
and not a default.

**The canvas usually already encodes the answer, and an author can miss it.** A canvas profile
shorter than the full frame — one reserving a band for a container's title — *means the container
owns the title*, and a graphic rendered to it must not draw one. If your project declares such a
profile, that is the decision, already made; read it as an instruction rather than as a dimension.
Two graphics in this skill's own parity testing put a title on exactly such a canvas, which is the
most common way this rule is broken.

Two consequences follow immediately:

- **The usable canvas changes.** A graphic sitting below a container's title band has less height
  than one occupying the full frame. Both the stylesheet's canvas height and the renderer's viewport
  must agree on which, or the output is letterboxed or cropped.
- **A family must be consistent.** Mixed conventions inside one deck or one paper read as
  carelessness even when each graphic is individually correct.

> **Attributed example.** The reference corpus states a deck-titled convention and, by its own
> mining record, contains both: 23 masters sized for a title band and 8 at full-slide height, of
> which 3 are self-titled and 5 are full-bleed with the title owned elsewhere. Two generations of
> the rule coexist in one directory. Treat that as the cost of not deciding early, not as a pattern
> to copy.

## 3. Reserve the edges, and never for decoration `[medium]`

**Rule.** The graphic keeps an inset at every edge, sized to the medium: enough that nothing
important sits where a projector crops, a page is trimmed, or a slide template's furniture overlaps.
The inset is empty. It is not a place to put a logo, a page number, or a stray label.

Where a fixed band is reserved for attribution, that band's height is part of the layout, not
padding — content is laid out against the band, not over it.

The values belong to your project's canvas profile. The rule is that they exist and that the
renderer and the stylesheet agree on them.

## 4. Chart against commentary: the divider is the invariant `[style]`

**Rule.** When a graphic pairs a chart with written commentary, the commentary occupies a column of
its own, separated by a visible division and a gutter, with the column's width set by its content.

The thing to hold constant across a family is the **division**, not a ratio. A fixed proportion
forces either a cramped column or a stretched chart as content changes; a visible divider plus a
content-sized column stays coherent across graphics whose commentary differs in length.

A rule that follows and is easy to miss: **the division carries the structure that padding would
otherwise provide**. Once there is a line between chart and commentary, the two do not also need
generous whitespace between them, and adding both makes the pair read as two graphics.

> **Attributed example.** Across the reference corpus's rail-bearing visuals the commentary column
> ranges from roughly 320 to 510 px against a 1920 px canvas, with a gutter in the low thirties and
> a one-pixel border. Those are that corpus's separator choices, held constant across its own family
> while the column width varies. A different project may separate chart from commentary by
> whitespace, a panel, or a rule of another weight; what §4 asks is that the choice be one thing and
> be held, not that it be this one.

## 5. Pin the standing definition to the bottom of the commentary `[style]`

**Rule.** Where a commentary column carries both per-frame observations and a definition that is true
of every frame, the standing definition is pinned to the bottom of the column and worded identically
in every frame.

It reads as a standing definition precisely because it does not move and does not change. A block
that shifts between frames reads as per-frame commentary, and the reader re-reads it each time
looking for what changed.

## 6. Prevent overflow structurally, not by checking `[core]`

**Rule.** A graphic rendered to a fixed canvas must be built so content cannot push past the canvas
edge, rather than built loosely and inspected afterwards.

This matters more than it sounds. "Content clipped outside the canvas" is one of only four conditions
that block in this skill, because it is the defect that makes an artifact broken rather than
merely ugly — and the usual cause is a layout whose children are permitted to exceed their track.
In CSS grid and flex layouts specifically, a content-bearing child that does not have its minimum
size constrained will expand its track rather than scroll or shrink, and a fixed-height canvas
silently becomes a taller one.

Build the constraint in — and do not expect a command to catch it if you do not. The blocking
`clipped-content` condition compares the delivered frame's dimensions against the receipt's viewport;
it detects a canvas that grew, **not** content clipped inside a correctly-sized frame. Until
scene-graph measurement exists, content overflowing *within* the canvas is found by looking at the
frame (see [`release-check.md`](release-check.md) §2), which is one more reason to make the layout
incapable of it.

## 7. Let labels overhang the plot, but not the canvas `[style]`

**Rule.** The drawing area of a chart may be permitted to paint outside its own bounds so that a
label sitting at the edge of the data is not clipped mid-glyph. The canvas edge is still hard.

This is the common case where a tidy-looking constraint produces a worse graphic: clipping a chart's
drawing region to its plot rectangle cuts the outermost tick label and the right-hand annotation,
which are exactly the ones carrying the most information.

## 8. Match canvases across a family `[style]`

**Rule.** Charts intended to be read in sequence — successive slides, figures in one section — share
a drawing geometry, so that moving between them does not change the apparent size of the plot.

Two charts with different internal proportions placed on consecutive slides read as a jump. The fix
is to decide one drawing geometry for the family and build each member to it, even when a member
would individually prefer a different shape.

> **Attributed example.** The reference corpus has two such families, each sharing one drawing
> geometry across its members, and records the reason in a brief: matching the sibling's geometry so
> that nothing is letterboxed when the deck moves between them.

---

## Deciding, in order

1. **Medium** → canvas and reading distance.
2. **Title ownership** → usable height; record it in the brief.
3. **Does this graphic carry commentary?** → one column or two, and the divider.
4. **Is it one of a family?** → adopt the family's drawing geometry before choosing your own.
5. **Build the overflow constraint in** before adding content, not after.

## Related

- [`progressive-builds.md`](progressive-builds.md) — what composition must hold still when a graphic
  is revealed in stages.
- [`axes-and-sidebar.md`](axes-and-sidebar.md) — what goes in the commentary column once it exists.
- [`source-credit.md`](source-credit.md) — the attribution band this file reserves.
