"""Narrow adopted-project context used by command adapters and run workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..policy.manifest import Manifest, load_manifest
from .discovery import Project, discover_project


@dataclass(frozen=True)
class AdoptedProject:
    """A discovered project paired with its parsed, validated manifest."""

    discovery: Project
    root: Path
    manifest: Manifest


def load_adopted_project(start: str | Path = ".") -> AdoptedProject:
    """Discover and validate the adopted project containing *start*."""

    project = discover_project(start)
    return AdoptedProject(project, project.root, load_manifest(project.manifest))
