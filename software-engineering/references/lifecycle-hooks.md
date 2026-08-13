# Lifecycle hooks — warn/record-only reminders (pilot)

`scripts/se-lifecycle-hook.sh` is the **non-blocking** sibling of the consult gate
([`enforcement-hooks.md`](enforcement-hooks.md)). The gate _blocks_ an un-consulted code edit; this
hook only _notifies_ and _records_ the `engineering start` / `finish` lifecycle. It is a **pilot**
under a warn/record-only policy (task 0055): a hook here may **not** block, edit project files, grant
approval, or turn an unavailable check into success. Blocking behavior is a separate maintainer call.

## Contract

- Reads the harness hook JSON on stdin (`hook_event_name`, `tool_name`, `tool_input.file_path`,
  `session_id`, `cwd`). Two advisory observations:
  1. **edit event + no active run** in the project's `.engineering/runs` → "consider `engineering start`".
  2. **session-end event + an unfinished run** (a run dir with `baseline.json` but no `final.json`)
     → "consider `engineering finish RUN_ID`".
- **Never blocks:** always exits 0; neither dialect emits a `deny` decision. Any malformed stdin,
  missing field, unsupported event, or absent run store → silent exit 0.
- **Edit reminders are code/build only** (mirrors the gate's extension set); prose/data edits are
  never reminded.
- **Reentrancy-safe:** performs only bounded filesystem checks and **never invokes the CLI**, so it
  cannot trigger the tools it observes. Reminders are throttled to **once per (session, kind)**.
- **Records** each classified observation to `${XDG_STATE_HOME:-~/.local/state}/se-lifecycle/<session>.log`
  as `session <tab> kind <tab> run <tab> project <tab> reminded?`. Privacy: only paths, run ids, and
  the session id — never file content or diffs.
- **Opt-out:** `SE_LIFECYCLE_DISABLE=1` records but surfaces nothing; `SE_LIFECYCLE_SILENT=1` is a
  full bypass (no record, no surface). Uninstall = remove the hook entry; the hook then never runs,
  but the local logs/markers it already wrote persist under `${XDG_STATE_HOME:-~/.local/state}/se-lifecycle`
  and `${XDG_CACHE_HOME:-~/.cache}/se-lifecycle` until you delete them (`rm -rf` either dir).
- **Hardening:** the `session_id` is sanitized to `[A-Za-z0-9._-]` before it is used as a marker/log
  filename (no path traversal), and the once-per-(session,kind) marker is claimed atomically
  (`noclobber`), so an unwritable cache degrades to no-reminder rather than per-event spam.
- **Timeouts/cancellation:** the hook is a fast local file scan; give it a small timeout (10 s). A
  timeout or non-zero exit is treated by every harness as "no reminder", never as a block.

## Claude Code (settings.json)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.agents/skills/software-engineering/scripts/se-lifecycle-hook.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.agents/skills/software-engineering/scripts/se-lifecycle-hook.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

The default dialect emits `hookSpecificOutput.additionalContext` (advisory context, not a decision).
Merge with existing hooks; do not replace unrelated entries.

## Codex (config.toml) — verify live

```toml
[[hooks.PostToolUse]]
matcher = "^(Edit|Write|apply_patch)$"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "$HOME/.agents/skills/software-engineering/scripts/se-lifecycle-hook.sh codex"
timeout = 10
statusMessage = "engineering lifecycle reminder"
```

The `codex` argument emits a `Notification` object (no `permissionDecision`). Wire the harness's
session-end event to the same command where available.

## OpenCode (plugin) — verify live

OpenCode uses a plugin; keep it **non-throwing** (throwing would block, which this pilot forbids).
Place at `~/.config/opencode/plugins/se-lifecycle.ts`:

```ts
import { Plugin } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
const HOOK = `${process.env.HOME}/.agents/skills/software-engineering/scripts/se-lifecycle-hook.sh`;
export default Plugin.define({
  id: "local.se-lifecycle",
  setup: async (ctx) => {
    await ctx.tool.hook("execute.after", (e) => {
      const payload = JSON.stringify({
        hook_event_name: "PostToolUse",
        tool_name: e.tool,
        tool_input: {
          file_path: String(e.input?.filePath ?? e.input?.path ?? ""),
        },
        session_id: e.sessionID,
        cwd: process.cwd(),
      });
      // Fire-and-forget; a hook failure must never interrupt the session.
      const child = execFile("bash", [HOOK], () => {});
      child.stdin?.end(payload);
    });
  },
});
```

## Pilot thresholds and disposition

Pre-registered before trusting the reminders, measured against the direct-CLI baseline:

- **Recall:** ≥ 80% of sessions with a non-trivial change but no `start` receive exactly one reminder.
- **Noise:** ≤ 1 reminder per session per kind (guaranteed by throttling), and 0 reminders on
  trivial/prose-only sessions.
- **Latency:** hook wall-time < 200 ms at p95 on a warm checkout.
- **Safety:** 0 blocked edits and 0 project-file writes attributable to the hook across the pilot.

Record observed values per harness in a task/audit record, then take a disposition — **promote**
(keep as recommended opt-in), **revise** (adjust events/messages), **retain** (leave available but
not recommended), or **remove** — without weakening the canonical direct CLI. Blocking semantics
remain out of scope until a separate reviewed decision.

## Verify

```bash
H="$HOME/.agents/skills/software-engineering/scripts/se-lifecycle-hook.sh"
T=$(mktemp -d)
# edit with no run → one reminder (exit 0)
printf '{"hook_event_name":"PostToolUse","tool_name":"Edit","tool_input":{"file_path":"%s/a.py"},"session_id":"t","cwd":"%s"}' "$T" "$T" | "$H"; echo "exit=$? (expect 0 + reminder)"
# prose file → silent
printf '{"hook_event_name":"PostToolUse","tool_name":"Write","tool_input":{"file_path":"%s/README.md"},"session_id":"t","cwd":"%s"}' "$T" "$T" | "$H"; echo "exit=$? (expect 0, silent)"
```
