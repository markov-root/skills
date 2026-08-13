# Enforcement hooks — make consulting this skill non-optional

Policy in an `AGENTS.md` ("invoke `software-engineering` for non-trivial code work") is advisory:
a model can ignore it, and in practice Claude Code sessions under-invoke it while Codex complies.
`scripts/se-consult-gate.sh` turns the policy into a **mechanism** — a pre-edit gate that blocks a
code/build-file edit until the skill has been consulted this session. Same idea as the
`situational-awareness` budget gate.

## Contract

- The gate is a **PreToolUse** command hook on the edit tools (`Write|Edit|MultiEdit`, plus
  `apply_patch` where the harness uses it). It reads the harness hook JSON on stdin
  (`tool_input.file_path`, `session_id`, `transcript_path`).
- It **allows** everything except one case; it **blocks** only a _code/build_ file edit when the
  skill has **not** been consulted this session. Prose docs (`.md/.txt/.rst`) and data are not gated.
  Extend the gated set per-invocation with `SE_GATE_EXTS="*.tf *.proto"`; disable entirely with
  `SE_GATE_DISABLE=1` (audit only).
- **Consulted** = the session transcript shows the `software-engineering` Skill was invoked or its
  `engineering.py` CLI ran. Detected once, then cached at
  `${XDG_CACHE_HOME:-~/.cache}/se-consult-gate/<session_id>.ok` so later edits are a file-exists check.
- **Fail-open by construction:** the only non-allow path is the positive "code file AND not
  consulted" decision. Any error, missing field, unparseable stdin, or absent transcript → allow. A
  bug cannot brick editing.
- Block dialects: default = **exit 2 + stderr** (Claude Code). `--json` = emit the
  `hookSpecificOutput.permissionDecision:"deny"` object on stdout with exit 0 (Codex).

The gate is a guardrail, not a boundary: it forces the _first_ consult, not the quality of the work.

## Claude Code — wired (settings.json)

Add to the `PreToolUse` array (points at the universal-root install, which always resolves):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.agents/skills/software-engineering/scripts/se-consult-gate.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Merge with existing hooks; do not replace unrelated entries. Optional companion — a `SessionStart`
reminder so the requirement is surfaced proactively (not only at the block):

```json
{
  "matcher": "startup|resume|compact",
  "hooks": [
    {
      "type": "command",
      "command": "printf '%s' '{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"Reminder: the software-engineering skill is NON-OPTIONAL before code edits (enforced by a pre-edit gate). Consult it once at the start of any non-trivial code task.\"}}'"
    }
  ]
}
```

## Codex — recipe (verify live)

Codex exposes `PreToolUse` with `Edit|Write|apply_patch` and denies via the same
`hookSpecificOutput` object. Use the `--json` dialect. In `~/.codex/config.toml` (or, for
policy-hard enforcement, `requirements.toml` with `[features] hooks = true` +
`allow_managed_hooks_only = true`):

```toml
[[hooks.PreToolUse]]
matcher = "^(Edit|Write|apply_patch)$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "$HOME/.agents/skills/software-engineering/scripts/se-consult-gate.sh --json"
timeout = 10
statusMessage = "software-engineering gate"
```

Codex already tends to consult the skill; this makes it enforced. Run `/hooks` once to trust it, and
verify a real block before relying on it.

## OpenCode — recipe (verify live)

OpenCode V2 blocks by throwing from a `tool.execute.before` plugin. It sees the `skill` tool
invocation live, so it tracks consultation in-memory (no transcript grep). Place at
`~/.config/opencode/plugins/se-consult-gate.ts`:

```ts
import { Plugin } from "@opencode-ai/plugin";
export default Plugin.define({
  id: "local.se-consult-gate",
  setup: async (ctx) => {
    const consulted = new Set<string>();
    await ctx.tool.hook("execute.before", (e) => {
      if (
        e.tool === "skill" &&
        String(e.input?.name ?? "").includes("software-engineering")
      ) {
        consulted.add(e.sessionID);
        return;
      }
      const CODE =
        /\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|c|h|cc|cpp|hpp|java|kt|rb|php|sh|sql)$/;
      const path = String(e.input?.filePath ?? e.input?.path ?? "");
      if (
        ["edit", "write", "apply_patch"].includes(e.tool) &&
        CODE.test(path) &&
        !consulted.has(e.sessionID)
      ) {
        throw new Error(
          "Consult the software-engineering skill before editing code files (non-optional; run its engineering inspect).",
        );
      }
    });
  },
});
```

## Verify

```bash
G="$HOME/.agents/skills/software-engineering/scripts/se-consult-gate.sh"
# code file, empty transcript → BLOCK (exit 2)
printf '{"tool_name":"Edit","tool_input":{"file_path":"/x/a.py"},"session_id":"t","transcript_path":"/dev/null"}' | "$G"; echo "exit=$?  (expect 2)"
# prose doc → allow (exit 0)
printf '{"tool_name":"Write","tool_input":{"file_path":"/x/README.md"},"session_id":"t","transcript_path":"/dev/null"}' | "$G"; echo "exit=$?  (expect 0)"
```
