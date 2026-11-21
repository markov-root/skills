"""The visuals neighbour (task 0009; portfolio ADR 0006): find its CLI, resolve deck pins, theme.

`present` never re-implements visuals. It runs the `visuals` command with the working directory
at a visuals project (`<talk>/visuals/`, task 0026 layout) and reads `visuals index --json`.

Pin resolution:

- `key` is a slug in this talk's visuals project, or a repository-relative path to another
  talk's visual (`example-talk/visuals/firefox-security-fixes`).
- `latest` resolves to the published version. An exact version must exist, and it is
  *published* when it is not newer than the published latest; `visuals render --unpublished`
  creates versions newer than latest without moving it.
- Legacy projects without `visuals.toml` cannot be indexed. Their pin resolves from the visual's
  `latest` symlink and version folders, with a `visuals_index_unavailable` note.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import store
from .commands.doctor import NEIGHBOURS, find_neighbour

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class VisualsError(Exception):
    def __init__(self, code: str, message: str, next: str | None = None):
        super().__init__(message)
        self.code, self.message, self.next = code, message, next


def cli() -> Path | None:
    override = os.environ.get("PRESENT_VISUALS")
    if override is not None:
        return Path(override) if override else None
    rel = NEIGHBOURS["visuals"][0]
    return find_neighbour("visuals", rel)


def run(project: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    exe = cli()
    if exe is None:
        raise VisualsError(
            "capability_unavailable",
            "the visuals CLI is not installed.",
            next=NEIGHBOURS["visuals"][2],
        )
    proc = subprocess.run(
        [str(exe), *args], cwd=project, capture_output=True, text=True, timeout=600
    )
    if check and proc.returncode != 0:
        raise VisualsError(
            "visuals_failed",
            f"visuals {' '.join(args)} exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:300]}",
        )
    return proc


def index(project: Path) -> dict[str, dict[str, Any]] | None:
    """slug → index row, or None when the project is not adopted (legacy)."""
    if not (project / "visuals.toml").is_file():
        return None
    proc = run(project, "index", "--json")
    if proc.returncode != 0:
        raise VisualsError(
            "visuals_failed",
            f"visuals index failed: {(proc.stderr or proc.stdout).strip()[:300]}",
        )
    data = json.loads(proc.stdout)
    rows = (
        data.get("data", data).get("rows")
        or data.get("data", data).get("visuals")
        or []
    )
    return {r["slug"]: r for r in rows}


def _vkey(v: str) -> tuple[int, int, int]:
    return store.parse(v.lstrip("v"))


@dataclass
class Pin:
    key: str
    selector: str
    resolved: str
    folder: Path  # the version folder holding the frames
    receipt: Path
    published: bool
    indexed: bool


def _locate(repo_root: Path, talk: Path, key: str) -> tuple[Path, str]:
    """(project dir, slug) for a pin key."""
    if "/" not in key:
        return talk / "visuals", key
    target = repo_root / key
    if not target.is_dir():
        raise VisualsError("visual_not_found", f"no visual at {key}")
    # the project is the nearest ancestor holding visuals.toml, else the visual's parent
    for cand in target.parents:
        if cand == repo_root:
            break
        if (cand / "visuals.toml").is_file():
            return cand, target.relative_to(cand).as_posix()
    return target.parent, target.name


def resolve(repo_root: Path, talk: Path, key: str, selector: str) -> Pin:
    project, slug = _locate(repo_root, talk, key)
    rows = index(project)
    folder_base = (
        (project / slug) if (project / slug).is_dir() else (project / "visuals" / slug)
    )
    if rows is not None:
        row = rows.get(slug)
        if row is None:
            raise VisualsError(
                "visual_not_found",
                f"{key}: visuals index has no {slug!r}",
                next=f"present visual new {slug}",
            )
        latest = (row.get("latest") or "").lstrip("v") or None
        versions = [v.lstrip("v") for v in row.get("versions", [])]
        if row.get("receipt"):
            folder_base = (project / row["receipt"]).parent.parent
    else:
        link = folder_base / "latest"
        latest = os.readlink(link).lstrip("v") if link.is_symlink() else None
        versions = sorted(
            (
                p.name.lstrip("v")
                for p in folder_base.glob("v*")
                if p.is_dir() and SEMVER.match(p.name.lstrip("v"))
            ),
            key=store.parse,
        )
    if selector == "latest":
        if latest is None:
            raise VisualsError(
                "visual_unpublished",
                f"{key}: nothing is published yet",
                next=f"present visual publish {slug} <version>",
            )
        resolved = latest
    else:
        if selector not in versions:
            raise VisualsError(
                "visual_version_missing", f"{key}: no version {selector}"
            )
        resolved = selector
    folder = folder_base / f"v{resolved}"
    receipt = folder / "receipt.json"
    if not receipt.is_file():
        raise VisualsError(
            "visual_receipt_missing", f"{key} v{resolved} has no receipt.json"
        )
    published = latest is not None and store.parse(resolved) <= store.parse(latest)
    return Pin(key, selector, resolved, folder, receipt, published, rows is not None)


# --------------------------------------------------------------------------- theme


def theme_toml(tokens: dict[str, Any], tokens_sha: str) -> str:
    """A visuals theme generated from brand tokens' semantic roles (ADR 0008). Only the values
    the tokens determine are written; visuals fills the rest from its bundled default."""
    colors = tokens.get("color", {})
    roles = tokens.get("roles", {})

    def hexof(role: str, *fallback: str) -> str | None:
        for name in (roles.get(role), role, *fallback):
            if not name:
                continue
            v = colors.get(name)
            if v is not None:
                return (v["value"] if isinstance(v, dict) else v).lower()
        return None

    lines = [
        f"# Generated by `present visual theme` from {tokens.get('name', 'brand')} tokens "
        f"{tokens.get('version', '?')} (sha256 {tokens_sha[:16]}). Do not edit: change the tokens.",
        "schema_version = 1",
        f'name = "{_theme_name(tokens)}"',
        "",
    ]
    pairs = [
        ("background.page", "background", "text"),
        ("background.surface", "surface", "text"),
        ("text.body", "ink", "text"),
        ("text.muted", "muted", "text"),
        ("accent.base", "accent", "text"),
    ]
    for role_path, role, _ in pairs:
        h = hexof(role)
        if h:
            kind = "text" if role_path.startswith("text.") else "non-text"
            lines += [f"[colour.roles.{role_path}]", f'hex = "{h}"', f'kind = "{kind}"']
            if role_path.startswith(("text.", "accent.")):
                lines.append('on = ["background.page", "background.surface"]')
            lines.append("")
    fonts = tokens.get("font", {})
    fams = {
        "sans": fonts.get("body", {}).get("family"),
        "display": fonts.get("display", {}).get("family"),
    }
    for k, fam in fams.items():
        if fam:
            lines += [
                f"[type.families.{k}]",
                f"stack = \"'{fam}', system-ui, sans-serif\"",
                "",
            ]
    series = [
        hexof(s)
        or (
            colors.get(s, {}).get("value")
            if isinstance(colors.get(s), dict)
            else colors.get(s)
        )
        for s in roles.get("series", [])
    ]
    series = [s.lower() for s in series if s]
    if series:
        lines += [
            "[chart.palette.categorical]",
            "colours = [" + ", ".join(f'"{s}"' for s in series) + "]",
            "",
        ]
    return "\n".join(lines)


def _theme_name(tokens: dict[str, Any]) -> str:
    return "brand-" + re.sub(
        r"[^a-z0-9]+", "-", str(tokens.get("name", "brand")).lower()
    ).strip("-")


def write_theme(project: Path, tokens_path: Path) -> tuple[Path, str, str]:
    """Write <project>/themes/<name>.toml and point visuals.toml at it. → (path, name, sha)."""
    raw = tokens_path.read_bytes()
    tokens = json.loads(raw)
    sha = store.sha256_bytes(raw)
    name = _theme_name(tokens)
    out = project / "themes" / f"{name}.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(theme_toml(tokens, sha) + "\n", encoding="utf-8")
    cfg = project / "visuals.toml"
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8")
        new = re.sub(
            r'^theme\s*=\s*".*"\s*$', f'theme = "{name}"', text, count=1, flags=re.M
        )
        if new != text:
            cfg.write_text(new, encoding="utf-8")
    return out, name, sha
