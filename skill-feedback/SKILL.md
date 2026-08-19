---
name: skill-feedback
description: >-
  Record evidence-backed feedback and outcomes for skills: noteworthy positive
  value, friction, bugs, wishes, ideas, invocation results, and lifecycle
  dispositions. Use after a skill materially helps or hinders a task; when
  reviewing, prioritizing, preserving, resolving, declining, or deduplicating
  portfolio feedback; after creating, installing, or registering a skill that
  needs feedback onboarding; or when instrumenting a tool-backed skill through
  the shared event contract. Qualitative notes stay beside each skill under
  docs/feedback/, while privacy-safe events go to a central append-only ledger.
  Do NOT use for feedback about the user's project code, generic praise with no
  reusable lesson, or inferred user satisfaction.
license: Apache-2.0
compatibility: Requires Python 3.11+ (stdlib only; needs tomllib)
metadata:
  version: "0.5.0"
---

# Skill Feedback

Make the skill library improve from real use without teaching every skill its
own feedback system.

## Ownership boundary

Feedback is a cross-cutting capability:

- Each skill knows **when** it was invoked and which feature/backend it used.
- The Feedback CLI owns **how** observations and outcomes are represented,
  validated, stored, filtered, and eventually learned from.
- Tool-backed skills use either explicit `start`/`finish` calls or a
  Feedback-owned, repository-versioned adapter at their outer execution
  boundary.
- Text-only skills rely on the harness/agent to emit noteworthy observations.
- Automatic CLI instrumentation is explicit per command and privacy-gated.
  Describe coverage only for boundaries that actually emit; pure-text
  activation still depends on harness/agent emission.

Route every emission through this CLI so one event and privacy contract evolves
centrally.

## After creating or installing a skill

Run:

```bash
skill-feedback onboard <skill>
```

