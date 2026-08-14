# Prompt evaluation templates

## Experiment plan

```text
Decision: <ship / select / diagnose / model-upgrade>
Behavior: <observable job the prompt must perform>
Primary metric: <name, direction, practical threshold>
Veto metrics: <safety, critical slices, cost/tokens, latency>

Dataset:
- development: <case IDs and role>
- validation: <case IDs and role>
- holdout: <frozen IDs; no optimization access>
- slices: <task/risk/locale/length/etc.>
- perturbations: <meaning-preserving variations>

Variants:
- baseline: <prompt hash/version>
- candidate: <prompt hash/version>
- isolated change/hypothesis: <one axis>

Runtime held constant: <model/version, sampling, effort, tools, schemas>
Trials per case: <N and why>
Graders: <criterion -> deterministic / calibrated LLM / human>
Analysis: <paired effect, uncertainty, slices, regressions>
Release gate: <quality + operational + safety thresholds>
Artifacts: <raw outputs/traces and full configuration snapshot>
```

## Defensive prompt-patch record

```text
Patch ID: <stable identifier>
Motivating failure: <case/trace and observable wrong behavior>
Target configuration: <model/version, prompt hash, harness, tools/schemas>
Change: <one instruction/example/layout axis>
Rationale: <why this change should address the failure>
Regression and counterexamples: <case IDs>
Owner: <maintainer or owning component>
Review/removal trigger: <model migration, date, or invalidating evidence>
Result: <run ID and bounded evidence>
```

## Failure-to-regression workflow

```text
1. Reproduce the production failure without changing the prompt.
2. Decide whether it is a requirement, capability, data, harness, tool, grader, model, or prompt
   failure.
3. Add a minimal labelled case to development; add neighboring counterexamples.
4. Propose one prompt change and run the full development + regression suites.
5. Select on validation, inspect changed traces, and check critical slices.
6. Run the frozen holdout once for the release claim.
7. Version the prompt, data, graders, and result; graduate the fixed case into
   the next regression-suite version.
```

## Prompt-optimizer boundary

```text
The optimizer may read DEVELOPMENT and receive VALIDATION scores.
It may not read HOLDOUT inputs, labels, outputs, or aggregate results.
Keep every candidate prompt, parent, change summary, target model, and score.
After selection, evaluate exactly one chosen candidate on HOLDOUT and report
both validation and holdout results. A holdout failure returns to a new
experiment version; do not keep tuning against the same holdout.
```

## Production-feedback change proposal

```text
Proposal ID: <stable identifier>
Deployed configuration: <prompt/config hash and version>
Triggering case: <trace/artifact ID; access-controlled if sensitive>
Observed action and rationale: <human action, override, correction, or outcome>
Signal classification: <durable preference | exception | corrected mistake | ambiguous | drift>
Proposed change: <prompt/data/tool/harness axis; no direct production mutation>
Immutable constraints checked: <policy, safety, privacy, legal, fairness, permissions>
Regression and counterexamples: <case IDs and affected slices>
Validation/holdout result: <run IDs, paired effect, regressions, uncertainty>
Reviewer and approval: <accountable owner and decision>
Promotion/rollback: <release ID, monitoring threshold, rollback target>
```
