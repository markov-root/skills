# Structure & ordering

How to lay a prompt out. Structure moves accuracy as much as wording does (formatting alone changes
scores — CFPO; "A Single Character" 2025 shows delimiter choice can swing MMLU ±23%). So treat layout
as a first-class variable, and test it in your own evals.

## The four components, in order

**Instruction → Context → Input data → Output cue** (IBM's canonical order). Not every task needs all
four, but this order rarely hurts.

```
<instruction>Summarize the report for a non-technical exec. 3 bullets, ≤15 words each.</instruction>
<context>Audience: board members with no ML background. Tone: plain, confident.</context>
<input>{{REPORT_TEXT}}</input>
Summary:            ← output cue primes the response form
```

- **Open with a verb.** Act, Analyze, Classify, Compare, Extract, Generate, List, Rank, Rewrite,
  Summarize, Translate, Write… A concrete verb beats "I was wondering if you could…".
- **Output cue** (a trailing `Summary:` / `JSON:` / `Class:`) primes the shape — cheap and effective.

## Delimiters — mark every distinct block

Wrap each _type_ of content in its own clearly-named block so the model can't confuse instructions with
data. XML-style tags are the most robust and are Claude's native idiom, but consistent Markdown headers
or fenced blocks also work — **the consistency matters more than the syntax**.

```
<instructions>…</instructions>
<context>…</context>
<examples>
  <example>…</example>
</examples>
<input>…</input>
```

- Use **descriptive, consistent** tag names; nest for hierarchy (`<document index="1">` inside
  `<documents>`).
- **Match prompt style to desired output.** The formatting of your prompt bleeds into the output —
  strip markdown from the prompt and you get less markdown back; write in flowing prose and you get
  prose. Don't format the prompt in a style you don't want echoed.

## System vs user

- **System prompt:** the invariant layer — role/persona, global rules, output policy, safety, tool
  policy. One good sentence of role focuses tone.
- **User message:** the variable task, the input, per-interaction rules. Few-shot examples go at the
  **start of the first user message**.
- **Front-load task + intent + constraints** for autonomous/single-turn work — an underspecified
  prompt spread across turns reduces efficiency and sometimes quality.

## Role and context hygiene

- Describe the system's real function. A role may steer expertise or tone, but do not claim an AI
  system is a human or give it capabilities the harness has not supplied.
- Remove copied navigation, cookie notices, image labels, and other residue that has no task value.
  More context is not automatically better context.
- Keep role, general guidance, binding policy, tone, authoritative data, and dynamic input visibly
  separate. When sources can conflict, state their scope and precedence rather than making the model
  infer which one governs.

## Long-context placement (inputs ≳ 20k tokens)

- **Put the long data/documents at the TOP; put the query/instructions at the BOTTOM.** Query-at-end
  can improve quality by up to ~30% on multi-document inputs (Anthropic).
- Wrap each document with source + content:
  ```
  <documents>
    <document index="1"><source>q3.pdf</source><document_content>{{DOC1}}</document_content></document>
  </documents>
  Question: …
  ```
- **"Lost in the middle" is not solved.** Single relevant fact ≈ robust on modern models, but
  multi-evidence tasks and the spacing/position of the pieces still bias answers (LongPiBench 2025;
  Wan 2025). Mitigations: put the most critical evidence at the edges, extract quotes first, or reduce
  the window with retrieval rather than stuffing everything in.

## Ordering examples (few-shot)

- **Simple → complex** so the model builds context gradually.
- For **classification**, randomize the class order across examples — same-order examples cause the
  model to overfit to order, not features.
- **Select by relevance,** not count — retrieve the most similar exemplars (semantic/BM25). One bad or
  ambiguous example can poison the set.
- For **reasoning** tasks, format examples as chains (`Premise → Reasoning → Conclusion`), not bare
  input→output pairs.

## Separate reasoning from the answer, and from machine-readable output

- Put deliberation in `<thinking>`/`<analysis>` and the deliverable in `<answer>`/`<result>` — makes
  the answer extractable (needed for self-consistency) and lets you discard the reasoning.
- **Reason first, serialize second.** Forcing the model to reason _inside_ a strict JSON/XML schema can
  cost accuracy ("The Format Tax" 2026, esp. on smaller/open models). When accuracy matters, let it
  reason in prose, then emit the structured object as a final step (or a second call).
- Treat formatting as a prompt-and-harness contract. The prompt defines field meaning and behavior;
  native schemas/tool contracts, parsers, validators, stop controls, retries, and escalation enforce
  what the runtime can. A stop sequence can bound generation but cannot validate semantics.

## Templates & variables

- Separate fixed scaffolding from variable content; mark variables `{{DOUBLE_BRACKETS}}` and wrap them
  in a tag. Benefits: consistency, testability, version control, and no accidental hardcoding.
- Store prompts in files separate from code; version them; keep a tiny eval alongside.
