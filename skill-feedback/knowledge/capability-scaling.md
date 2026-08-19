# Capability-scaling doctrine

## Purpose

Use this as the portfolio baseline when deciding whether to build, integrate, or buy an AI
capability.

> Buy cognition. Integrate routing. Own context, evidence, memory, policy, outcomes, and the stable
> capability contracts that connect them.

The goal is not to avoid ambitious orchestration work. It is to compete where local ownership creates
a durable advantage and to compose upstream intelligence rather than rebuilding a weaker copy.

## Current upstream baseline

OpenRouter already handles model selection, provider selection, load balancing, failover, and
cost/quality trade-offs. Its current documentation deprecates `openrouter/auto` in favor of
`openrouter/auto-beta`, which classifies tasks and ranks eligible models:

- <https://openrouter.ai/docs/guides/routing/routers/auto-router>
- <https://openrouter.ai/blog/insights/model-routing/>

Sakana Fugu goes further: it decides whether to answer directly or assemble agents, then performs
model selection, delegation, verification, and synthesis behind one model-like endpoint. Its internal
model choices and orchestration are intentionally opaque:

- <https://sakana.ai/fugu-release/>
- <https://sakana.ai/fugu/>

OpenRouter also exposes server-side Fusion panels, advisors, and subagents:

- <https://openrouter.ai/docs/guides/features/server-tools/overview>

Treat these as a capability baseline and as components or comparison targets. Re-check the sources
before relying on dated product details.

A dated first-party-source snapshot and the resulting portfolio applications are preserved in
Research 0001 (routing-orchestration-and-feedback-learning-landscape).

## Build-versus-integrate test

Prefer to build when the capability:

1. Uses private or local information upstream vendors cannot possess.
2. Encodes the owner's goals, preferences, policies, infrastructure, or accepted decisions.
3. Produces durable artifacts, provenance, auditability, or deterministic verification.
4. Can replace its model/router/provider backend without rewriting its domain contract.
5. Becomes more valuable when general model capability improves.
6. Can compose upstream routers or orchestrators as backends, voices, evaluands, or fallbacks.

Prefer to integrate or buy when the generic component is model selection, provider routing,
load-balancing, failover, generic multi-agent synthesis, general prompt optimization, embedding model
training, or another intelligence-layer capability where upstream systems have much larger training
and traffic advantages.

This is a default, not a prohibition. Compete with an upstream capability when local evidence shows a
specific advantage, but require a benchmark, an observable success criterion, and a credible path to
maintenance. "We might combine the components better" is a hypothesis to test, not a conclusion to
ban.

## Portfolio architecture

Keep a stable waist between domain capabilities and interchangeable intelligence:

```text
private data · policies · preferences · evidence · outcomes
                              |
                  stable skill/tool contracts
                              |
       Claude · GPT · Fugu · OpenRouter · local/future systems
```

Own the upper two layers. Treat the lower layer as replaceable and continuously evaluated.

## Consequences for current skills

- **Feedback:** learn which local capability and feature helped, separately from which backend powered
  it.
- **Evaluation:** test new models, routers, and skill versions on the owner's real workflows.
- **Research Database:** own curation, provenance, projects, and retrieval evaluation; integrate
  interchangeable retrievers and rerankers.
- **Homelab:** own the topology, telemetry, incident labels, and policies; use standard statistical or
  model components.
- **Debate:** compete on recorded protocol, auditability, blinding, labels, and measured uplift rather
  than generic panel synthesis alone; admit Fugu/Fusion as voices or baselines.
- **Software Engineering:** keep deterministic policy and evidence as the assurance floor around
  increasingly capable agents.
- **Media:** own lineage, production constraints, and personal preferences; replace generation
  backends freely.
- **Skill Installer:** own portable identity and contracts; do not assume it must out-route native
  frontier agents without evidence.
