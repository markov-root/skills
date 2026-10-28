# Encoding, legend, and colour

Choosing what carries meaning, and making sure it carries it for everyone.

**No palette ships here.** Colour values come from your project's theme. What follows is structural:
what a colour must agree with, and what it may never be the only carrier of.

---

## 1. Colour is never the sole carrier of a distinction `[core]` _(sourced)_

**Rule.** Any distinction encoded by colour is also encoded by at least one non-colour channel:
marker shape, line pattern, fill texture, position, a printed value, or a direct label.

This is a conformance requirement, not a preference — WCAG 2.2 Success Criterion 1.4.1 (Use of
Colour) requires that colour not be the only visual means of conveying information
([`SOURCES.md`](../references/SOURCES.md), `src-wcag`). It also survives contact with reality in a
way a pure-colour encoding does not: graphics are printed in greyscale, projected through
poor optics, compressed by conferencing software, and read by people with colour vision deficiency.

A rough ordering of channels by robustness. **This is a heuristic for choosing what to try, not a
measurement** — every "yes" below has a size and contrast at which it fails, and the only way to
know for your graphic is to look at it at delivery size
([`release-check.md`](release-check.md) §3).

| Channel            | Without hue | Under compression    | At small sizes        |
| ------------------ | ----------- | -------------------- | --------------------- |
| Direct label       | holds       | holds                | until text is too small |
| Printed value      | holds       | holds                | until text is too small |
| Position           | holds       | holds                | until marks merge     |
| Marker shape       | holds       | holds                | degrades first        |
| Line pattern       | holds       | holds                | degrades first        |
| Fill texture/hatch | holds       | degrades if fine     | degrades first        |
| Fill lightness     | partly      | poorly               | holds                 |
| Hue                | lost        | partly               | holds                 |

The practical reading: **the top three are the cheapest insurance, and the bottom one is not a
channel on its own.**

## 2. Keep all five expressions of a series in agreement `[core]`

**Rule.** A series on a graphic typically appears five times — as a mark, as a direct label, as a
legend entry, as a figure in the commentary, and in the accessible description. All five describe
the same thing, in the same words, with the same visual identity.

This is the structural rule that replaces a palette. The skill does not say what colour a series is;
it says that whatever colour it is, the legend swatch is that colour, the commentary figure is the
same quantity, the label is the same name, and nothing else on the graphic uses that identity for
something unrelated.

The common drift is a series renamed in the commentary but not the legend, or a colour reused
decoratively elsewhere on the canvas so the reader's learned association breaks.

## 3. A legend swatch mirrors the mark it stands for `[core]`

**Rule.** The legend reproduces the geometry of the thing it labels: a dashed series gets a dashed
swatch, a diamond-marked series gets a diamond, an interval gets a bar of the right orientation, a
hatched region gets a hatched swatch.

A legend of identical coloured squares standing for marks of several shapes forces the reader to
match by hue alone — which rule 1 just said is not a channel on its own. The legend is the one place
the dual encoding is easiest to get right and most often got wrong.

## 4. Reserve a semantic role and never spend it decoratively `[style]`

**Rule.** Where a project gives a colour a _meaning_ — warning, absence, anomaly, "not settled" — that
colour appears only where the meaning applies, and never because a region needed visual variety.

The value of a reserved semantic colour is cumulative: after a reader has met it three times meaning
"this is the thing to worry about", the fourth appearance communicates before they have read a word.
One decorative reuse spends the whole accumulated meaning.

This is a style-level rule because which colours carry which meanings is your project's decision. The
structural part — that a semantic assignment, once made, is exclusive — is what transfers.

> **Attributed example.** One reference corpus reserves a single amber for warning, absence, and
> anomaly, and uses it across twelve visuals — an exploitation window, an absent commitment, a
> crossed threshold, an attack path — with, by its own mining audit, zero decorative reuse.

## 5. Distinguish highlighted marks from the field `[style]`

**Rule.** Where a chart calls out specific points among many, the called-out marks are distinguished
by more than size: typically an inverted fill, a contrasting edge, or a different shape, so that a
highlighted mark remains visible when it sits on top of a line.

The matching half of the rule: the unlabelled field is drawn **recessively** — smaller, lower
contrast, lighter — because it is context rather than content. A field drawn at full strength
competes with the points that carry the argument.

## 6. Distinguish what is not ordinary data by more than fill colour `[core]`

**Rule.** A region of a chart that is not settled observation — a projection, an unreliable band, a
provisional period, an inferred area, a category meaning "not available" — is distinguished by
something other than fill colour alone.

For a **region**, texture is usually the right choice: a pale wash degrades badly under compression
and projector gamma, while a hatch is geometry. For a **single mark or cell**, a hollow treatment, a
dashed edge, or the printed word can carry it just as well, and a hatch at that scale may be the
thing that disappears.

This rule and §4 of [`numbers-and-claims.md`](numbers-and-claims.md) are the same discipline from two
sides: that one requires a non-colour cue plus a stated consequence, this one is about which cue to
pick for which shape of thing.

## 7. Label a derived series as yours `[core]`

**Rule.** Where a graphic plots a quantity you computed rather than one the publisher published — a
running maximum, a rate, a ratio, a smoothed line, a reconstruction — the graphic names it as your
construction, in the legend or the label, not only in a methods note.

A reader who sees a stepped frontier line beside a publisher's logo reasonably believes the publisher
drew it. If you drew it, say so where the line is.

A second-order rule that follows: **state the construction's tie-breaking choices** where they change
the picture. A running maximum over records sharing a timestamp looks very different depending on
whether ties all appear or only the best survives.

## 8. Give every mark an inspectable identity `[medium: interactive]`

**Rule.** In a medium where the graphic is viewed in a browser rather than as a flat image, every
data mark carries its own identity — a tooltip, a title, an accessible name — so that an unlabelled
mark is still inspectable.

This is how a chart can afford rule 5's recessive field: the field is not labelled, but it is not
anonymous either. In a print or flat-image medium, this channel does not exist and the labelling
burden shifts entirely to direct labels, which is a reason print figures carry more labels than
screen figures.

## 9. Choosing the chart form `[core]`

The form follows the question, and most disagreements about form are really disagreements about which
question the graphic answers.

| The reader's question               | What the form must make easy           |
| ----------------------------------- | -------------------------------------- |
| How has this changed over time?     | Reading a direction and a rate         |
| How do these compare right now?     | Comparing lengths from a shared base   |
| How much of the whole is this?      | Reading a part against its total       |
| Do these two things move together?  | Seeing position in two dimensions      |
| Where does this one sit among many? | Seeing a distribution and an outlier   |
| What is the state of each cell?     | Scanning a grid and finding exceptions |
| What happens in what order?         | Following a path                       |

Two rules that hold across forms:

- **A shared baseline is what makes lengths comparable.** Truncating a value axis on a form whose
  meaning is length exaggerates differences; it is a legitimate choice only where the form's meaning
  is position, and then it is stated.
- **Sort by the quantity, not by the label**, unless the label's order is itself the information
  (time, severity, a stated sequence). An alphabetically-sorted bar chart asks the reader to do the
  ranking the chart exists to show.

---

## Related

- [`annotation.md`](annotation.md) — the direct labels rule 2 requires, and how to place them.
- [`numbers-and-claims.md`](numbers-and-claims.md) — the figures in the commentary that must agree
  with the marks.
- [`axes-and-sidebar.md`](axes-and-sidebar.md) — naming the quantity a colour encodes.
