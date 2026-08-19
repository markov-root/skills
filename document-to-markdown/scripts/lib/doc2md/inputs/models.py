"""Owned values for resolving and inspecting untrusted document input."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from doc2md.core import SourceDocument


class InputErrorCode(str, Enum):
    """Stable public error classes used by the input boundary."""

    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_SCHEME = "unsupported_scheme"
    UNSAFE_INPUT = "unsafe_input"
    ENCRYPTED_INPUT = "encrypted_input"
    CORRUPT_INPUT = "corrupt_input"
    UNSUPPORTED_FORMAT = "unsupported_format"
    RESOURCE_EXHAUSTED = "resource_exhausted"


class RetryMeaning(str, Enum):
    """Stable retry meanings from the versioned error contract."""

    NEVER = "never"
    AFTER_INPUT_CHANGE = "after-input-change"
    AFTER_PERMISSION = "after-permission"
    AFTER_CAPABILITY_INSTALL = "after-capability-install"
    AFTER_DELAY = "after-delay"
    RESUME = "resume"


class InputRefusal(ValueError):
    """Expected, structured refusal at the untrusted-input boundary."""

    def __init__(
        self,
        code: InputErrorCode,
        message: str,
        *,
        retry: RetryMeaning,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if not message:
            raise ValueError("input refusal message must not be empty")
        super().__init__(message)
        self.code = code
        self.retry = retry
        self.details = MappingProxyType(dict(details or {}))

    def as_public_error(self) -> dict[str, Any]:
        """Project this refusal into the accepted v1 error shape."""

        return {
            "schema_version": 1,
            "code": self.code.value,
            "message": str(self),
            "retry": self.retry.value,
            "resumable": False,
            "resume_token": None,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class InputLimits:
    """Hard limits applied before any format adapter is invoked."""

    max_source_bytes: int = 64 * 1024 * 1024
    max_archive_entries: int = 1_000
    max_archive_entry_bytes: int = 128 * 1024 * 1024
    max_archive_total_bytes: int = 512 * 1024 * 1024
    max_archive_ratio: float = 100.0
    max_probe_bytes: int = 64 * 1024
    max_requested_pages: int = 10_000

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_source_bytes,
            self.max_archive_entries,
            self.max_archive_entry_bytes,
            self.max_archive_total_bytes,
            self.max_probe_bytes,
            self.max_requested_pages,
        )
        if any(type(value) is not int or value <= 0 for value in integer_limits):
            raise ValueError("integer input limits must be positive integers")
        if self.max_archive_ratio <= 0:
            raise ValueError("max_archive_ratio must be positive")


@dataclass(frozen=True, slots=True)
class SubsetRequest:
    """Explicit bounded subset requested by a caller."""

    pages: tuple[int, ...] = ()
    slides: tuple[int, ...] = ()
    sheets: tuple[str, ...] = ()
    entries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, integer_values in (
            ("pages", self.pages),
            ("slides", self.slides),
        ):
            if any(type(value) is not int or value <= 0 for value in integer_values):
                raise ValueError(f"{label} must contain positive integers")
            if len(integer_values) != len(set(integer_values)):
                raise ValueError(f"{label} must not contain duplicates")
        for label, string_values in (
            ("sheets", self.sheets),
            ("entries", self.entries),
        ):
            if any(not isinstance(value, str) or not value for value in string_values):
                raise ValueError(f"{label} must contain non-empty strings")
            if len(string_values) != len(set(string_values)):
                raise ValueError(f"{label} must not contain duplicates")

    @property
    def requested(self) -> bool:
        return any((self.pages, self.slides, self.sheets, self.entries))


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """Bounded central-directory evidence for one archive member."""

    name: str
    compressed_bytes: int
    uncompressed_bytes: int
    is_directory: bool


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    """Archive safety evidence collected without extracting members."""

    format: str
    entries: tuple[ArchiveEntry, ...]
    total_compressed_bytes: int
    total_uncompressed_bytes: int
    active_content: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MediaDetection:
    """Actual media-type evidence and disagreement diagnostics."""

    media_type: str
    signals: tuple[str, ...]
    declared_media_type: str | None = None
    filename_media_type: str | None = None
    disagreement: bool = False
    encoding: str | None = None
    active_content: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorValidation:
    """What was validated now and what remains adapter-owned."""

    request: SubsetRequest
    validated: tuple[str, ...]
    deferred: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InspectedSource:
    """Bytes plus security and media evidence passed to later stages."""

    source: SourceDocument
    detection: MediaDetection
    selectors: SelectorValidation
    archive: ArchiveInspection | None = None
