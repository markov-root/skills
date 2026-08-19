"""DOCX extractor using only the standard library (zipfile + XML).

Office Open XML is a ZIP of XML parts. A deterministic, dependency-free reader is enough to
recover the visible reading order — paragraphs, headings, list items, and hyperlinks — which is
exactly what the reference pipelines do (CoP Dataset extracts DOCX with ``zipfile`` + regex, no
``python-docx``). Macros, embedded objects, and external relationships are treated as untrusted
and never executed or followed for their side effects; only hyperlink *targets* are read as text.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

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
    {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DC = "{http://purl.org/dc/elements/1.1/}"

_ZIP_MAGIC = b"PK\x03\x04"

# Untrusted-input guards (see docs/context/input-boundary-threat-model.md). OOXML parts never
# legitimately declare a DTD, so a DOCTYPE/ENTITY is either malformed or an XXE / billion-laughs
# attack; reject rather than parse. The size cap bounds a zip-bomb part before decompression.
_MAX_PART_BYTES = 64 * 1024 * 1024


def _safe_read(archive: zipfile.ZipFile, name: str) -> bytes:
    """Read one archive part with a decompressed-size cap and XML-entity rejection."""

    info = archive.getinfo(name)
    if info.file_size > _MAX_PART_BYTES:
        raise ValueError(
            f"DOCX part {name} exceeds the {_MAX_PART_BYTES}-byte safety cap"
        )
    data = archive.read(name)
    lowered = data.lstrip()[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError(
            f"DOCX part {name} declares a DTD/entity and is rejected as untrusted"
        )
    return data


def _safe_fromstring(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def _heading_level(pstyle: str | None) -> int | None:
    """Return a Markdown heading level from a paragraph style id, or None for body text."""

    if not pstyle:
        return None
    match = re.match(r"(?i)heading([1-6])", pstyle)
    if match:
        return int(match.group(1))
    if pstyle.lower() in {"title"}:
        return 1
    return None


def _load_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    """Map relationship ids to external hyperlink targets, if the rels part exists."""

    try:
        raw = _safe_read(archive, "word/_rels/document.xml.rels")
    except KeyError:
        return {}
    targets: dict[str, str] = {}
    for rel in _safe_fromstring(raw):
        rid = rel.get("Id")
        target = rel.get("Target")
        mode = rel.get("TargetMode")
        if rid and target and mode == "External":
            targets[rid] = target
    return targets


def _run_text(node: ET.Element) -> str:
    """Concatenate the visible text of a run, rendering tab elements as tabs."""

    parts: list[str] = []
    for child in node.iter():
        if child.tag == f"{_W}t":
            parts.append(child.text or "")
        elif child.tag == f"{_W}tab":
            parts.append("\t")
    return "".join(parts)


def _paragraph_text(paragraph: ET.Element, rels: dict[str, str]) -> str:
    """Render a paragraph to inline Markdown in document order, resolving hyperlinks.

    Walks the paragraph's direct children so plain runs and hyperlink runs interleave correctly
    (an earlier version dropped the text surrounding a hyperlink).
    """

    parts: list[str] = []
    for child in paragraph:
        tag = child.tag
        if tag == f"{_W}hyperlink":
            text = _run_text(child)
            url = rels.get(child.get(f"{_R}id") or "")
            parts.append(f"[{text}]({url})" if url and text else text)
        elif tag == f"{_W}r":
            parts.append(_run_text(child))
    return "".join(parts).strip()


def _extract_title(archive: zipfile.ZipFile) -> str | None:
    try:
        raw = _safe_read(archive, "docProps/core.xml")
    except KeyError:
        return None
    node = _safe_fromstring(raw).find(f"{_DC}title")
    if node is not None and node.text and node.text.strip():
        return node.text.strip()
    return None


def _render_document(document_xml: bytes, rels: dict[str, str]) -> str:
    body = _safe_fromstring(document_xml).find(f"{_W}body")
    if body is None:
        return ""
    lines: list[str] = []
    for paragraph in body.findall(f"{_W}p"):
        pstyle_node = paragraph.find(f"{_W}pPr/{_W}pStyle")
        pstyle = pstyle_node.get(f"{_W}val") if pstyle_node is not None else None
        is_list = paragraph.find(f"{_W}pPr/{_W}numPr") is not None
        text = _paragraph_text(paragraph, rels)
        if not text:
            lines.append("")
            continue
        level = _heading_level(pstyle)
        if level is not None:
            lines.append(f"{'#' * level} {text}")
        elif is_list:
            lines.append(f"- {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


class DocxExtractor:
    """Emit DOCX visible reading order as an extractive Markdown candidate."""

    ADAPTER_ID = "docx"
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
        if not source.data.startswith(_ZIP_MAGIC):
            raise ValueError("not an Office Open XML (ZIP) document")
        with zipfile.ZipFile(BytesIO(source.data)) as archive:
            try:
                document_xml = _safe_read(archive, "word/document.xml")
            except KeyError as error:
                raise ValueError("DOCX is missing word/document.xml") from error
            rels = _load_relationships(archive)
            title = _extract_title(archive)
        context.raise_if_stopped()
        body = collapse_blank_lines(
            strip_invisibles(_render_document(document_xml, rels))
        ).strip()
        if not body:
            raise ValueError("no extractable text in DOCX body")
        metadata = {"extractor": "zipfile+xml (stdlib)"}
        if title:
            metadata["title"] = title
        return Candidate(
            adapter_id=self.ADAPTER_ID,
            source_sha256=source.sha256,
            markdown=body + "\n",
            provenance_tier=ProvenanceTier.DETERMINISTIC_EXTRACTION,
            diagnostics=("zipfile+xml (stdlib)",),
            transformations=(
                TransformationRecord(
                    operation="strip-invisibles",
                    version=TEXTNORM_VERSION,
                    lossy=False,
                ),
            ),
            metadata=metadata,
        )
