# Release check

Deciding whether a graphic is finished.

The commands check what a machine can currently check: that every frame rendered, that each frame's
dimensions match the receipt's viewport, that a receipt exists, that `latest` points somewhere, and
that output names are well formed. That is narrower than it sounds — notably, it does **not** detect
content clipped *inside* a correctly-sized frame, and it says nothing about whether the graphic is
good or even right. This is the part that is yours.

**Do this in order.** Each step is cheap and catches a different class of defect, and the order is
chosen so that an expensive look happens only after the cheap checks have passed.

---

## 1. Render every frame and read the receipt `[core]`

Confirm the frame count matches the manifest and the viewport matches the canvas profile you
intended. A frame missing from a build is invisible until the deck is presented, and a viewport
mismatch produces output that looks correct in isolation and wrong in place.

Where the render reports how it decided the page was ready, read it. A frame captured on a fallback
time budget rather than an explicit readiness signal is a frame that may have been captured
mid-build — correct today and a race tomorrow.

## 2. Look at every frame at full size `[core]`

Not the contact sheet, not a thumbnail. Full size, one at a time.

What you are looking for, in roughly the order it is missed:

- a label covering a mark, or two labels colliding;
- a number that disagrees with another number on the same canvas;
- a series in the chart with no legend entry, or a legend entry with no series;
- an axis whose quantity you cannot name from the graphic alone;
- the attribution band blank, half-built, or showing an error;
- something overlapping the reserved edge inset.

## 3. Look at the final frame at delivery size `[medium]`

Reduce the graphic to the proportion it will actually occupy — a slide seen from the back of a room,
a figure at column width, a diagram at README width — and look again.

This is the step most often skipped and the one that most reliably finds a real defect, because
authors build at full size on a large monitor and audiences do not. What disappears first: tick labels,
the caveat in the attribution band, hairline rules, the distinction between two similar hues, and
anything whose contrast was marginal.

**If something important disappears, the graphic is not finished.** Shrinking it further is not a
fix. Reflowing the layout, changing the type hierarchy, or raising contrast may recover it; if none
of those do, the graphic is carrying more than it can at this size, and something comes out.

## 3b. Check it is *finished*, not merely correct `[core]`

A graphic can satisfy every rule in this knowledge and still be thin. This is the most common way a
competent graphic falls short of a good one, and no rule above catches it, because every rule above
is a constraint — a thing not to do — and thinness is an absence.

**List the parts a finished graphic of this family carries, then check each one is present and
pulling its weight.** For a chart with a commentary rail that list is typically: the plot, the
legend, the direct labels, the axis treatment, each rail block, the pinned definition, and every
element of the attribution band. If your project declares styles, the style's description is where
that list belongs; if it does not, write the list in the brief before you build.

Two specific symptoms worth naming, because both look like restraint and are not:

- **An element present but under-loaded.** A matrix cell carrying only a score, where the data also
  supports an interval and a denominator. A rail block carrying one sentence where the data supports
  a figure and a sentence. Ask of each element: *what else does the data already justify putting
  here?* Adding information to an element that already exists costs no layout and is the cheapest
  improvement available.
- **A region left empty by accident.** A commentary column with one block and a large gap below it
  is not minimalism; it is an unanswered question about what else the reader needs. Either fill it
  or narrow the column.

The test: put your graphic beside an existing one from the same family and ask **what the other one
tells a reader that yours does not.** If you have no sibling to compare against, you are also
deciding the family's conventions, and should write them down.

## 4. Check the claims, not just the pixels `[core]`

Walk the questions from [`numbers-and-claims.md`](numbers-and-claims.md):

- If the dataset were refreshed tonight, which printed number would be wrong tomorrow?
- Which quantity appears twice, and do both appearances have one origin?
- What would a reader conclude from the end of this series, and is that conclusion supported?
- Which single sentence, removed, would let an honest reader be wrong — and is it on the canvas?

## 5. Check it without colour `[core]`

View the graphic in greyscale. Every distinction that mattered in colour must still be readable.

This takes seconds and is precisely a **hue-reliance test**: it tells you whether meaning survives
without colour, which is what greyscale printing and severe colour vision deficiency do to it. If
the graphic collapses, the fix is a second channel (see
[`encoding-and-colour.md`](encoding-and-colour.md) §1), not a different palette.

It is **not** a proxy for projection or video compression, which degrade contrast, fine detail, and
small text rather than removing hue. Step 3 is what tests those, and a graphic can pass this step
and fail that one.

## 6. Check the build, if there is one `[core]`

Step through the frames in order and watch for movement. Anything that shifts between frames that
should not have shifted is a geometry failure, and it is far more visible in sequence than in any
single frame.

Confirm each revealed thing arrives complete — its label, its legend entry, and its commentary all
appear together — and that the accessibility state tracks the visual state.

## 7. Place it where it will live `[medium]`

Put the graphic into the actual container: the slide template, the page layout, the README.

This is the only step that catches the composite defects: a duplicate title, a graphic sized for a
different canvas, a colour that fights the template, an attribution band colliding with the
template's own furniture, two consecutive figures whose plots are different sizes.

## 8. Read it as a stranger `[core]`

Last, and the only one that cannot be made mechanical.

Look at the graphic as someone who has not read the brief, does not know the dataset, and has twenty
seconds. Ask:

- **What is the one thing this is telling me?** If you cannot say it in a sentence, the graphic is
  carrying more than one argument.
- **What would I wrongly conclude?** The honest answer usually names a missing caveat or an
  under-marked region.
- **What do I have to already know to read this?** Everything on that list is either added to the
  graphic or deliberately delegated to the speaker, the caption, or the surrounding prose — and
  "deliberately" means written down in the brief, not assumed.

---

## Before you repoint `latest`

`latest` is the only thing a consumer references, so repointing it is the moment of publication. By
that point: every frame rendered, every frame inspected at full size, the final frame inspected at
delivery size, the claims checked, the composite checked in its container.

A version directory is immutable. If you find a defect after repointing, you fix it in the next
version — you do not edit a published one.

## Related

- [`numbers-and-claims.md`](numbers-and-claims.md) — the four questions in step 4.
- [`encoding-and-colour.md`](encoding-and-colour.md) — the second channel step 5 tests for.
- [`progressive-builds.md`](progressive-builds.md) — what step 6 is checking.
- [`source-credit.md`](source-credit.md) — what the attribution band should contain when you inspect it.
