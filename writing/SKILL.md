---
name: writing
description: >-
  Produce and revise human-facing prose that is clear, specific, true, and in
  the intended voice — actively avoiding AI "slop" (generic phrasing, false
  specificity, flattened voice, ritual transitions). A risk-calibrated editorial
  control loop: establish the reader contract, draft or rewrite the whole piece
  coherently, diagnose the most consequential defect and fix it, then check
  release-critical invariants and stop — rigor scales with the stakes. Routes
  voice and genre by what is being written, and holds a fact-integrity floor:
  never invent a study, statistic, date, author, or citation to sound specific.
  Use when drafting, rewriting, editing, or reviewing essays, articles,
  explainers, posts, emails, reports, docs, or scripts for a human audience. Do
  NOT use for machine-facing text or prompt/system-instruction authoring (that is
  prompt-engineering's domain), for drawing out an under-specified task (that is
  elicit), or for trivial fully-specified one-liners.
license: Apache-2.0
compatibility: >-
  Instruction-first. Ships a few small stdlib-only measurement scripts
  (fact-integrity/source wall, voice fingerprint, trace map) with no runtime
  service dependencies; the optional Vale style pack additionally needs the Vale
  binary. Uses the harness's own file and shell tools.
metadata:
  author: markov-root
  version: "0.5.1"
---

# writing

This skill is a **risk-calibrated editorial control loop**, not a prose
assembly line. It establishes a reader contract, supplies authoritative voice
and evidence context when needed, diagnoses the most consequential gap in a
draft, applies one bounded revision, and reports only what its checks establish.
The default path is short; higher-stakes work earns stronger evidence and
independent review.

The durable value is **routing and discipline**, not the ability to string
sentences — every capable model can already generate fluent text, and fluent
generic text is exactly the "slop" this skill exists to remove. So the skill
does not try to out-write the base model. It makes the writing _correct for this
reader, true, and in the intended voice_, and it refuses to fabricate
specificity to get there.

## The loop

Four states with a **short default path** and **risk-triggered escalation**.
Most pieces walk Frame → Make → Deliver; Challenge earns its place when the
draft has a real defect or the stakes justify a check.

1. **Frame** — establish only what is _missing_ about the piece.
2. **Make** — produce or revise the whole piece coherently.
3. **Challenge** — diagnose the dominant defect and fix that one thing.
4. **Deliver** — check release-critical invariants, state residual risk, stop.

Hold the loop as a habit of attention, not a checklist: infer and restate what
you can rather than filling out a form. A rigid template re-imposed on every
request _is_ the sameness the skill fights.

### 1. Frame — the reader contract

Before writing, pin down what the piece must do — inferring what you can and
**restating it in one line** for a clear ask, rather than interrogating the user:

- **Reader** — who reads this, and what they already know.
- **Intended effect** — what they should know, feel, or do afterward.
- **Controlling idea** — the single sentence the whole piece serves.
- **Constraints** — length, medium, genre, register, deadline.
- **Evidence mode** — `closed-source` (only supplied facts/IDs) ·
  `research-enabled` (retrieve and freeze an evidence packet before drafting) ·
  `no-source` (explain from supplied facts and reasoning; **no named studies,
  numbers, dates, or citations pulled from memory**).
- **Facts I must not get wrong** — the claims where a mistake is expensive.

If the ask is genuinely under-specified — you cannot name the reader or the
controlling idea — **hand off to the `elicit` skill** rather than guessing.
Route voice and genre now: read [`knowledge/genres.md`](knowledge/genres.md) for
the audience/purpose/medium → voice + bounds mapping, then resolve **whose voice**
governs. Start from the general default
([`knowledge/voice-default.md`](knowledge/voice-default.md)), then **discover any
writeup-specific voice installed locally** — list `knowledge/` and match this
writeup to a module's `voice_scope` frontmatter; if one matches, apply it as an
override on the default. A fresh install carries only the general default, which is
the expected fallback. See [`knowledge/authoring-voices.md`](knowledge/authoring-voices.md).

### 2. Make

Produce or revise the **whole piece coherently**. Outlining is an optional
technique, not an admission gate. A holistic rewrite is allowed to beat a
sequence of narrow repairs — it can resolve coupled problems and preserve rhythm
at the same time. Write in the resolved voice, not a flattened committee voice;
consult [`knowledge/ai-tells.md`](knowledge/ai-tells.md) for the patterns to
avoid _as review judgment_ (context decides — these are not a banned-word list).

