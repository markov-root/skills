# Tuning for the model era (reasoning / "thinking" models)

**This is the file that goes stale fastest — treat it as versioned, re-checkable knobs, not timeless
law.** The 2025-2026 shift to reasoning models inverted several habits. Sources: provider docs
(Anthropic, OpenAI GPT-5, Gemini thinking) plus the empirical work cataloged in
[`../references/SOURCES.md`](../references/SOURCES.md).

## The big inversions

1. **Don't force chain-of-thought by default.** Generic "think step by step" gives small/inconsistent
   gains on non-reasoning models and little on reasoning models, while adding latency, tokens, and
   answer _variance_ — and it can **degrade instruction-following** (the model gets absorbed in
   reasoning and drops format/length/lexical constraints). _CONFIRMED:_ Prompting Science Report 2
   (Meincke/Mollick 2025); When Thinking Fails (2025); ReasonIF (2025); MathIF (2025).
   - **Do instead:** give a clear goal, constraints, tools, and an output contract. Let the model's
     _own_ thinking mechanism run, and spend a high reasoning budget only on genuinely hard coding /
     planning / math / multi-tool tasks.
2. **Newer models are more literal.** They won't silently generalize or infer unrequested work. State
   scope explicitly: "Apply this to _every_ section, not just the first." Conversely, remove old
   "anti-laziness" / "you MUST / CRITICAL" scaffolding — it now causes over-triggering and bloated
   answers.
3. **Reasoning ↔ obedience tradeoff.** More reasoning capacity can _reduce_ adherence to user
   constraints (Scaling Reasoning 2025). If a thinking model ignores a hard rule, put the rule _near
   where it applies_, keep it in the final instruction, and consider lowering effort for
   constraint-heavy formatting tasks.

## Effort / thinking budgets

Match the reasoning budget to task difficulty — high effort is not free and can _overthink_.

- **Anthropic (Opus 4.x)** — `effort: low | medium | high | xhigh | max` via `output_config`, with
  `thinking: {type: "adaptive"}` (model decides when/how much to think). Rough guide: `xhigh` for
  coding/agentic, `high` for intelligence-sensitive, `medium` cost-sensitive, `low` for short scoped
  latency-bound work. `max` hits diminishing returns / overthinks. At high effort, raise
  `max_output_tokens` (start ~64k) to leave room to think + call tools. `budget_tokens` extended
  thinking is **deprecated** on 4.6+.
- **OpenAI (GPT-5)** — reasoning-effort + verbosity controls; lower effort for classification/
  extraction/retrieval, higher for hard coding/debugging + a verification step.
- **Google (Gemini 2.5)** — controllable **thinking budget** + thought summaries; spend tokens only
  when the task needs them.
- **General rule (Stop Overthinking survey 2025):** for simple classification/extraction, _lower_
  reasoning improves latency/cost with no quality loss; only complex multi-step work earns high effort.
- **Steering the reasoning in-prompt (thinking off):** to suppress — "Thinking adds latency; use it
  only when it meaningfully improves the answer. When in doubt, respond directly." To encourage —
  "This involves multi-step reasoning; think carefully before responding." When thinking is disabled,
  some Claude models are sensitive to the literal word "think" — use "consider / evaluate / reason
  through." Prefer a general "think thoroughly" over a hand-written step list — the model's own plan
  often beats yours.

## Prefill is deprecated (Claude 4.6/4.7)

Assistant-message prefill errors or is ignored on current Claude models. Migrations:

- **Force JSON/schema** → use **Structured Outputs** (`output_config` + `json_schema`) or a tool with an
  enum, not a prefill trick or "return only JSON" incantation.
- **Kill preambles** ("Here is…", "Based on…") → instruct `Respond directly without preamble.` or wrap
  the answer in a tag / tool call and strip stragglers in post.
- **Continue an interrupted response** → move the continuation into the user turn.

## Verbosity, markdown, tools

- **Verbosity:** modern models calibrate length to perceived complexity. To shorten: "Provide concise,
  focused responses; skip non-essential context." Positive concision examples beat "don't be verbose."
- **Markdown/LaTeX:** some models default to heavy markdown or LaTeX math — override explicitly with a
  "flowing prose, reserve markdown for code/headings" block if you want plain text.
- **Tool-use triggering:** be explicit about act-vs-suggest ("Change this function…" edits; "Can you
  suggest…" only suggests). On models that use tools _less_ and reason more, raise effort or describe
  when/how to use a tool to increase usage; on models that over-trigger, dial back imperative language.
- **Parallel tool calls:** capable models parallelize well — "If you intend to call multiple tools with
  no dependencies between them, make all the independent calls in the same turn."

## Sampling parameters (when you control them)

- **Temperature** 0 = deterministic/greedy; higher = more random (beyond ~1 it dominates and can loop).
  **CoT/single-correct-answer tasks: temp 0.** Self-consistency: raise temp to get diverse samples.
- **Top-P / Top-K** shape the candidate pool; extreme settings cancel the others (temp 0 → top-k/p
  irrelevant; k=1 → greedy). Google starting points: balanced `temp 0.2, top-P 0.95, top-K 30`;
  creative `0.9 / 0.99 / 40`; conservative `0.1 / 0.9 / 20`.
- **Repetition-loop bug:** both extremes (too greedy / too random) can cause filler loops — tune toward
  the middle.
- **Output length is a _stop_, not a compressor** — lowering max tokens truncates; it doesn't make the
  model concise. Engineer brevity in the prompt.

## Re-test on every model change

A prompt tuned for one model generation can regress on the next — sensitivity, default verbosity, tool
eagerness, and reasoning behavior all shift. Keep a small eval set and re-run it when you upgrade.
