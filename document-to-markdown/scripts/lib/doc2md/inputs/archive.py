"""Bounded ZIP-family inspection without archive extraction."""

from __future__ import annotations

import io
import re
import stat
import zipfile
from pathlib import PurePosixPath

from doc2md.inputs.models import (
    ArchiveEntry,
    ArchiveInspection,
    InputErrorCode,
    InputLimits,
    InputRefusal,
    RetryMeaning,
)

_OOXML_MARKERS = {
    "word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt/presentation.xml": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_EXTERNAL_RELATIONSHIP = re.compile(
    rb"""targetmode\s*=\s*["']external["']""",
    re.IGNORECASE,
)


def _normalized_member_name(name: str) -> str:
    if "\x00" in name:
        raise InputRefusal(
            InputErrorCode.UNSAFE_INPUT,
            "archive member contains a null byte",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
        )
    portable = name.replace("\\", "/")
    path = PurePosixPath(portable)
    if path.is_absolute() or ".." in path.parts:
        raise InputRefusal(
            InputErrorCode.UNSAFE_INPUT,
            "archive member escapes its logical root",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"member": name},
        )
    if path.parts and ":" in path.parts[0]:
        raise InputRefusal(
            InputErrorCode.UNSAFE_INPUT,
            "archive member uses an absolute drive path",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"member": name},
        )
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise InputRefusal(
            InputErrorCode.CORRUPT_INPUT,
            "archive member has no usable name",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
        )
    return normalized


