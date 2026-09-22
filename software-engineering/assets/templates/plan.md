---
schema_version: 2
id: "NNNN"
uid: plan-YYYYMMDDTHHMMSSffffffZ-RANDOM8
title: Execution plan
role: plan
status: active
summary: Bank ordered execution progress so work can resume from evidence, not memory, across sessions.
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
owner: PLAN OWNER
supersedes: ""
superseded_by: ""
engineering_document:
  version: 1
  contract_tier: full
  role: plan
  id: "NNNN"
  uid: plan-YYYYMMDDTHHMMSSffffffZ-RANDOM8
  title: Execution plan
  state: active
  authority:
    kind: execution-plan
    owner: PLAN OWNER
    scope: MUTABLE EXECUTION PROGRESS FOR ONE PROGRAMME OF WORK
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"
  transition_history: unverified
  transitions: []
  relationships: []
  details:
    objective: WORK THIS PLAN EXECUTES
    started: "YYYY-MM-DD"
---

# Plan NNNN: Execution plan

<!-- Quality bar — write to the Plan content standard
the software-engineering skill knowledge file knowledge/documentation-record-content-standards.md (section #plan):
objective and the task(s) it executes · small, independently bankable checkpoints · append-only
progress log with evidence · banked vs uncompleted state separated · a rewritten current resume
point. Discriminating test: if execution stops anywhere, can a successor identify what is banked,
what remains, and the exact next safe action? Route first: ordered multi-step work with bankable
checkpoints earns a plan; a single scheduling change is usually task state, and a durable decision belongs
in the project's decision record (see the worthiness table in knowledge/documentation-structure.md).
Audience and lifecycle judgment: decide deliberately
who reads this plan and whether it may travel beyond its current boundary. A contribution-facing
plan is a legitimate public record written for a cold outside reader; an operational plan may keep
necessary local detail in a correctly scoped access-controlled space. Judgment per plan — never a
default never-publish rule. Delete this comment once the plan is under way. -->

## Objective

The outcome this plan executes and the task(s) or programme it advances. One paragraph; link the
driving task/ADR by identifier.

## Approach

The ordered decomposition into small, independently checkpointable steps. Keep each step bankable —
completing it should leave verifiable evidence in the environment, not only in memory.

## Progress log

Append-only, dated checkpoint entries (newest last). Each entry records what was completed, the
evidence (commit, test run, file), and any decision made. This is the durable bank of progress.

## Current state

Where execution stands right now: the last completed checkpoint and the exact resume point. Keep
this section rewritten to the present so a cold reader can resume without the conversation.

## Next steps

The remaining ordered steps and the immediate next action. Do not silently broaden scope beyond the
Objective.
