---
schema_version: 2
id: "NNNN"
uid: adr-YYYYMMDDTHHMMSSffffffZ-RANDOM8
title: Decision
role: adr
status: proposed
summary: Record one bounded architectural decision, its forces, consequences, and alternatives.
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
owner: DECISION OWNER
supersedes: ""
superseded_by: ""
engineering_document:
  version: 1
  role: adr
  id: "NNNN"
  uid: adr-YYYYMMDDTHHMMSSffffffZ-RANDOM8
  title: Decision
  state: proposed
  authority:
    kind: decision-record
    owner: DECISION OWNER
    scope: DECISION BOUNDARY
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"
  transition_history: unverified
  transitions: []
  relationships: []
  details:
    decision_date: "YYYY-MM-DD"
    deciders: [DECIDER]
---

# ADR NNNN: Decision

Once accepted, preserve this decision body. Change direction with a superseding ADR and metadata
transition rather than rewriting the earlier rationale.

If a separate research record preserves material deliberation, add exactly one `derived-from`
relationship here targeting `research:NNNN`; do not duplicate the inverse link in the research
record.

## Context

Forces, constraints, and the decision required. Link detailed research instead of copying it.

## Decision

The chosen direction and its bounded authority.

## Consequences

Benefits, costs, responsibilities, compatibility effects, and revisit triggers.

## Alternatives considered

Concise rejected options and why. Keep extensive evidence, uncertainty, and open questions in a
research record.
