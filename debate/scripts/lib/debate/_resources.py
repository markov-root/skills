"""Locate immutable runtime data in a source checkout or installed wheel."""

from __future__ import annotations

import shutil
from pathlib import Path


def resource_root() -> Path:
    """Return the installed skill's immutable asset root."""
    return Path(__file__).resolve().parents[3] / "assets"


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def copy_private_tree(source: Path, destination: Path) -> None:
    """Copy a trusted prompt/resource tree without inheriting publishable source modes."""
    shutil.copytree(source, destination, copy_function=shutil.copyfile)
    destination.chmod(0o700)
    for path in destination.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
