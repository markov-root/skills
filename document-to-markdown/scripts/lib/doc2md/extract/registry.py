"""Build the set of certified extractors available in the current environment.

Each adapter is certified against a tiny in-process fixture before it may route (see
``core/conformance.py``). Adapters whose optional backend is missing, or that fail certification,
are reported as unavailable with a reason rather than silently dropped — this is what ``doctor``
surfaces. The Apache-2.0 core always has the two dependency-free adapters (plaintext, docx); the
HTML, PDF, and Pandoc adapters require their optional backends.
"""

from __future__ import annotations

import io
import shutil
import zipfile
from dataclasses import dataclass, field

from doc2md.core.conformance import CertifiedExtractor, certify_extractor
from doc2md.core.models import ConversionPolicy, SourceDocument
from doc2md.core.ports import ExtractorPort
from doc2md.extract.office import DocxExtractor
from doc2md.extract.plaintext import PlaintextExtractor

_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@dataclass(frozen=True, slots=True)
class RegistryReport:
    """Certified adapters plus the reason each unavailable adapter was excluded."""

    extractors: tuple[CertifiedExtractor, ...]
    unavailable: tuple[dict[str, str], ...] = field(default_factory=tuple)


def _text_fixture() -> SourceDocument:
    return SourceDocument.from_bytes(
        b"# Fixture\n\nHello world fixture content.\n",
        media_type="text/markdown",
        display_name="fixture.md",
    )


def _docx_fixture() -> SourceDocument:
    document = (
        f'<?xml version="1.0"?><w:document xmlns:w="{_W}"><w:body>'
        "<w:p><w:r><w:t>Fixture paragraph.</w:t></w:r></w:p>"
        "</w:body></w:document>"
    ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        archive.writestr("word/document.xml", document)
    return SourceDocument.from_bytes(
        buffer.getvalue(), media_type=_DOCX_MEDIA, display_name="fixture.docx"
    )


def _html_fixture() -> SourceDocument:
    body = (
        "<html><head><title>Fixture</title></head><body>"
        "<h1>Fixture Heading</h1><p>"
        + ("This is a sufficiently long paragraph of real content. " * 24)
        + "</p></body></html>"
    ).encode()
    return SourceDocument.from_bytes(
        body, media_type="text/html", display_name="fixture.html"
    )


def _pdf_fixture() -> SourceDocument:
    from typing import Any

    import pymupdf

    document: Any = pymupdf.open()  # type: ignore[no-untyped-call]
    page = document.new_page()
    page.insert_text((72, 72), "Fixture PDF text content for certification.")
    data: bytes = document.tobytes()
    document.close()
    return SourceDocument.from_bytes(
        data, media_type="application/pdf", display_name="fixture.pdf"
    )


def _pandoc_fixture() -> SourceDocument:
    return SourceDocument.from_bytes(
        b"Fixture Title\n=============\n\nFixture body paragraph.\n",
        media_type="text/x-rst",
        display_name="fixture.rst",
    )


def _load_html_adapter() -> ExtractorPort:
    import trafilatura  # noqa: F401  (probe the optional backend)

    from doc2md.extract.html import HtmlExtractor

    return HtmlExtractor()


def _load_pdf_adapter() -> ExtractorPort:
    import pymupdf4llm  # type: ignore[import-untyped]  # noqa: F401

    from doc2md.extract.pdf import PdfExtractor

    return PdfExtractor()


def _load_pandoc_adapter() -> ExtractorPort:
    if shutil.which("pandoc") is None:
        raise RuntimeError("pandoc not installed")

    from doc2md.extract.pandoc_adapter import PandocExtractor

    return PandocExtractor()


def build_registry(policy: ConversionPolicy | None = None) -> RegistryReport:
    """Certify every adapter whose backend is present; report the rest as unavailable."""

    authority = policy if policy is not None else ConversionPolicy()
    plan: list[tuple[str, ExtractorPort, SourceDocument]] = [
        ("plaintext", PlaintextExtractor(), _text_fixture()),
        ("docx", DocxExtractor(), _docx_fixture()),
    ]
    optional: list[tuple[str, object]] = [
        ("html", _load_html_adapter),
        ("pdf", _load_pdf_adapter),
        ("pandoc", _load_pandoc_adapter),
    ]
    unavailable: list[dict[str, str]] = []
    for name, loader in optional:
        try:
            adapter = loader()  # type: ignore[operator]
        except Exception as error:  # backend or adapter import failed
            unavailable.append(
                {"adapter": name, "reason": f"{type(error).__name__}: {error}"}
            )
            continue
        if name == "html":
            fixture = _html_fixture()
        elif name == "pdf":
            fixture = _pdf_fixture()
        else:
            fixture = _pandoc_fixture()
        plan.append((name, adapter, fixture))

    certified: list[CertifiedExtractor] = []
    for name, adapter, fixture in plan:
        try:
            certified.append(
                certify_extractor(adapter, fixture=fixture, policy=authority)
            )
        except Exception as error:
            unavailable.append(
                {"adapter": name, "reason": f"certification failed: {error}"}
            )
    return RegistryReport(extractors=tuple(certified), unavailable=tuple(unavailable))
