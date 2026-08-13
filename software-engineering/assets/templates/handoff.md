---
schema_version: 2
id: "NNNN"
uid: handoff-YYYYMMDDTHHMMSSffffffZ-RANDOM8
title: Continuation checkpoint
role: handoff
status: current
summary: Preserve a bounded continuation checkpoint with evidence, open work, blockers, and resume state.
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
owner: HANDOFF OWNER
supersedes: ""
superseded_by: ""
engineering_document:
  version: 1
  role: handoff
  id: "NNNN"
  uid: handoff-YYYYMMDDTHHMMSSffffffZ-RANDOM8
  title: Continuation checkpoint
  state: current
  authority:
    kind: continuation-state
    owner: HANDOFF OWNER
    scope: NEXT-SESSION CONTINUATION ONLY
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"
  transition_history: unverified
  transitions: []
  relationships: []
  details:
    captured_at: "YYYY-MM-DDTHH:MM:SSZ"
    repository: REPOSITORY IDENTITY
    revision: COMMIT OR DIRTY-STATE IDENTITY
    objective: CURRENT OBJECTIVE
    completed: []
    open_work: [task:NNNN]
    blockers: []
    authority_refs: [AGENTS.md, docs/tasks/NNNN-title.md]
    resume: FIRST SAFE COMMAND
---

# Handoff NNNN: Continuation checkpoint

## Outcome

Current bounded result and proof limits.

## Completed work

Implemented and verified records, with identifiers.

## Open work

Remaining tasks in dependency order. Do not silently broaden their scope.

## Blockers

Required user decisions, permissions, missing evidence, or `None`.

## Resume

First safe command, authority files to read, and verification state to re-establish.
