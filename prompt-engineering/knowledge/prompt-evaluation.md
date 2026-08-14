# Prompt evaluation, experimentation, and regression

**Route:** `prompt_evaluation`. Use when designing prompt test sets, A/B
experiments, automatic optimization, release gates, or model-upgrade
regressions. Use `llm_judge` only for the focused rubric/grader component.

## Start with the decision

Write the behavior and release question before editing the prompt:

- What user/task distribution must this represent?
- Which failures are unacceptable?
- What primary metric decides selection?
- Which quality, safety, cost, and latency constraints can veto it?
- What minimum effect or threshold is practically meaningful?

Do not choose a metric merely because a platform exposes it. Match each success
criterion to the cheapest valid grader.

Before tuning, classify the failure. Ask whether the requirement and expected
answer are sound, whether the model has the needed capability, and whether the
data, prompt, harness, tool, grader, or runtime configuration caused the
observed behavior. Instructions can steer an available capability; they cannot
supply missing computation, retrieval, permissions, or model capability.

## Build two suites

**Capability suite:** difficult, discriminative cases that expose the current
frontier and guide hill-climbing. It can have a low baseline pass rate.

**Regression suite:** behavior the system already promises. It should pass at
or near the required reliability and block backsliding.

Populate both from real task distributions and failure traces. Include
known-good controls, previously failed edge cases, boundary, absence/abstention,
handoff/refusal, malformed, adversarial, long-context, and safety cases as
applicable. Add meaning-preserving variations of formatting,
wording, order, and irrelevant context to detect prompt sensitivity.

Annotate slices (task type, locale, length, risk, source, difficulty) so a gain
in a majority class cannot conceal a critical regression.

## Keep optimization and proof separate

Assign non-overlapping roles:

1. **Development:** inspect failures and propose prompt changes.
2. **Validation:** select among candidates and tune thresholds.
3. **Holdout:** run after selection to support the final claim.

Never repeatedly inspect and optimize against the final holdout. When a
production failure becomes a new regression case, version the suite and keep
the previous result's provenance.

Synthetic cases can expand coverage, but seed them from real requirements,
label their origin, deduplicate them across splits, and have a human review a
sample. Do not let the same model generate a case, expected answer, and sole
grade without independent validation.

## Run a controlled comparison

For a causal prompt A/B:

- establish a working baseline;
- state the hypothesis and change one instruction/example/layout axis;
- use the same input cases, model/version, sampling/reasoning settings, tools,
  schemas, and environment for both variants;
- randomize/interleave execution order when time or cache drift can confound it;
- record every raw output and error;
- repeat trials when generation or the workflow is stochastic.

Treat prompt text, model/version, reasoning settings, context assembly, tools,
schemas, output controls, and harness as one deployment configuration. Hold the
unexamined axes constant; when comparing models or architectures, name that axis
and retain the same cases and graders.

Use paired per-case differences. Report sample size, effect size, uncertainty,
aggregate result, important slices, and regressions. A point estimate from one
run is not a stable win.

Automatic prompt optimizers may change many dimensions. Treat their output as a
candidate with lineage, then evaluate it on data the optimizer never saw.

## Learn from production feedback without self-corruption

When user judgment or task distributions evolve, production outcomes can
discover missing requirements. They are not automatically correct labels.
Separate the feedback loop into governed stages:

1. preserve the deployed prompt/configuration and the triggering case;
2. record the action, optional rationale, provenance, and relevant context;
3. classify it as a durable preference, one-off exception, corrected mistake,
   ambiguous signal, or possible distribution drift;
4. let an optimizer or agent **propose** a versioned change, never mutate the
   deployed prompt directly;
5. require an accountable reviewer for policy, safety, legal, privacy, or
   fairness-affecting changes;
6. replay the full regression suite, neighboring counterexamples, affected
   slices, and a holdout before promotion;
7. monitor the promoted version and keep rollback available.

Keep immutable objectives, permissions, critical constraints, and protected
evaluation data outside the optimizer's write authority. Recent agreement can
improve local fit while erasing rare but important behavior; gate on critical
slices and regressions, not only aggregate agreement. If feedback comes from a
decision-support workflow, preserve the human decision and rationale rather
than silently treating a model recommendation or click as ground truth.

## Match grader to claim

Prefer, in order:

1. environment/outcome checks and executable tests;
2. schema, exact, enum, regex, set, numeric-tolerance, and citation checks;
3. task-specific deterministic metrics;
4. blinded pairwise or rubric-based LLM graders;
5. domain-expert/human review.

Combine graders when one cannot capture the whole outcome. Calibrate LLM
graders on human-labelled examples, measure disagreement, freeze their model and
rubric versions, and inspect both false positives and false negatives. Do not
use uncalibrated self-grading as a release oracle.

## Gate and preserve the run

A release contract should name:

- minimum primary-quality threshold and allowed regression;
- critical slice/safety thresholds;
- maximum cost/token and latency change;
- minimum reliability across repeated trials;
- holdout required or explicitly waived with a reason.

Save prompt text/hash, dataset and split version, case IDs, model/provider
version, all settings, tools/schemas, graders, timestamps, trial seeds/IDs, raw
outputs/traces, aggregate and slice metrics, failures, and release decision.

For a defensive prompt patch, also save the failure that motivated it, target
model/configuration, neighboring counterexamples, rationale, owner, and
review/removal trigger. On a model upgrade, rerun the unchanged regression
first and remove obsolete patches rather than layering new exceptions over
them.

After a model/provider upgrade, rerun the unchanged regression suite first.
Then retune against development/validation data and confirm once on the frozen
holdout.

Evidence and review provenance: [`../references/SOURCES.md`](../references/SOURCES.md).
