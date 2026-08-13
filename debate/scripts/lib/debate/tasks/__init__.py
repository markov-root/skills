"""Debate tasks. A task supplies the prompts, schemas, and aggregate() step;
the engine stays task-agnostic (ADR-0002). Subclass DebateTask (base.py)."""

from debate.tasks.base import DebateTask

__all__ = ["DebateTask"]
