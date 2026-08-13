---
knowledge:
  version: 1
  id: epistemic-contract
  summary: Label engineering claims by authority, volatility, confidence, and scope so guidance does not masquerade as fact or binding policy.
  routes: [documentation-repository-organization, agent-facing-skill-tool]
---

# Epistemic Contract for Engineering Guidance

> **Purpose:** Make the authority, volatility, and override conditions of engineering advice visible.
>
> **Read this when:** authoring or reviewing a reference, resolving conflicting guidance, or deciding
> whether a statement is a requirement, a default, a preference, or merely a useful smell.

---

## Claim Types

Material guidance uses one of these labels when its status would otherwise be ambiguous:

| Label                | Meaning                                                                | What a project may do                                                      |
| -------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **Standard/fact**    | An externally defined requirement or verifiable descriptive claim      | Verify applicability and version; do not silently alter the external claim |
| **Project default**  | A strong starting point that works across many ordinary contexts       | Replace it with a reasoned project decision and evidence                   |
| **House preference** | This library's maintainability or safety bias                          | Override it explicitly in project policy                                   |
| **Heuristic**        | A diagnostic, smell, threshold, or decision aid—not a law              | Weigh counter-evidence and local costs                                     |
| **Example**          | An illustration, sample threshold, or possible implementation          | Adapt or ignore it; never treat a sample value as an inherited requirement |
| **Legal note**       | A legal/regulatory issue whose application depends on facts and locale | Obtain current, jurisdiction-specific qualified review when stakes warrant |

Absence of a label does not turn prose into policy. Project instructions, accepted ADRs, and
explicitly selected project policy outrank defaults, preferences, and heuristics in this corpus.
Applicable law and external standards remain constraints on the project rather than house policy.

## Normative Language

Use `must` or `must not` only when at least one of these is true:

- the statement defines the contract of the reference or artifact itself;
- violating it would break an explicitly stated safety, security, privacy, or integrity invariant;
- an identified external standard uses normative language and is applicable in the stated scope.

Use `should` for a recommended default with known exceptions. Use `may` for an option. Avoid
`always`, `never`, and numerical thresholds unless the scope, rationale, and exception conditions
are visible.

**Example:** “A password verifier subject to NIST SP 800-63B-4 SHALL…” is a scoped standards claim.
“All applications must require 15-character passwords” is not: the standard has an applicability
scope and distinguishes single-factor from MFA-associated passwords.

## Evidence and Freshness

Material external claims record:

1. the primary source or specification;
2. the version, publication state, or effective date;
3. the date this corpus verified the claim;
4. the event that requires re-verification.

Prefer standards bodies, regulators, original research, and maintainers over summaries. A search
result, vendor comparison, blog recap, or model answer can locate a source but does not replace it.

Re-verify before:

- adopting a security, privacy, accessibility, identity, protocol, or compliance requirement;
- selecting a provider, framework, dependency, hosted service, or jurisdiction;
- relying on a draft specification, product feature, price, support matrix, or end-of-life date;
- publishing a claim whose source is older than the project's declared currency window.

If evidence is missing, say what is unknown. Do not manufacture certainty from consensus-sounding
language.

The bundled factual register uses one row per unique HTTPS source with source title,
publisher/author, access date, `verified | unverified | paywalled | archived` status, informed
knowledge IDs, stable `src-*` relationship groups, and an event-based re-verification trigger.
`verified` means the source was reviewed on that date; it does not promote a synthesized claim into
permanent fact or project policy.

## Legal and Regulatory Claims

**Legal note:** This library is engineering decision support, not legal advice. Regulations often
depend on role, purpose, data, users, establishment, contract, transfer path, and current regulator
guidance. A reference may identify a trigger and the evidence an engineer should preserve; it must
not invent a universal lawful basis, jurisdiction ranking, retention period, or controller/processor
role.

Record:

- applicable regimes and why they may apply;
- the organization's role for each processing activity;
- purpose, lawful basis, data categories, recipients, retention, and transfer mechanism;
- the qualified reviewer, decision date, and re-review trigger where review is required.

## Canonical Topic Ownership

Repeated principles drift. The canonical owner defines the rule; other references link and add only
domain-specific consequences.

| Topic                                      | Canonical owner                                                   |
| ------------------------------------------ | ----------------------------------------------------------------- |
| Outcomes, requirements, and traceability   | [requirements and traceability](requirements-and-traceability.md) |
| Test strategy and evidence limits          | [testing](testing.md), [advanced testing](testing-advanced.md)    |
| Retries, deadlines, and circuit breakers   | [error handling](error-handling.md)                               |
| API idempotency and wire semantics         | [API design](api-design.md)                                       |
| Delivery, ordering, and distributed safety | [concurrency](concurrency.md)                                     |
| Durable-state integrity and migration      | [data](data.md)                                                   |
| Release identity, compatibility, deprecation, rollout | [release engineering](release-engineering.md)                     |
| Reliability targets, capacity, incident practice | [reliability](reliability.md)                                     |
| Build reproducibility, hermeticity, artifact provenance | [build reproducibility](build-reproducibility.md)                 |
| Security controls and threat modeling      | [security](security.md)                                           |
| Personal-data obligations                  | [privacy](privacy.md)                                             |
| Provider and deployment location           | [hosting](hosting.md)                                             |
| Comments and documentation lifecycle       | [documentation](documentation.md)                                 |
| Repository layout                          | [repository structure](repository-structure.md)                   |
| Technology/framework choice                | [technology selection](technology-selection.md)                   |
| Accessibility                              | [accessibility](accessibility.md)                                 |
| Cost, energy, and carbon                   | [cost and sustainability](cost-and-sustainability.md)             |

## Review Rubric

For every reference, ask:

- Which statements are external facts or standards? Are their source and status current?
- Which are defaults, preferences, heuristics, examples, or legal notes? Is that visible?
- Does an absolute statement name its scope and invariant?
- Are counterexamples and “when not to apply” treated seriously?
- Is the advice ecosystem-neutral unless the topic requires a concrete example?
- Does verification say what the evidence establishes—and what it cannot establish?
- Does another reference already own the principle?
- Are costs, accessibility, security, privacy, operability, and reversibility considered where
  relevant?

## Meta-Question

What kind of claim is this, who has authority to make it, how fresh is its evidence, and what would
justify overriding or re-verifying it?
