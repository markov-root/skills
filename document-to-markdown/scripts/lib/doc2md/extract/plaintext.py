"""Plain-text and Markdown passthrough extractor.

Reference adapter: the smallest complete :class:`~doc2md.core.ports.ExtractorPort`. It decodes
bytes to text, strips invisibles, and normalizes blank lines. Markdown passes through verbatim
(minus invisibles); plain text is emitted unchanged as valid Markdown. No network, no paid or
generative processing, no source reconstruction.
"""

from __future__ import annotations

from doc2md.core.models import (
    AdapterCapabilities,
    AttemptContext,
    Candidate,
    ProvenanceTier,
    SourceDocument,
    TransformationRecord,
)
from doc2md.extract.textnorm import (
    TEXTNORM_VERSION,
    collapse_blank_lines,
    strip_invisibles,
)

_MEDIA_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
    }
)


def decode_text(data: bytes) -> tuple[str, tuple[str, ...]]:
    """Decode bytes to text with a deterministic fallback ladder.

    Returns the decoded text and a tuple of diagnostics naming any non-strict-UTF-8 decode.
    """

    try:
        return data.decode("utf-8"), ()
    except UnicodeDecodeError:
        pass
    # Windows-1252 is a strict superset of Latin-1 for the printable range and the most common
    # non-UTF-8 encoding for Western documents; decode is total (never raises).
    return data.decode("cp1252", errors="replace"), (
        "source was not valid UTF-8; decoded as cp1252 with replacement",
    )


class PlaintextExtractor:
    """Emit decoded, invisible-stripped text as an extractive Markdown candidate."""

    ADAPTER_ID = "plaintext"
    VERSION = "1"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_id=self.ADAPTER_ID,
            version=self.VERSION,
            media_types=_MEDIA_TYPES,
        )

    def extract(self, source: SourceDocument, context: AttemptContext) -> Candidate:
        context.raise_if_stopped()
        text, diagnostics = decode_text(source.data)
        context.raise_if_stopped()
        cleaned = collapse_blank_lines(strip_invisibles(text)).strip()
        markdown = cleaned + "\n" if cleaned else ""
        return Candidate(
            adapter_id=self.ADAPTER_ID,
            source_sha256=source.sha256,
            markdown=markdown,
            provenance_tier=ProvenanceTier.DETERMINISTIC_EXTRACTION,
            diagnostics=diagnostics,
            transformations=(
                TransformationRecord(
                    operation="strip-invisibles",
                    version=TEXTNORM_VERSION,
                    lossy=False,
                ),
            ),
        )
