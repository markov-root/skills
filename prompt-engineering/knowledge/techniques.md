# Technique catalog

Synthesized from Anthropic, Google (Boonstra 2025), and IBM (2026) guidance, reconciled with 2025-2026
empirical work (see [`../references/SOURCES.md`](../references/SOURCES.md)). Each entry: **what · when · template**. Golden rule: start with
the simplest technique that could work; add complexity only when an eval shows it pays.

## Choosing — a decision order

1. **Zero-shot** always first. Clear instruction + context + output contract beats a pile of examples
   surprisingly often on capable models.
2. Add **few-shot** only when the target behavior is hard to _describe_ but easy to _show_ (format,
   tone, a labeling scheme). Stop at 3–5 good, diverse examples.
3. Add **reasoning** (CoT / decomposition) only when the task genuinely needs intermediate steps —
   and on reasoning-era models, prefer the model's own thinking to hand-forced "step by step" (see
   `model-era.md`).
4. Reach for **retrieval (RAG)** when facts are fresh/proprietary; **tools (ReAct/ART/PAL)** when the
   model must act or compute; **multi-sample (self-consistency)** only for accuracy-critical reasoning
   where you can afford N× cost.
5. Escalate to **search-style methods (ToT), meta-prompting, chaining** only for genuinely hard,
   repeatable, or multi-stage problems.

> No single technique dominates across tasks/models (Santana 2025, _Which Prompting Technique…_; The
> Prompt Report 2024). Use the catalog to
> generate candidates; use an eval to pick.

## Example-based (in-context learning)

- **Zero-shot** — task description, no examples. _When:_ default; simple/known tasks; no labeled data.
  _Template:_ `Classify the review as POSITIVE, NEUTRAL, or NEGATIVE. Return only the label.\nReview: "..."`
- **One-shot** — one worked example. _When:_ a single example nails the format and more are impractical.
- **Few-shot** — 3–5 input→output pairs. _When:_ lock an output format/label scheme; lift accuracy on
  structured tasks. _Rules:_ examples must be **relevant** (mirror real use), **diverse** (cover edge
  cases so the model latches the _feature_, not an accidental pattern), **consistently formatted**, and
  wrapped in delimiters. For classification, **mix up the class order** so the model doesn't overfit to
  order. **More is not better** — too many examples can _degrade_ accuracy ("over-prompting"; Few-shot
  Dilemma 2025). Retrieve the _most similar_ examples (semantic/BM25) rather than piling on quantity.

## Reasoning-elicitation

- **Chain-of-Thought (CoT)** — elicit intermediate steps before the answer. _When:_ multi-step math,
  logic, commonsense; when you need a debuggable trace. _Template:_ append `Think step by step.` or,
  few-shot, show the reasoning in each example. **Answer MUST come after the reasoning** (generating the
  reasoning changes the tokens available for the answer). **Caveat (2025-2026):** on modern reasoning
  models generic CoT gives small/inconsistent gains, adds latency/variance, and can _hurt instruction
  following_ — see `model-era.md` and `anti-patterns.md`.
- **Self-consistency** — sample CoT N times (higher temp), majority-vote the answer. _When:_ a single
  CoT is unreliable and accuracy is worth N× cost. Also a decent **calibration/confidence** signal —
  but consistency can amplify a _wrong_ answer, so it's not a guarantee (Lyu 2025).
- **Step-back prompting** — first ask a general/abstract question, feed its answer back as context for
  the specific task. _When:_ activate background knowledge, reduce anchoring. _Template:_ (1) "What
  principles make a good X?" → (2) "Using those principles, do the specific task."
- **Generate-knowledge** — have the model list relevant facts/principles first, then answer using them.
  _When:_ grounding a knowledge-heavy answer.
- **Tree-of-Thoughts (ToT)** — branch into multiple reasoning paths, score, backtrack. _When:_
  search/planning/puzzles where early choices dominate (Game-of-24, scheduling). _Cost:_ heavy; can
  redundantly explore low-value branches. Components: decompose → generate (sample vs propose) →
  evaluate (value vs vote) → search (BFS/DFS).
- **Reflexion** — model critiques and revises its own prior output. _When:_ iterative refinement with a
  _clear rubric_. **Warning:** self-critique is a weak _verifier_ for reasoning/planning (Stechly 2025)
  — use an external/sound check, not "grade yourself," when correctness matters.

