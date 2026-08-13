#!/usr/bin/env bash
# se-lifecycle-hook — WARN/RECORD-ONLY reminders for the engineering start/finish lifecycle.
#
# The non-blocking sibling of se-consult-gate.sh. Where the gate BLOCKS an un-consulted code edit,
# this hook only NOTIFIES and RECORDS: it never blocks, never edits project files, never grants
# approval, and never turns an unavailable check into success (task 0055, warn/record-only policy).
#
# Two observations, both advisory:
#   1. edit event  + no active run in the project's .engineering/runs → "consider `engineering start`"
#   2. session end + an unfinished run (baseline written, no final record) → "run RUN_ID not finished"
#
# It reads the harness hook JSON on stdin (hook_event_name/tool_name/file_path/session_id/cwd) and
# always exits 0. Reminders are throttled to once per (session, kind) so a busy session is not spammy,
# and each observation is appended to a local session log. Reentrancy-safe: the hook performs only
# bounded filesystem checks and never invokes the CLI, so it cannot trigger the tools it observes.
#
# Env knobs: SE_LIFECYCLE_DISABLE=1 silences reminders (recording still happens);
#            SE_LIFECYCLE_SILENT=1 disables both reminders and recording (full bypass).
set -uo pipefail

emit_none() { exit 0; }   # never block; a quiet exit is always valid

[ "${SE_LIFECYCLE_SILENT:-0}" = 1 ] && emit_none

DIALECT="${1:-claude}"     # claude | codex ; anything else behaves like claude

input="$(cat 2>/dev/null)" || emit_none
[ -n "$input" ] || emit_none

# Extract only the fields we need, one per line (path/space safe). Any failure → silent.
mapfile -t F < <(printf '%s' "$input" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get("tool_input") or {}
print(d.get("hook_event_name") or d.get("hookEventName") or "")
print(d.get("tool_name", ""))
print(ti.get("file_path") or ti.get("path") or "")
print(d.get("session_id", ""))
print(d.get("cwd") or ti.get("cwd") or "")
' 2>/dev/null) || emit_none

EVENT="${F[0]:-}"; TOOL="${F[1]:-}"; FILE="${F[2]:-}"; SID="${F[3]:-}"; CWD="${F[4]:-}"
# The session id becomes a filename for the throttle marker and log, so it must never carry path
# separators or traversal — a crafted id like "../../x" would otherwise escape the state/cache dirs.
SID="$(printf '%s' "$SID" | tr -c 'A-Za-z0-9._-' '_')"
case "$SID" in ''|.|..) SID="nosid" ;; esac
root="${CWD:-$PWD}"

# Locate the run store without invoking the CLI: walk up from the project dir to a .engineering dir.
runs=""
dir="$root"
for _ in 1 2 3 4 5 6 7 8; do
  [ -n "$dir" ] || break
  if [ -d "$dir/.engineering/runs" ]; then runs="$dir/.engineering/runs"; break; fi
  parent="$(dirname "$dir")"; [ "$parent" = "$dir" ] && break; dir="$parent"
done

# An "active" run = a run directory with a baseline but no final record. Bounded scan.
active_run=""
if [ -n "$runs" ]; then
  for d in "$runs"/*/; do
    [ -d "$d" ] || continue
    if [ -f "${d}baseline.json" ] && [ ! -f "${d}final.json" ]; then
      active_run="$(basename "$d")"; break
    fi
  done
fi

# Classify the event into edit / session-end / other, across harness naming.
kind=""
case "$EVENT" in
  PostToolUse|post_tool_use|PreToolUse|pre_tool_use) [ -n "$TOOL$FILE" ] && kind="edit" ;;
  Stop|SessionEnd|session_end|stop) kind="end" ;;
esac
# Fall back to tool identity when the harness omits the event name.
if [ -z "$kind" ] && [ -n "$FILE" ]; then
  case "$TOOL" in Edit|Write|MultiEdit|apply_patch|edit|write) kind="edit" ;; esac
fi
[ -n "$kind" ] || emit_none

# Only remind about edits for code/build files (mirror the consult-gate set); never for prose/data.
if [ "$kind" = "edit" ]; then
  case "$FILE" in
    *.py|*.js|*.mjs|*.cjs|*.ts|*.tsx|*.jsx|*.go|*.rs|*.c|*.h|*.cc|*.cpp|*.hpp|*.java|*.kt|*.rb|\
    *.php|*.swift|*.lua|*.sh|*.bash|*.sql|*.cs|*.ex|*.exs|*.dart|*.hs) : ;;
    */Dockerfile|Dockerfile|*/Makefile|Makefile|*.mk|*/pyproject.toml|*/Cargo.toml|*/go.mod|\
    */package.json|*/CMakeLists.txt) : ;;
    *) emit_none ;;
  esac
fi

# Decide the advisory message. Silent when there is nothing to remind about.
message=""
if [ "$kind" = "edit" ] && [ -z "$active_run" ]; then
  message="[software-engineering] No active engineering run for this project. For non-trivial work, consider recording one: 'engineering start --intent \"...\" --paths ...'. This is a reminder only — the direct CLI remains canonical and nothing was blocked."
elif [ "$kind" = "end" ] && [ -n "$active_run" ]; then
  message="[software-engineering] Engineering run '$active_run' has a baseline but no sealed final record. Consider 'engineering finish $active_run' to record acceptance evidence. Reminder only; nothing was blocked."
fi

# Decide whether a reminder will actually SURFACE: it must exist, reminders must be enabled, and it
# must not already have fired once this (session, kind). Throttling prevents noise and apparent
# recursion. Claim the throttle marker here so the recorded log reflects exactly what the user saw.
surfaced=""
if [ -n "$message" ] && [ "${SE_LIFECYCLE_DISABLE:-0}" != 1 ]; then
  throttle="${XDG_CACHE_HOME:-$HOME/.cache}/se-lifecycle"
  seen="$throttle/${SID}.${kind}"
  # Atomically CLAIM the throttle marker (noclobber = only one winner, no check-then-create race).
  # surface iff the claim succeeds: if the cache is unwritable the claim fails and we stay silent
  # rather than surfacing on every event, so a broken cache degrades to no-reminder, never to spam.
  if mkdir -p "$throttle" 2>/dev/null && (set -o noclobber; : > "$seen") 2>/dev/null; then
    surfaced=1
  fi
fi

# RECORD every classified observation locally (privacy: only paths/run-ids/session, never content).
state="${XDG_STATE_HOME:-$HOME/.local/state}/se-lifecycle"
if mkdir -p "$state" 2>/dev/null; then
  printf '%s\t%s\t%s\t%s\t%s\n' "$SID" "$kind" "${active_run:-none}" "$root" "${surfaced:+reminded}" \
    >> "$state/$SID.log" 2>/dev/null || true
fi

# Never block. Surface only when a fresh reminder was claimed above; both dialects exit 0.
[ -n "$surfaced" ] || emit_none
case "$DIALECT" in
  codex)
    printf '%s' "$message" | python3 -c '
import sys, json
print(json.dumps({"hookSpecificOutput": {"hookEventName": "Notification",
      "additionalContext": sys.stdin.read()}}))' 2>/dev/null || true
    ;;
  *)
    printf '%s' "$message" | python3 -c '
import sys, json
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
      "additionalContext": sys.stdin.read()}}))' 2>/dev/null || printf '%s\n' "$message" >&2
    ;;
esac
exit 0