When specificity is needed, it is **evidence-bounded**. Never invent an author,
study, year, or number to sound concrete: false specificity survives casual
review and is worse than visible vagueness. Where a claim needs support you do
not have, drop a marker `[[SOURCE NEEDED: <claim>]]` and keep going — see the
fact-integrity floor below and [`knowledge/specificity.md`](knowledge/specificity.md).

### 3. Challenge — diagnose, then one targeted revision

Find the **dominant** failure and make **one targeted revision at a time**,
selected by _defect_, not by a fixed altitude schedule. Return **no more than
three consequential findings, each anchored to a span**. A review must add
information or an oracle _not already in the draft_; "no material defect found"
is a valid, honest result.

Revision is selected by defect type — read [`knowledge/revision.md`](knowledge/revision.md):

- **Reconceive** — the controlling idea, framing, or structure is wrong.
- **Substantiate** — a claim is unsupported, vague, or over-stated.
- **Clarify** — the meaning is right but the reader will not get it.
- **Polish** — voice, rhythm, and mechanics, last.

> **Provisional default (ADR 0005, not doctrine):** defect-driven revision is
> the current prior because its evidence base is stronger; ordered structure →
> sentence editing is a heuristic _within_ a full edit, not a mandatory pipeline.
> The marginal-return evaluator (roadmap) may overturn this — do not present it
> as settled.

#### Review dimensions — 3 gates + 2 screens

Each labeled by **evidence class**, so a proxy is never mistaken for proof:

1. **Reader/task fit** _(review signal)_ — does a representative reader get the
   point and reach the intended effect? Absorbs structure, genre, usefulness. A
   reverse-outline lives here; the `scripts/trace_map.py` pass makes "every
   paragraph earns its place" auditable.
2. **Claim integrity** _(hard gate on markers; review signal on truth)_ — are
   material claims supported and appropriately qualified? **Only unresolved
   required source markers are a hard gate** (`scripts/source_wall.py`);
   resolving a marker is not itself proof the claim is true.
3. **Voice & preservation** _(review signal)_ — does it keep protected meaning,
   idiolect, and genre-appropriate surface? Absorbs lexical hygiene.

Two **screens** — reported as **divergence from the author's own same-genre
baseline**, never as a score, never as a gate: readability/length and lexical
hygiene / rhythm density. The **writing-health panel** (`scripts/writing_health.py`)
composes the individual screens into ONE non-blocking diagnostic — readability
(`scripts/readability.py`), syntactic hedges/nominalization (`scripts/hedges.py`),
connective overuse (`scripts/connectives.py`), sentence-opener/expletive
(`scripts/openers.py`), and the cliché/stock-phrase Vale rule (`scripts/vale/`) —
alongside the voice fingerprint (`scripts/voice_fingerprint.py`). Each metric is a
divergence from baseline, **never an aggregate score**. A screen flags for review;
it never blocks and never auto-fixes.

#### Critics veto, never approve; the writer closes

Review can only **halt** — raise a blocking objection on fact or coherence. It
can never **pass** a draft. There is no standing multi-model panel: a committee's
consensus is the _Maximum Consent-Bland Set_ and sands off the very edge and
voice the skill protects. Default review is a single same-model, multi-lens
advisory pass (clarity / fact / reader-pull). Reserve true cross-vendor `debate`
for high-stakes or fact-adversarial pieces.

Declared **edges** — stances or stylistic choices the writer intends to hold —
are review-only: a softening finding against a declared edge does not block.
**Precedence:** an edge protects style and stance only. A **fact-or-coherence
veto against the substance of a declared edge still blocks** — the fact gate is
the moat and the edge ledger must never shield a false claim from it.

### 4. Deliver — completion checklist

Not a report template — a short honesty check:

- [ ] The piece serves the controlling idea; a reader gets the intended effect.
- [ ] Every material claim is supported, qualified, or marked — **no unresolved
      `[[SOURCE NEEDED: …]]` markers** in final mode (run `scripts/source_wall.py
--final`; the bare `[[SOURCE NEEDED]]` form is accepted too).
- [ ] No fabricated study, number, date, author, or citation.
- [ ] Voice is the resolved voice; protected spans intact.
- [ ] **One line of residual risk** — the voice/edge/uncertainty you knowingly
      kept. "Done" is the writer accepting with that statement, not a panel
      signing off.

