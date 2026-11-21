"""Every command leaf, implemented or declared. This module is the only command catalog."""
from __future__ import annotations

from ..console import Effects, declare
from . import claims, components, deck, delivery, doctor, explain, lesson, library, schema, script, talk, validate, visual  # noqa: F401 — implemented leaves register on import

R = Effects()  # read-only
W = lambda d: Effects(writes=True, description=d)  # noqa: E731

# Declared surface (specification §10). Each exits 3 until its task lands.
