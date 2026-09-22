---
summary: Specificity is evidence-bounded — the skill's moat; evidence modes, the claim ledger, the specificity ladder, and source markers make "sounds natural" into "is true" without ever fabricating a study, number, date, author, or citation. Missing evidence is not a style defect.
status: standing
role: knowledge
---

# Specificity and fact-integrity (the moat)

The strongest anti-slop lever is replacing vague attribution ("studies show") with
a named study or number. It is also the strongest **hallucination** lever: false
specificity — a plausible author, year, or percentage — is _worse_ than visible
vagueness because it survives casual review. Commodity models do not police this
for themselves; doing it well is the skill's durable advantage.

**The rule: specificity is evidence-bounded. The skill never invents support.**
Retrieval and citation prompting do not solve this — a citation being _present_ is
not the same as the source _entailing_ the claim.

## Evidence mode is an input to the job

Set it in the Frame step and hold it:

- **`closed-source`** — use only supplied facts and IDs.
- **`research-enabled`** — retrieve, inspect the source, and **freeze an evidence
  packet before drafting**; draft only from what the packet supports.
- **`no-source`** — explain from supplied facts and reasoning. **No named studies,
  numbers, dates, or citations pulled from parametric memory.** Reasoning and
  mechanism are fine; invented evidence is not.

## The claim ledger (before prose)

For each checkable proposition, record: **claim · source_id · supporting passage ·
scope · status · report-vs-inference.** Status is one of:

`supported` — draft it. `partial` — draft it _qualified_ to what the source
actually supports. `conflict` — surface the conflict, do not pick a side silently.
`missing` — **never render as fact**; mark it (below) or cut it.

## The specificity ladder (a repair is a decision, never decoration)

When a claim is vague, choose — top preferred, do **not** climb by inventing:

1. **Source-backed detail** — the real named study, number, or date, from the
   evidence packet.
2. **Narrower entailed claim** — say only what you _can_ support.
3. **Concrete mechanism or example** — explain _how_, or give a real instance,
   instead of asserting a statistic.
4. **Honest uncertainty** — "the evidence here is thin / I can't verify this."
5. **Deletion** — cut the unsupported claim.

A vague-attribution finding offers _supply evidence / narrow / mark / delete_ and
**must never propose an author, study, year, or number.**
**Missing evidence is not a style defect** — do not "polish" it away.

## Source markers and the source wall

When a claim needs support you do not have, drop a marker inline and keep drafting:

```
[[SOURCE NEEDED: <the exact claim that needs support>]]
```

Markers are allowed and _visible_ in draft mode. In **final mode they are a hard
integrity failure**: `scripts/source_wall.py --final` lists every unresolved
marker (paragraph + line + claim) and exits non-zero until the wall is empty.
Shrink the wall by **sourcing or narrowing**, never by fabricating. The
unresolved-marker count is also the Goodhart-resistant specificity signal the eval
reuses — it is winnable only by getting facts right.

Deterministic code verifies **marker presence only**; entailment (does the source
actually support the claim?) needs the inspected evidence and human or tool review
and stays advisory. Provenance: [`references/SOURCES.md`](../references/SOURCES.md).
