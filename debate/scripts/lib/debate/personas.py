"""Optional per-debater personas (task-0008).

A persona is a short system-prompt fragment that gives one voice an expert LENS (a threat-modeller,
a statistician, a domain skeptic). It is prepended to that voice's system prompt only, is never
shown to peers/arbitrator (blinding is preserved), and is **off by default** — a persona-less debate
is byte-identical to before.

**Guidance (a hard-won methodology rule):** use DOMAIN-EXPERT personas only. A domain lens raises
validity; a STAKEHOLDER or IDEOLOGICAL persona ("argue as a privacy activist / as industry") injects
bias and is exactly what a steelman must avoid. Keep personas about *expertise*, never *interest*.

A debater spec's `persona` may be inline text or the NAME of a file under `prompts/personas/`
(`<name>.md`, no extension); `resolve_persona` expands a name to its file text, passing inline and
`None` through unchanged.
"""

from __future__ import annotations

from pathlib import Path

from debate._resources import resource_path

_PERSONA_DIR = resource_path("prompts", "personas")


def resolve_persona(value: str | None, *, personas_dir: Path | None = None) -> str | None:
    """Expand a persona reference to its text. A bare token (no whitespace) that matches a
    `<personas_dir>/<token>.md` file loads that file; anything else (inline text, or an unmatched
    token) is returned unchanged. `None` → `None` (no persona)."""
    if not value:
        return None
    directory = personas_dir or _PERSONA_DIR
    token = value.strip()
    if token and not any(c.isspace() for c in token):
        candidate = directory / f"{token}.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    return value
