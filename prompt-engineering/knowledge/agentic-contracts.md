# Agentic prompt contracts

## Tool description

```text
Name: <distinct task-shaped name>
Outcome: <what the caller receives>
Use when: <observable trigger>
Do not use when: <nearest competing case; name the alternative>
Arguments: <meaning, constraints, defaults, mutually exclusive fields>
Effects: <read/write/external message/cost/latency/idempotency>
Approval: <what requires confirmation>
Returns: <success, partial, no-data, and error shapes>
```

## Bounded specialist call

```text
Objective: <one independently completable result>
Acceptance: <observable checks>
Inputs: <only relevant context; authority/trust labels>
Permissions: <tools, paths, state, spend, side effects>
Dependencies: <none, or named completed artifacts>
Ownership: <what you own; what the manager/other workers own>
Deliverable: <schema, evidence, artifact paths>
Stop/escalate: <done, insufficient input, permission boundary, failure>
```

## Handoff

```text
Destination: <one specialist>
Reason: <routing category>
Ownership transfer: <what the specialist now owns>
Relevant history: <filtered summary, not automatic transcript dump>
Open user intent: <unresolved request>
Constraints/approvals: <still-active boundaries>
Completion: <whether specialist answers directly or returns control>
```

## Manager plan

```text
Why multiple agents: <measurable benefit over one agent>
Topology: <manager-tools | handoff | deterministic workflow>
Tasks: [{id, owner, dependencies, read/write scope, deliverable}]
Parallel groups: <only dependency-free tasks>
Merge owner: <one agent/process>
Verification: <per-deliverable and end-to-end checks>
Budgets/retries: <runtime-enforced limits>
Termination: <success, partial, escalation, and failure conditions>
Trace: <inputs, calls, results, state changes, decisions>
```

## Generate–evaluate–repair loop

```text
Objective: <one candidate artifact and acceptance criteria>
Generator input/output: <trusted inputs and candidate schema>
Hard checks: <deterministic criterion IDs and executable oracles>
Soft checks: <calibrated semantic criterion IDs and evidence contract>
Violation record: [{criterion_id, status, evidence, repair_scope}]
Repair rule: <change only evidenced failures; preserve passing invariants>
Maximum repairs: <runtime-enforced bound>
Revalidation: <rerun every hard check and affected soft check>
Termination: <all criteria pass | partial with evidence | escalation | budget exhausted>
Trace: <candidate versions, violations, repairs, check results, tokens/cost/latency>
```
