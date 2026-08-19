"""Fused budget view (task 0007) — context + quota in one call, with the *binding*
axis chosen for you.

Neither number alone tells an agent what to do: compacting fixes context but not
quota; waiting for reset fixes quota but not context. This picks whichever is more
urgent and reports one merged action.
"""

from __future__ import annotations

import argparse
import json

from situational_awareness import cache as cache_analysis
from situational_awareness import config, core, registry
from situational_awareness.quota import analysis
from situational_awareness.quota.models import QuotaReading

# severity ladders (both axes collapse to 0=ok / 1=soft / 2=hard)
_CTX_SEV = {"continue": 0, "wrap_up": 1, "handoff_now": 2}
_QUOTA_SEV = {"continue": 0, "wind_down": 1, "wait_for_reset": 2}
_EXIT_BY_SEV = {0: core.EXIT_CONTINUE, 1: core.EXIT_WRAP_UP, 2: core.EXIT_HANDOFF}


def _context_reading():
    provider, path = registry.detect("current")
    if provider is None or path is None:
        return None, None, None
    raw = provider.read(path)
    window, source = config.resolve_window(provider.name, raw, is_current=True)
    sid = provider.resolve_session_id("current", path)
    policy = config.resolve_context_policy(provider.name)
    return (
        core.build_reading(provider.name, sid, raw, window, source, policy),
        provider,
        path,
    )


def combine(ctx, quota, cache=None) -> dict:
    """Pure merge of a context Reading and a quota QuotaReading (either may be None/
    degraded). Returns {binding, action, exit_code, message, context, quota}."""
    ctx_ok = ctx is not None
    q_ok = isinstance(quota, QuotaReading)
    ctx_sev = _CTX_SEV.get(ctx.action, 0) if ctx_ok else -1
    q_sev = _QUOTA_SEV.get(quota.action, 0) if q_ok else -1

    if not ctx_ok and not q_ok:
        return {
            "binding": None,
            "action": "unknown",
            "exit_code": core.EXIT_NO_DATA,
            "message": "[budget] no context or quota data",
            "context": {"status": "no_data"},
            "quota": quota if isinstance(quota, dict) else {"status": "no_data"},
            "cache": cache.to_dict() if cache is not None else {"status": "no_data"},
        }

    if ctx_sev > q_sev:
        binding = "context"
    elif q_sev > ctx_sev:
        binding = "quota"
    else:  # tie → whichever has less headroom remaining
        ctx_rem = ctx.remaining_pct if ctx_ok else 100.0
        q_windows = [w.remaining_pct for w in (quota.five_hour, quota.seven_day) if w.available]
        q_rem = min(q_windows) if q_ok and q_windows else 100.0
        binding = "context" if ctx_rem <= q_rem else "quota"

    action = ctx.action if binding == "context" else quota.action
    sev = ctx_sev if binding == "context" else q_sev
    ctx_str = f"ctx {ctx.remaining_pct:.0f}%" if ctx_ok else "ctx n/a"

    def qwin(window):
        return f"{window.used_pct:.0f}%" if window.available else "n/a"

    q_str = (
        f"{quota.provider} 5h {qwin(quota.five_hour)} wk {qwin(quota.seven_day)}"
        if q_ok
        else "quota n/a"
    )
    cache_str = f"cache {cache.hit_ratio:.0%}" if cache is not None else "cache n/a"
    return {
        "binding": binding,
        "action": action,
        "exit_code": _EXIT_BY_SEV[max(sev, 0)],
        "message": f"[{ctx_str} · {q_str} · {cache_str}] → {binding} binding: {action}",
        "context": ctx.to_dict() if ctx_ok else {"status": "no_data"},
        "quota": quota.to_dict()
        if q_ok
        else (quota if isinstance(quota, dict) else {"status": "no_data"}),
        # Cache is an advisory resource axis. It never overrides a context/quota
        # action because a cold cache is inefficient, not a reason to stop work.
        "cache": cache.to_dict() if cache is not None else {"status": "no_data"},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="budget", description="Fused view: context window + subscription quota."
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    args = ap.parse_args(argv)

    try:
        ctx, provider, session_path = _context_reading()
    except Exception:  # noqa: BLE001 — one axis failing must not sink the other
        ctx, provider, session_path = None, None, None
    try:
        quota = analysis.read_quota(
            provider=provider.name if provider is not None else "claude-code",
            session_path=session_path,
        )
    except Exception:  # noqa: BLE001
        quota = None
    try:
        cache = cache_analysis.read_current()
    except Exception:  # noqa: BLE001
        cache = None

    merged = combine(ctx, quota, cache)
    if not args.quiet:
        if args.json:
            print(json.dumps(merged, indent=2))
        else:
            print(merged["message"])
    return merged["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
