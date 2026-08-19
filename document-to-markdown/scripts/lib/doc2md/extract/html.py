"""Deterministic main-content extraction for HTML documents."""

from __future__ import annotations

from doc2md.core.models import (
    AdapterCapabilities,
    AttemptContext,
    Candidate,
    ProvenanceTier,
    SourceDocument,
    TransformationRecord,
)
from doc2md.extract.plaintext import decode_text
from doc2md.extract.textnorm import (
    TEXTNORM_VERSION,
    collapse_blank_lines,
    strip_invisibles,
)

THIN_THRESHOLD = 800

_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_METADATA_FIELDS = ("title", "author", "date", "sitename", "hostname")


def _real_character_count(value: str | None) -> int:
    """Count non-whitespace characters in an optional extraction result."""

    return sum(not character.isspace() for character in value or "")


class HtmlExtractor:
    """Extract article-like Markdown from HTML without network or reconstruction."""

    ADAPTER_ID = "html"
    VERSION = "1"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_id=self.ADAPTER_ID,
            version=self.VERSION,
            media_types=_MEDIA_TYPES,
            requires_network=False,
            external_processing=False,
            paid=False,
            generative=False,
        )

    def extract(self, source: SourceDocument, context: AttemptContext) -> Candidate:
        context.raise_if_stopped()
        try:
            import trafilatura
        except ImportError as error:
            raise RuntimeError("trafilatura is required for HTML extraction") from error

        html_str, decode_diagnostics = decode_text(source.data)
        version = str(trafilatura.__version__)
        primary_result = trafilatura.extract(
            html_str,
            output_format="markdown",
            include_links=True,
            include_images=False,
            include_tables=True,
            include_comments=False,
            favor_recall=True,
        )
        primary = primary_result if isinstance(primary_result, str) else None

        metadata: dict[str, str] = {"extractor": f"trafilatura {version}"}
        extracted_metadata = trafilatura.extract_metadata(html_str)
        if extracted_metadata is not None:
            for field in _METADATA_FIELDS:
                value = getattr(extracted_metadata, field, None)
                if value is not None and (text := str(value).strip()):
                    metadata[field] = text

        chosen = primary
        if primary is None or len(primary) < THIN_THRESHOLD:
            try:
                import readability  # type: ignore[import-untyped]
            except ImportError as error:
                raise RuntimeError(
                    "readability-lxml is required for thin HTML rescue"
                ) from error

            document = readability.Document(html_str)
            summary_html = document.summary()
            rescue_result = trafilatura.extract(
                summary_html,
                output_format="markdown",
                include_links=True,
                include_tables=True,
            )
            rescue = rescue_result if isinstance(rescue_result, str) else None
            if _real_character_count(rescue) > _real_character_count(primary):
                chosen = rescue
                metadata["extractor"] = f"readability-lxml + trafilatura {version}"

        if _real_character_count(chosen) == 0:
            raise ValueError("no main content extracted")

        body = collapse_blank_lines(strip_invisibles(chosen or "")).strip()
        if not body:
            raise ValueError("no main content extracted")

        diagnostics = [metadata["extractor"], *decode_diagnostics]
        if len(body) < THIN_THRESHOLD:
            diagnostics.append(f"thin: {len(body)} chars")

        context.raise_if_stopped()
        return Candidate(
            adapter_id=self.ADAPTER_ID,
            source_sha256=source.sha256,
            markdown=body + "\n",
            provenance_tier=ProvenanceTier.DETERMINISTIC_EXTRACTION,
            diagnostics=tuple(diagnostics),
            transformations=(
                TransformationRecord(
                    operation="strip-invisibles",
                    version=TEXTNORM_VERSION,
                    lossy=False,
                ),
            ),
            metadata=metadata,
        )
