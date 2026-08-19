"""Secret-provider seams that do not require argv or environment variables."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from doc2md.inputs.models import (
    InputErrorCode,
    InputRefusal,
    RetryMeaning,
)


class CredentialProvider(Protocol):
    """One-shot credential source supplied directly by a trusted caller."""

    def read(self) -> bytes:
        """Return credential bytes without logging or serializing them."""


def _read_descriptor(descriptor: int, max_bytes: int) -> bytes:
    if type(descriptor) is not int or descriptor < 0:
        raise ValueError("credential descriptor must be a non-negative integer")
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("credential max_bytes must be a positive integer")
    duplicate = os.dup(descriptor)
    try:
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(duplicate, min(4096, max_bytes - observed + 1))
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            observed += len(chunk)
            if observed > max_bytes:
                raise InputRefusal(
                    InputErrorCode.INVALID_INPUT,
                    "credential exceeds the configured byte limit",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                )
    finally:
        os.close(duplicate)


@dataclass(frozen=True, slots=True)
class FileDescriptorCredential:
    """Read a secret from a caller-supplied descriptor."""

    descriptor: int
    max_bytes: int = 4096

    def read(self) -> bytes:
        return _read_descriptor(self.descriptor, self.max_bytes)


@dataclass(frozen=True, slots=True)
class ProtectedFileCredential:
    """Read a secret from a regular, owner-only, non-symlink file."""

    path: Path
    max_bytes: int = 4096

    def read(self) -> bytes:
        try:
            metadata = self.path.lstat()
        except FileNotFoundError as error:
            raise InputRefusal(
                InputErrorCode.INVALID_INPUT,
                "credential file does not exist",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise InputRefusal(
                InputErrorCode.UNSAFE_INPUT,
                "credential path must be a regular non-symlink file",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )
        if metadata.st_mode & 0o077:
            raise InputRefusal(
                InputErrorCode.UNSAFE_INPUT,
                "credential file must not grant group or other permissions",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )
        if metadata.st_uid != os.geteuid():
            raise InputRefusal(
                InputErrorCode.UNSAFE_INPUT,
                "credential file must be owned by the current user",
                retry=RetryMeaning.AFTER_INPUT_CHANGE,
            )
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.path, flags)
        try:
            opened = os.fstat(descriptor)
            if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
                raise InputRefusal(
                    InputErrorCode.UNSAFE_INPUT,
                    "credential file changed while it was being opened",
                    retry=RetryMeaning.AFTER_INPUT_CHANGE,
                )
            return _read_descriptor(descriptor, self.max_bytes)
        finally:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class CallbackCredential:
    """Invoke a trusted in-process callback only when an adapter needs a secret."""

    callback: Callable[[], bytes] = field(repr=False)

    def read(self) -> bytes:
        value = self.callback()
        if not isinstance(value, bytes):
            raise TypeError("credential callback must return bytes")
        return value
