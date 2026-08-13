---
schema_version: 2
id: "NNNN"
uid: audit-YYYYMMDDTHHMMSSffffffZ-RANDOM8
title: Audit title
role: audit
status: draft
summary: Preserve a point-in-time audit's scope, method, findings, limitations, and disposition.
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
owner: AUDIT OWNER
supersedes: ""
superseded_by: ""
engineering_document:
  version: 1
  role: audit
  id: "NNNN"
  uid: audit-YYYYMMDDTHHMMSSffffffZ-RANDOM8
  title: Audit title
  state: draft
  authority:
    kind: point-in-time-evidence
    owner: AUDIT OWNER
    scope: SUBJECTS AND AS-OF BOUNDARY
  created: "YYYY-MM-DD"
  updated: "YYYY-MM-DD"
  transition_history: unverified
  transitions: []
  relationships: []
  details:
    as_of: "YYYY-MM-DD"
    subjects: [SUBJECT AND VERSION]
    method: BOUNDED METHOD
    limitations: []
---

# Audit NNNN: Audit title

## Scope

Subjects, versions, environment, and time boundary.

## Method

Repeatable inspection method and selection limits.

## Findings

Observed facts separated from inference.

## Limitations

What was not observed or established.

## Disposition

Accepted follow-up, owner, or explicit no-action decision.
