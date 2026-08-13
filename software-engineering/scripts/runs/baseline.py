"""Immutable, repository-contained baseline records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class BaselineError(ValueError):
    """A baseline is invalid, tampered with, or incompatible."""


@dataclass(frozen=True)
class CheckRecord:
    name: str
    status: str
    exit_code: int | None = None
    duration_ms: int | None = None
    output: str = ""


@dataclass(frozen=True)
class ToolIdentity:
    check: str
    executable: str
    resolved_executable: str | None
    executable_sha256: str | None
    version_command: tuple[str, ...] | None
    version_status: str
    version_output: str


@dataclass(frozen=True)
class BaselineIdentity:
    repository_root: str
    commit: str | None
    dirty_fingerprint: str
    manifest_digest: str
    profile: str
    cli_identity: str
    tools_digest: str


@dataclass(frozen=True)
class BaselineRecord:
    identity: BaselineIdentity
    checks: tuple[CheckRecord, ...]
    tools: tuple[ToolIdentity, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class FinalRecord:
    baseline_digest: str
    identity: BaselineIdentity
    checks: tuple[CheckRecord, ...]
    tools: tuple[ToolIdentity, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: int = SCHEMA_VERSION


def fingerprint_paths(root: Path, paths: Sequence[str]) -> str:
    """Hash path names and contents without following files outside *root*."""
    root = root.resolve()
    digest = hashlib.sha256()
    for name in sorted(set(paths)):
        candidate = (root / name).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise BaselineError(f"path escapes project root: {name}") from exc
        digest.update(name.encode())
        digest.update(b"\0")
        if candidate.is_file():
            digest.update(candidate.read_bytes())
        elif candidate.exists():
            digest.update(b"<non-file>")
        else:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def tool_identities_digest(tools: Sequence[ToolIdentity]) -> str:
    return _seal([asdict(item) for item in tools])


def record_digest(record: BaselineRecord) -> str:
    return _seal(_payload(record))


def _payload(record: BaselineRecord) -> dict[str, Any]:
    return asdict(record)


def _seal(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_baseline(root: Path, run_id: str, record: BaselineRecord) -> Path:
    """Atomically create an immutable baseline; an existing run is never replaced."""
    if (
        not run_id
        or run_id in {".", ".."}
        or any(character in run_id for character in ("/", "\\", "\x00"))
    ):
        raise BaselineError("invalid run id")
    directory = root.resolve() / ".engineering" / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / "baseline.json"
    payload = _payload(record)
    envelope = {"record": payload, "integrity": {"sha256": _seal(payload)}}
    fd, temporary = tempfile.mkstemp(prefix=".baseline-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        try:
            directory.rmdir()
        except OSError:
            pass
        raise
    return target


def write_final(root: Path, run_id: str, record: FinalRecord) -> Path:
    """Atomically add an immutable final record to an existing run."""
    if (
        not run_id
        or run_id in {".", ".."}
        or any(character in run_id for character in ("/", "\\", "\x00"))
    ):
        raise BaselineError("invalid run id")
    directory = root.resolve() / ".engineering" / "runs" / run_id
    if not directory.is_dir():
        raise BaselineError(f"baseline run does not exist: {run_id}")
    target = directory / "final.json"
    if target.exists():
        raise BaselineError(f"final record already exists: {run_id}")
    payload = asdict(record)
    envelope = {"record": payload, "integrity": {"sha256": _seal(payload)}}
    fd, temporary = tempfile.mkstemp(prefix=".final-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def _decode_record(path: Path) -> dict[str, Any]:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope["record"]
        if envelope["integrity"]["sha256"] != _seal(payload):
            raise BaselineError(f"{path.name} integrity check failed")
        if payload["schema_version"] != SCHEMA_VERSION:
            raise BaselineError(f"unsupported {path.name} schema version")
        return payload
    except BaselineError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BaselineError(f"malformed {path.name} record") from exc


def _identity_from(payload: Mapping[str, Any]) -> BaselineIdentity:
    return BaselineIdentity(**payload["identity"])


def _checks_from(payload: Mapping[str, Any]) -> tuple[CheckRecord, ...]:
    return tuple(CheckRecord(**item) for item in payload["checks"])


def _tools_from(payload: Mapping[str, Any]) -> tuple[ToolIdentity, ...]:
    return tuple(
        ToolIdentity(
            **{
                **item,
                "version_command": (
                    tuple(item["version_command"])
                    if item.get("version_command") is not None
                    else None
                ),
            }
        )
        for item in payload.get("tools", ())
    )


def read_baseline(path: Path) -> BaselineRecord:
    try:
        payload = _decode_record(path)
        return BaselineRecord(
            identity=_identity_from(payload),
            checks=_checks_from(payload),
            tools=_tools_from(payload),
            created_at=payload["created_at"],
            schema_version=payload["schema_version"],
        )
    except BaselineError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BaselineError("malformed baseline record") from exc


def read_final(path: Path) -> FinalRecord:
    try:
        payload = _decode_record(path)
        return FinalRecord(
            baseline_digest=payload["baseline_digest"],
            identity=_identity_from(payload),
            checks=_checks_from(payload),
            tools=_tools_from(payload),
            created_at=payload["created_at"],
            schema_version=payload["schema_version"],
        )
    except BaselineError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise BaselineError("malformed final record") from exc


def identity_changes(baseline: BaselineIdentity, current: BaselineIdentity) -> tuple[str, ...]:
    fields = (
        "repository_root",
        "commit",
        "dirty_fingerprint",
        "manifest_digest",
        "profile",
        "cli_identity",
        "tools_digest",
    )
    return tuple(name for name in fields if getattr(baseline, name) != getattr(current, name))


def incompatibilities(baseline: BaselineIdentity, current: BaselineIdentity) -> tuple[str, ...]:
    fields = (
        "repository_root",
        "commit",
        "manifest_digest",
        "profile",
        "cli_identity",
        "tools_digest",
    )
    return tuple(name for name in fields if getattr(baseline, name) != getattr(current, name))
