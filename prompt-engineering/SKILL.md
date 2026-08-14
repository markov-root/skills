---
name: prompt-engineering
description: >-
  Write and improve prompts, system prompts, personas, agent instructions,
  CLAUDE.md/AGENTS.md files, tool descriptions, few-shot templates, and
  LLM-as-judge rubrics using sourced provider guidance and current research.
  Use when authoring or substantially revising an LLM-facing instruction,
  diagnosing an underperforming prompt, answering "how should I prompt X?", or
  safely converging AGENTS.md and CLAUDE.md on one canonical instruction file.
  Includes structure, output contracts, reasoning-era model guidance,
  anti-patterns, evaluation, vision/OCR grounding, and a prompt linter. Do not
  use for non-prompt prose, provider API mechanics, or image-generation
  prompting. Use
  `image-generation` for image briefs, visual references, edits, and assets.
license: Apache-2.0
compatibility: Requires Python 3.10+; agents-link additionally requires a POSIX shell.
metadata:
  author: markov-root
  version: "0.1.2"
---

# prompt-engineering — write the prompt like an engineer, not a wordsmith

A prompt is an **interface to a model**, tuned against evidence, not an incantation. This skill gives
you a repeatable method plus a sourced knowledge library. The whole library lives in `knowledge/`;
load only the file you need (progressive disclosure). External provenance is bundled in
`references/SOURCES.md`.

## The method (run this every time you author a non-trivial prompt)

1. **State the job in one sentence.** Task + audience + what "good" looks like. If you can't, the
   prompt can't either.