This resolves the skill from the installed skill directories (skills.sh places
skills under each harness's skill folder) and the writable source artifacts
under `SKILLS_HOME/<name>/public`, then returns the current boundary,
operator-policy readiness, exact next actions, and verification gates. Run
`skill-feedback onboard --check --json` after a batch installation to obtain
one machine-readable portfolio receipt. Inventory failure is an explicit
failing gate with an unavailable population. A future skill appears
automatically once installed or present under `SKILLS_HOME`; keep Feedback
runtime code inventory-agnostic. Reserve `SKI_REGISTRY` (and an explicit
`SKILL_MANAGER_COMMAND`, for compatibility with an instrumented Manager) for
explicit test/operator integrations.

## Instrument every new reliable CLI boundary

When creating or changing a tool-backed skill with a stable executable:

1. Identify the outer command and its documented exit semantics.
2. Generate a source-owned adapter:

   ```bash
   skill-feedback wrapper <skill> \
     --feature <stable-feature> \
     --target <real-executable> \
     --output <repository-adapter> \
     --apply
   ```

3. Add repeatable `--success-exit-code N` for nonzero codes that mean correct
   control states.
4. Commit the adapter beside the skill in its `scripts/` so skills.sh installs
   it as an ordinary executable.
5. Re-run the command without `--apply` and require `status=current`.
6. Test public invocation, privacy-off fallback, expected exits, ordinary
   failure, and signals in proportion to the command's risk.
7. Run `skill-feedback coverage --check --declared-only`.

The adapter must be committed beside the skill in its `scripts/`. skills.sh
places it as an ordinary executable and contains no Feedback-specific policy. For MCP,
text-only, paid, resumable, exact-parent, or unusual process-group capabilities,
select and verify the real emission boundary; classify CLI adapter coverage
only after the public path crosses that boundary.

## Capability-scaling boundary

Own the library's portable contracts, private context, evidence, outcomes,
privacy, evaluation, and preservation rules. Treat frontier models, generic
routers, and opaque agent orchestrators as interchangeable backends or
comparison targets. Propose custom routing or learned control only when a real
local workload, benchmark, and shadow evaluation show an advantage. Read
[`knowledge/capability-scaling.md`](knowledge/capability-scaling.md)
before adding ML, RL, model selection, or multi-agent policy to this loop.

## Standing convention

After using any skill, record feedback when the event teaches a reusable lesson:

```bash
skill-feedback praise <skill> "<what helped, on which task, and why>"
skill-feedback friction <skill> "<what impeded the task, and the smallest useful fix>"
```

Positive feedback should identify the exact capability that earned preservation
or reuse. A successful exit code, generic thanks, or an agent praising its own
work belongs to telemetry. Require affirmative evidence before attributing
user satisfaction. If evidence is insufficient, record the outcome as unknown
or omit the qualitative judgment. For an unsupported requested attribution,
respond exactly: `I don't know / not enough information.`

Use `--source` honestly:

- `explicit_user`: the user directly said it.
- `observed_user`: repeat use, acceptance, correction, or abandonment was seen.
- `deterministic`: a test, validator, or exact check established it.
- `independent_evaluation`: a separate evaluator established it.
- `agent_judgment`: the acting agent's assessment.
- `automation`: a wrapper emitted a lifecycle fact.

## Record observations

```bash
skill-feedback praise debate \
  "Resume preserved the panel after an SSH disconnect" \
  --feature resume --outcome success --impact high \
  --source observed_user --evidence task:debate-42

skill-feedback friction research-database \
  "Full-text search missed a system card; a body-tier option would have found it" \
  --feature search --outcome partial --impact medium

# Long or multiline note:
skill-feedback codex-cli - --kind idea --feature usage-report <<'EOF'
Include token counts in JSON output so callers can budget without a second call.
EOF
```

Kinds are `wish`, `friction`, `bug`, `praise`, and `idea`. Praise defaults to
positive signal and non-actionable `observed` status. Friction and bugs default
to negative signal and actionable `open` status. Use `preserve` when a positive
property is important enough to protect with a regression test or design
constraint.

Minimize qualitative prose before recording: describe the reusable capability
lesson without private task content, personal identifiers, credentials, or
machine-specific details. The CLI rejects high-confidence secrets and requires
review for likely identifiers such as email addresses, user-home paths, IP
addresses, internal hostnames, SSH remotes, URL queries, and explicitly
labelled person/contact fields. Prefer generalizing the note. Use
`--privacy-reviewed` only when an operator or maintainer has actually reviewed
the flagged content and determined it belongs in local storage; reserve it for
that reviewed case. If the check fires, rewrite the smallest complete idea so
the note still identifies the capability, behavior, causal condition, and
useful fix. Preserve that causal meaning while generalizing the matched
context.

## Emit invocation outcomes

Tool wrappers can join execution facts to later observations:

```bash
invocation_id="$(skill-feedback start codex-cli \
  --feature research --model gpt-5.5 --source automation)"

skill-feedback finish codex-cli "$invocation_id" \
  --outcome success --duration-ms 1830 --source automation \
  --evidence test:research-contract
```

Record only backend fields actually known at the boundary. Use null provider
and model values for opaque routers.

## Review and close the loop

```bash
skill-feedback review
skill-feedback review --json --kind friction
skill-feedback list debate --json
skill-feedback deliver                  # preview all pending notes
skill-feedback deliver debate --apply   # verify canonical copy, then prune outbox
skill-feedback privacy-check            # audit qualitative prose
skill-feedback privacy-check debate --json
skill-feedback privacy-check debate --acknowledge ID \
  --note "Reviewed for local storage"      # dry-run
skill-feedback privacy-check debate --acknowledge ID \
  --note "Reviewed for local storage" --apply
skill-feedback events --skill debate --limit 20
skill-feedback stats --after 2026-07-01T00:00:00Z --group-by skill
skill-feedback doctor --json
skill-feedback coverage --json
skill-feedback onboard <skill> --json
skill-feedback triage debate ID --status planned \
  --note "Promoted to task-0042" --task task-0042
skill-feedback triage debate ID --status preserve \
  --note "Protected by resume regression test" --test test_resume
skill-feedback triage debate ID --status duplicate \
  --note "Same root cause" --duplicate-of OTHER_ID
```

Actionable review excludes praise by default. Raw notes are immutable except for
documented semantic privacy remediation that preserves the stable feedback ID
and content-free hash lineage; a status sidecar records ordinary dispositions.
Statuses are `open`, `observed`, `preserve`, `planned`, `resolved`, `declined`,
and `duplicate`.

`stats` uses invocation starts as the use denominator, joins matching finishes,
and keeps incomplete/conflicting outcomes explicit. It reports praise,
friction, preservation guards, and later negative evidence without producing a
scalar ranking. Every report also carries the current portfolio coverage
summary, and each skill group carries its coverage status. If inventory or
coverage is incomplete, the report says the usage denominator is incomplete.
Treat the aggregates as descriptive associations; require separate causal
evidence before changing routing policy.

## Record meta-feedback

Target this skill through the same qualitative contract:

```bash
skill-feedback praise skill-feedback \
  "Review preserved a lesson across tasks" --feature review
skill-feedback friction skill-feedback \
  "The process hid pending delivery" --feature delivery
```

Use features such as `record`, `review`, `triage`, `delivery`,
`instrumentation`, `privacy`, or `meta-feedback` to locate the process surface.
Keep the `skill-feedback` executable self-exempt in automatic coverage: direct
qualitative recording already emits exactly one note and event, while automatic
self-wrapping would recurse.

## Data and privacy

- Human-readable observations:
  `<skill-repo>/docs/feedback/YYYY-MM-DD.md`
- Pending notes for read-only/unresolved skills:
  `$SKILL_FEEDBACK_HOME/note-outbox/<skill>/docs/feedback/YYYY-MM-DD.md`
- Dispositions:
  `<skill-repo>/docs/feedback/.status.json`
- Verified outbox deliveries:
  `<skill-repo>/docs/feedback/.delivery.json`
- Machine events:
  `$SKILL_FEEDBACK_HOME/events.jsonl`

`SKILL_FEEDBACK_HOME` is an explicit override. Without it, new installations
use the platform-local state directory (on Linux,
`${XDG_STATE_HOME:-~/.local/state}/skill-feedback`). An existing legacy
`~/Skills/exported-data/skill-feedback` directory remains in place, keeping an
upgrade on one ledger.

The event ledger excludes note bodies, prompts, outputs, and command lines by
default. It stores hashes, local references, structured metadata, and evidence
references. Qualitative observations and disposition rationales are screened
locally before CLI persistence. `privacy-check` and `doctor` also audit legacy,
curated, manually edited, source, and pending notes without returning their
prose. Keep tags, evidence references, IDs, and backend fields free of secrets
and sensitive user content.

Pattern screening is a limited guardrail. Agents decide whether an arbitrary
proper name, project name, or combination of harmless-looking details
identifies someone and generalize content before
recording. Manual Markdown edits can only be detected after the write.
Historical review acknowledgements are dry-run-first and bind to the exact
entry hash plus scanner findings; a content or finding change makes them stale.
Likely secrets cannot be acknowledged and must be removed or redacted.
For historical remediation, preserve actionable meaning and keep the stable
feedback ID plus a content-free hash lineage while redacting the matched
context.

Privacy controls are local and dry-run-first:

```bash
skill-feedback doctor --json
skill-feedback privacy-check --json
skill-feedback export --skill debate --out debate-events.jsonl
skill-feedback retention --forever         # explicit indefinite retention
skill-feedback retention --days 90 --json  # bounded alternative
skill-feedback collection --manifest-opt-in # permit source-adapter collection
skill-feedback collection --off            # disable every automatic wrapper
skill-feedback retention --apply           # explicit deletion
skill-feedback delete --session ID --json  # targeted preview
skill-feedback delete --session ID --apply
skill-feedback doctor --migrate-privacy    # upgrade legacy IDs/paths
```

Content capture is fixed off. Automatic collection defaults off and requires
both explicit retention plus `manifest_opt_in`; each command must also opt in
by executing through a Feedback-owned adapter. The privacy mode retains its
historical name for configuration compatibility. Use
`SKILL_FEEDBACK_DISABLE=1` for an
environment-scoped global opt-out or
`SKILL_FEEDBACK_DISABLE_SKILLS=name,...` for selected skills. Session
identifiers are keyed pseudonyms, and note paths are portable relative
references. A read-only source records `delivery=pending` in the private outbox
rather than losing or falsely delivering the note.
Read-only commands perform zero lock creation, mode changes, or state repair. `doctor`
reports repair actions separately; shared reads use an existing lock when one
is available and otherwise perform a best-effort read.
Telemetry deletion covers the private event ledger; repository notes, Git
history, previous exports, and backups have separate owner-managed lifecycles.

The versioned envelope and semantics are documented in
[`knowledge/feedback-v2-contract.md`](knowledge/feedback-v2-contract.md).
Read [`knowledge/privacy-controls.md`](knowledge/privacy-controls.md)
when configuring retention, export, or deletion.
Read
[`knowledge/automatic-instrumentation.md`](knowledge/automatic-instrumentation.md)
when adding a wrapper boundary or evaluating its process semantics.
Read
[`knowledge/inventory-and-read-side-contract.md`](knowledge/inventory-and-read-side-contract.md)
for inventory authority, read-side behavior, locking, and statistics coverage.
The JSON Schema is
[`assets/schemas/feedback-event.schema.json`](assets/schemas/feedback-event.schema.json).

## Routing boundaries

- Route feedback about the user's project code to that project's tracker.
- Store praise only for a specific reusable capability-level lesson.
- Keep private prompts and outputs outside training data.
- If a safe fix is tiny and already in scope, fix it and then record the
  resolution only when the history will be useful.
