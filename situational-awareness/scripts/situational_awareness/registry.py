"""Provider registry + auto-detection.

Order matters for "current": if $CLAUDE_CODE_SESSION_ID is set we're inside
Claude Code, so try it first. Otherwise probe each provider's locate().
"""

from __future__ import annotations

import os

from situational_awareness.providers import (
    ClaudeCodeProvider,
    CodexProvider,
    OpenCodeProvider,
    Provider,
)

_PROVIDERS: dict[str, Provider] = {
    p.name: p for p in (ClaudeCodeProvider(), CodexProvider(), OpenCodeProvider())
}


def get(name: str) -> Provider:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise KeyError(f"unknown provider {name!r}; known: {', '.join(_PROVIDERS)}")


def names() -> list[str]:
    return list(_PROVIDERS)


def detect(session: str | None):
    """Return (provider, path) for the first provider that can locate `session`."""
    order = list(_PROVIDERS.values())
    if (not session or session == "current") and os.environ.get("CLAUDE_CODE_SESSION_ID"):
        order.sort(key=lambda p: p.name != "claude-code")
    for provider in order:
        path = provider.locate(session)
        if path is not None:
            return provider, path
    return None, None