2. **Pick the altitude.** Instructions over constraints; positive over negative ("do X", not "don't
   do Y"). Give the _reason_ behind a rule — the model generalizes from it.
3. **Structure before wording.** Order the components (instruction → context → input → output cue),
   delimit each block (XML tags / clear headers), put long data on top and the ask at the bottom. See
   `knowledge/structure.md`.
4. **Choose techniques deliberately, don't stack them.** Zero-shot first; add few-shot only where it
   pays; reason step-by-step only when the task genuinely needs it. Catalog: `knowledge/techniques.md`.
5. **Specify the output contract.** Exact shape, fields, allowed values, and what to do when unsure
   ("say 'I don't have enough information'"). Structured output > "return JSON-ish".
6. **Tune for the model era.** Reasoning/"thinking" models invert several old rules — when NOT to add
   CoT, effort/thinking budgets, literal instruction-following, prefill deprecation. See
   `knowledge/model-era.md`. For agents/tools/context, see `knowledge/context-engineering.md`.
7. **Delete the myths and anti-patterns.** No tipping/threats, no politeness-for-accuracy, no
   self-critique-as-verifier, no negative-only rules, no overloaded mega-prompt. See
   `knowledge/anti-patterns.md`.
8. **Test it.** Run the pre-flight checklist (`knowledge/checklist.md`); for anything that matters,
   build a tiny eval set — prompting is prompt + eval + regression, because model upgrades shift
   sensitivity.

**The golden rule (Anthropic):** _Show your prompt to a colleague with minimal context and ask them to
follow it. If they'd be confused, the model will be too._

## Optional: lint a draft

A dependency-free heuristic linter flags common anti-patterns (negative-only rules, vague verbs,
missing output contract, myth phrases, overload) in a draft prompt:

```bash
python3 scripts/prompt-lint.py path/to/draft.md
# or:  pbpaste | python3 scripts/prompt-lint.py -
# changed lines only:
git diff -- AGENTS.md | python3 scripts/prompt-lint.py - --diff
# explicit fragment or inclusive line range:
python3 scripts/prompt-lint.py AGENTS.md --lines 40:70
```

Resolve `scripts/prompt-lint.py` relative to this skill directory. Vercel `skills` installs the
folder; it does not register PATH executables.

Whole-document mode includes completeness checks such as an output contract.
`--diff`, `--fragment`, and `--lines` lint only local smells and suppress those
whole-document checks. The linter is advisory heuristics, not a grader—it
catches smells, it does not certify quality.

## Route the task, then load only what it needs

Classify the request once. Read the required references; add optional ones only when the task needs
that concern. A capability delegation ends this skill's routing—do not duplicate modality guidance.

| Route                      | Task class                                                                           | Required                                                                      | Optional / delegation                                           |
| -------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `agent_system`             | System prompts, AGENTS.md/CLAUDE.md, personas, single-agent instructions             | `knowledge/context-engineering.md`, `knowledge/structure.md`                  | `knowledge/model-era.md`, `knowledge/checklist.md`              |
| `agentic_tools`            | Tool descriptions/policy, delegation, handoffs, subagents, multi-agent orchestration | `knowledge/agentic-tools.md`, `knowledge/agentic-contracts.md`                | context, structured-output, and judge modules as needed         |
| `llm_judge`                | LLM judges, graders, scoring rubrics                                                 | `knowledge/llm-as-judge.md`, `knowledge/checklist.md`                         | technique, anti-pattern, and model-era modules as needed        |
| `prompt_evaluation`        | Prompt eval sets, A/B tests, optimizers, release gates, model-upgrade regression     | `knowledge/prompt-evaluation.md`, `knowledge/prompt-eval-templates.md`        | judge, checklist, and model-era modules as needed               |
| `vision_understanding`     | Image/screenshot analysis, OCR, visual tables, document QA, bounding boxes           | `knowledge/vision-understanding.md`, `knowledge/vision-templates.md`          | structured-output, RAG, and checklist modules as needed         |
| `structured_output`        | Extraction, classification, schemas, enums                                           | `knowledge/structured-output.md`, `knowledge/structured-output-templates.md`  | shared structure/model/technique/checklist modules as needed    |
| `rag`                      | RAG, retrieval/query construction, grounded answers, citations                       | `knowledge/rag-retrieval.md`, `knowledge/rag-templates.md`                    | context-engineering, structure, and checklist modules as needed |
| `translation_localization` | Translation, localization, transcreation, terminology and multilingual QA            | `knowledge/translation-localization.md`, `knowledge/translation-templates.md` | structured-output, judge, and checklist modules as needed       |
| `technique_selection`      | Few-shot/CoT/tool/reasoning-technique choice                                         | `knowledge/techniques.md`, `knowledge/model-era.md`                           | `knowledge/anti-patterns.md`                                    |
| `general_prompt`           | Author, diagnose, or substantially revise another LLM-facing prompt                  | `knowledge/structure.md`, `knowledge/checklist.md`                            | technique/model/anti-pattern modules as needed                  |
| `delegate_image`           | Generate or edit an image                                                            | —                                                                             | Use `image-generation`; stop here                               |
| `delegate_animate`         | Turn a still into a finished loop                                                    | —                                                                             | Use `animate`; stop here                                        |
| `delegate_video`           | Raw/custom text-to-video or image-to-video                                           | —                                                                             | Use `openrouter-video`; stop here                               |

The machine-readable route contract is `knowledge/routes.json`; the focused-module convention is in
`knowledge/domains.md`.

## Maintain one instruction source

Use the bundled `agents-link [DIR]` command when a repository should keep `AGENTS.md` as its real
instruction file and `CLAUDE.md` as a relative symlink to it. It migrates a lone real `CLAUDE.md`,
repairs a missing or incorrect symlink, and refuses to overwrite two real files. Reconcile divergent
real files manually before retrying.

## Provenance & stability

Every external claim traces to `references/SOURCES.md` (provider guidance + ~40 2025-2026
papers/docs, with a verification pass on the citations). Treat the _method and technique catalog_ as the stable
contract; treat _model-era knobs_ (effort levels, prefill status, specific model quirks) as versioned
and re-checkable—they drift with each model generation. When in doubt, re-check the linked primary
sources and re-run your eval; do not trust a remembered knob.

## Related boundary

Use `image-generation` for prompts whose output is an image. Image generation
depends on reference roles, composition, provider image controls, iterative
editing, inspection, and post-processing; duplicating that material here would
make both skills drift. Prompts whose input is an image and output is grounded
text or structured evidence use the `vision_understanding` route above.
