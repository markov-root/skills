"""Emit only a project's declared scaffold wiring for an explicit style.

The bare path stays in scaffold.py. This module has no bundled family,
include, readiness choice, or footer; every such value comes from
``visuals.toml``. It substitutes literal declarations into fixed HTML slots.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

import scaffold
import visual_style


def _include_href(path: str, root: Path, source_dir: Path) -> str:
    if path.startswith("/"):
        return path  # the project explicitly chose the served web-root path
    return Path(os.path.relpath(root / path, source_dir)).as_posix()


def _master(slug: str, wiring, root: Path, source_dir: Path) -> str:
    lines = [
        "<!doctype html>", "<html>", "<head>",
        '    <meta charset="utf-8" />',
        f"    <title>{html.escape(slug)}</title>",
    ]
    for include in wiring.includes:
        href = html.escape(_include_href(include.path, root, source_dir), quote=True)
        if include.kind == "stylesheet":
            lines.append(f'    <link rel="stylesheet" href="{href}" />')
        else:
            script_type = ' type="module"' if include.module else ""
            lines.append(f'    <script{script_type} src="{href}"></script>')
    lines.extend((
        "    <style>",
        "      html, body { margin: 0; }",
        "      body { display: flex; flex-direction: column; min-height: 100vh; }",
        "      main { flex: 1 1 auto; }",
        "    </style>",
    ))
    if wiring.readiness in ("ready", "rendered"):
        lines.extend((
            "    <script>",
            "      requestAnimationFrame(() => {",
            f'        document.documentElement.dataset.{wiring.readiness} = "true";',
            "      });",
            "    </script>",
        ))
    lines.extend(("</head>", "<body>", "    <main></main>"))
    if wiring.footer is not None:
        attrs = "".join(
            f' {name}="{html.escape(value, quote=True)}"'
            for name, value in wiring.footer.attributes.items()
        )
        lines.append(f"    <{wiring.footer.tag}{attrs}></{wiring.footer.tag}>")
    lines.extend(("</body>", "</html>", ""))
    return "\n".join(lines)


def plan_scaffold_style(config_resolved, kind: str, slug: str, force: bool, style: str):
    """Return a normal ScaffoldPlan after validating every style reference."""
    if kind not in scaffold.KINDS:
        raise scaffold.ScaffoldRefused(
            f"unknown kind {kind!r}; one of: {', '.join(scaffold.KINDS)}", exit_code=2
        )
    parts = scaffold._check_slug(slug)
    declared = config_resolved.styles
    if style not in declared:
        names = ", ".join(sorted(declared)) or "none"
        raise scaffold.ScaffoldRefused(
            f"unknown style {style!r}; declared styles: {names}", exit_code=2
        )
    wiring = config_resolved.scaffold_wiring.get(style)
    if wiring is None:
        names = ", ".join(sorted(config_resolved.scaffold_wiring)) or "none"
        raise scaffold.ScaffoldRefused(
            f"style {style!r} has no [scaffold.{style}] wiring; wired styles: {names}",
            exit_code=2,
        )
    undeclared = sorted(set(config_resolved.scaffold_wiring) - set(declared))
    if undeclared:
        raise scaffold.ScaffoldRefused(
            f"scaffold wiring names undeclared styles: {', '.join(undeclared)}; "
            f"declared styles: {', '.join(sorted(declared))}", exit_code=2,
        )

    root = Path(config_resolved.root)
    visual_dir = root.joinpath(scaffold.VISUALS_DIR, *parts)
    source_dir = visual_dir / scaffold.SOURCE_DIR_NAME
    if visual_dir.exists() and not force:
        raise scaffold.ScaffoldRefused(
            f"refusing to scaffold: {visual_dir} already exists "
            "(pass --force to fill only absent files)", exit_code=2,
        )
    if visual_dir.exists() and not visual_dir.is_dir():
        raise scaffold.ScaffoldRefused(
            f"refusing to scaffold: {visual_dir} exists and is not a directory", exit_code=2,
        )
    if visual_dir.exists():
        existing_style, error = visual_style.declared_style(visual_dir)
        if error:
            raise scaffold.ScaffoldRefused(error, exit_code=2)
        if (visual_dir / scaffold.BRIEF_NAME).is_file() and existing_style != style:
            raise scaffold.ScaffoldRefused(
                f"existing BRIEF.md declares style {existing_style!r}, requested {style!r}",
                exit_code=2,
            )

    profile = (
        scaffold.ProfileSelection(wiring.canvas, "style-declaration")
        if wiring.canvas else scaffold.select_profile(kind, config_resolved)
    )
    brief = (
        scaffold._template("BRIEF.md.tmpl")
        .replace("{{SLUG}}", slug)
        .replace("{{PROFILE}}", profile.name)
        .replace("{{BASIS}}", profile.basis)
        .replace("{{KIND}}", kind)
    )
    brief = brief.replace(
        f"default canvas profile: {profile.name}",
        f"style: {style}\ndefault canvas profile: {profile.name}",
        1,
    )
    content = (
        (visual_dir / scaffold.BRIEF_NAME, brief),
        (source_dir / scaffold.MASTER_NAME, _master(slug, wiring, root, source_dir)),
        (source_dir / scaffold.MANIFEST_NAME, scaffold._template("frames.txt.tmpl")),
    )
    writes, skipped = [], []
    for path, text in content:
        (skipped if path.exists() else writes).append((path, text))
    return scaffold.ScaffoldPlan(
        visual_dir=visual_dir, writes=writes, skipped=skipped,
        profile=profile, theme=None, theme_link="",
    )
