# Numbers and claims

Read this before putting any figure on a graphic. Everything else in this knowledge is a default you
may override; this file is the reason the rest exists.

A graphic is read as evidence, and it separates from its context. Exported, screenshotted, or pasted
elsewhere, it arrives without the brief that justified it, the caption that qualified it, or the
speaker who was going to explain it. Whatever is wrong with a number on it therefore travels
unaccompanied, and the reader has nothing to check it against.

---

## 1. Every printed number traces to its source `[core]`

**Rule.** Every figure on a graphic has a known origin you can produce on demand, and the graphic
cannot drift away from that origin without someone noticing.

**For a data-driven graphic rendered from a dataset, the way to satisfy that is derivation**: the
figure is computed at render time from the data that justifies it `[style: data-driven]`. A number
typed into the markup is a number that can silently stop being true.

A graphic with no dataset — a quotation card, a hand-authored schematic, a figure quoting a single
published statistic — cannot derive anything, and the core rule still binds: the origin is recorded
beside the graphic, and the check is the one in "When you cannot derive it" below.

The failure hides well: a visual prints one figure as a literal while computing its siblings from
the data, so a refresh moves the chart and leaves the printed number behind, with nothing on the
canvas to show that the two no longer agree. Nobody rereads a number that was correct when it was
written.

**What derived means in practice.** The chart reads the dataset. The commentary beside the chart
reads the same dataset. The footer's snapshot date reads the dataset's own provenance record. None of
the three is typed. Sharing one source removes the most common way the
three drift apart; it does not make them *incapable* of disagreeing, since two different filters or
aggregations over one dataset still can. That is what §2's consistency checks are for.

**When you cannot derive it.** Sometimes a figure legitimately comes from elsewhere — a published
summary, a different measurement window, a hand-coded count. Then say so at the point of use:
record where it came from, and say in the brief that it is not derived. An undocumented literal and a
documented one fail differently: the first is a trap, the second is a known limitation.

> **Attributed example.** The reference corpus derives sidebar figures at render in every data-driven
> visual, and its mining record names the six places it does not — a chart annotation reading `148`
> beside a sidebar computing the same quantity, a message count quoted from a different window than
> the one plotted, a hardcoded `N` in a footer whose counts all derive from the file. The corpus
> treats each as a finding to carry, not a style to copy.

## 2. When two things on the graphic state the same quantity, make them one thing `[core]`

**Rule.** If a number appears twice — in the chart and in the commentary, in a label and in a
headline, in the footer and in the caption — it must have one origin. Two origins is a bug waiting
for a data refresh.

The strong form is to **fail the render** when two independently-computed values of the same quantity
disagree. This sounds severe and is not: the alternative is publishing the disagreement. A render
that stops is a problem you have; a render that completes with two different numbers for one fact is
a problem your audience has.

To be clear about where that guard lives: it is an assertion **you write into your own source
master**, which throws before drawing. No `visuals` command imposes it, and none could — the skill
cannot know which two numbers on your canvas are meant to be the same quantity.

What such a check asserts, in order of how often it earns its keep:

1. A drawn series and a published summary of that same series agree, within a stated tolerance.
2. A quantity computed two ways in the same file agrees with itself.
3. Every entity the annotations name actually exists in the data.
4. The dataset carries every field the graphic needs, before drawing starts.

> **Attributed example.** The reference corpus's strictest master refuses to render on five distinct
> conditions, including a disagreement between the drawn series and the publisher's own summary
> beyond a small stated tolerance.

## 3. Take a quoted figure from whoever is quoted `[core]`

**Rule.** When a graphic draws a trend and the surrounding text quotes a number for that trend, the
drawn line and the quoted number must have the same origin — and if the number is the publisher's,
the line must be the publisher's too.

Fitting your own trend to someone else's data and then quoting their headline figure beside it
produces a graphic where the line and the number disagree by an amount nobody has measured. Fit the
constrained parameter from the publisher and solve only for what remains, or quote your own figure
and attribute it to yourself. Both are honest. Mixing them is not.

> **Attributed example.** One corpus master takes each trend line's slope from the publisher's
> stated doubling time and fits only the intercept, recording in the source why: an ordinary
> least-squares fit over the same points yields materially different figures, "and the slide would
> then be quoting us, not them."

## 4. Mark incomplete data, and say what follows from it `[core]`

