---
knowledge:
  version: 1
  id: documentation
  summary: Author and maintain documentation with clear audience, authority, structure, navigation, currentness, and evidence boundaries.
  routes: [documentation-repository-organization, agent-facing-skill-tool]
  sources: [src-documentation-practices]
---

# documentation.md — Writing Docs That Get Read

> **Purpose:** Reference for what to document, where it lives, who it's for, how to keep it from rotting, and how to organise it so a new contributor (or your future self) can find the right answer in under a minute.
>
> **Read this when:** writing a README; setting up a `docs/` folder; deciding what belongs in code, in a wiki, in an ADR, in a runbook; reviewing the docs of a project you're inheriting; auditing what's stale.
>
> **Do NOT** write docs because "we should have docs." Docs that nobody reads are debt. Docs that are wrong are worse than no docs.

---

## The Premise

> Docs exist so the next person—including future-you—does not have to reconstruct contracts,
> operation, rationale, and context from code alone.

Three rules:

1. **Write for a specific reader doing a specific thing.** A doc that addresses everyone addresses no one.
2. **Live with their owner and lifecycle.** Versioned product contracts usually belong with code.
   Access-controlled operational, support, or organizational knowledge may belong elsewhere when it
   has explicit ownership, review triggers, stable links, and a current-truth pointer from the repo.
3. **Keep docs small enough to read** in the time the reader has. If the doc takes an hour and the reader has ten minutes, the doc loses.

---

## The Diátaxis Framework — Four Kinds of Doc

Diátaxis identifies four forms of user documentation around four reader needs.

| Type             | Reader's goal              | Form                             | Example                              |
| ---------------- | -------------------------- | -------------------------------- | ------------------------------------ |
| **Tutorial**     | Learning by doing          | Step-by-step, hand-held, leading | "Build your first plugin"            |
| **How-to guide** | Solving a specific problem | Goal-oriented, recipe-shaped     | "How to enable SSO"                  |
| **Reference**    | Looking something up       | Dry, complete, predictable       | API reference; CLI flags             |
| **Explanation**  | Understanding              | Discursive; the _why_            | "Why we chose Postgres over MongoDB" |

**Heuristic:** Use these forms when separating user-facing material would improve retrieval or task
success. A small project may label sections or pages instead of creating four folders. A large
documentation site may combine the taxonomy with product, version, audience, or locale navigation.
Evaluate whether readers can find and successfully use the right material; do not grade the folder
names.

**Diagnostic:** when a doc feels off, ask which genre it claims to be. Most "bad docs" are reference dressed as tutorial, or explanation hidden in how-to.

Diátaxis is not a complete taxonomy for repository lifecycle records. ADRs preserve decisions,
tasks own work state, audits/research preserve dated evidence, lessons carry reusable inferences,
and handoffs carry temporary continuation state. Keep those authority and lifecycle contracts
explicit rather than relabelling them as tutorials, how-tos, reference, or explanation.

---

## An Adoptable Repository Documentation Profile

[`documentation-structure.md`](documentation-structure.md) defines an opt-in profile for document
roles, authority, currency, sources, and cross-linking. The following tree is an example, not a
universal standard:

```
README.md                   ← Front door
CHANGELOG.md               ← What changed, per release
CONTRIBUTING.md             ← How to contribute (or this project's calibration; see top-level)
LICENSE or explicit rights/status statement ← Required before distribution; private repos may reserve rights
docs/
  README.md                 ← Index of docs
  context/                 ← Current specifications, orientation, and architecture explanation
  adr/                     ← Architecture Decision Records (see architecture.md)
  tasks/                   ← Open work with explicit provenance and completion criteria
  lessons/                 ← Dated learnings and standing thematic notes
  audits/                  ← Point-in-time reviews and deep analyses
  templates/               ← Templates for the above
  runbooks/                ← Operational: "what to do when alert X fires"
  privacy/                 ← If applicable: data inventory, processor list, retention table
```

Add `tutorials/`, `how-to/`, or `reference/` when the project has enough reader-facing material to
justify separate Diátaxis genre folders. Otherwise, label or index the forms wherever the
ecosystem's documentation tool expects them. `runbooks/` and `privacy/` deserve access,
classification, ownership, and lifecycle appropriate to their content; they need not be public or
stored in this exact tree.

