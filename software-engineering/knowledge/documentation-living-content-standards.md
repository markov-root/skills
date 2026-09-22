---
knowledge:
  version: 1
  id: documentation-living-content-standards
  summary: Distill the per-role content-quality standard for the eight living documentation roles so an author knows what current guidance, reference, and operational content must contain.
  routes: [documentation-repository-organization]
  sources: [src-documentation-practices, src-documentation-structures]
---

# Living-document content standards

> **Purpose:** State the content-quality standard for the eight living documentation roles
> (specification, knowledge, reference, standard, guide, roadmap, changelog, runbook) — the telos
> each serves, the properties that make its content good, the test that discriminates a good
> living document from a well-formed empty one, and a compact exemplar/anti-example for each.
>
> **Read this when:** authoring or reviewing current guidance, reference, operational, or
> standards content; choosing whether a living document earns its role and currentness.

These roles describe what **currently** holds or what a defined audience should do. Their distinct
failure is a well-formed body that is inert: it does not actually help the routed reader act,
look up, verify, or decide. Read this alongside
[`documentation-structure.md`](documentation-structure.md) for the folder and lifecycle shape; these
sections say what the content must be.

## The shared floor

A living document has two independent axes:

- **Well-formedness** — does it satisfy its structural contract (role, metadata, currentness,
  version/audience/scope fields)?
- **Warrant and content quality** — does it earn its current authority, is it truthful and
  current, and does it produce the role's distinct reader outcome?

Both axes matter, and neither substitutes for the other. **Structure hard, warrant loud**: shape is
mechanically checkable, but content judgments stay irreducible. A proxy check (link resolves, field
present) is necessary-not-sufficient — it never replaces the question of whether the content is
true, current, and useful for the intended reader.

## Specification

**Telos:** Define current normative behavior, qualities, and failure semantics so independent
reviewers reach the same conformance judgment.

**Content-quality properties:**
- Requirement identities and modalities trace to an authorized need.
- Normal and boundary cases covered, with evolution and divergence owners named.
- Cross-rule coherence, precedence, failure, and versioning closed; examples linked to rules.

**Discriminating test:** Can independent reviewers classify the same representative/boundary cases
alike, and trace every material rule to authorized need without private intent?

**Exemplar:** A specification whose requirements are stable identities tied to authorized need,
whose normal and boundary cases let two reviewers reach the same conformance verdict, and whose
version/evolution/divergence is owned.

**Anti-example:** A spec that reads as a behavior wish-list — requirements with no source of need,
boundary cases omitted, and a version claim that hides silently changed rules.

## Knowledge

**Telos:** Preserve reusable vocabulary, trade-offs, and explanatory synthesis without silently
becoming project policy.

**Content-quality properties:**
- The synthesis adds reasoning unavailable from raw code; it is not a restatement.
- The model stays durable within declared limits.
- Self-originated normative markers are absent or explicitly routed to a real authority.

**Discriminating test:** Does it help a routed reader reason about the system without acting as a
specification or standard?

**Exemplar:** A knowledge document that explains a trade-off a reader could not get from the code
alone, that knows the limits of its model, and that never silently becomes binding policy.

**Anti-example:** Knowledge that reads as a rulebook — it starts dictating behavior the project
never adopted, or it merely restates what the code already shows without adding the reasoning.

## Reference

**Telos:** Provide rapid, trustworthy lookup of precise facts against a declared canonical source.

**Content-quality properties:**
- Findable entry structure with source/version/date.
- Exact values and defaults; freshness and coverage bounds.
- Derivation and canonical-source markers, with honest anti-drift claims.

**Discriminating test:** Can a reader land on the exact fact and confirm it against the declared
source without re-searching or re-deriving it?

**Exemplar:** A reference whose entry answers the intended question, whose source genuinely
authorizes the fact, and whose qualifiers, freshness, and coverage let a reader trust the value
without a second search.

**Anti-example:** A reference whose values drifted from the declared source, or whose qualifiers
and freshness claims overstate completeness — the reader re-derives the fact and cannot trust the
page.

## Standard

