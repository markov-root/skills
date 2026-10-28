# Axes and the commentary column

Naming the quantity, and writing the words that sit beside the chart.

---

## 1. The quantity must be recoverable, by some route `[core]`

**Rule.** A reader must be able to determine what a quantitative axis measures and in what units,
from the graphic alone.

Note the shape of that rule. It is not "every axis carries a title" — it is that the meaning is
**recoverable**. Several routes satisfy it:

- an axis title carrying the quantity and its unit;
- tick labels that carry the unit themselves;
- a label on the commentary column naming what is plotted;
- a standing definition in the commentary that states the unit and its interpretation;
- a caption, in a medium where the caption travels with the figure.

What fails the rule is a bare numeric axis with no route at all, and that failure is common because
the author knows what the numbers mean.

**An index or a constructed scale always needs an explicit statement.** A unit a reader recognises —
days, people, currency — can be carried by tick labels. A number that is relative, normalised, or
constructed cannot, and the statement has to say not just its name but how to read it: whether zero
is meaningful, whether differences or only ordering carry information.

> **Attributed example.** Requiring an axis title on every quantitative axis is the reference
> corpus's single largest gap between its stated standard and its practice: 1 of 9 charts satisfies
> the strict rule, while the rest make the quantity recoverable through unit-bearing ticks, a
> commentary label, or a pinned definition. Its mining report concludes the practised rule is
> recoverability, not titling — which is why this file states it that way.

## 2. Scale the axis to the reading distance, not the screen `[medium]`

**Rule.** Axis and tick text is sized for how far away the graphic will be read, which for a
projected or screen-shared slide is much further than the author's own monitor.

The author's failure mode is reliable: everything is legible at the distance from which it was built.
The check is to view the graphic at the delivery size — reduced to the proportion it will occupy, or
at the viewing distance it will be read from — and see what disappears. See
[`release-check.md`](release-check.md).

## 3. Do not repeat the axis in the title, the ticks, and the label `[core]`

**Rule.** State the quantity once. An axis titled "Incidents per month" above ticks reading
"incidents" beside a commentary headed "monthly incidents" spends three places on one fact and
crowds out the one that is missing.

## 4. The commentary column carries takeaways, not narration `[style]`

**Rule.** Where a graphic has a commentary column, each block in it states one thing the reader
should take from the data — not a description of what the chart shows, and not the speaker's script.

Three things it is not, each a real failure:

- **Not a second narration track.** If the commentary says what the chart already says, the reader
  reads it twice and learns once.
- **Not a methods essay.** The method belongs in the brief, the caption, and the shortest material
  caveat in the attribution band.
- **Not the speaker's notes.** On a slide, the speaker says the sentence; the column holds what
  remains true when the slide is read without them — which is what happens to every slide eventually.

**One block per revealed thing** is the shape that works: when a series appears, its takeaway appears
with it, and the reader's attention moves between chart and column in step rather than scanning a
wall of text.

## 5. Pin the standing definition, and never reword it `[style]`

**Rule.** A definition true of every frame sits in a fixed position — conventionally the bottom of
the column — and is worded identically everywhere it appears.

Identical wording is what makes it recede. A reader who has read it once recognises it by shape and
skips it; a block whose wording shifts between frames pulls attention back every time, because the
reader has to check whether something changed.

This is [`composition.md`](composition.md) §5 seen from the content side.

## 6. The commentary's numbers are the chart's numbers `[core]`

**Rule.** Every figure in the commentary column is derived from the same data that drew the chart.

This is [`numbers-and-claims.md`](numbers-and-claims.md) §1 and §2 applied to the place they are
violated most often, because the commentary is written in prose and prose invites typing a number.

## 7. Let the typographic scale express the hierarchy `[style]`

**Rule.** Within the commentary, the size of a thing matches its importance: the figure the graphic
exists to convey is the largest element, supporting figures are smaller, explanatory text is
smallest and set for reading rather than for glancing.

The structural rule that transfers is **three levels, consistently applied**: the headline quantity,
the supporting quantities, and the prose. A column where everything is one size has no hierarchy and
is read as a paragraph; a column with six sizes has no hierarchy either.

The values are your project's. The relationship between them is what matters, and it should be the
same relationship in every graphic in a family.

> **Attributed example.** The reference corpus's headline figures range from roughly 62 to 92 px on a
> 1920 px canvas, with its own stated band of 70–74 px matching 2 of 10 cases. The band is a dated
> statement; the practice is content-dependent sizing within a consistent three-level hierarchy.
> Recorded as observation, not as a range to adopt.

## 8. Align numbers meant to be compared `[core]`

**Rule.** Figures a reader will compare down a column are set so their digits align — tabular
figures, consistent decimal places, the same unit treatment.

Proportional digits make a column of numbers ragged, so place values do not line up and the reader
has to compare digit by digit instead of by length. Alignment is what makes a column scannable.

---

## Related

- [`composition.md`](composition.md) — where the column sits and how wide it is.
- [`numbers-and-claims.md`](numbers-and-claims.md) — where the column's figures come from.
- [`encoding-and-colour.md`](encoding-and-colour.md) — keeping the column's figure, the legend, and
  the mark in agreement.
