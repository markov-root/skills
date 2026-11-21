#!/usr/bin/env bash
# se-consult-gate — make consulting the software-engineering skill NON-OPTIONAL before editing
# code/build files. Converts "always-on by policy" (AGENTS.md prose) into "always-on by mechanism"
# (a pre-edit gate), mirroring how situational-awareness gates on budget.
#
# Wired as a PreToolUse hook on Write|Edit|MultiEdit (Claude Code). It reads the harness's hook JSON
# on stdin and BLOCKS (exit 2) a code/build-file edit ONLY when the software-engineering skill has
# not been consulted this session. Everything else — a prose/doc/data file, an already-consulted
# session, or ANY error (unparseable stdin, absent/unreadable transcript, missing python3) —
# ALLOWS the edit. Fail-OPEN by construction: the sole exit-2 path is the positive "code file AND
# not consulted" decision, so a bug cannot brick editing (Claude Code treats any non-2 exit /
# timeout as allow).
#
# "Consulted" (task 0118) = this session's transcript — or, for a subagent, the parent session
# transcript / for a parent, any of its subagent transcripts — shows a STRUCTURED tool_use entry:
# the Skill tool invoked with `software-engineering`, or a Bash tool_use running the engineering
# CLI (bundled engineering.py or the `engineering` launcher). Prose mentions, tool_result text and
# hook block messages never count: the 0.12 gate satisfied itself with its own block REASON, so
# the first block un-blocked every later edit. File classes AND consultation detection live in
# se_gate_shared.py — the single source shared by every dialect (consult sh, lifecycle sh, and the
# OpenCode plugin template rendered by harness/hooks.py). Detection runs once, then is cached per
# session_id under ${XDG_CACHE_HOME:-~/.cache}/se-consult-gate/ (ids sanitized) so subsequent edits
# are a cheap check.
#
# Env knobs (optional): SE_GATE_DISABLE=1 disables the block (audit only); SE_GATE_EXTS adds
# space-separated extra globs to treat as code (e.g. "*.tf *.proto", matched case-insensitively).
set -uo pipefail
allow() { exit 0; }   # permit / fail-open

[ "${SE_GATE_DISABLE:-0}" = 1 ] && allow

input="$(cat 2>/dev/null)" || allow
[ -n "$input" ] || allow

# Every decision — parse, code-file classification, transcript consultation scan, per-session
# marker — comes from the shared module. Any failure (missing module, missing python3, crash)
# allows: fail-open by construction.
helper="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/se_gate_shared.py"
verdict="$(printf '%s' "$input" | python3 "$helper" gate 2>/dev/null)" || allow
[ "$verdict" = "block" ] || allow

# Code/build file AND not consulted → BLOCK.
REASON="[software-engineering gate] Blocked: this edits a code/build file but the software-engineering skill has NOT been consulted in this session. It is NON-OPTIONAL for non-trivial code work (project policy) — it establishes local authority, a pre-edit baseline, and the verification you must meet before claiming completion. Do this now then retry the edit: invoke the software-engineering skill (Skill tool) and run its first step, 'engineering inspect' (or the bundled script: uv run --script <skill-root>/scripts/engineering.py inspect). Once consulted, every further edit this session proceeds without interruption (one-time per-session gate)."

# Two block dialects. Default: Claude Code exit 2 + stderr (tested). --json: emit the
# hookSpecificOutput deny object on stdout (Codex PreToolUse dialect) with exit 0.
if [ "${1:-}" = "--json" ]; then
  printf '%s' "$REASON" | python3 -c '
import sys, json
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
      "permissionDecision": "deny", "permissionDecisionReason": sys.stdin.read()}}))'
  exit 0
fi
printf '%s\n' "$REASON" >&2
exit 2