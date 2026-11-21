# Working with the visuals skill

The `presentation` and `visuals` skills are designed to be used together, with a strict division
of labour. This page explains who owns what and the exact path from a drawn graphic to a slide.

## Who owns what

| Concern                                                                           | Owner                                        |
| --------------------------------------------------------------------------------- | -------------------------------------------- |
| The talk, script, deck, claims, delivery, and when a visual is needed             | `presentation` (`present`)                   |
| Drawing an HTML graphic, rendering it to PNG frames, versioning and publishing it | `visuals`                                    |
| Placing a published visual on a slide and recording which version was used        | `presentation`                               |
| The shared palette and type (one token file)                                      | the consumer repository; both skills read it |

`present` never re-implements visuals. It runs the `visuals` command inside the talk's visuals
project and reads `visuals index --json` to resolve versions. If `visuals` is not installed,
`present` reports `capability_unavailable` rather than guessing.

## When to use a visual at all

Native first (see [`deck-standard.md`](deck-standard.md)):

- Charts and diagrams (timelines, chains, step boxes, flows, comparisons, grids) are native deck
  components. A rendered image of something a component could draw is a regression.
- Use a `visuals` graphic **only for what native shapes cannot draw**: illustrations, sketches,
  genuinely complex diagrams, or a map's geometry (its labels and legend stay native text).
- Draw it only once the script's beats are locked (protocol step 5); a visual for a beat that may
  still move is wasted work.

Because the visuals theme is generated from the same token file as the deck, an HTML visual and
the native slides share one palette.

## Layout

Each talk has one visuals project in `<talk>/visuals/`. The first `present visual new` adopts it
by running `visuals init` there (its parent holds `audience/talk.yaml`) and writes the brand theme
generated from the token file. The resulting `visuals.toml` that keeps each graphic in
`<talk>/visuals/<slug>/` and joins every module's `modules/*/deck/deck.yaml`, so `visuals`
can check which versions the decks pin.

## From graphic to slide

```sh
present visual new <slug> [--talk <talk>] [--kind diagram|figure|poster|presentation]
# edit the graphic's source (HTML/CSS/data) in <talk>/visuals/<slug>/
present visual render <slug> [--talk <talk>]           # render PNG frames into a new immutable version
present visual publish <slug> <vX.Y.Z> [--talk <talk>] # make that version the published `latest`
present visual show <slug> [--talk <talk>]             # published version, frames, and the pin to use
```

Then, in the module's `deck/deck.yaml`, pin the visual and place it on a slide:

```yaml
visuals:
  <slug>: latest # or an exact published version, e.g. 1.2.0, to hold it still
```

and reference it from `src/slides.yaml` as `@visual:<slug>` (first frame) or
`@visual:<slug>/<frame>` (a named frame). A slide that references an unpinned visual, a missing
frame, or a version with no PNG frames fails the build with a message naming the problem.

## Versions and pins

- `latest` resolves to the **published** version. `visuals render --unpublished` can create newer
  versions for review without moving what decks see.
- An exact pin must exist and be published; `visuals` reports pins to absent or unpublished
  versions as advisories when it joins the decks.
- The deck receipt records the exact visual version each build used, so a delivered deck can be
  traced back to the graphic that produced it.
- A visual from another talk can be pinned by its repository-relative path
  (`<other-talk>/visuals/<slug>`); `visuals` lists it as external.

## Reuse across talks

A graphic used by more than one talk belongs in the repository's `library/`, not copied:
`present library promote <talk>/visuals/<slug>` moves it and rewrites the pins to
`library: {<slug>: <selector>}`. Retiring a library visual (`retired: true`) makes
`present validate` block talks that still pin it.

## Division of checks

- `visuals check`, `measure` and `validate` judge the graphic itself (geometry, fonts, contrast
  candidates, render receipts).
- `present deck` and `present validate` judge its use: pinned, published, placed, and native-first.
