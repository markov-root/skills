---
schema_version: 2
id: "NNNN"
uid: research-YYYYMMDDTHHMMSSffffffZ-RANDOM8
title: Research question
role: research
status: planned
summary: Investigate one decision-relevant question with explicit method, sources, and uncertainty.
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
owner: RESEARCH OWNER
supersedes: ""
superseded_by: ""
engineering_document:
  version: 1
  role: research
  id: "NNNN"
  uid: research-YYYYMMDDTHHMMSSffffffZ-RANDOM8
  title: Research question
  state: planned
  authority:
    kind: research-record
    owner: RESEARCH OWNER
    scope: QUESTION AND DECISION BOUNDARY
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"
  transition_history: unverified
  transitions: []
  relationships: []
  details:
    question: PRECISE QUESTION
    started: "YYYY-MM-DD"
    method: SOURCE AND COMPARISON METHOD
    limitations: []
---

# Research NNNN: Research question

Research informs decisions but is not decision authority. If an ADR uses this deliberation, record
one `derived-from` relationship in the ADR; do not add a duplicate `decided-by` edge here.

## Question

Decision-relevant question, success conditions, and exclusions.

## Method

Search, comparison, experiment, and selection method.

## Sources

Primary sources or reproducible evidence with dates and versions.

## Findings

Evidence, competing explanations, and claim types.

## Uncertainty and limitations

Missing evidence, volatility, conflicts, and re-verification triggers.

## Conclusion

Bounded answer, unresolved questions, and decision handoff.
