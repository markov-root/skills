# visuals knowledge — index

Guidance for **producing** an explanatory graphic. Read the files this index routes you to; do not
read them all. Nothing here is executed by a command, and nothing here is a gate.

## How to use this, and what it is not

**Your project outranks this knowledge.** Where a project states a rule — in its own visual system,
its `BRIEF.md`, or its `visuals.toml` — the project wins, always. What is written here is the
default for a project that has not decided, and the vocabulary for one that is deciding. It is not a
house style and you are not obliged to adopt it.

**No command enforces any of it.** `validate` blocks on exactly four conditions, all of them
correctness defects that make an artifact broken regardless of taste; every aesthetic finding is
advisory and project-selected, and no command ranks, scores, or grades a design (ADR 0004, ADR
0007). If a rule here and a gate ever seem to agree, that is a coincidence of wording, not a
mechanism — and a gate that enforced a rule here would be a defect to report.

## Every rule states its level

A rule is true at exactly one of three levels, and says which (ADR 0008). Reading a rule without its
level is how a line-chart convention becomes a mandate for a diagram.

| Level      | True of                                                                  | Decided by                       |
| ---------- | ------------------------------------------------------------------------ | -------------------------------- |
| **core**   | any explanatory graphic, any medium, any style                           | this knowledge                   |
| **medium** | graphics read in one place — slide, paper figure, README, poster         | your canvas and delivery context |
| **style**  | a named family within one project — chart, matrix, fact slide, schematic | your project, per family         |

**Medium and style are orthogonal, not nested.** A line chart in a textbook and a line chart on a
slide share their encoding rules and differ on canvas, titling, and whether staged builds exist at
all. A rule here tagged `[style]` describes a shape a family _may_ take; it is never a rule you
inherit by default, because the skill declares no styles (ADR 0008 §2). Your project declares them.

## Every rule states its authority

A rule is either:

- **attributed** — "the reference corpus adopts X". That is a record of one project's deliberate
  choice, evidenced in its own work. It is not a claim that X is correct in general, and a different
  project may reasonably choose otherwise; or
- **sourced** — it asserts an external standard, and carries a row in
  [`../references/SOURCES.md`](../references/SOURCES.md).

A rule with neither does not belong here. If you find one, that is a defect in this knowledge, not a
rule you should follow. **An unsourced number is worse than a missing one**: prefer naming, with
attribution, what a real corpus actually does, over stating a minimum nobody can trace.

**No colour, typeface, or measurement ships as a default.** Where a specific value appears it is an
_attributed example_ — marked as one, drawn from a named corpus, and binding nobody. If you could
mistake it for a default, that is a defect to report. The value you use comes from your project's
theme and declared style.

## Routing

| Read this                                          | When you are…                                                                                        |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| [`numbers-and-claims.md`](numbers-and-claims.md)   | putting any figure on a graphic — **read this one first, and read it even if you read nothing else** |
| [`composition.md`](composition.md)                 | choosing a canvas, laying out chart against commentary, or deciding where anything sits              |
| [`progressive-builds.md`](progressive-builds.md)   | building a graphic revealed in stages across several slides                                          |
| [`encoding-and-colour.md`](encoding-and-colour.md) | choosing a chart form, assigning series colours, or building a legend                                |
| [`annotation.md`](annotation.md)                   | labelling series or data points, or resolving label collisions                                       |
| [`axes-and-sidebar.md`](axes-and-sidebar.md)       | naming axes and units, or writing the commentary that sits beside the chart                          |
| [`source-credit.md`](source-credit.md)             | attributing data, placing logos, or handling a licence                                               |
| [`release-check.md`](release-check.md)             | deciding whether a graphic is finished                                                               |

If you are doing something none of these covers, they do not cover it. Say so rather than stretching
the nearest rule to fit.

## The one thing that is not negotiable

A graphic must not assert more than its data supports. That is why `data snapshot` requires a
non-empty `limitations` array and offers no flag to waive it, and why the source credit carries the
shortest material method caveat rather than only a logo. Everything else in this knowledge is a
default you may override; this one is the reason the rest exists.
