"""Capability detection for the generative delegate: the `image-generation` skill.

ADR 0006: `visuals image` is a capability-detecting delegating shim. The delegate
is detected here, in the capability domain, and every route is checked —
installed skill trees first, then a PATH-exposed launcher — because absence
must degrade honestly (exit 3 naming the install path), never crash and never
silently no-op. This module is the single source of the detection constants;
`doctor.py` consumes them through thin wrappers so the environment report and
this shim can never drift apart (audit F7 discipline: a value lives once).

The detection pattern follows doctor.py's established shape: candidates are
plain paths, absence is a first-class result, and nothing here assumes the
delegate is installed.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

# Where an installed image-generation skill may live, in priority order.
DELEGATE_INSTALL_CANDIDATES = (
    Path.home() / ".agents" / "skills" / "image-generation",
    Path.home() / ".claude" / "skills" / "image-generation",
    Path.home() / "Skills" / "image-generation" / "public",
)

# Within an install root, the entrypoints that make the delegate usable.
DELEGATE_ENTRYPOINTS = ("scripts/image_generation.py", "scripts/generate.sh")

# The delegate may also be exposed as a PATH command (e.g. a skills.sh CLI
# launcher). Capability-detected like every other route — absence degrades
# honestly, never a hard dependency (ADR 0006).
DELEGATE_COMMAND_NAMES = ("image-generation",)


@dataclass(frozen=True)
class Delegate:
    """A detected delegate and how to invoke it.

    `kind` is "entrypoint" (a Python/shell entry script inside an install root;
    invoked via its interpreter) or "path" (a PATH command; invoked directly).
    `detail` is the human-readable provenance of the detection.
    """

    kind: str  # "entrypoint" | "path"
    location: str
    invocation: tuple[str, ...]

    @property
    def is_entrypoint(self) -> bool:
        return self.kind == "entrypoint"


def delegate_on_path(
    command_names: tuple[str, ...] = DELEGATE_COMMAND_NAMES,
) -> str | None:
    """Resolve the delegate as a PATH command, if the machine exposes one."""
    for name in command_names:
        resolved = shutil.which(name)
        if resolved and os.access(resolved, os.X_OK):
            return resolved
    return None


def resolve_delegate(
    candidates: tuple[Path, ...] | None = None,
    entrypoints: tuple[str, ...] | None = None,
    command_names: tuple[str, ...] | None = None,
) -> Delegate | None:
    """Detect the installed delegate across every route; None means absent.

    Arguments default to the module constants at CALL time (not definition
    time), so tests can monkeypatch the constants on this module and every
    consumer sees the patched search space.

    Install roots are searched first (entry scripts in priority order), then a
    PATH-exposed launcher. A hit records where it was found, so the receipt can
    name its provenance.
    """
    candidates = DELEGATE_INSTALL_CANDIDATES if candidates is None else candidates
    entrypoints = DELEGATE_ENTRYPOINTS if entrypoints is None else entrypoints
    command_names = DELEGATE_COMMAND_NAMES if command_names is None else command_names
    for root in candidates:
        if not root.is_dir():
            continue
        for entry in entrypoints:
            script = root / entry
            if script.is_file():
                return Delegate(
                    kind="entrypoint",
                    location=str(script),
                    invocation=(str(script),),
                )
    path_hit = delegate_on_path(command_names)
    if path_hit:
        return Delegate(
            kind="path",
            location=path_hit,
            invocation=(path_hit,),
        )
    return None


def missing_detail(
    candidates: tuple[Path, ...] | None = None,
    command_names: tuple[str, ...] | None = None,
) -> str:
    """The honest-degradation message: every location checked, and how to get it."""
    candidates = DELEGATE_INSTALL_CANDIDATES if candidates is None else candidates
    command_names = DELEGATE_COMMAND_NAMES if command_names is None else command_names
    return (
        "delegate not installed (checked "
        + ", ".join(str(c) for c in candidates)
        + "; no "
        + "/".join(command_names)
        + " on PATH)"
        + "; install the image-generation skill (e.g. `npx skills add image-generation`) "
        "or point an install root at it"
    )