---
knowledge:
  version: 1
  id: roadmap
  summary: Maintain a roadmap as an outcome- and evidence-oriented direction record rather than a speculative feature queue or delivery promise.
  routes: [new-project, requirements-acceptance-scope]
---

# roadmap.md — Strategic Direction Reference

> **Purpose:** Guidance for what a _project-level_ `roadmap.md` should contain, how it differs from a backlog or a TODO list, and how to keep it honest. **This file in the knowledge library is a template/guide; each project keeps its own roadmap.**
>
> **Read this when:** setting up a project; communicating direction to contributors or stakeholders; deciding whether something belongs on the backlog or the roadmap; auditing a project's stated direction against what it actually does.
>
> **Do NOT** confuse a roadmap with a plan. A roadmap is direction; a plan is sequence with dates. Most projects need the former and don't have the rigour to maintain the latter.

---

## The Premise

A **roadmap** answers: _where does this project want to go, and why?_ It complements:

| Doc                         | Time horizon       | Granularity                                                                                               |
| --------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------- |
| **TODO.md / Issue tracker** | Days to weeks      | Tactical, checkbox-driven                                                                                 |
| **CHANGELOG.md**            | Past (per release) | What shipped                                                                                              |
| **roadmap.md**              | Months to years    | Strategic direction                                                                                       |
| **ADRs**                    | Per-decision       | The _why_ for a specific architectural choice ([ARCHITECTURE](architecture.md))                           |
| **contributing.md**         | Always-current     | How the project is run ([CONTRIBUTING](contributing.md))                                                  |
| **Requirements/criteria**   | Per-outcome/change | What is needed and what observable boundary accepts it ([REQUIREMENTS](requirements-and-traceability.md)) |

A roadmap is **declarative**, not promissory. "We want X" is different from "X will ship on date Y."

---

## What a Roadmap Should Contain

| Element                           | Detail                                                                       |
| --------------------------------- | ---------------------------------------------------------------------------- |
| **Vision** — one paragraph        | What does the project want to be when it grows up?                           |
| **Non-goals**                     | What this project will deliberately _not_ become — as important as the goals |
| **Horizons** (now / next / later) | Uncertainty-aware buckets; externally committed dates link to an owned plan  |
| **Themes / pillars**              | Two to five recurring directions (performance, ecosystem, ergonomics, etc.)  |
| **What motivates each item**      | The principle, code area, or constraint that justifies it                    |
| **Open questions**                | What's not yet decided; what's blocked on what                               |

What a roadmap should **not** contain:

- Unsupported precision. Regulatory, contractual, event, or migration deadlines are legitimate;
  record owner, confidence/range, dependency, source, and review trigger in the roadmap or linked
  delivery plan.
- Marketing copy.
- Items at task granularity (those belong in the backlog).
- Decisions that already happened (those belong in ADRs / CHANGELOG).

---

## The Bucket Model — Now / Next / Later

A robust default uses horizons; add dates only where there is a real commitment or constraint:

| Bucket    | Meaning                                                                     |
| --------- | --------------------------------------------------------------------------- |
| **Now**   | Actively being worked on; committed; reasonably high confidence on shipping |
| **Next**  | Planned soon; some prep done; specifics may shift                           |
| **Later** | Direction is right; details TBD; will be re-evaluated when "next" finishes  |

Horizons are honest about uncertainty. A date can be honest too when its source, confidence,
dependencies, and update process are visible.

---

## A Template

```markdown
# Roadmap

> Where this project wants to be long-term, and why. Complements TODO.md (tactical)
> and CHANGELOG.md (historical). Items are bucketed by horizon, not by priority within.

## Vision

One paragraph: what this project is becoming.

## Non-goals

What this project will deliberately _not_ become.

## Themes

- **Theme A** — short description
- **Theme B** — short description

## Now

- **Item** — motivation; links to issues / PRs

## Next

- **Item** — motivation; what would unlock it

## Later

- **Item** — motivation; current uncertainty

## Open questions

- What's not yet decided
```

---

## Maintenance Discipline

Like every doc, the roadmap rots without discipline.

| Cadence              | Action                                                                                            |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| **Per PR**           | Reviewer asks: does this change shift the roadmap?                                                |
| **Per release**      | Update CHANGELOG; reconcile shipped items against roadmap; promote / demote buckets               |
| **Quarterly review** | Re-read the whole roadmap. Stale items demoted, irrelevant items removed, new themes acknowledged |
| **On scope change**  | Update non-goals; update vision if needed                                                         |

**A roadmap that hasn't been touched in a year is fiction.** Either it's being followed, or it's wrong.

---

## Roadmaps for Open-Source Projects — Honesty First

For open-source projects, the roadmap is also a contract with contributors. Discipline:

- **Be honest about maintainer capacity.** "We'd like to" ≠ "this is happening." Mark items accordingly.
- **Be clear about what you'll merge and what you won't.** Saves contributors wasted work.
- **Flag stability** of roadmap items (firm direction vs exploratory).
- **Don't promise what depends on others** without acknowledging the dependency.

---

## Anti-Patterns

| Pattern                                            | Why it fails                                                               |
| -------------------------------------------------- | -------------------------------------------------------------------------- |
| **Date-driven roadmaps without process to update** | False precision; trust erodes when dates slip                              |
| **Roadmap is a marketing document**                | Optimistic; bears no resemblance to engineering reality; loses credibility |
| **Roadmap = backlog**                              | Two different things at different granularities                            |
| **Items added but never removed**                  | Becomes a wishlist; signal-to-noise crashes                                |
| **Stale roadmap**                                  | Worse than no roadmap; readers extract wrong direction                     |
| **Hidden roadmap**                                 | Direction is decided but unwritten; people work cross-purposes             |
| **Roadmap that contradicts CHANGELOG**             | Shipped work doesn't match stated direction; one is wrong                  |

---

## Diagnostic Framework

| Symptom                                                   | Likely cause                                                |
| --------------------------------------------------------- | ----------------------------------------------------------- |
| Contributors propose work outside the project's direction | Roadmap doesn't exist, isn't read, or isn't enforced        |
| Roadmap items year-old                                    | Maintenance discipline missing; quarterly review absent     |
| Roadmap and CHANGELOG diverge                             | One is wrong; reconcile each release                        |
| Stakeholders surprised by direction                       | Roadmap not communicated; or not honest                     |
| Team works on items not on the roadmap                    | Either the roadmap is wrong, or scope discipline is missing |

---

## Meta-Question

A roadmap is the answer to: _if a new contributor or stakeholder reads this in five minutes, do they understand where the project is heading and what it's deliberately not doing?_ If yes, the roadmap is doing its job. If no, the roadmap is decoration.

---

_See [INIT](init.md) for the day-0 scoping that the vision descends from._
_See [CONTRIBUTING](contributing.md) for the always-current per-project record of decisions._
_See [DOCUMENTATION](documentation.md) for the broader doc-organisation discipline._
_See [GIT_AND_VERSIONING](git-and-versioning.md) for the CHANGELOG that complements this._
