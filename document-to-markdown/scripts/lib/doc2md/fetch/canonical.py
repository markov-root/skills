"""Pure URL canonicalization for source acquisition."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def canonicalize(url: str) -> str:
    """Return the best fetchable form of *url* without its fragment."""

    parsed = urlsplit(url)
    netloc = parsed.netloc
    path = parsed.path
    parts = path.lstrip("/").split("/")
    if netloc.lower() == "github.com" and len(parts) >= 4 and parts[2] == "blob":
        netloc = "raw.githubusercontent.com"
        path = "/" + "/".join((*parts[:2], *parts[3:]))
    return urlunsplit((parsed.scheme, netloc, path, parsed.query, ""))
