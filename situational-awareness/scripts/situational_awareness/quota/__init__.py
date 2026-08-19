"""Quota-awareness — the subscription rate-limit dimension of situational-awarenessness.

Port of usage-check (ADR-0005): reader (reads ~/.claude/usage/*) → analysis
(burn/eta/forecast/marks/action/binding) → models (QuotaReading) → cli. Fixes the
12 bugs in docs/lessons/0003 rather than replicating them.
"""
