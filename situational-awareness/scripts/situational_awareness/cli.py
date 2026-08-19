"""CLI — the stable contract. `situational-awareness [session] [--provider P] [--json]`.

Exit codes are load-bearing (agents gate on them):
  0  continue      2  usage error
  11 wrap_up       3  data unavailable
  10 handoff_now
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from situational_awareness import __version__, config, core, fleet, handoff, registry


def _build_reading(session, provider_name, policy_override=None):
    if provider_name:
        provider = registry.get(provider_name)
        path = provider.locate(session)
    else:
        provider, path = registry.detect(session)
    if provider is None or path is None:
        return None, None, None
    raw = provider.read(path)
    # statusline detection is only valid for the live session — a different session
    # may be running a different model with a different window.
    env_sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    is_current = session in (None, "current") or (env_sid is not None and session == env_sid)
    window, source = config.resolve_window(provider.name, raw, is_current=is_current)
    sid = provider.resolve_session_id(session, path)
    policy = config.resolve_context_policy(provider.name, policy_override)
    return (
        provider,
        core.build_reading(provider.name, sid, raw, window, source, policy),
        raw,
    )


def _human(r: core.Reading) -> str:
    win = f"{r.window / 1_000_000:.1f}M" if r.window >= 1_000_000 else f"{r.window // 1000}K"
    head = (
        f"situational-awareness · {r.provider} · {r.model or '?'} · {win} window · "
        f"{r.used_tokens:,} used · {r.remaining_pct:.0f}% remaining → "
        f"{r.action} ({r.zone})"
    )
    lines = [head]
    if r.confidence != "high":
        lines.append(f"  confidence: {r.confidence}")
    for n in r.notes:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


def _estimate_file_tokens(paths: list[str]) -> int:
    """Rough token estimate from on-disk byte sizes (~3.5 chars/token)."""
    total = 0
    for p in paths:
        try:
            total += Path(p).stat().st_size
        except OSError:
            pass
    return round(total / 3.5)


def _print_extra(extra: dict) -> None:
    f = extra.get("forecast")
    if f:
        rate = f["tokens_per_turn"]
        if rate <= 0:
            print("  forecast: context not growing — no estimate")
        elif "turns_until_checkpoint" in f:
            print(
                f"  forecast: ~{rate:,} tok/turn → "
                f"~{f['turns_until_checkpoint']} turns to durable checkpoint reminder"
            )
        elif f["turns_until_handoff"] is None:
            print("  forecast: no handoff boundary for this policy")
        else:
            print(
                f"  forecast: ~{rate:,} tok/turn → ~{f['turns_until_wrap_up']} turns to "
                f"wrap_up, ~{f['turns_until_handoff']} to handoff"
            )
    fit = extra.get("fits")
    if fit:
        print(
            f"  fits {fit['estimate']:,}? {fit['advice']} "
            f"(headroom {fit['remaining_before']:,} → {fit['remaining_after']:,})"
        )


# --- hook mode ---------------------------------------------------------------
# Escalating directive per action, appended to the injected line so the agent
# knows what to DO, not just the number.
_HOOK_DIRECTIVE = {
    "continue": "Prefer offloading bulky file reads/searches to subagents so raw "
    "content stays out of your context.",
    "wrap_up": "Finish the current thread and record anything deferred; draft a "
    "handoff. Don't start new threads unless the user explicitly asks.",
    "handoff_now": "Checkpoint NOW: write a handoff doc (state, next steps, key "
    "files), tell the user you're near the context limit, and do not "
    "start new work.",
}

_COMPACTION_RECOVERY_CONTEXT = (
    "[situational-awareness:compaction-recovery] Compaction completed. Continue the same user outcome; "
    "do not hand off or stop merely because compaction occurred. Before further work, re-read the "
    "applicable instruction files and active task/checkpoint documentation from disk. Reconcile "
    "the compacted summary with the current plan, working-tree state when applicable, and recorded "
    "verification. Preserve completed work and resume from the first unresolved step."
)


def _hook_text(r: core.Reading) -> str:
    directive = _HOOK_DIRECTIVE.get(r.action, "")
    conf = "" if r.confidence == "high" else f" (window {r.confidence}-confidence)"
    return f"[situational-awareness] {r.remaining_pct:.0f}% of the context window remains{conf}. {directive}"


def _emit_hook_context(event_name: str, context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": context,
                },
            }
        )
    )


def _hook_mode() -> int:
    """Handle supported lifecycle events without ever disrupting the turn.

    - SessionStart(source=compact): inject the cross-harness recovery contract.
    - UserPromptSubmit: inject Claude's occupancy directive once the window fills.
    """
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    try:
        event_name = data.get("hook_event_name")
        if event_name == "SessionStart":
            if data.get("source") == "compact":
                _emit_hook_context("SessionStart", _COMPACTION_RECOVERY_CONTEXT)
            return 0
        if event_name not in (None, "UserPromptSubmit"):
            return 0

        sid = data.get("session_id")
        provider = registry.get("claude-code")
        path = provider.locate(sid)
        if path is None:
            return 0
        raw = provider.read(path)
        # A UserPromptSubmit hook always fires for the live session → is_current.
        window, source = config.resolve_window("claude-code", raw, is_current=True)
        reading = core.build_reading("claude-code", sid or "current", raw, window, source)
        if reading.zone == "normal":
            return 0  # plenty of headroom — stay silent
        _emit_hook_context("UserPromptSubmit", _hook_text(reading))
    except Exception:  # noqa: BLE001 — swallow everything; the turn must proceed
        return 0
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="situational-awareness",
        description="Report LLM agent context-window occupancy for a session.",
    )
    ap.add_argument(
        "session",
        nargs="?",
        default="current",
        help="session id (default: 'current' — this agent's own session)",
    )
    ap.add_argument(
        "--provider", choices=registry.names(), help="force a provider instead of auto-detecting"
    )
    ap.add_argument(
        "--policy",
        choices=config.CONTEXT_POLICIES,
        help="override the provider's context workflow policy",
    )
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument(
        "--quiet", action="store_true", help="no stdout; communicate only via exit code"
    )
    ap.add_argument(
        "--hook",
        action="store_true",
        help="lifecycle hook mode: recover durable state after compaction, or inject "
        "a UserPromptSubmit status line when Claude's window is filling",
    )
    ap.add_argument(
        "--forecast",
        action="store_true",
        help="estimate turns until the wrap_up / handoff thresholds (task 0006)",
    )
    ap.add_argument(
        "--fits",
        type=int,
        metavar="TOKENS",
        help="check whether TOKENS more would fit the remaining window (task 0010)",
    )
    ap.add_argument(
        "--fits-files",
        nargs="+",
        metavar="FILE",
        help="estimate tokens from on-disk file sizes and run --fits",
    )
    ap.add_argument(
        "--handoff",
        action="store_true",
        help="emit a pre-filled handoff doc for the next agent to complete (task 0004)",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="fleet view: context across ALL recent sessions/subagents (task 0009)",
    )
    ap.add_argument(
        "--since",
        type=float,
        default=24.0,
        metavar="HOURS",
        help="with --all, how far back to look (default 24h)",
    )
    ap.add_argument("--version", action="version", version=f"situational-awareness {__version__}")
    args = ap.parse_args(argv)

    if args.hook:
        return _hook_mode()

    if args.all:
        items = fleet.gather(max_age_s=int(args.since * 3600))
        if not args.quiet:
            if args.json:
                print(
                    json.dumps(
                        [{**it["reading"].to_dict(), "current": it["current"]} for it in items],
                        indent=2,
                    )
                )
            else:
                print(fleet.render(items))
        return fleet.worst_exit(items)

    try:
        _, reading, raw = _build_reading(args.session, args.provider, args.policy)
    except LookupError as e:
        if not args.quiet:
            print(f"situational-awareness: no usage data ({e})", file=sys.stderr)
        return core.EXIT_NO_DATA
    except Exception as e:  # noqa: BLE001 — boundary: never crash a caller
        if not args.quiet:
            print(f"situational-awareness: error: {e}", file=sys.stderr)
        return core.EXIT_ERROR

    if reading is None:
        if not args.quiet:
            print(
                f"situational-awareness: could not locate session {args.session!r} for any provider",
                file=sys.stderr,
            )
        return core.EXIT_NO_DATA

    # --- sub-outputs (all share the one reading) ---
    if args.handoff:
        print(handoff.render(reading))
        return reading.exit_code

    extra: dict = {}
    if args.forecast:
        extra["forecast"] = core.forecast(
            reading.used_tokens, reading.window, raw.series, policy=reading.policy
        )
    est = args.fits
    if args.fits_files:
        est = (est or 0) + _estimate_file_tokens(args.fits_files)
    if est is not None:
        extra["fits"] = core.fits(est, reading.used_tokens, reading.window, policy=reading.policy)

    if not args.quiet:
        if args.json:
            print(json.dumps({**reading.to_dict(), **extra}, indent=2))
        else:
            print(_human(reading))
            _print_extra(extra)
    return reading.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