The standard role defines required practice, so its content bar is adjudicability rather than mere
clarity.

**Telos:** Turn an authorized coordination, safety, integrity, or quality decision into
adjudicable rules for a bounded population.

**Content-quality properties:**
- Legitimate issuer/adoption and applicability warrant.
- Proportionate scope/burden/feasibility for the governed population.
- Contested-case adjudicability and evidence integrity, with waiver/non-waiver classification.

**Discriminating test:** In a contested case, can a reviewer establish legitimate applicability,
decide conformance, and determine whether an exception is authorized — without hidden intent or
displaced burden?

**Exemplar:** A standard whose issuer and adoption are legitimate, whose scope and burden are
proportionate, and whose rules a reviewer can apply to a contested case without consulting hidden
intent.

**Anti-example:** A standard whose scope is unstated or whose burden falls on parties who never
agreed — so a contested case cannot be decided from the text without displaced intent.

## Guide

**Telos:** Lead a defined audience to a defined outcome while exposing assumptions, friction, and
verification along the way.

**Content-quality properties:**
- Audience, environment, and version stated.
- Intermediate/final verification commands or observations.
- Applicable failure and troubleshooting paths.

**Discriminating test:** Can the intended audience complete and verify the goal without
undocumented environmental assumptions?

**Exemplar:** A guide whose audience can follow the steps in their environment and verify each
outcome, with failure paths where the environment or assumptions differ.

**Anti-example:** A guide that works only for the author's machine — undocumented assumptions,
no verification, and a dead end for anyone else.

## Roadmap

**Telos:** Align stakeholders on sequenced intent, dependencies, timing, and calibrated
commitment under uncertainty.

**Content-quality properties:**
- Dated commitment bands with reasons and dependencies per phase.
- Assumptions and break triggers stated; reconciliation with graph/task state.
- Committed items link to owning task or ADR.

**Discriminating test:** When reality diverges, can a reader tell which priority/commitment changes
and which evidence or dependency triggered it?

**Exemplar:** A roadmap whose commitments are dated bands, whose sequencing is tied to reasons and
dependencies, and whose break triggers name the evidence that would change direction.

**Anti-example:** A roadmap that reads as a wish list — no dates, no owning task/ADR, no
break trigger — so when reality diverges nobody can tell what changed or why.

## Changelog

**Telos:** Explain what materially changed in a release, and what the declared audience must
understand or do, without requiring the diff.

**Content-quality properties:**
- Audience/scope named; each entry states the behavior or outcome, not the internal refactor.
- Breaking/action markers and migration actions explicit.
- Omissions disclosed where disclosure would otherwise be expected.

**Discriminating test:** Can a non-contributor in the declared audience answer "what changed in my
release, and what do I do?" without chasing the code?

**Exemplar:** A changelog whose entries name user-visible outcomes and actions, whose breaking
changes are marked with migration guidance, and whose release boundaries are honest.

**Anti-example:** A changelog that names internal refactors instead of user-visible behavior, hides
a breaking change behind a reword, and gives the reader no action to take.

## Runbook

**Telos:** Turn a recognizable operational condition or recurring objective into a safe,
closed-loop procedure.

**Content-quality properties:**
- Entry/outcome/environment/authority clear; mutations state effects and reversibility.
- Branch fields at the risky step; independent outcome evidence.
- Usable under expected cognitive load; honesty about what is not known.

**Discriminating test:** When the highest-risk or most uncertain step surprises the operator, can
they reach a safe disposition and preserve evidence of what did and did not happen?

**Exemplar:** A runbook whose entry conditions recognize the situation, whose risky step has a
branch for the unexpected, and whose outcome evidence lets an operator reach a safe disposition.

**Anti-example:** A runbook that assumes a clean path and gives no safe disposition when the risky
step surprises — the operator is left to improvise without evidence of the outcome.

## Meta-Question

What does the author of a living document need to know that shape validation alone will not tell
them? For each role the answer is the discriminating test above — the one question that separates a
well-formed living document from one that actually helps its reader act, verify, or decide. Use the
template quality bar to surface that test at the point of writing.