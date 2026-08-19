"""Born-digital PDF extraction with a bounded local fallback."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from collections.abc import Mapping
from typing import Any

from doc2md.core.models import (
    AdapterCapabilities,
    AttemptContext,
    Candidate,
    ProvenanceTier,
    SourceDocument,
    TransformationRecord,
)
from doc2md.extract.pdf_preflight import preflight
from doc2md.extract.textnorm import (
    TEXTNORM_VERSION,
    collapse_blank_lines,
    strip_invisibles,
)

_MEDIA_TYPES = frozenset({"application/pdf"})
_PDF_MAGIC = b"%PDF-"
_PYMUPDF_MAX_MB = 10.0
_PYMUPDF_MAX_BYTES = int(_PYMUPDF_MAX_MB * 1024 * 1024)
_PDFTOTEXT_TIMEOUT_SECONDS = 20.0

_OMITTED_PICTURE = re.compile(
    r"^.*==>.*intentionally omitted.*<==.*$",
    flags=re.IGNORECASE,
)
# Remove the whole Start..End span wherever it sits — the markers are not always on their own
# lines (pymupdf4llm often glues the End marker to the garbled picture text, e.g.
# "ANTHROP\C<br><!-- End of picture text -->"), so neither marker is anchored to line start.
_PICTURE_TEXT_BLOCK = re.compile(
    r"<!--\s*Start of picture text\s*-->.*?<!--\s*End of picture text\s*-->[ \t]*",
    flags=re.IGNORECASE | re.DOTALL,
)
_PICTURE_TEXT_COMMENT = re.compile(
    r"^[ \t]*<!--[^\n]*picture text[^\n]*-->[ \t]*(?:\n|$)",
    flags=re.IGNORECASE | re.MULTILINE,
)
_BARE_PAGE_NUMBER = re.compile(r"^\s*\d+\s*$")
_DIGITS = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")


def _clean_pymupdf_markdown(markdown: str) -> str:
    joined = "\n".join(
        line for line in markdown.splitlines() if not _OMITTED_PICTURE.match(line)
    )
    joined = _PICTURE_TEXT_BLOCK.sub("", joined)
    joined = _PICTURE_TEXT_COMMENT.sub("", joined)
    return collapse_blank_lines(strip_invisibles(joined)).strip()


def _masked_short_line(line: str) -> str | None:
    normalized = _WHITESPACE.sub(" ", line).strip()
    if not normalized or len(normalized) >= 80:
        return None
    return _DIGITS.sub("#", normalized)


def _clean_pdftotext(text: str) -> tuple[str, int]:
    raw_pages = text.split("\x0c")
    if raw_pages and not raw_pages[-1].strip():
        raw_pages.pop()
    pages = raw_pages or [""]

    page_forms: list[set[str]] = []
    for page in pages:
        forms = {
            masked
            for line in page.splitlines()
            if (masked := _masked_short_line(line)) is not None
            and not _BARE_PAGE_NUMBER.match(line)
        }
        page_forms.append(forms)
    occurrences = Counter(form for forms in page_forms for form in forms)
    running_forms = {
        form
        for form, count in occurrences.items()
        if count >= 2 and count * 2 >= len(pages)
    }

    removed = 0
    cleaned_pages: list[str] = []
    for page in pages:
        kept_lines: list[str] = []
        for line in page.splitlines():
            masked = _masked_short_line(line)
            if _BARE_PAGE_NUMBER.match(line) or (
                masked is not None and masked in running_forms
            ):
                removed += 1
                continue
            kept_lines.append(line.rstrip())
        cleaned_pages.append("\n".join(kept_lines).strip())

    cleaned = "\n\n".join(page for page in cleaned_pages if page)
    return collapse_blank_lines(strip_invisibles(cleaned)).strip(), removed


def _remaining_timeout(context: AttemptContext) -> float:
    remaining = context.deadline - context.clock()
    if remaining <= 0:
        context.raise_if_stopped()
    return min(_PDFTOTEXT_TIMEOUT_SECONDS, remaining)


def _extract_with_pdftotext(
    data: bytes,
    context: AttemptContext,
) -> tuple[str, int]:
    completed = subprocess.run(
        ["pdftotext", "-layout", "-", "-"],
        input=data,
        capture_output=True,
        timeout=_remaining_timeout(context),
        check=False,
    )
    return _clean_pdftotext(completed.stdout.decode("utf-8", errors="replace"))


def _normalize_anchor(text: str) -> str:
    return _WHITESPACE.sub(" ", strip_invisibles(text)).strip()


def _extract_hyperlinks(pymupdf: Any, data: bytes) -> list[tuple[str, str]]:
    hyperlinks: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for page in document:
            for link in page.get_links():
                if not isinstance(link, Mapping):
                    continue
                uri = link.get("uri")
                rectangle = link.get("from")
                if not isinstance(uri, str) or not uri or rectangle is None:
                    continue
                anchor = _normalize_anchor(page.get_textbox(rectangle))
                pair = (anchor, uri)
                if not anchor or pair in seen:
                    continue
                seen.add(pair)
                hyperlinks.append(pair)
    return hyperlinks


class PdfExtractor:
    """Emit a born-digital PDF text layer as an extractive Markdown candidate."""

    ADAPTER_ID = "pdf"
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
        if not source.data.startswith(_PDF_MAGIC):
            raise ValueError("not a PDF")
        pre = preflight(source.data)
        if pre.encrypted:
            raise ValueError("encrypted PDF; a password is required")
        try:
            import pymupdf
            import pymupdf4llm  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError("pymupdf/pymupdf4llm not installed") from error

        diagnostics = [f"preflight: {pre.page_count}p coverage={pre.text_coverage:.2f}"]
        transformations = [
            TransformationRecord(
                operation="strip-invisibles",
                version=TEXTNORM_VERSION,
                lossy=False,
            )
        ]
        markdown = ""
        extractor = ""

        if len(source.data) > _PYMUPDF_MAX_BYTES:
            diagnostics.append(
                f"pymupdf4llm skipped: source exceeds {_PYMUPDF_MAX_MB:g} MiB"
            )
        else:
            try:
                with pymupdf.open(  # type: ignore[no-untyped-call]
                    stream=source.data,
                    filetype="pdf",
                ) as document:
                    primary = pymupdf4llm.to_markdown(
                        document,
                        ignore_images=True,
                        ignore_graphics=True,
                        show_progress=False,
                    )
                if not isinstance(primary, str):
                    raise TypeError("pymupdf4llm returned non-text output")
                markdown = _clean_pymupdf_markdown(primary)
                extractor = f"pymupdf4llm {pymupdf4llm.__version__}"
                if not markdown:
                    diagnostics.append(
                        "pymupdf4llm produced no text; used pdftotext fallback"
                    )
            except Exception:
                diagnostics.append("pymupdf4llm failed; used pdftotext fallback")

        context.raise_if_stopped()
        if not markdown:
            markdown, removed = _extract_with_pdftotext(source.data, context)
            extractor = "pdftotext -layout (poppler)"
            transformations.append(
                TransformationRecord(
                    operation="remove-running-headers",
                    version="1",
                    lossy=True,
                    affected_units=removed,
                )
            )
            context.raise_if_stopped()

        if not markdown:
            raise ValueError("no extractable text layer; OCR required")

        hyperlinks = _extract_hyperlinks(pymupdf, source.data)
        if hyperlinks:
            link_lines = "\n".join(f"- [{text}]({uri})" for text, uri in hyperlinks)
            markdown = (
                f"{markdown}\n\n"
                "## Hyperlinks (extracted from PDF link annotations)\n\n"
                f"{link_lines}"
            )

        diagnostics.insert(0, extractor)
        metadata = {
            "extractor": extractor,
            "hyperlinks": str(len(hyperlinks)),
            "pages": str(pre.page_count),
            "text_coverage": f"{pre.text_coverage:.2f}",
        }
        if pre.doc_info_date:
            metadata.setdefault("date", pre.doc_info_date)
        return Candidate(
            adapter_id=self.ADAPTER_ID,
            source_sha256=source.sha256,
            markdown=markdown.strip() + "\n",
            provenance_tier=ProvenanceTier.DETERMINISTIC_EXTRACTION,
            diagnostics=tuple(diagnostics),
            transformations=tuple(transformations),
            metadata=metadata,
        )
