# Provider-version matrix (dated, re-checkable)

**This is the fastest-drifting doc in the skill.** Model IDs, thinking defaults, effort levels,
sampling restrictions, and token limits change with every model generation — treat every cell as a
_versioned, sourced knob_, not a timeless fact. Re-check against the linked primary docs before you
rely on any row, and re-run your eval on a model change.

- **Reviewed:** 2026-08-14. **Re-check by:** 2026-09-14, and sooner on any new flagship model,
  effort/thinking-control change, sampling-restriction change, or model retirement.
- **Trust tiers.** The **Anthropic** rows are verified against Anthropic's first-party docs and the
  `claude-api` skill on the review date. The **OpenAI** and **Google** rows are from those providers'
  docs via web research on the review date and still need a first-party spot-check before you depend
  on them; cells marked `[UNVERIFIED]` were not confirmed in the primary docs read during this pass.
- **Provenance:** every URL below is mirrored in [`../references/SOURCES.md`](../references/SOURCES.md).

## Anthropic (verified 2026-08-14 via first-party docs + `claude-api` skill)

| Model                                 | Default thinking state                                                                                                       | Effort control                                                           | Sampling                                                                                 | Context / max output | Structured output                      | Key deprecations                                                                                  |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- | -------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Claude Opus 4.8 (`claude-opus-4-8`)   | Adaptive is the only on-mode; **if `thinking` is omitted it runs _without_ thinking** — set `{type: "adaptive"}` explicitly. | `output_config.effort`: `low\|medium\|high\|xhigh\|max`; default `high`. | Non-default `temperature`/`top_p`/`top_k` → **HTTP 400**; omit them, steer with prompts. | 1M / 128K            | `output_config.format` (`json_schema`) | `budget_tokens` → 400; prefill → 400. Fast mode is beta (Opus 4.8/4.7 only).                      |
| Claude Sonnet 5 (`claude-sonnet-5`)   | Adaptive thinking **on by default** when `thinking` is omitted.                                                              | `output_config.effort`: `low\|medium\|high\|xhigh\|max`; default `high`. | Non-default `temperature`/`top_p`/`top_k` → **HTTP 400**.                                | 1M / 128K            | `output_config.format` (`json_schema`) | `budget_tokens` → 400; prefill → 400. New tokenizer (~30% more tokens vs Sonnet 4.6).             |
| Claude Fable 5 (`claude-fable-5`)     | Thinking is **always on** — omit `thinking`; an explicit disabled config → 400.                                              | `output_config.effort`: `low\|medium\|high\|xhigh\|max`; default `high`. | Non-default `temperature`/`top_p`/`top_k` → **HTTP 400**.                                | 1M / 128K            | `output_config.format` (`json_schema`) | `budget_tokens` → 400; prefill unsupported (400). Anthropic's most capable widely released model. |
| Claude Haiku 4.5 (`claude-haiku-4-5`) | Older extended-thinking style (`{type: "enabled", budget_tokens: N}`).                                                       | **`effort` not supported** (errors).                                     | Standard sampling knobs apply.                                                           | 200K / 64K           | `output_config.format` (`json_schema`) | —                                                                                                 |

- **Also active** (older, not the current default): `claude-opus-4-7`, `claude-opus-4-6`,
  `claude-sonnet-4-6`. `claude-mythos-5` (Project Glasswing) shares Fable 5 specs and pricing but is
  limited-availability. **There is no "Opus 5"** — the Opus line currently tops out at 4.8; the
  "Claude 5 family" is Fable 5, Sonnet 5, Haiku 4.5, and Mythos 5.
- **Extended thinking:** `thinking: {type: "enabled", budget_tokens: N}` is deprecated on 4.6 and
  **removed (400)** on Fable 5 / Opus 4.8 / Opus 4.7 / Sonnet 5. Replacement: `thinking: {type:
"adaptive"}` + `output_config.effort`.
- **Prefill** (trailing assistant turn) returns **400** on Claude 4.6 and later. Use structured
  outputs instead of a "return only JSON" prefill trick.
- **Structured outputs** use `output_config.format` (`json_schema`); the old top-level
  `output_format` is deprecated API-wide.
- **Prompt caching:** 5-minute TTL (write ~1.25×) and 1-hour TTL (write ~2×); cache read ~0.1×.
  Minimum cacheable prefix: Opus 4.8/4.7/4.6/4.5 and Haiku 4.5 = 4096 tokens; Fable 5 and Sonnet 4.6
  = 2048; Sonnet 4.5 = 1024. Up to 4 cache breakpoints.

## OpenAI (web research 2026-08-14 — spot-check before relying)

| Model                                        | Default reasoning state                                                                              | Effort / verbosity                                                                                | Sampling                                                                                                                  | Context / max output | Structured output                                               | Notes                                                                                           |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| GPT-5.6 Sol (`gpt-5.6-sol`, alias `gpt-5.6`) | `reasoning.effort` defaults to `medium`; `reasoning.mode` standard vs `pro` is separate from effort. | `reasoning.effort`: `none\|low\|medium\|high\|xhigh\|max`; `text.verbosity`: `low\|medium\|high`. | `top_k` not documented as a Responses API control. Non-default `temperature`/`top_p` on reasoning models: `[UNVERIFIED]`. | ~1.05M / 128K        | Responses structured outputs (JSON Schema / SDK parse helpers). | Balanced/efficient siblings: `gpt-5.6-terra`, `gpt-5.6-luna` (same controls, `medium` default). |

## Google Gemini (web research 2026-08-14 — spot-check before relying)

| Model                                 | Default thinking state              | Thinking control                                                                                  | Sampling                                                                                                              | Context / max output | Structured output                                                                    | Notes                                                                                                                   |
| ------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| Gemini 3.7 Flash (`gemini-3.7-flash`) | Thinking on by default at `medium`. | `generation_config.thinking_level`: `low\|medium\|high`; no provider-native verbosity enum found. | Gemini 3.x guidance: **remove** `temperature`/`top_p`/`top_k`; 3.6 Flash already drops them and newer models may 400. | 1M / 64K             | `response_format` with `application/json` + JSON Schema (SDKs support Pydantic/Zod). | `thinking_budget` deprecated for 3.x → use `thinking_level`. Prefilled model turns unsupported on the current 3.x path. |

## How to use this file

1. Read the row for the exact model you are targeting; do not generalize across a family.
2. Prefer the model's **effort / thinking control** over sampling knobs — on current reasoning models
   the sampling knobs are often rejected outright.
3. If a cell is `[UNVERIFIED]` or the review date is stale, open the linked source and confirm before
   you ship. Then update this file's review date and the `model-era` freshness record.
