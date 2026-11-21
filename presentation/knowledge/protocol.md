# Protocol: the order of work, and what locks when

A talk moves through six stages. Each one produces something the next stage reads, and each
**locks** before the next stage is built on it. A lock is not a freeze: a locked thing can still
change, but the change is a deliberate, recorded act.

| # | Stage | Produces | Locks when |
| --- | --- | --- | --- |
| 1 | **Brief** | `audience/talk.yaml`, `promised.md`, `correspondence/`, `materials/` | the facts carry their sources |
| 2 | **Outline** | `docs/0001-outline.md`: beats per module, each with a time budget and a reason | the maintainer signs it off |
| 3 | **Claims** | rows in `research/claims.md`, notes in `research/notes/` | each load-bearing statement in a beat has a row |
| 4 | **Script** | `modules/<m>/script/src/script.md` and `annotations.yaml`, then versions | an approved version exists |
| 5 | **Visuals and deck** | `visuals/<slug>/`, `modules/<m>/deck/` | an approved deck version, built from an approved script version |
| 6 | **Delivery** | `delivery/<date>.yaml` | written once, never edited |

## Rules

- **Never build on an unlocked stage.** Do not draft prose against an unsigned outline, and do
  not draw a visual for a beat that may still move. Steps overlap in practice; dependencies do not.
- **The outline locks before prose.** A beat states what it proves and why it sits where it sits
  in the module's argument. Each step of the argument answers the previous step's question.
- **Facts live once.** A date, a slot, a contact or an audience size lives in `talk.yaml`, with a
  `source` pointing at the evidence in `audience/`. READMEs are generated from it
  (`present talk readme`). Never restate a fact in a handoff or a README by hand.
- **Records, not root files.** Continuation state goes in `docs/handoffs/` (exactly one current),
  decisions in `docs/adr/`. There is no root-level `HANDOFF.md` or `OUTLINE.md`.
- **Timing is advisory.** Report minutes as information. Never garble an explanation or cut a
  sentence mid-thought to fit a slot; if a module is long, the outline drops a beat.
- **End every working session** by superseding the talk's handoff with a new one, then running
  `present validate`.

## Commands by stage

| Stage | Commands |
| --- | --- |
| 1 | `present talk new`, `present talk status`, `present talk readme` |
| 3 | `present claims list`, `present claims check` |
| 4 | `present script new`, `script check`, `script annotate`, `script bump`, `script approve` |
| 5 | `present visual …`, `present deck …`, `present components gallery` |
| 6 | `present delivery record`, `present delivery list` |
| any | `present validate`, `present doctor`, `present explain <command>` |

`[enforced: present validate]` layout, schemas, receipts, approvals and one current handoff.
