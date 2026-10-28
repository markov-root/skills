# Annotation and direct labelling

Putting words next to data without covering it.

---

## 1. A label never covers the data it labels `[core]`

**Rule.** No annotation obscures the mark it refers to, or any other mark.

This is the one rule in this file that is not a matter of degree. A label over a data point destroys
the thing the reader came for, and it is the most common defect in otherwise careful graphics,
because labels are usually placed when the data looks one way and the data later looks another.

The rest of this file is the set of techniques that make this rule survive a data refresh.

## 2. Reserve the space before you place the label `[style: chart]`

**Rule.** Where labels sit beside the data — typically at the ends of series — the drawing area is
stopped short of the canvas edge to create an empty corridor, and labels are anchored to that
corridor rather than to the points they describe.

This is a chart technique, not a universal rule: a diagram or a matrix has no plot to stop short of.
What is core is §1 — the label does not cover the data — and in a chart this is the most reliable way
to make §1 survive a data refresh. It is the highest-leverage technique in this file and it is
usually discovered too late.

The naive approach places each label at a small offset from its point. It looks correct on today's
data. When the data updates, two points come close together and their labels collide; a point moves
near the edge and its label is clipped; a series ends higher than before and its label lands on
another line. Each is fixed by hand, and the fix does not survive the next refresh.

The corridor approach pins the labels' horizontal position and lets only their placement along the
corridor follow the data. Labels cannot collide with marks, because no mark is ever in the corridor.
They cannot be clipped, because the corridor is inside the canvas.

Two different kinds of movement are worth separating here. **A data refresh** may move a label along
the corridor, which is fine and is the point — it tracks its series. **A staged build must not**: if
later stages add series, compute every label's position from the complete data once and hold it
across the stages, or the earlier frames will shift when the later ones arrive.

**Where the corridor goes** depends on the form: at the end of time series, outside the extremes of
a scatter, beside the bars of a horizontal bar chart. The constant is that it is empty by
construction, not empty by luck.

## 3. An offset label keeps a leader back to its mark `[core]`

**Rule.** When a label is not adjacent to its mark, a line connects them.

An offset label with no leader is ambiguous as soon as there is more than one candidate mark nearby,
and the reader resolves the ambiguity by guessing. The leader costs nothing and removes the guess.

Draw the leader _behind_ the marks rather than over them, so the connection is visible and the data
point stays whole — which is rule 1 applied to the leader itself.

## 4. Text over busy content needs a separating treatment `[core]`

**Rule.** Text drawn over anything visually busy stays readable without obscuring what is under it.

`[style: chart]` The usual technique is a **halo**: a contrasting outline painted behind the glyphs,
so the text sits cleanly above the data while the data stays continuous underneath. Alternatives
that also satisfy the core rule are an opaque backing plate (which does obscure, so only over empty
regions), moving the text to a clear area, or the corridor of §2.

Untreated, text over data fragments: the reader sees letter shapes interrupted by a line and has to
work to reassemble the word.

Halo width is yours to choose and belongs to your project's conventions. What transfers is that the
outline is painted _behind_ the fill rather than over it, so the letterforms stay sharp.

> **Attributed example.** The reference corpus applies a halo as a shared, reusable class in every
> chart whose labels cross the plot, with widths varying from 4 to 7 px by visual and no stated rule
> for which — an unstated convention its own mining report lists among untraced numbers.

## 5. Label the landmarks; leave the field inspectable `[style]`

**Rule.** In a chart with many marks, only the marks a reader would recognise or the argument depends
on get direct labels. The rest stay unlabelled.

The instinct to label everything produces a graphic that cannot be read at all: the labels collide,
overflow, and crowd out the shape the chart exists to show. The instinct to label nothing produces a
graphic the reader cannot enter.

The resolution: label the few that anchor the reader — the recognisable name, the extreme, the
turning point, the one the commentary discusses — and make the rest inspectable by other means (see
[`encoding-and-colour.md`](encoding-and-colour.md) §8).

**How many is "few" depends on reading conditions**, which is a medium question. A figure studied on
paper supports more labels than a slide read for twenty seconds in a video call.

## 6. Keep label placements as data, not as coordinates `[style: data-driven]`

**Rule.** Which marks are labelled, and the offset of each label, live in a declared table that is
maintained alongside the data — not as coordinates scattered through drawing code.

The reason is maintenance, and it is the same reason as rule 2. When the dataset refreshes, someone
must check the labels. If the placements are a table, that check is reading one list. If they are
inline coordinates, the check is reading the whole drawing routine, so it does not happen.

## 7. Annotate the anomaly where the anomaly is `[core]`

**Rule.** When a graphic shows something that will prompt the question "why does it do that there" —
a break, a spike, a partial tail, a regime change — the answer is on the canvas at that place, not
only in the commentary column or the caption.

A reader's eye goes to the anomaly first. If the explanation is elsewhere, they form a wrong
hypothesis before they reach it, and the wrong hypothesis is what they remember.

See [`numbers-and-claims.md`](numbers-and-claims.md) §4–§6 for what specifically must be annotated:
incomplete data, timing markers that are not causal claims, and provenance seams.

## 8. Hide decorative marks from assistive technology `[medium: interactive]`

**Rule.** Arrows, connectors, rules, chevrons, and quotation ornaments that carry no information are
marked as decorative so they are not announced.

The matching half: anything that _does_ carry information — a connector that means "feeds into", an
arrow that means "becomes" — is not decorative and needs an accessible name, because its meaning
exists nowhere else.

Where the deliverable is a flat image, there is nothing to mark up; the whole graphic carries one
accessible description, and the same judgment applies to what that description includes.

---

## When a label will not fit

In order of preference:

1. **Shorten the text.** Most data labels carry more words than they need.
2. **Move it to the corridor** (§2) and add a leader (§3).
3. **Drop the label and move the fact to the commentary**, where there is room for a sentence.
4. **Drop the mark from the labelled set** — it was not a landmark (§5).

Shrinking the type is not on this list. A label too small to read at the medium's reading distance is
not a label; it is visual noise that looks like diligence.

## Related

- [`encoding-and-colour.md`](encoding-and-colour.md) — direct labelling as a non-colour channel, and
  tooltips for the unlabelled field.
- [`composition.md`](composition.md) §7 — letting labels overhang the plot without clipping.
- [`progressive-builds.md`](progressive-builds.md) — why a fixed corridor is what lets annotations
  hold position across stages.
