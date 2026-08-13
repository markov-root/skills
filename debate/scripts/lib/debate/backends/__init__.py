"""Debater backends — the modularity primitive (ADR-0004/0012). A `Debater` turns (system, user)
into text; the engine marshals context and writes files, indifferent to how a voice produces it.
One file per backend; `build_debater` wires a spec to a concrete backend.
"""

from __future__ import annotations

import shutil

from debate.backends.base import (
    AtCapacity,
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
]


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
