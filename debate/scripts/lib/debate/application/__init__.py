"""Application use-case boundary for incremental CLI/runtime migration."""

from debate.application.resolve_plan import (
    ResolvedExecution,
    execution_from_plan,
    resolve_execution_plan,
)

__all__ = ["ResolvedExecution", "execution_from_plan", "resolve_execution_plan"]