## Role, context & framing

- **Role / persona** — assign an identity to steer tone/expertise. _Template (system):_
  `You are a compassionate, experienced veterinarian.` One sentence in the system prompt is usually
  enough. Keep persona in `system`, the variable task in `user`.
- **Contextual prompting** — supply task-specific background so output is relevant to a narrow
  situation. _Template:_ `Context: writing for a blog about retro 80s arcade games. Suggest 3 topics.`
- **System prompting** — global rules: output format, language, safety, refusal behavior. Put invariant
  policy here; keep per-turn execution prompts single-purpose.
- **Neutral elicitation** — do not reveal the verdict you want when asking for critique, forecasting,
  or advice. State evidence and decision criteria, explicitly permit disagreement, and ask what would
  change the conclusion. _When:_ sycophancy or confirmation bias would make an agreeable answer
  harmful. A neutral frame reduces anchoring; it does not make the model objective.

## Retrieval, tools & code

- **RAG** — retrieve external/current/proprietary data (vector/semantic search) and inject it. _When:_
  accuracy on fresh or domain facts is paramount. Pairs with few-shot (retrieve the best exemplars).
- **ReAct** — interleave Reason + Act (tool calls) in a loop. _When:_ the model must fetch info or act.
  Control output length (models emit filler after the answer). See `context-engineering.md`.
- **ART / ATC** — reasoning + external tools/APIs (calculator, search) for steps the model shouldn't do
  in its head.
- **PAL / Program-Aided** — offload computation to generated code, then explain the result. _When:_
  arithmetic/data work an LLM is unreliable at. Always read/run generated code — LLMs can't truly do
  math and will confidently err.

## Orchestration & automation

- **Prompt chaining** — split a complex task into a sequence of single-purpose prompts, each output
  feeding the next. _When:_ multi-step pipelines; you want observability and lower error rates.
  Distinct from CoT (reasoning _within one_ prompt). Most common pattern: **draft → review against
  criteria → refine**, each a separate call.
- **Explore → select → refine** — generate a bounded set of materially different options, obtain user
  selection or criterion-level feedback, then elaborate the selected direction. _When:_ brainstorming,
  planning, or creative work where the first request under-specifies preferences. Preserve rejected
  constraints so later rounds do not cycle back to them.
- **Outline → inspect → expand → draft** — settle document structure and section claims before writing
  final prose. _When:_ a structural correction would otherwise require rewriting large passages. End
  with a whole-document coherence and evidence pass.
- **Iterative prompting** — like chaining, but each step validates/refines the previous under a
  standing "behaviour policy" (thresholds, schema, refusal rules) held separate from per-turn prompts.
- **Meta-prompting** — give the model a reusable _template of how to think_ about a whole **category**
  of problems (not one instance). _When:_ repeatable classes (math, code, structured writing) needing
  consistency. Variants: user-provided, recursive (model writes its own template then solves),
  conductor (an orchestrator writes specialist prompts for sub-agents).
- **APE / automatic prompt optimization** — generate candidate prompts, score against a metric, keep
  the winners, iterate. _Mental model (DSPy):_ not "LLM critiques my prompt" — it's evolutionary
  selection on a fitness metric. "Compiling often beats human writing because optimizers try more,
  more systematically."

## Grounding / anti-hallucination (technique bundle)

- **Permit "I don't know":** `If you're unsure, say "I don't have enough information."`
- **Quote-first (long context):** ask the model to extract exact supporting quotes into `<quotes>`
  _first_, then answer only from those.
- **Cite-then-claim:** after drafting, require a supporting quote per claim; retract unsupported ones.
- **Restrict to provided context:** forbid using general knowledge when answering from documents.
- **Source-class steering:** for current, local, niche, or high-stakes research, name required recency,
  jurisdiction, and source classes (for example primary data, official documentation, or peer-reviewed
  evidence). Treat those classes as selection constraints, not proof of correctness.
- **Citation entailment:** open the cited source and check that it supports the exact entity, period,
  version, and claim. Citation presence alone is not groundedness.

See `structure.md` for how to lay these out, `model-era.md` for reasoning-era tuning, and
`anti-patterns.md` for what to avoid.
