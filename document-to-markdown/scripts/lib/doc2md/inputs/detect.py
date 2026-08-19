"""Deterministic media detection and subset validation over bounded bytes."""

from __future__ import annotations

import mimetypes
import re
from pathlib import PurePosixPath

from doc2md.core import SourceDocument
from doc2md.inputs.archive import inspect_zip
from doc2md.inputs.models import (
    ArchiveInspection,
    InputErrorCode,
    InputLimits,
    InputRefusal,
    InspectedSource,
    MediaDetection,
    RetryMeaning,
    SelectorValidation,
    SubsetRequest,
)

_HTML_CHARSET = re.compile(
    rb"""<meta\b[^>]*\bcharset\s*=\s*["']?\s*([A-Za-z0-9._-]+)""",
    re.IGNORECASE,
)
_TEXT_MEDIA_TYPES = {
    "application/json",
    "application/xml",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/plain",
    "text/xml",
}
_PAGE_MEDIA_TYPES = {"application/pdf"}
_SLIDE_MEDIA_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
}
_SHEET_MEDIA_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}
_ARCHIVE_MEDIA_TYPES = {
    "application/epub+zip",
    "application/zip",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _filename_media_type(display_name: str) -> str | None:
    media_type, _ = mimetypes.guess_type(display_name, strict=False)
    return media_type.lower() if media_type is not None else None


def _normalize_declared_media_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.split(";", 1)[0].strip().lower()
    if "/" not in normalized:
        raise InputRefusal(
            InputErrorCode.INVALID_INPUT,
            "declared media type is not a MIME type",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
        )
    return normalized


def _text_encoding(data: bytes, media_type: str) -> str | None:
    if media_type not in _TEXT_MEDIA_TYPES:
        return None
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if media_type == "text/html":
        match = _HTML_CHARSET.search(data[:8192])
        if match is not None:
            try:
                return match.group(1).decode("ascii").lower()
            except UnicodeDecodeError:
                return "unknown"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "unknown"
    return "utf-8"


def _looks_like_text(data: bytes) -> bool:
    sample = data[:8192]
    if b"\x00" in sample:
        return False
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            decoded = sample.decode("cp1252")
        except UnicodeDecodeError:
            return False
    if not decoded:
        return False
    visible = sum(
        character.isprintable() or character.isspace() for character in decoded
    )
    return visible / len(decoded) >= 0.9


def _detect_non_archive(data: bytes) -> tuple[str, tuple[str, ...]]:
    prefix = data[:8192]
    stripped = prefix.lstrip(b"\xef\xbb\xbf\x00\t\n\r ")
    lower = stripped.lower()
    signals: list[tuple[str, str]] = []
    pdf_index = data[:1024].find(b"%PDF-")
    if pdf_index >= 0:
        signals.append(("application/pdf", f"pdf-header@{pdf_index}"))
    if lower.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        signals.append(("text/html", "html-root"))
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        signals.append(("application/x-ole-storage", "ole-compound-header"))
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        signals.append(("image/png", "png-signature"))
    if data.startswith(b"\xff\xd8\xff"):
        signals.append(("image/jpeg", "jpeg-signature"))
    if data.startswith((b"GIF87a", b"GIF89a")):
        signals.append(("image/gif", "gif-signature"))
    if data.startswith((b"II*\x00", b"MM\x00*")):
        signals.append(("image/tiff", "tiff-signature"))
    if lower.startswith(b"{") or lower.startswith(b"["):
        signals.append(("application/json", "json-leading-token"))
    if lower.startswith(b"<?xml"):
        signals.append(("application/xml", "xml-declaration"))
    if lower.startswith(b"{\\rtf"):
        signals.append(("application/rtf", "rtf-header"))

    media_types = {media_type for media_type, _ in signals}
    if len(media_types) > 1:
        raise InputRefusal(
            InputErrorCode.UNSAFE_INPUT,
            "input has conflicting active format signatures",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"signals": [signal for _, signal in signals]},
        )
    if signals:
        media_type = signals[0][0]
        return media_type, tuple(signal for _, signal in signals)
    if _looks_like_text(data):
        return "text/plain", ("printable-text",)
    raise InputRefusal(
        InputErrorCode.UNSUPPORTED_FORMAT,
        "input format is not recognized by the bounded detector",
        retry=RetryMeaning.AFTER_CAPABILITY_INSTALL,
    )


def _validate_entry_selector(name: str) -> str:
    portable = name.replace("\\", "/")
    path = PurePosixPath(portable)
    if (
        path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
        or "\x00" in name
    ):
        raise InputRefusal(
            InputErrorCode.INVALID_INPUT,
            "requested archive entry escapes the archive root",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"entry": name},
        )
    return path.as_posix()


