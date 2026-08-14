"""Debater backends — the modularity primitive (ADR-0004/0012). A `Debater` turns (system, user)
into text; the engine marshals context and writes files, indifferent to how a voice produces it.
One file per backend; `build_debater` wires a spec to a concrete backend.
"""

from __future__ import annotations

import shutil

from debate.backends.base import (
    AtCapacity,
    BackendProbe,
    CallRecord,
    Debater,
    EmptyCompletion,
    QuotaExceeded,
    extract_json,
    voice_descriptor,
)
from debate.backends.claude_code import ClaudeCodeDebater
from debate.backends.codex import CodexCliDebater
from debate.backends.fake import FakeDebater
from debate.backends.openrouter import OpenRouterDebater

__all__ = [
    "Debater",
    "CallRecord",
    "OpenRouterDebater",
    "ClaudeCodeDebater",
    "CodexCliDebater",
    "FakeDebater",
    "build_debater",
    "voice_descriptor",
    "extract_json",
    "EmptyCompletion",
    "QuotaExceeded",
    "AtCapacity",
    "BackendProbe",
    "BackendPreflightError",
    "probe_backends",
    "required_backends",
    "require_backend_readiness",
]


BACKEND_TYPES = {
    "openrouter": OpenRouterDebater,
    "claude_code": ClaudeCodeDebater,
    "codex_cli": CodexCliDebater,
}


class BackendPreflightError(RuntimeError):
    """A selected cast contains locally unavailable or unauthenticated backends."""

    def __init__(self, blocked: list[BackendProbe]):
        self.blocked = blocked
        lines = [
            f"{probe.backend}: {probe.detail}. Remediation: {probe.remediation}"
            for probe in blocked
        ]
        super().__init__("selected panel is not runnable:\n  - " + "\n  - ".join(lines))


def probe_backends(names: set[str] | None = None) -> dict[str, BackendProbe]:
    """Probe registered providers once each; one adapter registration feeds every consumer."""
    selected = set(BACKEND_TYPES) if names is None else set(names)
    results: dict[str, BackendProbe] = {}
    for name in sorted(selected):
        adapter = BACKEND_TYPES.get(name)
        if adapter is None:
            results[name] = BackendProbe(
                name,
                "unknown",
                False,
                False,
                "backend is not registered",
                "Choose a registered backend or install an adapter for this backend.",
            )
            continue
        try:
            results[name] = adapter.probe()
        except (Exception, SystemExit) as exc:
            results[name] = BackendProbe(
                name,
                "api" if name == "openrouter" else "cli",
                False,
                None,
                f"probe failed safely ({type(exc).__name__})",
                "Repair the backend configuration and rerun `debate doctor`.",
            )
    return results


def required_backends(cast: dict, *, include_redteam: bool) -> set[str]:
    """Derive capabilities from the declared voices without constructing a debater."""
    voices = [*cast["debaters"], cast["arbitrator"]]
    if include_redteam and cast.get("redteam"):
        voices.append(cast["redteam"])
    return {voice.get("backend", "openrouter") for voice in voices}


def require_backend_readiness(cast: dict, *, include_redteam: bool) -> dict[str, BackendProbe]:
    """Fail before persistence when a selected panel lacks a required local capability."""
    names = required_backends(cast, include_redteam=include_redteam)
    if "openrouter" in names:
        # Preserve the established public missing-key error instead of wrapping it in a new type.
        from debate.config import get_settings

        get_settings().require_api_key()
    results = probe_backends(names)
    blocked = [results[name] for name in sorted(results) if not results[name].runnable]
    if blocked:
        raise BackendPreflightError(blocked)
    return results


def build_debater(spec: dict) -> Debater:
    backend = spec.get("backend", "openrouter")
    if backend == "openrouter":
        from debate.backends.base import _client_for
        from debate.config import get_settings

        settings = get_settings()
        debater = OpenRouterDebater(
            id=spec["id"],
            model=spec["model"],
            temperature=spec.get("temperature", 0.0),
            web=spec.get("web", False),
            max_output_tokens=spec.get("max_output_tokens"),
            reasoning_effort=spec.get("reasoning_effort"),
            max_retries=spec.get("max_retries"),
            client=(
                _client_for(
                    settings.openrouter_api_key,
                    float(spec.get("timeout", settings.request_timeout_s)),
                    str(spec.get("app_title", settings.openrouter_app_title)),
                    str(spec.get("app_url", settings.openrouter_app_url)),
                )
                if settings.openrouter_api_key
                else None
            ),
        )
    elif backend == "claude_code":
        if not shutil.which("claude"):
            raise RuntimeError(f"debater {spec['id']}: claude CLI not on PATH")
        debater = ClaudeCodeDebater(
            id=spec["id"],
            model=spec.get("model"),
            timeout_s=spec.get("timeout"),
            workspace=spec.get("workspace"),
            max_retries=spec.get("max_retries"),
        )
    elif backend == "codex_cli":
        if not shutil.which("codex"):
            raise RuntimeError(f"debater {spec['id']}: codex CLI not on PATH")
        debater = CodexCliDebater(
            id=spec["id"],
            model=spec.get("model"),
            timeout_s=spec.get("timeout"),
            reasoning_effort=spec.get("reasoning_effort"),
            workspace=spec.get("workspace"),
            max_retries=spec.get("max_retries"),
        )
    else:
        raise ValueError(f"unknown backend: {backend}")
    # Optional persona (task-0008): the voice's expert lens, prepended to its system prompt by the
    # engine and recorded in provenance. Off by default (spec has no `persona`) → byte-identical.
    debater.persona = spec.get("persona")
    return debater
