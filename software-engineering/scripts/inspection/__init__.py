"""Passive and explicit active repository-inspection contracts."""

from .passive import inspect_repository
from .profiles import run_active_inspection
from .rendering import render_active_inspection, render_inspection

__all__ = (
    "inspect_repository",
    "render_active_inspection",
    "render_inspection",
    "run_active_inspection",
)