def _validate_selectors(
    request: SubsetRequest,
    media_type: str,
    limits: InputLimits,
    archive: ArchiveInspection | None,
) -> SelectorValidation:
    validated: list[str] = []
    deferred: list[str] = []
    if request.pages:
        if media_type not in _PAGE_MEDIA_TYPES:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "page selection is not valid for the detected format",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"media_type": media_type},
            )
        if max(request.pages) > limits.max_requested_pages:
            raise InputRefusal(
                InputErrorCode.RESOURCE_EXHAUSTED,
                "requested page exceeds the configured selector limit",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={
                    "requested": max(request.pages),
                    "limit": limits.max_requested_pages,
                },
            )
        deferred.append("page-existence")
    if request.slides:
        if media_type not in _SLIDE_MEDIA_TYPES:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "slide selection is not valid for the detected format",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"media_type": media_type},
            )
        assert archive is not None
        slide_names = {
            entry.name
            for entry in archive.entries
            if re.fullmatch(r"ppt/slides/slide[1-9][0-9]*\.xml", entry.name)
        }
        available = len(slide_names)
        missing = [value for value in request.slides if value > available]
        if missing:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "requested slide does not exist in the detected package",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"missing": missing, "available_count": available},
            )
        validated.append("slide-existence")
    if request.sheets:
        if media_type not in _SHEET_MEDIA_TYPES:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "sheet selection is not valid for the detected format",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"media_type": media_type},
            )
        deferred.append("sheet-name-existence")
    if request.entries:
        if media_type not in _ARCHIVE_MEDIA_TYPES or archive is None:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "archive-entry selection is not valid for the detected format",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"media_type": media_type},
            )
        available_names = {entry.name for entry in archive.entries}
        normalized = [_validate_entry_selector(name) for name in request.entries]
        missing_entries = sorted(set(normalized).difference(available_names))
        if missing_entries:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "requested archive entry does not exist",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"missing": missing_entries},
            )
        validated.append("archive-entry-existence")
    return SelectorValidation(
        request=request,
        validated=tuple(validated),
        deferred=tuple(deferred),
    )


def inspect_bytes(
    data: bytes,
    *,
    display_name: str = "<bytes>",
    declared_media_type: str | None = None,
    selectors: SubsetRequest | None = None,
    limits: InputLimits | None = None,
) -> InspectedSource:
    """Inspect bounded bytes without invoking a document parser or active content."""

    authority = limits if limits is not None else InputLimits()
    request = selectors if selectors is not None else SubsetRequest()
    if not isinstance(data, bytes):
        raise TypeError("input data must be bytes")
    if not data:
        raise InputRefusal(
            InputErrorCode.INVALID_INPUT,
            "input stream is empty",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
        )
    if len(data) > authority.max_source_bytes:
        raise InputRefusal(
            InputErrorCode.RESOURCE_EXHAUSTED,
            "source bytes exceed the configured limit",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"observed": len(data), "limit": authority.max_source_bytes},
        )
    normalized_declared = _normalize_declared_media_type(declared_media_type)

    archive: ArchiveInspection | None = None
    signals: tuple[str, ...]
    if data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        media_type, archive = inspect_zip(data, authority)
        signals = ("zip-central-directory",)
    else:
        media_type, signals = _detect_non_archive(data)

    if media_type == "application/pdf":
        if b"%%EOF" not in data[-4096:]:
            raise InputRefusal(
                InputErrorCode.CORRUPT_INPUT,
                "PDF is truncated or lacks an end-of-file marker",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )
        if b"/Encrypt" in data[-65536:]:
            raise InputRefusal(
                InputErrorCode.ENCRYPTED_INPUT,
                "PDF is encrypted and requires a credential",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )

    filename_media_type = _filename_media_type(display_name)
    declared_values = {
        value
        for value in (normalized_declared, filename_media_type)
        if value is not None
    }
    disagreement = any(value != media_type for value in declared_values)
    active_content = archive.active_content if archive is not None else ()
    detection = MediaDetection(
        media_type=media_type,
        signals=signals,
        declared_media_type=normalized_declared,
        filename_media_type=filename_media_type,
        disagreement=disagreement,
        encoding=_text_encoding(data, media_type),
        active_content=active_content,
    )
    selector_validation = _validate_selectors(
        request,
        media_type,
        authority,
        archive,
    )
    return InspectedSource(
        source=SourceDocument.from_bytes(
            data,
            media_type=media_type,
            display_name=display_name,
        ),
        detection=detection,
        selectors=selector_validation,
        archive=archive,
    )
