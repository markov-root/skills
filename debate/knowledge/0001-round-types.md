---
schema_version: 2
id: 0001-round-types
uid: knowledge-0001-round-types
title: Debate rounds & phases — catalog, dependencies, and paired referee checks
role: knowledge
status: current
summary: The round/phase catalog behind the config-driven debate pipeline, with ordering constraints, passes, and paired referee checks.
created: 2026-07-26
updated: 2026-08-11
---

# Debate rounds & phases — catalog, dependencies, and paired referee checks

> Reference for the config-driven pipeline (ADR-0011) — the **protocol** axis of ADR-0012, encoded by
> the evidence-based protocol recorded by the Debate project. The executable schemas ship under
> `assets/schemas/`.
>
> **Vocabulary (ADR-0012, authoritative).** _voice_ = one participant (backend + optional persona);
> **round** = the config unit — the opening `propose`, or a `review → revise` cycle; **phase** = a
> round's atomic model call(s) — the rows in §1 (`propose`/`critique`/`revise`/`respond`/`aggregate`),
> a fan-out or single voice, each getting a `round-N-<phase>` artifact dir; **reviewer** = who performs
> a round's review (`peers` blinded-symmetric | `adversary` a dedicated dialectical voice |
> `panel-as-adversary`) — which is why "red-team" is a _reviewer_, not a separate type; **plan** = the
> ordered rounds = the protocol (lives in `configs/profiles/`). The §1 table lists **phase types**; a
> `redteam` phase is a `review` with `reviewer: adversary`, and `respond` is the `revise` after one.
> ("Round" in the §1 column heading is legacy — read it as **phase**.)

## 1. Round types

Each round has a **role**, an **actor** (who runs it), a **shape** (fan-out across proposers, or a
single voice), and a **precondition** (what must already exist in the debate).

| Round         | Role                                                                                                                       | Actor          | Shape                                        | Precondition                                  |
| ------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------- | -------------------------------------------- | --------------------------------------------- |
| **propose**   | Independent generation of an option set — the field the debate starts from.                                                | all proposers  | fan-out, **no peers shown** (anti-anchoring) | none — **must be first**                      |
| **critique**  | Blinded cross-examination: each voice steelmans/attacks peers' sets.                                                       | all proposers  | fan-out, sees blinded peers                  | `propose`                                     |
| **revise**    | Each voice refines its OWN set given the full discussion (consensus not required).                                         | all proposers  | fan-out                                      | `critique`                                    |
| **redteam**   | Adversary attacks the near-final field; in the _proposing_ variant may also add a NEW option (ADR-0028).                   | red-team voice | single                                       | a panel field (`revise` or a prior `respond`) |
| **respond**   | The panel concedes or defends against the findings — advocacy answering the adversary.                                     | all proposers  | fan-out                                      | `redteam` **or** `escalate`                   |
| **escalate**  | Red-team LICENSED TO PROPOSE on the contested subset — the breadth mechanism that surfaces options no proposer thought of. | red-team voice | single, **dynamic** (may repeat)             | a prior `respond` **and** a contested focus   |
| **aggregate** | Arbitrator merges/selects the final set from the blinded field (Delphi); or runs the PERT/opinion-pool math (IDEA).        | arbitrator     | single                                       | the last panel round — **must be last**       |

Advocacy (proposers, red-team) stays separate from judgment (arbitrator): the arbitrator only ever
runs `aggregate`, and sees the field **blinded**, so it never knowingly adjudicates its own voice.

## 2. Ordering constraints (the dependency graph)

```
propose → critique → revise → [ redteam → respond ]* → aggregate
                                    ↑         │
                                    └ escalate ┘   (dynamic: repeats on the contested subset)
```

Hard rules the plan validator enforces:

1. **`propose` is the mandatory opener** (index 0); **`aggregate` is the mandatory closer** (implicit
   if omitted). A plan cannot start with `critique` or end before aggregation.
2. **`critique` requires `propose`; `revise` requires `critique`.** These three are the **floor**
   (`min` defaults to 3) — the cheapest complete debate.
3. **`respond` never stands alone** — it must be preceded by an attacker (`redteam` or `escalate`)
   in the same pass (§3). An attack with no rebuttal before aggregation is disallowed.
4. **`escalate` requires a prior `respond` and a non-empty contested focus**; it is only reachable
   when a red-team voice is configured and the plan is `dynamic`.

## 3. Passes — rounds that auto-fire together

Some rounds are meaningless alone and are declared as one unit (a **pass**). The engine expands a
pass into its rounds; you enable/disable the pass, not the halves.

| Pass            | Expands to                    | When                                                      | Repeats?                                                                                                                  |
| --------------- | ----------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **floor**       | `propose · critique · revise` | always (the minimum debate)                               | no                                                                                                                        |
| **adversarial** | `redteam · respond`           | optional; a red-team voice is configured and not `--lean` | no (one standard pass)                                                                                                    |
| **escalation**  | `escalate · respond`          | `dynamic: true`; runs on the contested subset             | **yes**, until a stop rule fires (novelty-exhausted / no contested focus / `max` cap / token budget) — never on agreement |

