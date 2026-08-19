"""Bounded structural preflight for PDF extraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pymupdf

_PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True, slots=True)
class PdfPreflight:
    """Structural PDF facts gathered without producing extracted content."""

    is_pdf: bool
    encrypted: bool
    page_count: int
    text_pages: int
    text_coverage: float
    producer: str | None
    doc_info_date: str | None
    needs_ocr: bool


def _metadata_value(metadata: Any, key: str) -> str | None:
    if not isinstance(metadata, Mapping):
        return None
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def preflight(data: bytes) -> PdfPreflight:
    """Probe PDF structure and text-layer coverage without extracting a candidate."""

    if not data.startswith(_PDF_MAGIC):
        return PdfPreflight(
            is_pdf=False,
            encrypted=False,
            page_count=0,
            text_pages=0,
            text_coverage=0.0,
            producer=None,
            doc_info_date=None,
            needs_ocr=False,
        )

    try:
        document: Any = pymupdf.open(  # type: ignore[no-untyped-call]
            stream=data,
            filetype="pdf",
        )
    except Exception:
        return PdfPreflight(
            is_pdf=True,
            encrypted=False,
            page_count=0,
            text_pages=0,
            text_coverage=0.0,
            producer=None,
            doc_info_date=None,
            needs_ocr=True,
        )

    with document:
        page_count = int(document.page_count)
        encrypted = bool(document.needs_pass or document.is_encrypted)
        metadata: Any = document.metadata
        producer = _metadata_value(metadata, "producer")
        doc_info_date = _metadata_value(
            metadata,
            "creationDate",
        ) or _metadata_value(metadata, "modDate")

        if encrypted:
            return PdfPreflight(
                is_pdf=True,
                encrypted=True,
                page_count=page_count,
                text_pages=0,
                text_coverage=0.0,
                producer=producer,
                doc_info_date=doc_info_date,
                needs_ocr=False,
            )

        text_pages = sum(
            1 for page in document if page.get_text("text").strip()
        )
        text_coverage = text_pages / page_count if page_count else 0.0
        return PdfPreflight(
            is_pdf=True,
            encrypted=False,
            page_count=page_count,
            text_pages=text_pages,
            text_coverage=text_coverage,
            producer=producer,
            doc_info_date=doc_info_date,
            needs_ocr=page_count > 0 and text_coverage < 0.10,
        )
