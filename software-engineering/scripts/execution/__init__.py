"""Bounded subprocess execution and executable identity."""

from .process import (
    ExecutableIdentity,
    ProcessResult,
    inspect_executable,
    resolve_executable,
    run_process,
)

__all__ = (
    "ExecutableIdentity",
    "ProcessResult",
    "inspect_executable",
    "resolve_executable",
    "run_process",
)
