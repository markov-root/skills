"""Public CLI composition API."""

from ..commands.contracts import (
    EXIT_APPROVAL_REQUIRED,
    EXIT_BASELINE_INCOMPATIBLE,
    EXIT_CHECK_FAILED,
    EXIT_INVALID_POLICY,
    EXIT_OK,
    EXIT_UNAVAILABLE,
)
from .app import main
from .parser import build_parser
from .registry import COMMANDS

__all__ = [
    "COMMANDS",
    "EXIT_APPROVAL_REQUIRED",
    "EXIT_BASELINE_INCOMPATIBLE",
    "EXIT_CHECK_FAILED",
    "EXIT_INVALID_POLICY",
    "EXIT_OK",
    "EXIT_UNAVAILABLE",
    "build_parser",
    "main",
]
