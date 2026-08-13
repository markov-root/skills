"""Task-agnostic debate engine: backends, the IDEA/Delphi loop, artifacts, validation.

Knows about debaters, rounds, blinding, retries and run artifacts — NOT about any specific
question domain. Task-specific content (prompts, input bundle, output schema, aggregate step)
is supplied by a DebateTask (see debate/tasks/base.py). The engine/task split is ADR-0002.
"""