## Escalation triggers

Rigor scales with risk. Escalate past the short path only when a trigger fires:

- High-stakes or dense factual claims → a claim/source check and the source wall.
- Long or multi-section piece → an argument/trace map before line-editing.
- Publication or a series → a voice + preservation review; cross-document
  consistency for a maturing body of work.
- Legal, policy, or adversarial context → a qualified or genuinely independent
  (cross-vendor `debate`) reader.

## Fact-integrity floor (the moat)

Specificity is evidence-bounded and the truthfulness floor is mechanical.
Fabricated support is a **veto**, never averaged against prettier prose:
"missing evidence is not a style defect." Before prose, keep a **claim ledger**
for checkable propositions (claim → source → supporting passage → status:
`supported | partial | conflict | missing`); draft only from `supported`, qualify
`partial`, and never render `missing` as fact. The **specificity ladder** for a
vague claim is a decision, never decoration: _source-backed detail → narrower
entailed claim → concrete mechanism/example → honest uncertainty → deletion_ — it
**must never propose** an author, study, year, or number. Full method:
[`knowledge/specificity.md`](knowledge/specificity.md). Deterministic support:
`scripts/source_wall.py` (blocks final mode on unresolved markers).

**When you cannot establish something, say so.** Mark it, narrow the claim, or cut
it, and state the uncertainty plainly. "I can't verify this from the supplied
evidence" is a correct, expected result — reach for it instead of writing a
confident sentence you cannot support.

## Voice

The skill ships **one** voice — the general default — and treats every
writeup-specific voice as a **local, dynamically-discovered override**. It governs
prose quality directly, with no external document to point at (ADR 0007). Resolve
voice at Frame:

- **General default (always present)** —
  [`knowledge/voice-default.md`](knowledge/voice-default.md): plain, specific, and
  tuned to avoid AI "tells" ([`knowledge/ai-tells.md`](knowledge/ai-tells.md)).
  This is what a fresh install writes in, and the floor every other voice refines.
- **Writeup-specific voices (local only)** — a personal default, a house style, a
  genre/format profile. These are **not hardcoded here**; they are **discovered
  dynamically** from what is installed: list `knowledge/` and read each module's
  `voice_scope` frontmatter, then load the one whose scope matches this writeup as
  an override on the default. None installed (e.g. a fresh public checkout) → the
  general default, as expected.
- **Add a new one** — when a voice recurs, capture it once as a reusable module;
  method in [`knowledge/authoring-voices.md`](knowledge/authoring-voices.md).

`scripts/voice_fingerprint.py` measures a draft against _accepted_ passages, so
voice stays measurable without an AI detector, and the skill never emits an
"AI-written" verdict about an author. (An opt-in self-adversarial detector screen
on your _own_ draft is a separate, deliberate choice — ADR 0006.)

Writeup-specific voice modules are tagged `visibility: private`: they install
locally but are **excluded from any public export**, and `SKILL.md` never links to
them directly (discovery is dynamic), so a public export carries only the general
default and never a dangling link (the token-gate and the publish preflight guard
both boundaries).

## Knowledge routing

Load the smallest relevant set; do not read all of these for a short piece. These
modules always ship:

- [`knowledge/voice-default.md`](knowledge/voice-default.md) — the general default
  voice (the floor every writeup-specific voice refines).
- [`knowledge/authoring-voices.md`](knowledge/authoring-voices.md) — how
  writeup-specific voices are discovered locally, and how to author a new one.
- [`knowledge/genres.md`](knowledge/genres.md) — genre bounds, obligations, and
  the audience/purpose/medium → voice routing table.
- [`knowledge/ai-tells.md`](knowledge/ai-tells.md) — the AI-tell catalogue, as
  review judgment.
- [`knowledge/specificity.md`](knowledge/specificity.md) — evidence modes, claim
  ledger, and the specificity ladder.
- [`knowledge/revision.md`](knowledge/revision.md) — defect-selected revision,
  the deviation discipline, and ordered editing as a heuristic.

**Writeup-specific voice / style / format modules** (a personal voice, a house
style, a genre profile) are **local-only and discovered dynamically** by their
`voice_scope` frontmatter — they are not listed here and may be absent in a given
install. See [`knowledge/authoring-voices.md`](knowledge/authoring-voices.md).

Provenance for load-bearing claims: [`references/SOURCES.md`](references/SOURCES.md).
