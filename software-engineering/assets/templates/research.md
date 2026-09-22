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
  contract_tier: full
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

<!-- Quality bar — write to the Research content standard
the software-engineering skill knowledge file knowledge/documentation-record-content-standards.md (section #research):
a decision-relevant question stated up front · a reproducible method · sources with access dates ·
claims typed by strength · rival/null/conflict/currency records retained · bounded conclusion.
Discriminating test: can another investigator reproduce the selection and reasoning, derive the
strongest rival, explain why it loses, and name what would reverse the ordering? Research informs
decisions but is not decision authority. Delete this comment once the record is written. -->

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
