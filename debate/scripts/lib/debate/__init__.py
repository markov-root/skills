"""LLM-Expert-Debate: a task-agnostic, cross-vendor multi-model debate engine.

The engine runs independent-propose -> blinded-critique -> revise -> (red-team -> respond) rounds
over a pluggable panel of LLM backends, then hands the final field to a task-supplied
aggregate() step. Resumable, blinded, and recorded to disk for replay.
"""

__version__ = "0.0.1"
