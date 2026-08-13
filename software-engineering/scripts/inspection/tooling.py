"""Inspection-specific projection of the shared executable evidence contract."""

from __future__ import annotations

from pathlib import Path

from ..execution import inspect_executable, run_process
from .models import ToolEvidence, bounded_text


def tool_evidence(
    name: str,
    version_command: tuple[str, ...],
    *,
    network: str,
    root: Path,
) -> ToolEvidence:
    identity = inspect_executable(
        version_command[0],
        root=root,
        version_command=version_command,
        timeout_seconds=15,
        max_output_bytes=500,
    )
    return ToolEvidence(
        name=name,
        state="installed" if identity.resolved_executable else "unavailable",
        executable=(
            Path(identity.resolved_executable).name if identity.resolved_executable else None
        ),
        executable_sha256=identity.executable_sha256,
        version=(
            bounded_text(identity.version_output)
            if identity.resolved_executable and identity.version_status == "passed"
            else None
        ),
        network=network,
    )


def is_git_work_tree(root: Path) -> bool:
    result = run_process(
        ("git", "-C", str(root), "rev-parse", "--is-inside-work-tree"),
        root=root,
        timeout_seconds=10,
        max_output_bytes=100,
    )
    return result.status == "passed" and result.stdout.strip() == b"true"
