# Source credit, licensing, and logos

Attribution that reaches the reader with the graphic, and cannot drift from the data.

---

## 1. Attribution travels with the delivered unit `[core]`

**Rule.** Attribution — who produced the data, what the work is, when it was captured, and the
shortest material caveat — travels with whatever unit actually reaches a reader.

For a **paper or textbook figure**, that unit includes the numbered caption, and the caption is the
conventional place for it. For a **README diagram**, it is the surrounding prose. For a **slide or a
standalone image**, the unit is the image, and the attribution has to be inside it.

**The test is whether the graphic can circulate alone.** Graphics get screenshotted, pasted into
documents, forwarded, and re-shared, and the moment one does, any attribution that lived outside it
is gone. If a graphic can plausibly travel without its container — and a slide always can — put the
attribution in the image.

A graphic that uses no third-party data and makes no external claim — your own schematic of your own
system — may have nothing to attribute. That is a legitimate state, not an omission.

**Where a project reserves a band for attribution, that band is a contract element, not decoration.**
It has a fixed height the layout is built against (see [`composition.md`](composition.md) §3), and a
graphic in that family carries it whether or not the author feels it needs one — a family where some
members have the band and some do not reads as unfinished work, and the missing ones are the ones a
reader distrusts. Moving the attribution into the body instead is the same defect wearing a
different shape.

## 2. The snapshot date is read from the data, never typed `[core]`

**Rule.** The date, version, or vintage shown in the attribution is read from the dataset's own
provenance record at render time.

A typed date is wrong the first time the data is refreshed and nobody edits the string — and a
confidently-wrong vintage is worse than none, because it tells a reader the graphic is current when
it is not. When the date is a field of the data, the two cannot disagree.

This is [`numbers-and-claims.md`](numbers-and-claims.md) §1 applied to the one number nobody thinks
of as a number.

## 3. Every attribution asset has recorded provenance, and a miss is loud `[core]`

**Rule.** Every logo or attribution asset a graphic uses has recorded provenance — where it came
from, which version, under what terms — and a lookup that fails is visible rather than silent.

`[style: project]` The usual implementation is a **declared registry** that masters resolve
identifiers against. That is one method, not the rule; a project with three assets may record their
provenance beside them. What does not vary is that an identifier the registry cannot answer produces
a visible failure rather than a blank.

Two failures this prevents. The first is a graphic shipping with a blank where a logo should be,
which happens whenever a lookup fails quietly. The second is subtler and worse: pulling an
organisation's logo from the open web gives you an asset of unknown version, unknown licence, and
unknown provenance, placed on a graphic that asserts that organisation's authority.

The registry row carries where the asset came from, a digest, when it was retrieved, and — if it was
transformed — the untransformed original and a description of the transform.

> **Attributed example.** The reference corpus's attribution component replaces itself with a
> conspicuous error message in place of the credit when a source identifier does not resolve, rather
> than rendering an empty band.

## 4. Decide the fallback before you need it `[core]`

**Rule.** The project states what the attribution shows when the registry has no asset for a source
— typically a text credit in the same position and style — so that the fallback is a convention
rather than something invented twice, differently, under deadline.

This is the gap that most reliably produces inconsistency, because it appears only at the moment
someone is trying to finish a graphic.

> **Attributed example.** The reference corpus's registry holds no row for one organisation, and two
> of its masters hand-built a text footer with class names copied from the attribution component.
> The fallback happened twice, independently, and was never written down — the corpus's mining
> report names this as an open decision for its owner.

## 5. A logo is placed, not redrawn `[core]`

**Rule.** An organisation's mark is reproduced at its supplied geometry. Scale it; do not restretch,
recrop, recolour arbitrarily, rearrange, or rebuild it.

Where a project's visual scheme requires a single-colour treatment, render the supplied artwork as a
monochrome silhouette preserving its exact shapes, rather than substituting a redrawn version. The
geometry is the thing being licensed and recognised.