`aggregate` is appended automatically as the closer; it is not part of any pass.

## 4. Referee checks paired with rounds

Referee checks are cheap, deterministic functions that emit FACTS (never verdicts) injected as a
`FLAGS` block into the _next_ round, so the panel spends its reasoning on the residue, not on things
code can compute (ADR-0011 §referees; the mechanism is task-0013). Each check has a natural
**injection point** and is individually **toggleable** in config.

The config key for each injection point is the **`referees:` sub-key** an engine round reads — the
engine calls exactly two: **`before_revise`** (after `critique`) and **`before_respond`** (after
`redteam`). A wrong injection point (for example the old `before_critique`) or unknown checker name
fails during `cost`/`run`; it cannot silently fall back to a different set.

| Check                  | Default injection point       | What it flags                                                                                                                              |
| ---------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `near_duplicate`       | before_revise; before_respond | two options that are the same argument (token overlap ≥ τ) → merge/differentiate (MECE)                                                    |
| `non_atomic`           | before_revise; before_respond | an option bundling ≥2 distinct claims → split                                                                                              |
| `thin_rationale`       | before_revise; before_respond | a rationale below a length/《because》floor → justify or cut                                                                               |
| `unaddressed`          | before_respond                | a red-team finding no revision answered → must answer it                                                                                   |
| `overreach`            | before_respond                | a red-team claim that over-reaches the evidence → don't concede more than warranted (task-0020)                                            |
| `ungrounded_quote`     | respond (grounding)           | a cited quote not verbatim in the item/materials → fix or drop **(fed in via the grounding referee; auto-OFF in `search` mode, ADR-0010)** |
| `novelty_gate`         | escalate loop                 | a red-team `new_option` that duplicates an existing one → don't re-cycle it (drives the escalation stop; task-0015)                        |
| `arbitrator_invention` | after aggregate (gate)        | a final clause traceable to no proposal (Jaccard < τ) → the arbitrator selected, didn't author (ADR-0065 target)                           |

The `DelphiTask` defaults (used when the `referees:` block names nothing for a point) are
`before_revise: [near_duplicate, non_atomic, thin_rationale]` and
`before_respond: [near_duplicate, non_atomic, thin_rationale, unaddressed, overreach]`. Override by
naming a subset:

```yaml
rounds:
  min: 3
  max: 7
  plan:
    [
      propose,
      critique,
      revise,
      { pass: adversarial },
      { pass: escalation, dynamic: true },
    ]
  referees: # only `before_revise` / `before_respond` are read; each value NAMES the checks to run
    before_revise: [near_duplicate, non_atomic, thin_rationale]
    before_respond: [unaddressed, overreach]
```

> `dynamic: true` belongs on the **escalation** pass (it makes `escalate·respond` repeat until a stop
> rule); on `adversarial` it is ignored. A bare `{ pass: adversarial }` runs exactly once — list it
> more than once for multiple independent red-team passes.

## 5. How a plan is validated

At load the engine checks a plan against §2–§3: opener is `propose`, each round's precondition is
satisfied by something earlier, a `respond` has a preceding attacker, `escalate`/`dynamic` needs a
red-team voice, `min ≤ rounds executed ≤ max`. Referee names must be known checks; grounding checks
are silently skipped when the task is not `grounded()` (search mode). A malformed plan fails fast
with the offending round named — the same discipline as the materials-mode check (ADR-0010).

Every attacker must also receive a following `respond`; a second attack cannot overwrite an
unanswered one. Escalation must use `{ pass: escalation, dynamic: true }` because the runner executes
it through the bounded dynamic loop. Bounds are integers, `token_budget` is a positive integer or
null, referee selections are lists of names, and unknown mapping keys are errors.

## 6. Status

This catalog is **live** (ADR-0011, task-0017). The config-driven pipeline is wired end-to-end:
`engine/plan.py:load_plan` reads a `rounds:` block from `debate.yaml` (§3 list form — stages +
`{pass: …}` shorthands, `min`/`max`/`token_budget`/`referees`), validates it (§5), and
`engine/loop.py` iterates the resulting plan; repeated stages get unique storage keys
(`redteam` → `redteam-2`, …). Absent a `rounds:` block the engine builds `default_plan()` — the same
shape (`floor` + one `adversarial` pass + a dynamic `escalation` pass that only fires once `max` > 5).
The referee layer (task-0013), red-team-proposes as a first-class round (task-0014), and the novelty
gate (task-0015) are all in place. The `debate.yaml`-facing view of this block lives in
the generated schemas under `assets/schemas/` and the simple surface in `SKILL.md`.
