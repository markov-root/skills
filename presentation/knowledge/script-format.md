# Script format: spoken words only

A script holds only what will be said. Everything else stands off beside it.

## `src/script.md`

```markdown
## firefox-fixes

In April, the browser's maker fixed 423 security bugs, and 271 of them were found by one AI model.
That is almost two out of every three.

## next-slide-id

…
```

- **Headings are slide IDs.** Every section is `## <slide-id>`: kebab-case, unique, and the same
  ID the deck's `slides.yaml` uses. Speaker notes key on it, so reordering slides never
  renumbers anything. `[enforced: present script check]`
- **No markers of any kind.** That means no `[Slide 3]`, `[C-07]`, `[CLAIM]`, `[ON SCREEN …]`,
  `[pause]`, HTML comments, block quotes, tables, lists or code. If you would not say it out loud,
  it does not go in this file. `[enforced: present script check; script bump refuses]`
- **No text before the first heading**, and no other heading levels.
- A long script may be split into several `src/` files, listed in order under `sections:` in
  `script.yaml`.

## `src/annotations.yaml` — everything unspoken

Each entry is anchored to a slide and a **quoted span** of the spoken text, following the W3C Web
Annotation TextQuoteSelector pattern:

```yaml
- slide: firefox-fixes
  quote: "271 of them"
  kind: claim            # claim | note | cue
  claim: C-12
- slide: firefox-fixes
  quote: "almost two out of every three"
  kind: claim
  claim: C-12
  licence: "rounded from 64% for the room"   # a deliberate simplification
- slide: firefox-fixes
  quote: "fixed 423 security bugs"
  kind: note             # appears in notes.md and the deck's speaker notes
  text: "Source: the maker's security advisories, April."
- slide: next-slide-id
  quote: "…"
  kind: cue              # a delivery cue: pause, look up, click
  text: "Pause."
```

- **Quote the exact words**, short but unique within the slide. If the phrase occurs twice, add
  `prefix` or `suffix` (the words just before or after) rather than lengthening the quote.
- **Resolution** tries an exact match first, then a match that ignores case, punctuation and line
  breaks. The result is `resolved`, `ambiguous` or `orphaned`.
- **After a rewrite,** run `present script annotate`. Orphans come with a suggested new span.
  Accept a suggestion by editing `annotations.yaml` yourself; nothing is re-anchored
  automatically.

## What a version contains

`present script bump` writes:

- `script.md`;
- `annotations.yaml`;
- `speaking.md`: the same words, with headings as reading labels, which is what the speaker reads;
- `notes.md`: per slide, the spoken text plus its notes and cues, which is what the deck's speaker
  notes hold;
- `annotations.json`: the resolved anchors.
