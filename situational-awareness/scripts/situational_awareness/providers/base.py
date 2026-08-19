"""Provider contract. A provider does exactly two things:
   locate(session) -> transcript Path (or None)
   read(path)      -> Raw   (last-turn prompt tokens, model, maybe window)

Keep providers dumb: no ladder logic, no window defaults (except a window the
transcript states authoritatively). Core + config own everything else.
"""

from __future__ import annotations

import abc
from pathlib import Path

from situational_awareness.core import Raw


class Provider(abc.ABC):
    name: str

    @abc.abstractmethod
    def locate(self, session: str | None) -> Path | None:
        """Resolve a session id (or None/"current") to a transcript path."""

    @abc.abstractmethod
    def read(self, path: Path) -> Raw:
        """Extract the latest context occupancy from a transcript."""

    def resolve_session_id(self, session: str | None, path: Path) -> str:
        """Human-facing id for output; providers may override."""
        return session or path.stem

    def list_recent(self, max_age_s: int, limit: int) -> list[Path]:
        """Transcripts touched within max_age_s, newest first (for fleet view).
        Default: none — providers that can enumerate override this."""
        return []
