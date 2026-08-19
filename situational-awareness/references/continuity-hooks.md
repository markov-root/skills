# Continuity hooks

Use the same repository-owned handler for both supported lifecycle jobs:

- `UserPromptSubmit`: Claude Code receives a context-budget directive only after its window starts
  filling.
- `SessionStart` with `source = compact`: Claude Code and Codex receive a short recovery contract
  before the next model request. The contract continues the current task, re-reads durable
  instructions and task/checkpoint state, verifies disk state, and never forces a handoff.

The handler is fail-open, reads hook JSON on stdin, performs no writes, and always exits `0`.

## Claude Code

Add both matcher groups to the active `hooks` object in `settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "context-check --hook"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "context-check --hook"
          }
        ]
      }
    ]
  }
}
```

Merge these groups with existing hooks; do not replace unrelated settings. Claude Code runs
`SessionStart` after manual or automatic compaction and adds the handler's `additionalContext`
before the next request.

## Codex

Add this group to the active `hooks` table in `config.toml`:

```toml
[[hooks.SessionStart]]
matcher = "^compact$"

[[hooks.SessionStart.hooks]]
type = "command"
command = "context-check --hook"
additionalContextLimit = 600
statusMessage = "Recovering durable task context"
```

Codex runs this hook before the immediate continuation, including automatic compaction in the middle
of a turn. Open `/hooks` once after adding or changing the definition to review and trust it.

## Verification

The handler can be exercised without compacting a real session:

```bash
printf '%s\n' \
  '{"hook_event_name":"SessionStart","source":"compact","session_id":"test","cwd":"."}' |
  context-check --hook
```

The JSON response must name `SessionStart`, contain `additionalContext`, and contain no stop or block
decision.
