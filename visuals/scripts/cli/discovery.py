#!/usr/bin/env python3
"""Visual discovery: which directories under a project root are visuals.

A capability domain with several consumers — `validate`, `index`, and `render`
all have to agree on what a visual IS, and on which directories are deliberately
not walked. Two implementations of this walk would diverge the moment one of
them learned about a new corpus layout, and the symptom would be a command that
cannot see a visual another command reports on (task 0017 D2).

Extracted from validate.py, where it lived while `validate` was its only caller.
"""

from __future__ import annotations

import os
from pathlib import Path

import store

NON_VISUAL_DIR_NAMES = ("templates", "archive")


def is_visual_dir(path: Path) -> bool:
    """A visual directory holds a source master or a RENDERED version.

    Two discs, matching the artifact store's own shape: a `source/` directory
    (masters to check even before a first render), or a version directory
    containing at least one .png (rendered output). A directory with version
    directories that hold no rendered artifact is NOT a visual — the reference
    corpus also version-controls prose (script/sections, literature/sections
    keep vX.Y.Z/ of notes.md and spoken.md), and those are not the artifact
    store's concern. A directory that is only a container for nested visuals
    (the corpus's hm-mechanism-briefing) holds none of these and is not
    reported as a visual — its nested families are discovered on their own."""
    if (path / "source").is_dir():
        return True
    return _has_rendered_output(path)


def _has_rendered_output(path: Path) -> bool:
    for version in store.existing_versions(path):
        if any((path / version).glob("*.png")):
            return True
    return False


def discover_visuals(root: Path) -> tuple[Path, ...]:
    """Every visual directory under the project root, in stable path order.

    Walks the whole tree so nested visual families are covered (audit F6: the
    corpus's own validator only ever saw `*/source/index.html`). Does not
    descend into `source*` or version directories: masters are collected per
    visual, and a version directory is immutable output, not a project.

    Two directory names are never walked into, matching config discovery's own
    precedent (config.py skips files under `templates/` when locating a
    project's unique contract files): `templates/` holds scaffold exemplars
    (the corpus's visual-starter), and `archive/` holds deliberately retained
    copies that are not the live store (the corpus archives a misplaced visual
    copy under `script/archive/misplaced-by-another-agent/`). An archived
    broken store is not a finding against the live project.
    """
    found: list[Path] = []
    root = root.resolve()
    for dirpath, dirnames, _filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and d not in NON_VISUAL_DIR_NAMES
        )
        if is_visual_dir(here):
            found.append(here)
            dirnames[:] = [
                d
                for d in dirnames
                if not store.VERSION_RE.match(d) and not d.startswith("source")
            ]
    return tuple(found)
