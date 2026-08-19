"""Static source acquisition helpers."""

from doc2md.fetch.canonical import canonicalize
from doc2md.fetch.http import StaticHttpFetcher

__all__ = ["StaticHttpFetcher", "canonicalize"]