Small projects do not need empty directories. **Project default:** give each adopted role one
predictable owner and current-truth pointer, while following ecosystem conventions unless a
documented force justifies deviation.

### Resolve authority explicitly

“Code is truth” is useful only as a narrow statement about observed implementation. It is unsafe as
a universal conflict rule:

- when an adopted protocol specification or API schema defines required behavior, diverging code is
  a defect;
- when a database schema or migration policy owns a durable invariant, corrupt stored state does not
  repeal the invariant;
- when an approved safety case, contract, standard, or applicable law constrains the system,
  neither code nor prose can silently override it;
- when no higher contract exists, observed system behavior may be the best available evidence, but
  the project should still decide whether to preserve or change it.

Use the role matrix in
[`documentation-structure.md`](documentation-structure.md#authority-before-location). Record which
artifact owns current intent, which records are historical, how supersession works, and what event
requires review.

---

## The README — The Highest-Value Doc

A new visitor reads the README and either continues or leaves. Optimise it.

### The structure

```markdown
# Project name

One-sentence description. (What does it do? Who is it for?)

## What this is

A paragraph. Concrete, not marketing.

## Quick start

The minimum commands to see something running locally.

## Status

Maintained / experimental / archived. Latest stable version. Compatibility.

## Documentation

Pointers to docs/, tutorials, API reference, etc.

## Contributing

Pointer to `CONTRIBUTING.md`.

## License

One line + link.
```

### Discipline

- **Above the fold (first screen):** what it is, why it exists, how to try it. Don't bury.
- **Quick start that actually works.** Reads fresh; verify quarterly.
- **No dead links** ([DEPENDENCIES](dependencies.md) — run `lychee` in CI).
- **Don't list every feature.** Reference docs do that.
- **Don't quote your own marketing.** Concrete, not breathless.
- **State distribution rights/status.** Public distribution needs an explicit license; a private
  repository can state that no public redistribution permission is granted or link the governing
  internal terms.
- **Mention the project's status.** "Alpha; APIs will change" is information; absence is a guess.

---

## CHANGELOG — The Human-Readable History

(Cross-references [GIT_AND_VERSIONING](git-and-versioning.md).) **House preference:** Use a curated,
user-facing changelog when the project has versions or consumers who need to understand notable
changes. `CHANGELOG.md` at the repository root and Keep a Changelog are one established convention,
not an external requirement.

| Discipline                                                                  | Detail                                                                                  |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Updated in the PR**, not at release time                                  | The author writes it, the reviewer verifies it                                          |
| **Categorised** (Added / Changed / Deprecated / Removed / Fixed / Security) | Easy scanning                                                                           |
| **User perspective**, not internal                                          | "Refactored InternalHelper" is uninteresting; "Performance of `/orders` improved 5×" is |
| **Linked to issues / PRs**                                                  | Cross-reference for the curious                                                         |

---

## ADRs — Architecture Decision Records

(Full template in [ARCHITECTURE](architecture.md).) An ADR is a concise, durable record of one
significant decision. Filename, numbering, storage, and metadata are project conventions rather
than properties of the concept.

Why this matters for documentation:

- **ADRs are the answer to "why is it this way?"** — the most common question on inherited code.
- They're cheaper to write at the moment of decision than to reconstruct later.
- They're the cure for "we've had this same argument three times."

**Project default:**

- One decision per ADR; one ADR per significant decision.
- Define statuses such as Proposed, Accepted, Rejected, Deprecated, and Superseded.
- Keep the accepted decision body stable. Permit explicit status, correction, and supersession
  metadata under project policy; reverse a material decision through a linked new record.
- Store it in a durable, indexed, versioned home accessible to its decision participants. The
  repository is often appropriate, but an external decision system can work when ownership, access,
  export, stable links, and current-truth pointers are governed.
- Keep the concise decision record distinct from extensive deliberation, experiments, dissent, or
  unresolved questions. Link the research/deliberation artifact so future maintainers can recover
  why alternatives were rejected without turning the ADR into a transcript.

---

## Runbooks — Operational Documentation

A **runbook** is the doc the on-call reads at 3 AM. It must be:

| Property                                           | Reason                                           |
| -------------------------------------------------- | ------------------------------------------------ |
| **Linked from the alert**                          | You don't search for runbooks in an incident     |
| **Specific to one alert / one situation**          | Don't read 40 pages to find the relevant section |
| **Step-by-step at the top, context below**         | Triage first, understand later                   |
| **Updated after every incident** that exercised it | The thing it said to do was wrong; fix it        |

### Template

```markdown
# Runbook: <Alert / situation>

## TL;DR

One sentence: what's happening, what to do first.

## First steps

1. Confirm with: `<command>`
2. If true, immediate action: `<command>`
3. If unclear, escalate to: `<person / channel>`

## What this means

Plain language. What signal is this? What does the system look like in this state?

## Likely causes

- Cause A — check with `<command>`, fix with `<command>`
- Cause B — ...

## Mitigation vs fix

What to do to stop the bleeding. What to do to actually fix it (later).

## Escalation

When to wake whom. Phone tree.

## Related

Links to: dashboard, related alerts, related code, related ADRs.
```

A runbook that has been used and updated is one of the highest-value docs in any project.

---

## API Reference — Generated, Not Handwritten

(Cross-references [API_DESIGN](api-design.md).)

- **REST APIs:** generate from the OpenAPI spec. Don't write by hand.
- **GraphQL APIs:** generate from the SDL. Tools like GraphiQL provide live exploration.
- **gRPC APIs:** generate from protobuf comments.
- **Libraries:** language-native doc generators (Sphinx, JSDoc, GoDoc, rustdoc, Javadoc). Source-of-truth is the docstring.

**Discipline:**

- **Docstrings reviewed in PRs**, same rigour as code.
- **Generated docs in CI**, deployed automatically.
- **Versioned with the code.** Old versions remain accessible; current version is current.
- **Don't duplicate.** If the docstring says it, the prose docs don't repeat it; they link.

---

## Code Comments — A Different Genre

Code comments are documentation, but a specific kind. Discipline:

| Write a comment for                                                                     | Avoid                                                      |
| --------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Why a surprising choice exists and which alternative failed                             | Restating syntax or the function name                      |
| Public contract, state-machine transition, invariant, ownership/lifetime, or units      | Duplicating generated reference without added context      |
| Thread-safety, mutation, complexity, performance budget, or security/privacy assumption | Vague “slow,” “safe,” or “temporary” assertions            |
| Compatibility quirks, external bugs/standards/ADRs, linter suppression rationale        | Apologies instead of a reason, owner, and removal trigger  |
| Generated-file markers and safe regeneration boundary                                   | A comment that can drift independently from its real owner |

**Comments rot faster than code.** A wrong comment is worse than no comment. When you change the code, scan the comments.

**`TODO` / `FIXME` discipline:**

- Give deferred work a discoverable owner and trigger: a ticket is strong for tracked product work;
  a local dated/owned TODO can be sufficient for a small repository when an issue tracker adds no
  value.
- Add an expiry/review trigger when staleness matters, or auto-flag with a linter.
- Periodically harvest into the issue tracker; remove from code.

---

## What Belongs Where — A Cheatsheet

| Need                                            | Where it lives                                                                                |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------- |
| "What is this project?"                         | `README.md`                                                                                   |
| "How do I run it?"                              | `README.md` Quick Start                                                                       |
| "How do I contribute?"                          | `CONTRIBUTING.md`                                                                             |
| "What changed?"                                 | `CHANGELOG.md`                                                                                |
| "Why is it this way?"                           | An ADR in `docs/adr/`                                                                         |
| "How is it structured?"                         | `docs/context/architecture.md` (or the project's indexed explanation home), ADRs, C4 diagrams |
| "How do I do X?"                                | A how-to in `docs/how-to/`                                                                    |
| "What does this function / endpoint do?"        | Docstring / OpenAPI / generated reference                                                     |
| "What does this constant mean?"                 | Comment at the constant, or docs on the enum / table                                          |
| "Who do I contact about security?"              | `security.md`                                                                                 |
| "What does the team value?"                     | `CONTRIBUTING.md`; principles docs                                                            |
| "What should I do when alert X fires?"          | `docs/runbooks/alert-X.md`, linked from the alert                                             |
| "Where does data X live?"                       | `docs/privacy/data-map.md` ([PRIVACY](privacy.md))                                            |
| "What providers do we use, and where are they?" | `docs/privacy/processors.md` ([PRIVACY](privacy.md))                                          |

---

## The Eight-Page Onboarding Doc

For any project that another person will work on, write this once:

```markdown
# Onboarding

## What this is

One paragraph.

## How to run it locally

The minimum.

## How it's deployed

One paragraph + a link.

## Top-level directory tour

file:: purpose

## The core user journey, end to end

The one user flow you'd trace if you had 30 minutes.

## Where data lives

One diagram, even crude.

## What's load-bearing

The bits that, if broken, take everything down.

## Who to ask

Roles / maintained channels; names only when personal responsibility and currency are intentional.

## What's surprising

The non-obvious decisions. Where the bodies are buried.
```

A new contributor with this doc and a working environment can do something meaningful on day two. Without it, they spend a week reconstructing.

---

## Docs Maintenance — The Forgotten Discipline

Docs decay faster than code. The countermeasures:

| Practice                                                           | Detail                                                        |
| ------------------------------------------------------------------ | ------------------------------------------------------------- |
| **Docs review in every PR** that changes behaviour                 | Reviewers check affected contracts and user tasks             |
| **Link checking in CI** when docs are a relied-upon surface        | `lychee` or equivalent — see [DEPENDENCIES](dependencies.md)  |
| **Verification date plus trigger** on volatile or operational docs | A date without an owner or trigger becomes decoration         |
| **Risk-based audits** for hot docs (README, onboarding, runbooks)  | Set cadence from change rate, consequence, and observed drift |
| **Executable checks for examples** when their failure matters      | Pick a check that exercises the claimed environment           |
| **Generated reference** for a machine-owned contract               | Regenerate and check drift from its declared source           |
| **Remove, archive, or supersede according to role**                | Do not erase decision/audit history as if it never existed    |

**A conflict between documentation and implementation is a bug in the system of record.** Resolve
it using the declared authority for the affected claim; do not automatically rewrite the document
to match code or code to match prose.

## Sources and Claim Maintenance

Source claims that materially affect a decision or obligation, especially when they are volatile,
legal/regulatory, safety-relevant, quantitatively specific, or contested. Prefer the primary
standard, regulator, original research, or maintainer source. Record version/status, verification
date, and re-verification trigger when freshness matters.

Do not cite every non-obvious sentence. Project defaults, house preferences, heuristics, and
examples need visible labels, rationale, and override conditions—not decorative references. A
source can establish a factual premise; it does not make a project-specific choice on the project's
behalf. See the [epistemic contract](epistemic-contract.md).

---

## Diagrams

A picture is worth a thousand words _sometimes_. The catch is that diagrams rot as fast as docs.

| Form                                   | Use                                                                                        |
| -------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Mermaid** / **PlantUML** in Markdown | Text-source; versioned; renderable in the docs                                             |
| **draw.io / Excalidraw**               | When freeform is needed; commit the source file, not just the rendered image               |
| **C4 diagrams**                        | For architecture at levels 1–2 (context, container); use a tool that generates from source |
| **Sequence diagrams**                  | For request flows                                                                          |
| **ER diagrams**                        | For data models; generate from the schema where possible                                   |

**Anti-pattern:** a beautiful diagram in a JPG, committed once, never updated. Within months it's wrong. Either generate it from source, or label it with a date so readers know its currency.

---

## Writing for Readers Who Don't Speak Your Language

Docs are often the entry point for non-native English speakers. Discipline:

- **Plain language.** "Use" beats "utilize." "Show" beats "demonstrate."
- **Short sentences.** Long sentences hide ambiguity.
- **Define jargon on first use** or link to a glossary.
- **Avoid idioms** ("low-hanging fruit", "boiling the ocean", "out of the box").
- **Be careful with culturally specific examples** (US holidays, sports metaphors).
- **Use Markdown's structure** (headings, lists, tables) — they translate well; flowing prose less so.

This is also good writing for native readers. Plain is not dumbed-down; plain is effective.

---

## Anti-Patterns

| Pattern                                                                           | Why it fails                                                                                                        |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **External docs with no owner, version/current-truth pointer, or review trigger** | Readers cannot tell whether repo or wiki is authoritative; access-controlled shared docs can be valid when governed |
| **One giant `docs.md`**                                                           | No one reads to the bottom; no one knows what's in it                                                               |
| **README that is mostly badges**                                                  | Decorative; the actual reader's question is "what is this?"                                                         |
| **README that doesn't say how to run the thing**                                  | Highest-friction first impression                                                                                   |
| **No CHANGELOG**                                                                  | Users discover breaking changes by being broken                                                                     |
| **Docs auto-generated entirely from code, no prose**                              | The _why_ is missing; readers reconstruct                                                                           |
| **Tutorials that don't work when followed**                                       | Trust gone                                                                                                          |
| **Hand-maintained API reference next to source code**                             | Drifts; one is wrong                                                                                                |
| **Long unbroken paragraphs**                                                      | Tables, lists, and headings find what you need                                                                      |
| **Comments that lie**                                                             | Worse than no comments; readers trust them once                                                                     |
| **Aspirational docs** ("the system supports X") when X isn't yet implemented      | Sets the wrong expectation; eventually contradicts reality                                                          |
| **"See the wiki"** when the wiki is private / dead / wrong                        | The wiki link is the documentation; if it's bad, the doc is bad                                                     |
| **Multi-version docs without a version selector**                                 | Readers find the wrong page                                                                                         |
| **Volatile docs without owner, verification state, or review trigger**            | The reader cannot judge currency; a bare date alone does not keep the content true                                  |
| **Onboarding doc nobody can run**                                                 | The single highest-leverage doc is broken; fix today                                                                |

---

## Diagnostic Framework

| Symptom                                             | Likely cause                                                                                         |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| "How does this work?" asked repeatedly              | The answer is somewhere; either docs are missing, or discoverable docs don't exist, or they're wrong |
| New hires take a month to be productive             | Onboarding doc missing or broken; runbooks missing                                                   |
| Same incident response decisions made repeatedly    | Runbook missing or out of date                                                                       |
| Users surprised by breaking change                  | CHANGELOG missing or unread                                                                          |
| Architecture argument re-litigated every six months | ADRs missing or unread                                                                               |
| Docs and code disagree                              | No docs-in-PR discipline                                                                             |
| Docs are aspirational, not descriptive              | Written ahead of features without flagging                                                           |
| No one writes docs                                  | Cultural problem; no review enforcement; writing isn't valued; pair docs with code in PR templates   |
| Docs are written, never read                        | Wrong genre; wrong location; not linked from where the reader is                                     |
| Search across docs is bad                           | Single source of truth doesn't exist; consolidate                                                    |

---

## Meta-Question

Documentation is the answer to: _what does the next person need to know that they can't easily reconstruct from the code?_ Not everything that could be written should be — every doc is a maintenance commitment. Write the doc you'd be furious not to find in someone else's project. Write nothing more.

**Heuristic:** Common high-leverage documentation includes:

1. **README** that explains and gets you running.
2. **Onboarding doc** that survives the first week.
3. **ADRs** that capture the _why_.
4. **Runbooks** that survive the 3 AM page.
5. **CHANGELOG** that respects users.

Select them according to the product, users, operational risk, and existing documentation system.
A library may need excellent API/reference/versioning docs but no alert runbooks; a private service
may need operational and privacy records before tutorials.

---

_See [ARCHITECTURE](architecture.md) for the ADR template and architectural diagram discipline._
_See [GIT_AND_VERSIONING](git-and-versioning.md) for the CHANGELOG and commit-message discipline._
_See [OBSERVABILITY](observability.md) for runbooks per alert._
_See [API_DESIGN](api-design.md) for schema-driven reference docs._
_See [PRIVACY](privacy.md) for the data-map and processor-inventory docs._
_See [DEPENDENCIES](dependencies.md) for link-rot checking (`lychee`)._
_Sources (verified 2026-07-30): [Diátaxis](https://diataxis.fr/) for its four
user-documentation forms; [Keep a Changelog 2.0](https://keepachangelog.com/en/2.0.0/) for that
project's changelog convention; [Michael Nygard's original ADR
article](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) and
[MADR](https://adr.github.io/madr/) for decision records and supersession. Re-verify before changing
the attributed frameworks or presenting their current versions._
