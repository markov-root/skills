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
---

# Task NNNN: Title

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
