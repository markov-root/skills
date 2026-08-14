# Agentic tool-use and multi-agent prompting

**Route:** `agentic_tools`. Use for tool descriptions, delegation prompts,
subagents, handoffs, manager/worker systems, and agent orchestration. Generic
system prompts and repository instructions remain on `agent_system`.

## Start with the smallest topology

Default to one capable agent with the tools it needs. Add an agent only when at
least one benefit is concrete and measurable:

- independent work can run in parallel;
- a specialist has materially different knowledge/tools/context;
- isolation limits permissions or context exposure;
- an independent proposal or review reduces correlated error;
- ownership should transfer to a focused user-facing specialist.

More agents add routing, context transfer, disagreement, state, cost, and
termination failure modes. A persona label is not specialization.

## Choose orchestration semantics

- **Agent as tool / manager-worker:** a manager retains user-facing ownership,
  calls a specialist for a bounded deliverable, and synthesizes/verifies it.
- **Handoff:** control and user-facing ownership transfer to a specialist. Send
  typed routing metadata and only the relevant history.
- **Code workflow:** use deterministic code for known sequences, dependencies,
  budgets, permissions, retries, parallel joins, and stop rules.
- **LLM orchestration:** use when decomposition itself needs judgment and the
  runtime safely bounds choices.
- **Generate–evaluate–repair:** generate one candidate, evaluate each criterion
  with violation evidence, and repair only identified failures. Keep hard
  constraints in deterministic checks; use a calibrated semantic evaluator for
  soft requirements. Bound repairs and rerun all authoritative checks afterward.

Do not call a bounded specialist task a handoff, or assume a nested agent
inherits parent state. Make state transfer explicit.

A repair loop is not reliable merely because the same model says its revision
is better. Its value comes from separated responsibilities, explicit evidence,
independent or deterministic checks, bounded retries, and final revalidation.

## Design tool descriptions as routing prompts

Every tool description should state:

1. what outcome it provides;
2. when to use it and a nearby anti-trigger;
3. required arguments and distinctions that affect behavior;
4. side effects, idempotency, permissions, approval, cost, and latency;
5. result shape and how errors/partial results appear.

Use mutually exclusive scopes across neighboring tools. Prefer task-shaped
tools over thin API endpoints. Examples should target real ambiguity, not repeat
the schema. Runtime schemas and permission checks remain authoritative.

## Write a delegation packet

Give each specialist:

- one bounded objective and observable acceptance criteria;
- relevant inputs plus explicit source authority/trust;
- allowed tools, paths, state, spend, and side effects;
- dependencies and what other workers own;
- required deliverable schema with evidence/provenance;
- stop, escalation, and uncertainty behavior.

Tell the specialist what it must not decide when the manager owns that decision.
Return compact results and artifact paths, not an unfiltered transcript.

## Parallel and shared-state rules

Parallelize only independent work. If B needs A's result, sequence them or make
the dependency explicit in code. Prefer read-only workers and one writer.
Multiple writers require isolated workspaces, non-overlapping ownership, and a
named merge owner. Shared-file access does not imply permission to edit.

For independent judgment, blind author identity and collect proposals before
showing peer answers or votes. Otherwise herding or self-preference can erase
the intended diversity.

## Manager obligations

The orchestrator—not a worker—owns:

- dependency-aware scheduling and bounded retries;
- reconciliation of contradictions and duplicate work;
- validation of evidence, contracts, and side effects;
- integration/merge and final user-facing answer;
- termination when acceptance criteria pass or escalation is required.

“No worker reported an error” is not proof of completion. Verify artifacts and
observable state.

For consequential external effects, use an explicit **inspect → plan → approve
when required → act → verify** boundary. The preview must identify targets,
side effects, cost, reversibility, and the evidence used to select them. Do not
bundle a harmless read with a destructive, paid, privacy-sensitive, or
irreversible action in a way that bypasses the relevant approval. After acting,
verify the external state rather than trusting the tool's success message.

## Evaluate trajectories

Record each agent's received input, tools/permissions, calls/results, state
writes, output, and handoff/termination reason. Test role ambiguity, tool
overlap, missing context, dependency violations, concurrent writes, prompt
injection in worker inputs, partial failure, retry duplication, disagreement,
premature stop, and infinite delegation.

Score task success alongside routing accuracy, invalid calls, unauthorized
effects, duplicate work, merge conflicts, verification coverage, turns/tokens/
latency, and termination correctness.

Evidence and review provenance: [`../references/SOURCES.md`](../references/SOURCES.md).
