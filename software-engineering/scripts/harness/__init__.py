"""Harness-config wiring for the shipped hook scripts.

This domain merges the two shipped hook scripts (``se-consult-gate.sh`` and
``se-lifecycle-hook.sh``) into a named harness's runtime configuration. It never imports the CLI or
command adapters and never enables a hook as a side effect of installation.
"""

from __future__ import annotations

from .hooks import (
    HARNESSES,
    HOOKS,
    HookInstallError,
    default_target,
    plan_installation,
)

__all__ = [
    "HARNESSES",
    "HOOKS",
    "HookInstallError",
    "default_target",
    "plan_installation",
]