def _member_kind(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _reject_special_member(info: zipfile.ZipInfo) -> None:
    mode = _member_kind(info)
    if mode == 0:
        return
    if stat.S_ISLNK(mode):
        kind = "symbolic link"
    elif any(
        predicate(mode)
        for predicate in (
            stat.S_ISCHR,
            stat.S_ISBLK,
            stat.S_ISFIFO,
            stat.S_ISSOCK,
        )
    ):
        kind = "device or special file"
    else:
        return
    raise InputRefusal(
        InputErrorCode.UNSAFE_INPUT,
        f"archive member is a {kind}",
        retry=RetryMeaning.AFTER_INPUT_CHANGE,
        details={"member": info.filename},
    )


def _active_content(names: set[str]) -> tuple[str, ...]:
    flags: set[str] = set()
    lower_names = {name.lower() for name in names}
    if any(name.endswith("vbaproject.bin") for name in lower_names):
        flags.add("macro-project")
    if any("/embeddings/" in f"/{name}" for name in lower_names):
        flags.add("embedded-file")
    if any("/externallinks/" in f"/{name}" for name in lower_names):
        flags.add("external-relationship")
    if any(
        name.endswith((".exe", ".dll", ".js", ".vbs", ".bat", ".cmd"))
        for name in lower_names
    ):
        flags.add("executable-member")
    if any(
        name.endswith((".zip", ".docx", ".pptx", ".xlsx", ".epub"))
        for name in lower_names
    ):
        flags.add("nested-container")
    return tuple(sorted(flags))


def inspect_zip(data: bytes, limits: InputLimits) -> tuple[str, ArchiveInspection]:
    """Inspect a ZIP-family central directory and return its actual media type."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise InputRefusal(
            InputErrorCode.CORRUPT_INPUT,
            "ZIP-family input has an invalid central directory",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
        ) from error

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_archive_entries:
            raise InputRefusal(
                InputErrorCode.RESOURCE_EXHAUSTED,
                "archive entry count exceeds the configured limit",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={
                    "observed": len(infos),
                    "limit": limits.max_archive_entries,
                },
            )

        entries: list[ArchiveEntry] = []
        names: set[str] = set()
        total_compressed = 0
        total_uncompressed = 0
        encrypted_members: list[str] = []
        for info in infos:
            normalized = _normalized_member_name(info.filename)
            if normalized in names:
                raise InputRefusal(
                    InputErrorCode.UNSAFE_INPUT,
                    "archive contains duplicate normalized member names",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                    details={"member": normalized},
                )
            names.add(normalized)
            _reject_special_member(info)
            if info.flag_bits & 0x1:
                encrypted_members.append(normalized)
            if info.file_size > limits.max_archive_entry_bytes:
                raise InputRefusal(
                    InputErrorCode.RESOURCE_EXHAUSTED,
                    "archive member exceeds the uncompressed size limit",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                    details={
                        "member": normalized,
                        "observed": info.file_size,
                        "limit": limits.max_archive_entry_bytes,
                    },
                )
            if info.file_size > 0:
                if info.compress_size == 0:
                    ratio = float("inf")
                else:
                    ratio = info.file_size / info.compress_size
                if ratio > limits.max_archive_ratio:
                    observed_ratio: float | str = (
                        "infinite" if ratio == float("inf") else ratio
                    )
                    raise InputRefusal(
                        InputErrorCode.RESOURCE_EXHAUSTED,
                        "archive member expansion ratio exceeds the configured limit",
                        retry=RetryMeaning.AFTER_INPUT_CHANGE,
                        details={
                            "member": normalized,
                            "observed_ratio": observed_ratio,
                            "limit": limits.max_archive_ratio,
                        },
                    )
            total_compressed += info.compress_size
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_archive_total_bytes:
                raise InputRefusal(
                    InputErrorCode.RESOURCE_EXHAUSTED,
                    "archive total uncompressed size exceeds the configured limit",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                    details={
                        "observed": total_uncompressed,
                        "limit": limits.max_archive_total_bytes,
                    },
                )
            entries.append(
                ArchiveEntry(
                    name=normalized,
                    compressed_bytes=info.compress_size,
                    uncompressed_bytes=info.file_size,
                    is_directory=info.is_dir(),
                )
            )

        if encrypted_members:
            raise InputRefusal(
                InputErrorCode.ENCRYPTED_INPUT,
                "archive contains encrypted members and requires a credential",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"members": encrypted_members[:20]},
            )

        media_type = "application/zip"
        for marker, candidate in _OOXML_MARKERS.items():
            if marker in names:
                media_type = candidate
                break
        if "mimetype" in names:
            try:
                mimetype_info = archive.getinfo("mimetype")
                if mimetype_info.file_size <= limits.max_probe_bytes:
                    with archive.open(mimetype_info) as member:
                        value = member.read(limits.max_probe_bytes + 1)
                    if value == b"application/epub+zip":
                        media_type = "application/epub+zip"
            except (KeyError, RuntimeError, zipfile.BadZipFile) as error:
                raise InputRefusal(
                    InputErrorCode.CORRUPT_INPUT,
                    "archive mimetype member cannot be read safely",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                ) from error

        active_flags = set(_active_content(names))
        for info in infos:
            if not info.filename.lower().endswith(".rels"):
                continue
            if info.file_size > limits.max_probe_bytes:
                continue
            try:
                with archive.open(info) as member:
                    relationship_data = member.read(limits.max_probe_bytes + 1)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise InputRefusal(
                    InputErrorCode.CORRUPT_INPUT,
                    "archive relationship metadata cannot be read safely",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                    details={"member": info.filename},
                ) from error
            if _EXTERNAL_RELATIONSHIP.search(relationship_data):
                active_flags.add("external-relationship")

        if "macro-project" in active_flags:
            media_type = {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
                    "application/vnd.ms-word.document.macroenabled.12"
                ),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
                    "application/vnd.ms-powerpoint.presentation.macroenabled.12"
                ),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
                    "application/vnd.ms-excel.sheet.macroenabled.12"
                ),
            }.get(media_type, media_type)
        active = tuple(sorted(active_flags))
        return media_type, ArchiveInspection(
            format="zip",
            entries=tuple(entries),
            total_compressed_bytes=total_compressed,
            total_uncompressed_bytes=total_uncompressed,
            active_content=active,
        )
