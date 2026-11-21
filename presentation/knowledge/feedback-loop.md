# The feedback loop: lessons and who owns them

A talk is where the standard gets tested. When building or delivering one proves something, record
it once as a **lesson** in that talk, then route it to the single layer that owns it. The owner
ships it as a versioned change, and later talks pick it up through their normal pins. A talk
session never edits another layer's knowledge, components or tokens directly.

```sh
present lesson new <talk> --title "…" --target <owner> --proof explicit_user|deterministic|agent \
  --evidence <path> --observation "…" --generalisation "…" --boundary "…"
present lesson route <talk>/<NNNN>          # skill owners: files a skill-feedback note
present lesson list [<talk>|--all] [--open] # `present talk status` shows the open count
```

`[enforced: present lesson new — unknown owner, missing evidence; present lesson route — routes
once, agent-proof lessons only as ideas]`

## The proof bar

A lesson is **proven** in one of two ways, and it records which:

| `--proof` | Means | Routes as |
| --- | --- | --- |
| `explicit_user` | the maintainer's explicit verdict (correspondence, a review comment, a session note) | `idea`, `friction` or `praise`; filed as high impact |
| `deterministic` | a measurement: a before/after check, a re-voice diff, a detector precision run | `idea`, `friction` or `praise` |
| `agent` | an agent's judgment alone | `idea` only; never a rule change |

A proven lesson needs at least one evidence file inside the repository. Evidence paths are stored
repository-relative; the transport rejects home paths and private data.

## Who owns what

| `--target` | The finding is about… | Owner | Ships as |
| --- | --- | --- | --- |
| `presentation` | the standard: protocol, artifact contract, script format, claims, generic deck rules | `presentation` knowledge | a skill release |
| `components` | how a component draws, or a new generic component | `presentation` component library | a `COMPONENTS_VERSION` bump, gallery diff |
| `tokens` | a brand value: colour, font, size, logo | consumer `_shared/brand/tokens.json` | a token version bump |
| `library` | a recurring slide or visual | consumer `library/` | `present library promote` |
| `visuals` | graphic craft: encoding, annotation, composition | `visuals` knowledge | a visuals release |
| `writing-voice` | the speaker's voice, register, tone, wording habits | `writing` presentation-voice (private) | a writing release |
| `writing` | prose craft in general, or the re-voice check | `writing` knowledge or scripts | a writing release |
| `software-engineering` | records, handoffs, validation | `software-engineering` | an SE release |
| `talk` | only this talk | the talk itself | nothing to route |

Ask which layer would have to change for every future talk to get this right. A colour is a token
even when a component draws it; a component's geometry is the library's, even when one brand
exposed the flaw. When two rows fit, the finding is usually two lessons.

**Skill owners** receive a `skill-feedback` note (the shared transport) carrying the lesson's
observation, generalisation, boundary and proof, with the lesson file as evidence. The owning
skill's dev process triages it into a task.

**Consumer owners** (`tokens`, `library`) receive nothing from the transport. `lesson route` prints
the repository task to open; once it exists, `lesson route <lesson> --consumer-task NNNN` records it.

A misrouted note is re-filed by its owner, never applied where it landed, and never routed twice.

## Writing a lesson whose generalisation has a boundary

A lesson is a software-engineering `lesson` record: `Context`, `Durable lesson`, `Boundary`,
`Evidence`, `Consequence`. `lesson new` fills them from its flags. The part that decides whether it
helps the next talk is the pair of generalisation and boundary.

- **Observation** (`--observation`): what happened, concretely, in this talk. One or two sentences.
- **Generalisation** (`--generalisation`): the inference a competent author would not have drawn
  from the rule as written. Name the mechanism, not the event: "a quantitative axis states its
  unit in the label, because the audience reads the bar before the caption", not "the chart on
  slide 12 confused people".
- **Boundary** (`--boundary`): where it applies and where it must not. Name the similar-looking
  case it does not cover: "charts with a quantitative axis; not icon rows or timelines, whose
  units are in the marks".

The test: would this lesson change the owner's next decision, and would it stop that decision
spreading to a case that only looks similar? A lesson that applies everywhere changes nothing.
One that only restates this talk belongs to `--target talk`.

A lesson routed with `explicit_user` or `deterministic` proof becomes a standing record. An
agent-proof lesson stays a draft after routing: it is an idea until the maintainer or a
measurement backs it.
