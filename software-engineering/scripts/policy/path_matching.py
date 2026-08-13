"""Shared GitWildMatch semantics for every manifest path consumer."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from pathspec.patterns.gitwildmatch import GitWildMatchPattern


@lru_cache(maxsize=512)
def _compile(patterns: tuple[str, ...]) -> tuple[tuple[str, GitWildMatchPattern], ...]:
    return tuple((raw, GitWildMatchPattern(raw)) for raw in patterns)


def matching_pattern(path: str, patterns: Sequence[str]) -> str | None:
    """Return the effective positive pattern for *path*, honoring ordered exclusions."""
    included = False
    cause: str | None = None
    for raw, pattern in _compile(tuple(patterns)):
        if pattern.include is None or pattern.match_file(path) is None:
            continue
        included = pattern.include
        cause = raw if included else None
    return cause if included else None


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    """Return whether *path* is included by the ordered GitWildMatch patterns."""
    return matching_pattern(path, patterns) is not None
