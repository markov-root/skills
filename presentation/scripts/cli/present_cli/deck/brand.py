"""The one token reader for the deck engine and component library (ADR 0008; task 0015).

Every colour, font, size and logo the components use comes through here, by **semantic role**
(`ink`, `accent`, `context`, …), never by a brand's own colour names. A token file maps roles to
its colour tokens in an optional `roles` object; without one, a role reads the colour token named
after it (the neutral set does this). The active file is chosen once per process, before the
library is imported:

- `PRESENT_TOKENS=<path>`: a brand token file (e.g. a consumer's `_shared/brand/tokens.json`); its
  repository-relative font and logo paths resolve against `PRESENT_REPO` (default: the nearest
  ancestor of the token file holding `presentations.toml`);
- otherwise the skill's neutral set, `assets/tokens/neutral.json`.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pptx.dml.color import RGBColor

SKILL_ASSETS = (
    next(p for p in Path(__file__).resolve().parents if (p / "SKILL.md").is_file())
    / "assets"
)
NEUTRAL = SKILL_ASSETS / "tokens" / "neutral.json"

# Token vocabulary v1: the roles the library reads.
COLOR_ROLES = (
    "ink",
    "ink_2",
    "dark_ground",
    "accent",
    "accent_tint",
    "accent_2",
    "context",
    "context_line",
    "tint",
    "grid",
    "background",
    "surface",
    "muted",
    "label",
    "rule",
    "edge",
    "off_number",
    "off_text",
)
FONT_ROLES = ("display", "body", "team_display")
SIZE_KEYS = (
    "panel_lead_pt",
    "legend_row_pitch",
    "texture_pattern_ink_pct",
    "texture_ground_pct",
    "texture_faded_pct",
)


class TokenError(Exception):
    pass


def _find_repo(start: Path) -> Path | None:
    for cand in (start, *start.parents):
        if (cand / "presentations.toml").is_file():
            return cand
    return None


def _value(entry: Any) -> Any:
    return entry["value"] if isinstance(entry, dict) and "value" in entry else entry


def resolve_role(data: dict[str, Any], role: str) -> str:
    """The hex value of a colour role in a token document."""
    name = data.get("roles", {}).get(role, role)
    if not isinstance(name, str) or name not in data.get("color", {}):
        raise TokenError(f"colour role {role!r} → token {name!r} is not defined")
    return _value(data["color"][name])


def load(path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else NEUTRAL
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = []
    for role in COLOR_ROLES:
        try:
            resolve_role(data, role)
        except TokenError:
            missing.append(f"role {role}")
    missing += [f"font.{k}" for k in FONT_ROLES if k not in data.get("font", {})]
    missing += [f"size.{k}" for k in SIZE_KEYS if k not in data.get("size", {})]
    if missing:
        raise TokenError(
            f"{path}: token file lacks {', '.join(missing)} (token vocabulary v1)"
        )
    return data


_PATH = (
    Path(os.environ["PRESENT_TOKENS"]) if os.environ.get("PRESENT_TOKENS") else NEUTRAL
)
TOKENS = load(_PATH)
TOKENS_PATH = _PATH
TOKENS_SHA256 = hashlib.sha256(_PATH.read_bytes()).hexdigest()
TOKENS_VERSION = str(TOKENS.get("version", "0.0.0"))
TOKENS_NAME = str(TOKENS.get("name", ""))
ROOT = (
    Path(os.environ["PRESENT_REPO"])
    if os.environ.get("PRESENT_REPO")
    else (_find_repo(_PATH.resolve().parent) or _PATH.resolve().parent)
)


def hex_(role: str) -> str:
    return resolve_role(TOKENS, role)


def color(role: str) -> RGBColor:
    return RGBColor.from_string(hex_(role).lstrip("#").upper())


def rgb(role: str) -> tuple[int, int, int]:
    c = color(role)
    return (c[0], c[1], c[2])


def series() -> list[RGBColor]:
    """Colours for successive data series: `roles.series`, else ink, accent, ink_2, accent_2."""
    names = TOKENS.get("roles", {}).get("series")
    if names:
        return [
            RGBColor.from_string(_value(TOKENS["color"][n]).lstrip("#").upper())
            for n in names
        ]
    return [color(r) for r in ("ink", "accent", "ink_2", "accent_2")]


def font(role: str) -> str:
    return TOKENS["font"][role]["family"]


def _path(f: str) -> Path:
    p = Path(f)
    return p if p.is_absolute() else ROOT / p


def font_file(role: str) -> Path | None:
    f = TOKENS["font"].get(role, {}).get("file")
    if not f:
        return None
    p = _path(f)
    return p if p.is_file() else None


def size(name: str) -> float:
    return TOKENS["size"][name]


def logo(role: str) -> Path | None:
    """A logo role's file (repository-relative in the token file), or None when unset/missing."""
    f = TOKENS.get("logo", {}).get(role)
    if not f:
        return None
    p = _path(f)
    return p if p.exists() else None


def logo_dir() -> Path | None:
    """Where named logos (`logo_path(slug)`) live: the folder of the `mark` logo, if any."""
    mark = logo("mark") or logo("mark_png")
    return mark.parent if mark else None


def cache_dir() -> Path:
    """Where derived assets (monochrome logos) are written: a per-user cache keyed by the token
    hash. Never inside the skill, and never inside the consumer repository: a build or gallery
    must not leave untracked files in tracked folders (found 2026-11-10, gallery run)."""
    base = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "present"
        / "logos"
        / TOKENS_SHA256[:12]
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def identity() -> dict[str, str]:
    """What a receipt records about the brand (ADR 0008)."""
    return {"version": TOKENS_VERSION, "sha256": TOKENS_SHA256}
