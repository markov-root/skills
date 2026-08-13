#!/usr/bin/env bash
# se-consult-gate — make consulting the software-engineering skill NON-OPTIONAL before editing
# code/build files. Converts "always-on by policy" (AGENTS.md prose) into "always-on by mechanism"
# (a pre-edit gate), mirroring how situational-awareness gates on budget.
#
# Wired as a PreToolUse hook on Write|Edit|MultiEdit (Claude Code). It reads the harness's hook JSON
# on stdin and BLOCKS (exit 2) a code/build-file edit ONLY when the software-engineering skill has
# not been consulted this session. Everything else — a prose/doc/data file, an already-consulted
# session, or ANY error — ALLOWS the edit. Fail-OPEN by construction: the sole exit-2 path is the
# positive "code file AND not consulted" decision, so a bug cannot brick editing (Claude Code treats
# any non-2 exit / timeout as allow).
#
# "Consulted" = this session's transcript shows the software-engineering Skill was invoked OR its
# engineering.py CLI was run. Detected once from transcript_path, then cached per session_id so
# subsequent edits are a cheap file-exists check. No dependency on (undocumented) Skill-tool hooks.
#
# Env knobs (optional): SE_GATE_DISABLE=1 disables the block (audit only); SE_GATE_EXTS adds
# space-separated extra globs to treat as code (e.g. "*.tf *.proto").
set -uo pipefail
allow() { exit 0; }   # permit / fail-open

[ "${SE_GATE_DISABLE:-0}" = 1 ] && allow

input="$(cat 2>/dev/null)" || allow
[ -n "$input" ] || allow

# Extract exactly the fields we need, one per line (path-with-spaces safe). Any failure → allow.
mapfile -t F < <(printf '%s' "$input" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get("tool_input") or {}
print(d.get("tool_name", ""))
print(ti.get("file_path") or ti.get("path") or "")
print(d.get("session_id", ""))
print(d.get("transcript_path", ""))
' 2>/dev/null) || allow

FILE="${F[1]:-}"; SID="${F[2]:-}"; TP="${F[3]:-}"
[ -n "$FILE" ] || allow    # no file path → nothing to gate

# Gate code/build files only; prose docs (.md/.txt/.rst) and data are intentionally NOT gated.
is_code=1
case "$FILE" in
  *.py|*.js|*.mjs|*.cjs|*.ts|*.tsx|*.jsx|*.vue|*.svelte|*.go|*.rs|*.c|*.h|*.cc|*.cpp|*.hpp|*.cxx|\
  *.java|*.kt|*.scala|*.rb|*.php|*.swift|*.m|*.mm|*.lua|*.pl|*.pm|*.r|*.jl|*.sh|*.bash|*.zsh|*.fish|\
  *.sql|*.gradle|*.cs|*.fs|*.ex|*.exs|*.erl|*.clj|*.dart|*.hs) is_code=0 ;;
  */Dockerfile|Dockerfile|*/Makefile|Makefile|*.mk|*/pyproject.toml|*/Cargo.toml|*/go.mod|\
  */package.json|*/CMakeLists.txt) is_code=0 ;;
esac
if [ "$is_code" != 0 ]; then
  # shellcheck disable=SC2254  # $g is intentionally a glob pattern (e.g. *.tf)
  for g in ${SE_GATE_EXTS:-}; do case "$FILE" in $g) is_code=0; break ;; esac; done
fi
[ "$is_code" = 0 ] || allow

# Fast path: already consulted this session.
cache="${XDG_CACHE_HOME:-$HOME/.cache}/se-consult-gate"
marker="$cache/${SID:-nosid}.ok"
[ -f "$marker" ] && allow

# Detect consultation from the session transcript (Skill invocation OR engineering.py CLI run).
if [ -n "$TP" ] && [ -f "$TP" ]; then
  if { grep '"name":"Skill"' "$TP" 2>/dev/null | grep -q 'software-engineering'; } \
     || grep -q 'engineering\.py' "$TP" 2>/dev/null; then
    mkdir -p "$cache" 2>/dev/null && : > "$marker" 2>/dev/null
    allow
  fi
fi

# Code/build file AND not consulted → BLOCK.
REASON="[software-engineering gate] Blocked: this edits a code/build file but the software-engineering skill has NOT been consulted in this session. It is NON-OPTIONAL for non-trivial code work (project policy) — it establishes local authority, a pre-edit baseline, and the verification you must meet before claiming completion. Do this now then retry the edit: invoke the software-engineering skill and run its first step 'uv run --script ~/.agents/skills/software-engineering/scripts/engineering.py inspect'. Once consulted, every further edit this session proceeds without interruption (one-time per-session gate)."

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
