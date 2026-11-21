---
name: presentation
description: >-
  The presentation standard for building talks — briefs, claims, spoken scripts, native pptx
  decks, visuals and delivery records — and the `present` CLI that enforces it: talk scaffolding
  and discovery, a versioned artifact store, scripts with stand-off annotations, an advisory
  claims check, native decks from slides.yaml through a token-driven component library with a
  gallery and diff, delivery records and `present validate`. Declared-but-unbuilt commands exit 3
  (`present explain` says which). Use when creating or inspecting a talk, versioning or approving
  a script or deck, checking claims against a ledger, building a deck, or validating a talk.
  Not for voice or drafting (that is writing) or graphic rendering (that is visuals).
license: Apache-2.0
compatibility: >-
  Requires Python 3.11+ and uv (the launcher resolves PyYAML and jsonschema on first run; a
  cold offline run cannot). LibreOffice is needed only once deck building ships.
metadata:
  version: "0.7.2"
---

# presentation

The **presentation standard** says how a talk is built and recorded: brief → outline → claims →
script → visuals and deck → delivery. This skill owns the standard and the `present` CLI that holds
it. A consumer repository owns only its configuration (`presentations.toml`), its brand tokens,
its library and its talks.

**Built incrementally.** `present explain` marks each command as built or declared. A declared
command explains itself and exits `3`. Never report a declared command as working.

## Run it

`<skill-root>` is the directory holding this file. Every command takes `-j` for one JSON envelope
(`present.command-result` v1).

```sh
<skill-root>/scripts/present doctor                      # prerequisites, neighbours, repository in view
<skill-root>/scripts/present explain [<command>]         # the whole surface, with effects
<skill-root>/scripts/present talk new --format <online|onsite|hybrid> --occasion <o> --country <c> [--dry-run]
<skill-root>/scripts/present talk list | talk status [<talk>] | talk readme [--check]
<skill-root>/scripts/present script new <talk>/<module>
<skill-root>/scripts/present script check [<ref>]        # format, anchors, claims, re-voice preservation
<skill-root>/scripts/present script annotate [<ref>]     # anchor resolution, orphans, suggestions
<skill-root>/scripts/present script bump [<ref>] --level patch|minor|major --note "…"
<skill-root>/scripts/present script show [<ref>] [--version V] [--verify]
<skill-root>/scripts/present script approve [<ref>]      # needs a version built from committed src/
<skill-root>/scripts/present claims check [<talk>]       # advisory tiers; --ledger/--script for legacy files
<skill-root>/scripts/present claims list [<talk>]
<skill-root>/scripts/present deck new <talk>/<module>        # deck.yaml + a working src/slides.yaml
<skill-root>/scripts/present deck check [<ref>]              # slide IDs vs script headings; argument errors
<skill-root>/scripts/present deck build [<ref>] --note "…" [--dry-run]   # pptx + PDF + contact sheet, pinned
<skill-root>/scripts/present deck build [<ref>] --dry-run --out ~/.cache/present/preview/<deck>   # a look before a version: full-size pages
<skill-root>/scripts/present deck approve [<ref>]            # needs an approved script version
<skill-root>/scripts/present components gallery [--tokens F] [--out DIR] | components diff OLD NEW [--out DIR]
<skill-root>/scripts/present visual new|render|publish|show <slug>   # delegates to visuals; pin in deck.yaml, place with @visual:<slug>
<skill-root>/scripts/present library list|show|bump|promote        # reusable slides/visuals; pin with use: library/slides/<id>@<sel>
<skill-root>/scripts/present claims pin [<talk>] [--apply]          # record exact research:/dataset: versions in the ledger
<skill-root>/scripts/present lesson new|route|list                  # a proven finding → its owning layer (ADR 0012)
<skill-root>/scripts/present delivery record [<talk>] [--date D] [--materialize DIR]
<skill-root>/scripts/present validate [--talk T | --all] # blocking findings = contract violations
<skill-root>/scripts/present schema check <file>         # validate one standard file
```

- **Exit codes:** `0` ok, `1` error (including blocking findings), `2` usage, `3` declared but
  not implemented.
- **Effects:** every command declares whether it reads, writes, uses the network or spends money.
  Check with `present explain <command>` before running anything that writes.
- **Discovery:** `present` finds the repository by walking up to `presentations.toml`, and the
  talk or artifact from the working directory. It never counts parent directories.

## Route to the knowledge you need

| Task | Read |
| --- | --- |
| Starting a talk, or deciding what comes next | [`knowledge/protocol.md`](knowledge/protocol.md) |
| Versions, semver levels, pins, approval, delivery | [`knowledge/artifact-contract.md`](knowledge/artifact-contract.md) |
| Writing or editing a script file | [`knowledge/script-format.md`](knowledge/script-format.md) |
| What the spoken words must do; loading the voice | [`knowledge/script-standard.md`](knowledge/script-standard.md) |
| Claims, the advisory tiers, licence | [`knowledge/claims.md`](knowledge/claims.md) |
| Designing or reviewing a deck | [`knowledge/deck-standard.md`](knowledge/deck-standard.md) |
| Components, brand tokens, custom slides, reuse | [`knowledge/components.md`](knowledge/components.md) |
| Recording a proven improvement and routing it | [`knowledge/feedback-loop.md`](knowledge/feedback-loop.md) |

The index is [`knowledge/INDEX.md`](knowledge/INDEX.md). The schemas are in
[`assets/schemas/`](assets/schemas/) (JSON Schema 2020-12), and `present schema list` maps each one
to its file.

## Standing rules for agents

- **Scripts hold only spoken words.** Never add a bracketed marker, comment or stage direction to
  a script. Claims, notes and cues go in `annotations.yaml`.
- **Load the voice before drafting.** Use the writing skill's presentation-voice profile. Never
  invent a register.
- **Claims are advisory: flag, don't fix.** Report a concern, and never rewrite the speaker's
  framing for technical correctness unless asked. Licensed simplifications are legitimate.
- **Edit `src/`, then bump or build.** Never edit a version folder, never move `latest` by hand,
  never copy a version to make a variant.
- **Native decks.** Charts and diagrams are native components. An HTML visual is used only for
  what native shapes cannot draw.
- **Legacy talks** (listed under `[legacy]` in `presentations.toml`) follow their repository's
  older conventions. Never migrate them implicitly.
- **Never fake a pass.** A missing neighbour or prerequisite is `capability_unavailable`; say so.

## Neighbours

The skill integrates its neighbours only through their commands, and reports
`capability_unavailable` when one is missing:

- `visuals`: HTML visuals, rendering and publishing (how the two skills work together, from a
  drawn graphic to a pinned slide: [`knowledge/visuals.md`](knowledge/visuals.md));
- `writing`: the voice, and the lossless re-voice check `scripts/revoice_check.py`;
- `software-engineering`: the `engineering` record allocator and validator.
