# Pre-flight checklist

Run before shipping a non-trivial prompt. Fast; catches most failures.

## Clarity & scope

- [ ] **The colleague test:** a person with minimal context could follow it without confusion.
- [ ] One-sentence job statement exists: task + audience + what "good" looks like.
- [ ] Scope is explicit (what to do _and_ what not to touch); no reliance on the model inferring intent.
- [ ] Instructions are **positive** ("do X"), not negative-only ("don't Y").
- [ ] Rules carry their **reason** where it helps the model generalize.
- [ ] The role describes the system truthfully; it does not pretend to be human or imply unavailable
      capabilities.
- [ ] Critique/advice prompts do not reveal the preferred verdict; evidence and criteria are stated
      neutrally, disagreement is allowed, and any known stakeholder preference is labelled as context.

## Structure

- [ ] Components ordered: instruction → context → input → output cue.
- [ ] Each distinct block is **delimited** (XML tags / consistent headers); variables are `{{tagged}}`.
- [ ] Long data on top, the ask at the bottom (if long-context).
- [ ] Prompt's own formatting matches the style you want back.
- [ ] Role, guidance, binding policy, tone, authoritative data, and dynamic input are distinguishable;
      irrelevant copied residue is removed and source precedence is explicit where needed.
- [ ] Only relevant history/files are carried forward; unrelated work starts in a fresh context or a
      deliberately reconstructed one.

## Technique fit

- [ ] Simplest technique that could work is the starting point (zero-shot before few-shot before CoT).
- [ ] Few-shot examples (if any) are 3–5, relevant, diverse, uniformly formatted, class-order mixed.
- [ ] Reasoning is used only where the task needs it — not blanket "think step by step" on a reasoning
      model.
- [ ] Reasoning is separated from the answer, and from any machine-readable output (reason → serialize).

## Output contract

- [ ] Exact output shape specified: fields, allowed values, length.
- [ ] Structured output uses a real schema/tool, not "return JSON-ish".
- [ ] An "I don't know / not enough information" escape hatch exists where hallucination is a risk.

## Model-era knobs

- [ ] Effort / thinking budget matched to difficulty (low for extraction, high for hard reasoning).
- [ ] No deprecated tricks (prefill on current Claude; `budget_tokens`).
- [ ] No over-emphatic "CRITICAL/MUST" scaffolding that would over-trigger.
- [ ] Verbosity/markdown steered explicitly if the default is wrong.
- [ ] Defensive model patches name their motivating regression and have a review/removal trigger.

## Myths removed

- [ ] No tipping/threats, no politeness-for-accuracy.
- [ ] No self-critique used as a correctness _verifier_ (rubric polish only).
- [ ] Not overloaded into one mega-prompt; decomposed/chained if multi-step.
- [ ] Judgment instructions state both sides of material trade-offs; hard limits remain runtime rules.

## Agents / tools (if applicable)

- [ ] System prompt sectioned (role, constraints, tool policy, context policy, output/stop/escalate).
- [ ] Tool descriptions say when-to-use / when-not, return schema, side effects, examples.
- [ ] Retrieved/tool content treated as untrusted data, not instructions.
- [ ] Consequential effects use inspect/plan/approval/act/verify with targets, cost, side effects, and
      reversibility visible before the action.
- [ ] Durable project context lives in a versioned CLAUDE.md/AGENTS.md, maintained like code.

## Evidence

- [ ] A tiny eval set / representative cases exist to test against.
- [ ] Plan to re-run the eval on the next model upgrade.
- [ ] Prompt, model/version, reasoning settings, tools/schemas, harness, tokens/cost, and latency are
      evaluated as one deployment configuration.
- [ ] Production feedback can only propose a versioned prompt change; review, regression/critical-slice
      checks, promotion evidence, monitoring, and rollback remain explicit.

> If you can't tick "the colleague test" and "output contract," fix those before anything else — they
> are the two highest-leverage boxes.
