"""Fleet view (task 0009) — context occupancy across ALL recent sessions, including
subagents and parallel workers (each has its own window). Quota is account-global
(shared), so the per-session axis worth watching across a fleet is CONTEXT.

Lets an orchestrator answer "is any of my workers about to hit the wall?" at a glance.
"""

from __future__ import annotations

import os

from situational_awareness import config, core, registry

_SEV = {"continue": 0, "wrap_up": 1, "handoff_now": 2}


def gather(max_age_s: int = 86_400, limit: int = 50) -> list[dict]:
    """All recent sessions across providers, most-full (least remaining) first."""
    env_sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    out: list[dict] = []
    for name in registry.names():
        provider = registry.get(name)
        for path in provider.list_recent(max_age_s, limit):
            try:
                raw = provider.read(path)
            except (LookupError, OSError, ValueError):
                continue  # empty/!usage transcript — skip
            sid = provider.resolve_session_id(None, path)
            is_current = env_sid is not None and sid == env_sid
            window, source = config.resolve_window(name, raw, is_current=is_current)
            policy = config.resolve_context_policy(name)
            reading = core.build_reading(name, sid, raw, window, source, policy)
            out.append({"reading": reading, "current": is_current})
    out.sort(key=lambda x: x["reading"].remaining_pct)
    return out


def worst_exit(items: list[dict]) -> int:
    """Exit code of the most urgent session (so a gate can catch any worker in trouble)."""
    if not items:
        return core.EXIT_NO_DATA
    sev = max(_SEV.get(i["reading"].action, 0) for i in items)
    return {0: core.EXIT_CONTINUE, 1: core.EXIT_WRAP_UP, 2: core.EXIT_HANDOFF}[sev]


def render(items: list[dict]) -> str:
    if not items:
        return "situational-awareness: no recent sessions found"
    lines = [f"Fleet — {len(items)} session(s), most-full first:"]
    for it in items:
        r = it["reading"]
        star = " *" if it["current"] else ""
        lines.append(
            f"  {r.remaining_pct:5.0f}% left  {r.provider:11} {r.session[:12]:12} "
            f"{(r.model or '?'):17} {r.action}{star}"
        )
    return "\n".join(lines)
