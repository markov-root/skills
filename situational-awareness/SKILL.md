---
name: situational-awareness
description: >-
  Give an agent full awareness of its own budget — CONTEXT window and subscription
  QUOTA — and what to do about it. Use when you want to know how full your context
  is, how much usage/quota/limit is left (5-hour + weekly), whether to offload, wrap
  up, write a handoff, or stop before a limit binds; or to check another session /
  subagent by id. Provides: `context-check` (context occupancy + forecast + fit),
  `usage-check` (subscription quota — 5h/weekly, burn-rate, ETA, --mark pacing), and
  `cache-check` (cache-hit ratio, trend, and bust detection), and `budget` (fused
  view that picks the BINDING axis). Ordinary checks read local harness state with
  no ambient API keys; explicit refresh, pacing, and feedback options can invoke a
  local CLI or write local metadata. Providers: Claude Code, codex, and OpenCode
  (including its OpenRouter sessions). This skill
  SUBSUMES the old `usage-check` skill.
license: Apache-2.0
metadata:
  version: "0.1.1"
---

# situational-awareness

Answers "how much budget do I have, and what should I do about it?" across context,
subscription quota, and prompt-cache efficiency. The model can't introspect these;
the commands read the on-disk data the harness already writes.

## Commands (installed on PATH, or `./scripts/<cmd>` in-repo)

### `context-check` — context window

```bash
context-check                  # your session: model · window · used · % remaining → action
context-check --json           # machine-readable (parse action / remaining_pct)
context-check <session-id>     # another session / subagent (auto-detect provider)
context-check --all            # fleet: context across ALL recent sessions/subagents
context-check --forecast       # ~turns until wrap_up / handoff (from real growth)
context-check --fits 80000     # would 80k more tokens fit? (or --fits-files a b c)
context-check --handoff        # print a pre-filled handoff doc to complete & save
context-check --quiet; echo $? # gate: 0 continue · 11 wrap_up · 10 handoff · 3 no-data
context-check --policy conservative # override provider workflow policy
context-check --hook            # lifecycle handler for prompt budget + compaction recovery
```

Claude Code and OpenCode keep the conservative handoff ladder because compaction recovery is more
lossy in observed use. Codex defaults to continuous compaction: keep durable task/decision/test docs
current below 60%, never stop solely on a context percentage, and after compaction re-read applicable
instructions plus active task/checkpoint docs. Override with `--policy conservative` when automatic
compaction is disabled or the task needs stricter preservation.

### `usage-check` — subscription quota (ported from the old skill; a Pareto upgrade)

```bash
usage-check                    # 5h + weekly: % left, reset clock, burn-rate, ETA→90%
usage-check --json             # action ∈ continue|wind_down|wait_for_reset; binding; forecast
usage-check --provider codex   # force source attribution when auto-detection is unavailable
usage-check --quiet; echo $?   # gate: 0 continue · 11 wind_down (+--fail-on-warn) · 10 wait · 3 no-data
usage-check --mark LABEL       # per-iteration calibration → learns %/cycle, iters_left
usage-check --wait             # if wait_for_reset, poll until the window resets
```

Thresholds `--warn-5h/--max-5h/--warn-7d/--max-7d` (default 80/90), `--window`,
`--max-age`, `--fail-on-warn`, `--forecast`, `--refresh`. Claude quota comes from its statusline
capture; Codex quota comes from the active transcript and follows live reset epochs. A provider may
expose only one window; unavailable windows stay `n/a`. OpenCode quota remains unavailable unless
its upstream exposes a normalized subscription window.

### `budget` — fused view (context + quota, one binding action)

```bash
budget                         # [ctx 67% · 5h 58% wk 11% · cache 92%] → quota binding
budget --json                  # {binding, action, context{…}, quota{…}, cache{…}}
```

Neither number alone tells you what to do: compacting fixes context but not quota;
waiting for reset fixes quota but not context. `budget` picks whichever binds and adds
cache as an advisory efficiency axis.

### `cache-check` — prompt-cache efficiency

```bash
cache-check                    # recent/current hit ratio, trend, read/write/uncached tokens
cache-check --json             # structured status + confidence-labelled cache-bust events
```

Cache health changes cost and latency, not permission to work, so it never overrides
context/quota exit actions.

## Cache-efficient agent behavior

These rules are safe across the supported providers; provider-specific mechanics and dated sources
live in `references/0001-cache-optimization-findings.md`.

- Keep the stable prefix stable: system/developer instructions, tool schemas, model, and effort.
- Append changing task state and user-specific content after stable context instead of rewriting it.
- Keep models, effort, and prefix-loaded tools stable mid-task; change them when the benefit
  justifies a cache rebuild.
- Compact at a task boundary and preserve the parent prefix when the harness supports it.
- Run `cache-check --json` after an unexpected latency/cost increase or configuration change. Treat a
  measured drop as real, but trust a proposed cause only in proportion to its `confidence`.

## Automatic awareness

Claude Code can use `context-check --hook` on `UserPromptSubmit` to inject a
`[situational-awareness] …` line only after its window starts filling. Claude Code and Codex can use the
same handler on `SessionStart(source=compact)` to continue the current task, re-read durable
instructions/task state, and preserve completed work. This recovery path returns continuation
context without a handoff or blocking decision. Read `references/continuity-hooks.md` when enabling
or verifying hooks.

Writing a conservative-policy handoff? Run `context-check --handoff`; it stamps live context %,
changed files, and open tasks with the standard baked in.

## Notes

- Ordinary checks read local harness state and require no ambient API keys. `usage-check --refresh`
  invokes the installed Claude CLI; `--mark` writes local pacing data; configured feedback adapters
  can write privacy-screened lifecycle metadata.
- Context number is one turn stale and resets on compaction; statusline-based window
  detection applies only to your current session.
- Quota is provider-attributed. Use a quota reading only when its provider matches the active
  harness.
- JSON renders home-directory paths with `~` and hides parent directories for other absolute paths.
- Review `--handoff` output before sharing it: it intentionally summarizes local Git status,
  recent commit subjects, and open work.