**Prefer the full lockup** wherever the space can render it legibly; reserve the standalone mark for
genuinely icon-sized placements, which is what the standalone mark exists for.

## 6. Attribution is not endorsement, and a dual credit says which is which `[core]`

**Rule.** Where you have materially transformed, analysed, or reconstructed someone's data, the
graphic distinguishes **who owns the data** from **who did the analysis**. It never implies the data
owner endorses your conclusion.

A practical decision rule, and the one a real corpus converges on: credit **both** when the analysis
layer is yours or the data was transformed; credit the **source alone** when you have faithfully
redrawn what they published. Both are honest; the distinction is whether a reader looking at the
shape on the screen is looking at the publisher's claim or yours.

Note the asymmetry with §1, which is deliberate. **Data-source credit always travels with the
delivered unit** — a reader has to be able to see whose data this is. **Your own authorship is
context-dependent**: where a deck template or a publication's masthead already makes it unambiguous,
repeating it on every graphic adds noise. Repeat it when the distinction between source data and
your analysis is itself load-bearing — and remember that if the graphic is exported alone, the
masthead does not go with it.

## 7. Honour the licence in the image `[core]` _(sourced)_

**Rule.** For material under a licence requiring attribution, the graphic names the licence and — if
you adapted the material — indicates that changes were made.

For Creative Commons BY 4.0 these are licence **conditions**, not courtesies
([`SOURCES.md`](../references/SOURCES.md), `src-ccby`). Section 3(a)(1) requires that you retain
identification of the creator, a copyright notice, a notice referring to the licence, a notice
referring to the disclaimer of warranties, and a URI or hyperlink to the material so far as
reasonably practicable; that you **indicate if you modified the material** and retain any indication
of previous modifications; and that you indicate the material is licensed under that licence and
include its text, URI, or hyperlink. The same section allows these to be satisfied "in any
reasonable manner based on the medium, means, and context in which You Share the Licensed Material",
which is what makes the split below legitimate.

A note on a common error: the familiar "title, author, source, licence" formula is Creative Commons'
_best-practice guidance_, not the text of the licence — a title is not among 3(a)(1)'s conditions.
Follow the guidance by all means; do not state it as the legal requirement.

The practical split: the licence name and the changes-were-made indication go **in the image or its
immediately adjacent citation**, because that is what travels; the full licence URL and the
unmodified-original reference live in the source package beside the graphic.

## 8. Content with its own rights carries its own credit `[core]`

**Rule.** Photographs, portraits, quotations, and third-party figures embedded in a graphic carry
their credit **at the content**, not aggregated into the attribution band.

The band credits the data. An image inside the graphic has a different rights holder and often a
different licence, and a reader needs to be able to tell which credit belongs to which thing.

## 9. The caveat is part of the credit `[core]`

**Rule.** The attribution band carries the shortest material method caveat alongside the source — the
one clause whose absence would let an honest reader conclude something false.

An attribution line that is only a logo and a date tells a reader where the data came from and
nothing about what it can bear. See [`numbers-and-claims.md`](numbers-and-claims.md) §8.

---

## What the attribution band holds, in order of necessity

1. **Who** produced the data — organisation, and the specific work.
2. **When** — snapshot or version, derived from the data (§2).
3. **The material caveat** — one clause (§9).
4. **The licence** and changes-made indication, where one applies (§7).
5. **The claim reference**, where a single claim owns the figure.
6. **The mark**, from the registry, at supplied geometry (§3, §5).

A band that cannot fit all six is a layout problem, and the caveat is the last thing to touch. In
order: reflow or enlarge the band; drop a mark to the standalone form; shorten non-essential copy;
and only then shorten the caveat itself — never to the point of removing the material limitation
§1 and §9 exist to carry.

## Related

- [`numbers-and-claims.md`](numbers-and-claims.md) — provenance, claim binding, and limitations.
- [`composition.md`](composition.md) §3 — the band reserved in the layout.
- [`release-check.md`](release-check.md) — confirming the band rendered before publishing.