**Rule.** Where a graphic shows data that is partial, provisional, or still arriving, two things are
present: the incompleteness is **visibly marked** by a cue that does not depend on colour alone, and
the **interpretive consequence** is stated in words — what the reader must not conclude from it.

One marker is a convention the reader may not know. The words are what stop the misreading: the
visual cue tells a reader _that_ the tail is incomplete, and only the sentence tells them _what
follows_ — that a final downslope is an artefact of collection, not a finding.

**In a chart specifically, the practised form is four channels** `[style: chart]`: the **mark**
(hollow, dashed, or hatched rather than solid), the **region** (a band or segment separating it from
settled data), an **on-canvas note** at the anomaly, and a **sentence** in the commentary. A table, a
matrix, or a schematic has no "region" and no commentary column; there the core rule is satisfied by
a distinct cell treatment and a stated note.

**Choose a cue that survives delivery.** Low-contrast tints degrade badly under projection and video
re-encoding, which is why a geometric cue — a hatch, a dash, a hollow mark — is usually the safer
choice than a pale fill. Fine hatching can disappear too; the way to know is
[`release-check.md`](release-check.md) §3, which looks at the frame at delivery size.

## 5. Adjacency is not causation, and the disclaimer is on the canvas `[core]`

**Rule.** Where a graphic places an event next to a change — in time, in space, or in a sequence —
and does not intend a causal claim, the graphic denies the claim on its own canvas. The denial has to
be in the image, because the image is what travels.

`[style: chart]` The usual form is a marked event on a time axis carrying a short label saying it is
a timing reference rather than an attribution of cause.

## 6. Draw the seam where the data changes `[core]`

**Rule.** Where a graphic combines data of different provenance, method, population, or collection
regime, the boundary between them is visible rather than smoothed away.

`[style: chart]` In a series the boundary shows as a treatment change, a break, or a labelled
year-line at the crossing point; in a table or matrix, as a distinguished block with its own note.

Splicing two provenances invisibly produces a graphic that is wrong in a way no reader can detect,
which is the worst kind of wrong. A visible seam costs one line of explanation and makes the graphic
checkable.

## 7. Every figure resolves to a claim you can produce `[core]`

**Rule.** Each load-bearing number on a graphic traces to a record stating what is claimed, on what
evidence, with what limitation. Whether that record is a formal ledger with identifiers, rows in the
brief, or a provenance file beside the data is your project's choice; that it exists is not.

**No command checks this**, and it is worth being precise because the opposite is easy to assume:
`validate` does not read a claims ledger and does not test per-figure bindings. The binding is
maintained by you and your project. Nothing here judges whether a claim is *true* either — that is
not a thing a tool can do.

> **Attributed example.** The reference corpus surfaces a claim identifier in the footer of the
> visuals where a single claim owns the figure, and keeps identifiers in the brief where several
> claims feed one graphic. Both satisfy the rule; the corpus never leaves a figure with no record at
> all, and its mining report flags the cases where a ledger row was still owed.

## 8. The limitation ships on the graphic `[core]`

**Rule.** The shortest material caveat travels with the image, not only in the brief, the speaker
notes, or the paper. A graphic separates from its context immediately and permanently.

"Material" is the test: the caveat that changes what a reader may conclude. Not every methodological
footnote — the one whose absence would let an honest reader draw a wrong conclusion.

This is why `data snapshot` requires a non-empty `limitations` array and offers no flag to waive it:
the point at which you record a dataset is the point at which you still remember what is wrong with
it.

---

## What this looks like as a habit

Before a graphic is finished, answer four questions. If any answer is "I would have to check", the
graphic is not finished.

1. **If the dataset were refreshed tonight, which printed numbers would be wrong tomorrow?**
   Every one of them is a literal that should be derived, or a documented exception.
2. **Which quantity appears twice, and do both appearances have one origin?**
3. **What would a reader conclude from the right-hand end of this chart, and is that conclusion
   supported?** If not, the incompleteness is under-marked.
4. **Which single sentence, removed, would let an honest reader be wrong?** That sentence belongs on
   the canvas.

## Related

- [`source-credit.md`](source-credit.md) — where the caveat, the snapshot date, and the attribution
  sit, and why the date is read from the data rather than typed.
- [`annotation.md`](annotation.md) — how the on-canvas notes this file requires are placed without
  covering the data.
- [`release-check.md`](release-check.md) — the point at which these questions get asked.
