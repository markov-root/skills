"""Bounded static HTTP acquisition."""

from __future__ import annotations

from doc2md.core.models import SourceDocument
from doc2md.fetch.canonical import canonicalize


class StaticHttpFetcher:
    """Fetch one URL into an owned, size-bounded source document."""

    def __init__(
        self,
        user_agent: str = "doc2md/0.x (+local)",
        max_bytes: int = 25 * 1024 * 1024,
        timeout: float = 20.0,
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self.timeout = timeout

    def fetch_url(self, url: str) -> SourceDocument:
        """Fetch *url* while enforcing the configured response-size ceiling."""

        canonical_url = canonicalize(url)
        try:
            import requests
        except ImportError as error:
            raise RuntimeError(
                "requests is required for static HTTP fetching"
            ) from error

        try:
            with requests.get(
                canonical_url,
                headers={"User-Agent": self.user_agent},
                allow_redirects=True,
                stream=True,
                timeout=self.timeout,
            ) as response:
                status_code = response.status_code
                if not 200 <= status_code < 300:
                    raise ValueError(f"HTTP {status_code}")

                body = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(body) + len(chunk) > self.max_bytes:
                        raise ValueError(
                            f"response exceeds maximum size of {self.max_bytes} bytes"
                        )
                    body.extend(chunk)

                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )
        except requests.Timeout as error:
            raise ValueError("HTTP request timed out") from error
        except requests.ConnectionError as error:
            raise ValueError(f"HTTP connection error: {error}") from error

        media_type = content_type.split(";", 1)[0].strip()
        if not media_type:
            media_type = "application/octet-stream"
        return SourceDocument.from_bytes(
            bytes(body),
            media_type=media_type,
            display_name=url,
        )
