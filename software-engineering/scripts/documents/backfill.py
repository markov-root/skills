"""Atomic, body-preserving migration of existing Markdown to the v2 core."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from ..policy.manifest import DocsCurrencyPolicy
from .authoring import _HEX8, _ROLE_LABELS, _slug
from .contracts import ROLE_CONTRACTS
from .validation import _UniqueKeySafeLoader


@dataclass(frozen=True)
class DocumentBackfill:
    path: str
    role: str
    id: str
    uid: str
    created: str
    updated: str
    added_keys: tuple[str, ...]


def backfill_document(
    root: Path,
    source: str | Path,
    *,
    role: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    status: str | None = None,
    now: datetime | None = None,
    random_hex: str | None = None,
    policy: DocsCurrencyPolicy | None = None,
) -> DocumentBackfill:
    """Add or derive the v2 core while preserving the Markdown body bytes exactly."""
    root = root.resolve()
    target = _contained_file(root, source)
    original = target.read_bytes()
    metadata, body = _split_document(original)
    extension = metadata.get("engineering_document")
    if extension is not None and not isinstance(extension, Mapping):
        raise ValueError("engineering_document must be a mapping when present")
    nested: Mapping[str, Any] = extension or {}

    resolved_role = _resolve("role", role, metadata.get("role"), nested.get("role"))
    resolved_title = _resolve("title", title, metadata.get("title"), nested.get("title"))
    resolved_summary = _resolve("summary", summary, metadata.get("summary"))
    if not metadata:
        missing = [
            name
            for name, value in (
                ("role", resolved_role),
                ("title", resolved_title),
                ("summary", resolved_summary),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "document without frontmatter requires reviewed input for " + ", ".join(missing)
            )
    if resolved_role not in _ROLE_LABELS:
        raise ValueError(f"unknown document role {resolved_role!r}")
    if policy is not None:
        adopted = [item for item in policy.roles if item.name == resolved_role and item.contract]
        if len(adopted) != 1:
            raise ValueError(f"document role {resolved_role!r} is not adopted exactly once")
    resolved_title = _single_line("title", resolved_title)
    resolved_summary = _single_line("summary", resolved_summary)
    if len(resolved_summary) > 150:
        raise ValueError("document summary must be at most 150 characters")

    moment = (now or datetime.now(UTC)).astimezone(UTC)
    suffix = random_hex or uuid.uuid4().hex[:8]
    if not _HEX8.fullmatch(suffix):
        raise ValueError(
            "document UID random suffix must be eight lowercase hexadecimal characters"
        )
    day = moment.date().isoformat()
    contract = ROLE_CONTRACTS[resolved_role]
    default_status = contract.initial_states[0] if contract.initial_states else "current"
    resolved_status = (
        _resolve(
            "status",
            status,
            metadata.get("status"),
            metadata.get("state"),
            nested.get("state"),
        )
        or default_status
    )
    resolved_created = _date_text(metadata.get("created") or nested.get("created") or day)
    identifier = str(metadata.get("id") or nested.get("id") or _slug(resolved_title))
    uid = str(
        metadata.get("uid")
        or nested.get("uid")
        or f"{resolved_role}-{moment:%Y%m%dT%H%M%S%fZ}-{suffix}"
    )

    additions = {
        "schema_version": 2,
        "id": identifier,
        "uid": uid,
        "title": resolved_title,
        "role": resolved_role,
        "status": str(resolved_status),
        "summary": resolved_summary,
        "created": resolved_created,
        "updated": day,
    }
    added_keys = tuple(key for key in additions if key not in metadata)
    migrated = dict(metadata)
    for key, value in reversed(tuple(additions.items())):
        if key in migrated:
            migrated[key] = value
        else:
            migrated = {key: value, **migrated}

    rendered = _render(migrated, body)
    if rendered != original:
        _atomic_replace(target, rendered, original_mode=target.stat().st_mode & 0o777)
    return DocumentBackfill(
        target.relative_to(root).as_posix(),
        resolved_role,
        identifier,
        uid,
        resolved_created,
        day,
        added_keys,
    )


def _contained_file(root: Path, source: str | Path) -> Path:
    candidate = (
        (root / source).resolve() if not Path(source).is_absolute() else Path(source).resolve()
    )
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("document backfill path escapes the project") from exc
    if not candidate.is_file():
        raise ValueError(f"document backfill source is not a file: {source}")
    return candidate


def _split_document(content: bytes) -> tuple[dict[str, Any], bytes]:
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip(b"\r\n") != b"---":
        return {}, content
    closing = next(
        (index for index, line in enumerate(lines[1:], 1) if line.rstrip(b"\r\n") == b"---"),
        None,
    )
    if closing is None:
        raise ValueError("document frontmatter is unclosed")
    try:
        loaded = yaml.load(b"".join(lines[1:closing]).decode("utf-8"), Loader=_UniqueKeySafeLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"document frontmatter is invalid: {exc}") from exc
    if loaded is None:
        metadata: dict[str, Any] = {}
    elif isinstance(loaded, dict):
        metadata = loaded
    else:
        raise ValueError("document frontmatter must be a mapping")
    return metadata, b"".join(lines[closing + 1 :])


def _resolve(name: str, supplied: Any, *existing: Any) -> Any:
    observed = next((value for value in existing if value is not None), None)
    if supplied is not None and observed is not None and str(supplied) != str(observed):
        raise ValueError(f"reviewed {name} conflicts with existing metadata")
    return supplied if supplied is not None else observed


def _single_line(name: str, value: Any) -> str:
    if value is None:
        raise ValueError(f"document {name} is unavailable; supply reviewed --{name}")
    text = str(value).strip()
    if not text or any(character in text for character in "\r\n"):
        raise ValueError(f"document {name} must be a non-empty single line")
    return text


def _date_text(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"document created date is invalid: {text!r}") from exc
    return text


def _render(metadata: Mapping[str, Any], body: bytes) -> bytes:
    frontmatter = yaml.safe_dump(
        dict(metadata),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).encode("utf-8")
    return b"---\n" + frontmatter + b"---\n" + body


def _atomic_replace(path: Path, content: bytes, *, original_mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, original_mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
