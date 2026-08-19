"""Bounded local-path, stream, and URL-reference resolution."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import BinaryIO
from urllib.parse import urlsplit

from doc2md.inputs.detect import inspect_bytes
from doc2md.inputs.models import (
    InputErrorCode,
    InputLimits,
    InputRefusal,
    InspectedSource,
    RetryMeaning,
    SubsetRequest,
)


class ReferenceKind(str, Enum):
    """Input acquisition kind selected without performing network access."""

    LOCAL_PATH = "local-path"
    REMOTE_URL = "remote-url"


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    """Policy-checked acquisition metadata."""

    kind: ReferenceKind
    value: str = field(repr=False)


def resolve_reference(value: str) -> ResolvedReference:
    """Resolve an explicit local path or HTTP(S) URL without fetching it."""

    if not value or "\x00" in value:
        raise InputRefusal(
            InputErrorCode.INVALID_INPUT,
            "input reference is empty or contains a null byte",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
        )
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"}:
            raise InputRefusal(
                InputErrorCode.UNSUPPORTED_SCHEME,
                "input URL scheme is not supported",
                retry=RetryMeaning.NEVER,
                details={"scheme": parsed.scheme.lower()},
            )
        if not parsed.hostname:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "HTTP(S) input is missing a hostname",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )
        if parsed.username is not None or parsed.password is not None:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "credentials must not be embedded in an input URL",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )
        return ResolvedReference(ReferenceKind.REMOTE_URL, value)
    return ResolvedReference(ReferenceKind.LOCAL_PATH, value)


def _read_bounded(stream: BinaryIO, limit: int) -> bytes:
    chunks: list[bytes] = []
    observed = 0
    while True:
        chunk = stream.read(min(64 * 1024, limit - observed + 1))
        if not chunk:
            return b"".join(chunks)
        if not isinstance(chunk, bytes):
            raise TypeError("binary stream read() must return bytes")
        chunks.append(chunk)
        observed += len(chunk)
        if observed > limit:
            raise InputRefusal(
                InputErrorCode.RESOURCE_EXHAUSTED,
                "input stream exceeds the configured byte limit",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"observed_at_least": observed, "limit": limit},
            )


def inspect_stream(
    stream: BinaryIO,
    *,
    display_name: str = "<stream>",
    declared_media_type: str | None = None,
    selectors: SubsetRequest | None = None,
    limits: InputLimits | None = None,
) -> InspectedSource:
    """Spool a binary stream under a hard byte limit, then inspect it."""

    authority = limits if limits is not None else InputLimits()
    spool_threshold = min(authority.max_source_bytes, 8 * 1024 * 1024)
    with SpooledTemporaryFile(max_size=spool_threshold, mode="w+b") as spool:
        observed = 0
        while True:
            chunk = stream.read(
                min(64 * 1024, authority.max_source_bytes - observed + 1)
            )
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise TypeError("binary stream read() must return bytes")
            observed += len(chunk)
            if observed > authority.max_source_bytes:
                raise InputRefusal(
                    InputErrorCode.RESOURCE_EXHAUSTED,
                    "input stream exceeds the configured byte limit",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                    details={
                        "observed_at_least": observed,
                        "limit": authority.max_source_bytes,
                    },
                )
            spool.write(chunk)
        spool.seek(0)
        data = spool.read()
    return inspect_bytes(
        data,
        display_name=display_name,
        declared_media_type=declared_media_type,
        selectors=selectors,
        limits=authority,
    )


def inspect_path(
    path: str | os.PathLike[str],
    *,
    declared_media_type: str | None = None,
    selectors: SubsetRequest | None = None,
    limits: InputLimits | None = None,
    allow_final_symlink: bool = False,
) -> InspectedSource:
    """Open one local regular file once and inspect the bytes read from that descriptor."""

    authority = limits if limits is not None else InputLimits()
    candidate = Path(path)
    try:
        before = candidate.lstat()
    except FileNotFoundError as error:
        raise InputRefusal(
            InputErrorCode.INVALID_INPUT,
            "input path does not exist",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"path": os.fspath(candidate)},
        ) from error
    if stat.S_ISLNK(before.st_mode):
        if not allow_final_symlink:
            raise InputRefusal(
                InputErrorCode.UNSAFE_INPUT,
                "input path is a symbolic link",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"path": os.fspath(candidate)},
            )
        try:
            before = candidate.stat()
        except FileNotFoundError as error:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "input symlink target does not exist",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"path": os.fspath(candidate)},
            ) from error
    if not stat.S_ISREG(before.st_mode):
        raise InputRefusal(
            InputErrorCode.UNSAFE_INPUT,
            "input path is not a regular file",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"path": os.fspath(candidate)},
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not allow_final_symlink:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise InputRefusal(
            InputErrorCode.UNSAFE_INPUT,
            "input path could not be opened under the symlink policy",
            retry=RetryMeaning.AFTER_INPUT_CHANGE,
            details={"path": os.fspath(candidate)},
        ) from error
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise InputRefusal(
                InputErrorCode.UNSAFE_INPUT,
                "input path is not a regular file",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"path": os.fspath(candidate)},
            )
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise InputRefusal(
                InputErrorCode.UNSAFE_INPUT,
                "input path changed while it was being opened",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={"path": os.fspath(candidate)},
            )
        if opened.st_size > authority.max_source_bytes:
            raise InputRefusal(
                InputErrorCode.RESOURCE_EXHAUSTED,
                "input file exceeds the configured byte limit",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
                details={
                    "observed": opened.st_size,
                    "limit": authority.max_source_bytes,
                },
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = _read_bounded(stream, authority.max_source_bytes)
    finally:
        os.close(descriptor)
    return inspect_bytes(
        data,
        display_name=candidate.name,
        declared_media_type=declared_media_type,
        selectors=selectors,
        limits=authority,
    )
