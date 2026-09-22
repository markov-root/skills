---
schema_version: 2
id: "NNNN"
uid: task-YYYYMMDDTHHMMSSffffffZ-RANDOM8
title: Title
role: task
status: todo
summary: Define a bounded task with explicit scope, acceptance criteria, and completion evidence.
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
owner: OWNER
supersedes: ""
superseded_by: ""
engineering_document:
  version: 1
  contract_tier: full
  role: task
  id: "NNNN"
  uid: task-YYYYMMDDTHHMMSSffffffZ-RANDOM8
  title: Title
  state: todo
  authority:
    kind: work-state
    owner: OWNER
    scope: BOUNDED ACCEPTANCE AND COMPLETION AUTHORITY
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"
  transition_history: unverified
  transitions: []
  relationships: []
  details:
    criteria: [criterion:AC-1]
    # Optional scheduling hints:
    # depends_on: ["0042"]
    # parent: "0090"
    # touches: ["software-engineering/public/**", "software-engineering/dev/tests/**"]
    # size: m
    # priority: p1
    # Under the agent_scheduling profile, an oversized task warns (advisory) and prompts a split.
    # Justify legitimately atomic large work with an exception that suppresses the prompt:
    # atomic_large:
    #   rationale: "why this cannot be split into vertical slices"
    #   rollback: "how to revert / verify if it goes wrong"
    #   checkpoints: ["intermediate checkpoint 1", "intermediate checkpoint 2"]
---

# Task NNNN: Title

<!-- Quality bar — write to the Task content standard
the software-engineering skill knowledge file knowledge/documentation-record-content-standards.md (section #task):
objective, independently judgeable acceptance criteria, honest scope and non-goals, criterion-linked
completion evidence. Discriminating test: can a reviewer decide "done" from the criteria and evidence
without undocumented proof or author clarification? Right-size to one reviewable slice; oversized
work splits by vertical slice under a parent epic. Route first: tasks are for work with
independent value — a bug or refactor can earn one even when small, and a task is also the right
home for ordinary scheduling (do not promote a date change into an ADR); pure narration and
one-branch details belong in a PR description or code comment. Delete this comment
once the task is written. -->

## Problem

What observable gap exists, for whom, and why it matters.

## Scope

What this task is authorized to change.

## Out of scope

What remains separate.

## Done when

- AC-1: Observable, bounded acceptance condition.

## Completion evidence

Keep empty until evidence exists. Before changing state to `done`, link the implementation, checks,
records, and limitations that satisfy each criterion.
