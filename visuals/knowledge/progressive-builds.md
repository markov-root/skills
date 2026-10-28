# Progressive builds

Graphics revealed in stages: one source, several frames, read in order.

---

## 1. Frames of one graphic stay consistent `[core]`

**Rule.** The frames of a staged graphic never disagree with each other about a shared fact. A
correction to something they have in common reaches all of them.

**For an authored render, the way to guarantee that is one source** `[style: authored]`: one file
rendered at several parameterised states, never several copied files that drift.

Copied frames are the defect this rule exists to prevent, and the drift is always the same: a
correction lands in one frame and not in its siblings, and nobody notices, because each file looks
internally consistent.

The parameter belongs in the URL or an equivalent render-time input, so that a frame manifest can
name each frame and a renderer can produce all of them from one place.

## 2. Validate the frame parameter against an allowlist `[core]`

**Rule.** The set of valid frame states is declared, and a value outside it is an error, not a
silently-ignored input that renders something plausible.

An unrecognised stage that falls through to a default produces a frame that looks correct, carries
the wrong content, and passes every check. Rejecting it loudly costs three lines.

## 3. Declare what a bare render produces `[core]`

**Rule.** Rendering the source with no frame parameter produces a defined frame, and which frame
that is, is a decision you record rather than inherit.

Both answers are defensible. The first frame is the natural opening; the complete build is the
natural "the whole graphic". What is not defensible is not knowing: a renderer fetching the source
bare then gets a different frame depending on which graphic it is, and a reviewer looking at "the
graphic" sees a different thing than the author meant.

> **Attributed example.** The reference corpus splits roughly half and half between defaulting to
> the first frame and defaulting to the final complete build, with no stated rule and no per-visual
> record of the choice. Its mining report flags this as the clearest case of an unstated convention
> that a renderer can trip over.

## 4. Separate _staging_ from _switching_ — they have different rules `[core]`

This is the distinction that most often goes unstated, and getting it wrong produces either a
needlessly rigid graphic or a jumpy one.

**Staging** adds to a scene. Each frame is the previous frame plus something. The reader is
accumulating a picture, and the thing that makes accumulation legible is that **everything already
on the canvas stays exactly where it was**.

**Switching** replaces a scene. Each frame is an independent view of the same subject. The reader is
being shown alternatives or sequential episodes, and the thing that makes switching legible is a
**persistent frame of reference** — a shared spine, a constant header, a fixed outer geometry — so
the reader knows they are still in the same graphic.

Both are legitimate. A graphic should be one or the other, and should say which.

### If you are staging `[core]`

- **Geometry does not move.** Elements that will appear later occupy their final position from the
  first frame and are revealed, not inserted. A legend entry, an annotation, and a commentary block
  belonging to a later stage all hold their place from the start.
- **Reveal by visibility, not by layout.** Changing opacity or visibility leaves the layout
  untouched. Inserting an element reflows everything after it, and the reader sees the whole graphic
  twitch.
- **A revealed thing arrives complete.** When a series appears, its direct label, its legend entry,
  and its line in the commentary appear with it. A series that appears one frame before its label is
  a frame in which the reader does not know what they are looking at.
- **Text inside a held box may change.** The rule is that the _box_ stays; the words in it may be
  rewritten between stages. This is the practical form of "geometry does not move" and it is more
  permissive than the strict reading.

### If you are switching `[style]`

- **Hold the outer geometry fixed** even though the inner scene changes, so the frames read as one
  graphic.
- **Keep a persistent element across every frame** — a spine, a rail, a header, a running axis — that
  tells the reader where they are.
- **State the stability contract you actually honour.** "Geometry is stable within each pair" is a
  true and useful contract. "Geometry never moves" asserted over a graphic that swaps scenes is not,
  and it misleads anyone comparing frames.

## 5. Flip accessibility state with visibility, in the same step `[medium: interactive]`

**Rule.** When a stage hides content visually, the same operation hides it from assistive
technology; when a stage reveals it, the same operation exposes it.

A frame where content is invisible but still announced is a frame that reads correctly and sounds
wrong. Because the reveal is usually a single attribute or class change, the accessibility state has
to be flipped in the same place or it will be forgotten.

Content revealed by dimming rather than full concealment is a deliberate exception: if the hidden
state is still part of the argument — absence the reader is meant to perceive — then it is present,
and should be present to assistive technology too.

**Where the deliverable is a flat image** there is no accessible document to manage, and this rule
does not apply as written. The obligation it serves does: each delivered frame needs an accessible
description stating what that frame shows, carried wherever the image is published.

## 6. Make the render reproducible on purpose `[core]`

**Rule.** A published frame can be reproduced from its recorded inputs. What "reproduce" means
depends on the engine, and conflating the two is a mistake:

- `[style: authored]` An authored render is **deterministic**: re-rendered tomorrow on another
  machine from the same inputs, it produces the same pixels. This is engineered, not hoped for, and
  it is what makes a receipt's content hashes a checkable statement rather than a belief.
- `[style: generative]` A generative image is **stochastic** and cannot be reproduced pixel-for-pixel.
  Its reproducibility obligation is provenance — prompt, model, parameters, and lineage recorded in
  the receipt — and its verification is a human looking at it.

The rest of this section is the authored case.

The recurring sources of non-determinism, each with a cheap fix:

| Source                                    | Fix                                                               |
| ----------------------------------------- | ----------------------------------------------------------------- |
| Randomised placement, jitter, or sampling | Seed it explicitly, with the seed recorded in the source          |
| Dates parsed or formatted in local time   | Parse and format in one fixed timezone throughout                 |
| Data fetched from the network at render   | Snapshot locally; render from the snapshot; never fetch at render |
| Cached responses of a local fetch         | Request without cache, so a stale response cannot substitute      |
| Animation or transition still in flight   | Signal readiness only after declared transitions have settled     |
| Fonts not yet loaded at capture           | Gate readiness on font loading                                    |

## 7. Signal readiness explicitly; pick one convention and keep it `[core]`

**Rule.** A graphic that does anything asynchronous — loading data, loading fonts, resolving a
component — tells the renderer when it is ready, rather than letting the renderer guess with a timer.

A fixed time budget is a race: too short and the graphic is captured half-built, too long and every
frame costs the worst case. An explicit signal is correct and faster.

**A frame is ready when everything it needs has landed** — data, fonts, and any component that
resolves asynchronously. Readiness asserted before the attribution component has resolved produces a
frame with a blank or half-built footer.

Choose one signal convention per project and use it everywhere. Several conventions in one corpus
means tooling must know which graphic uses which, and the one that gets forgotten renders by timer.

> **Attributed example.** The reference corpus practises three conventions — two differently-named
> readiness attributes and, in fourteen masters, no signal at all — none of them stated. Its mining
> report names this as the convention most in need of one decision.

---

## Related

- [`composition.md`](composition.md) — the layout that staging must hold still.
- [`annotation.md`](annotation.md) — why annotations are anchored to a fixed position rather than to
  a data point, which is what lets them hold position across stages.
- [`numbers-and-claims.md`](numbers-and-claims.md) — derived figures, which keep per-stage commentary
  honest when the data moves.
