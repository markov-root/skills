"""Durable storage seam for skill-feedback.

AC-1 establishes the module boundary.  Ledger and projection I/O move behind
this seam without behavior changes as the later acceptance groups land.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .model import (
    AUTOMATIC_COLLECTION_MODES,
    PRIVACY_CONFIG_VERSION,
    QUALITATIVE_PRIVACY_SCANNER_VERSION,
    DispositionAuthority,
    FeedbackError,
    IntegrityConflict,
    ObservationAuthority,
    PromotionAuthorization,
    ReviewAuthority,
    _canonical_json,
    _empty_managed_note_file,
    _entry_sha256,
    _parse_timestamp,
    _utc_now,
    _validate_event,
    _validate_skill_name,
    _without_matches,
)

__all__: tuple[str, ...] = ()

HOME = Path(os.environ.get("HOME", str(Path.home())))


def _default_feedback_home() -> Path:
    """Use platform state for new installs without silently stranding legacy data."""
    legacy = HOME / "Skills" / "exported-data" / "skill-feedback"
    if legacy.exists():
        return legacy
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local"))
        return local / "Skill Feedback"
    if sys.platform == "darwin":
        return HOME / "Library" / "Application Support" / "Skill Feedback"
    state = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state"))
    return state / "skill-feedback"


FEEDBACK_HOME = Path(
    os.environ.get("SKILL_FEEDBACK_HOME", _default_feedback_home())
).expanduser()


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


@contextmanager
def _file_lock(path: Path, *, shared: bool = False, private: bool = False):
    """Hold a process lock for the complete transaction guarded by *path*."""
    if shared:
        # Inspection must remain usable in read-only sandboxes. Existing writers
        # publish the lock before mutation; a missing legacy lock therefore
        # permits a best-effort read without creating repository or state files.
        if not path.exists():
            yield
            return
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError:
            yield
            return
        with handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            except OSError:
                yield
            else:
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if private:
        _ensure_private_directory(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        if private:
            path.chmod(0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_json_atomic(path: Path, value: dict, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target_mode = (
        mode
        if mode is not None
        else (path.stat().st_mode & 0o777 if path.exists() else 0o644)
    )
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(target_mode)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _write_text_atomic(path: Path, content: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target_mode = (
        mode
        if mode is not None
        else (path.stat().st_mode & 0o777 if path.exists() else 0o644)
    )
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(target_mode)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _write_bytes_atomic(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(mode)
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()


def _event_path() -> Path:
    return FEEDBACK_HOME / "events.jsonl"


def _event_lock_path() -> Path:
    return FEEDBACK_HOME / ".events.lock"


def _notes_lock_path() -> Path:
    return FEEDBACK_HOME / ".notes.lock"


def _note_outbox_dir(skill: str) -> Path:
    return (
        FEEDBACK_HOME
        / "note-outbox"
        / _validate_skill_name(skill)
        / "docs"
        / "feedback"
    )


def _privacy_config_path() -> Path:
    return FEEDBACK_HOME / "privacy.json"


def _session_key_path() -> Path:
    return FEEDBACK_HOME / "session-hash.key"


def _session_key_lock_path() -> Path:
    return FEEDBACK_HOME / ".session-key.lock"


def _default_privacy_config() -> dict:
    return {
        "version": PRIVACY_CONFIG_VERSION,
        "automatic_collection": "off",
        "content_capture": False,
        "retention": {"mode": "unset", "days": None},
        "session_identifiers": "hmac-sha256",
        "note_locations": "skill-relative",
    }


def _read_privacy_config() -> tuple[dict, bool]:
    path = _privacy_config_path()
    if not path.exists():
        return _default_privacy_config(), False
    try:
        value = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise FeedbackError(f"cannot read privacy configuration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FeedbackError(f"privacy configuration must be an object: {path}")
    if value.get("version") == 1:
        expected = {
            "version",
            "automatic_collection",
            "content_capture",
            "retention_days",
        }
        unknown = set(value) - expected
        if unknown:
            raise FeedbackError(
                f"privacy configuration has unknown fields: {', '.join(sorted(unknown))}"
            )
        days = value.get("retention_days")
        if days is not None and (
            not isinstance(days, int) or isinstance(days, bool) or days < 1
        ):
            raise FeedbackError("retention_days must be null or at least 1")
        value = {
            **_default_privacy_config(),
            "automatic_collection": (
                "manifest_opt_in"
                if value.get("automatic_collection") is True
                else "off"
            ),
            "content_capture": value.get("content_capture"),
            "retention": {
                "mode": "days" if days is not None else "unset",
                "days": days,
            },
        }
    elif value.get("version") == 2:
        value = {
            **value,
            "version": PRIVACY_CONFIG_VERSION,
            "automatic_collection": (
                "manifest_opt_in"
                if value.get("automatic_collection") is True
                else "off"
            ),
        }
    config = _default_privacy_config()
    unknown = set(value) - set(config)
    if unknown:
        raise FeedbackError(
            f"privacy configuration has unknown fields: {', '.join(sorted(unknown))}"
        )
    config.update(value)
    if config["version"] != PRIVACY_CONFIG_VERSION:
        raise FeedbackError("unsupported privacy configuration version")
    if config["automatic_collection"] not in AUTOMATIC_COLLECTION_MODES:
        raise FeedbackError("automatic_collection must be off or manifest_opt_in")
    if config["content_capture"] is not False:
        raise FeedbackError("content_capture cannot be enabled in this release")
    retention = config["retention"]
    if not isinstance(retention, dict) or set(retention) != {"mode", "days"}:
        raise FeedbackError("retention must contain exactly mode and days")
    mode = retention["mode"]
    days = retention["days"]
    if mode not in ("unset", "forever", "days"):
        raise FeedbackError("retention.mode must be unset, forever, or days")
    if mode == "days":
        if not isinstance(days, int) or isinstance(days, bool) or days < 1:
            raise FeedbackError("retention.days must be at least 1 in days mode")
    elif days is not None:
        raise FeedbackError("retention.days must be null unless mode is days")
    if config["session_identifiers"] != "hmac-sha256":
        raise FeedbackError("session_identifiers must be hmac-sha256")
    if config["note_locations"] != "skill-relative":
        raise FeedbackError("note_locations must be skill-relative")
    return config, True


def _write_privacy_config(config: dict) -> Path:
    _ensure_private_directory(FEEDBACK_HOME)
    path = _privacy_config_path()
    _write_json_atomic(path, config, mode=0o600)
    return path


def _session_hash_key() -> bytes:
    path = _session_key_path()
    with _file_lock(_session_key_lock_path(), private=True):
        if not path.exists():
            _write_bytes_atomic(path, secrets.token_bytes(32), mode=0o600)
        try:
            key = path.read_bytes()
        except OSError as exc:
            raise FeedbackError(f"cannot read session hash key {path}: {exc}") from exc
        if len(key) != 32:
            raise FeedbackError(f"session hash key must be exactly 32 bytes: {path}")
        path.chmod(0o600)
        return key


def _append_event(event: dict) -> Path:
    return EventLedger(_event_path()).append(event)


def _append_event_once(event: dict) -> tuple[Path, bool]:
    """Append *event* unless its stable event_id is already present."""
    path = _event_path()
    line = json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
    with _file_lock(_event_lock_path(), private=True):
        events = _read_events_unlocked()
        if any(item["event_id"] == event["event_id"] for item in events):
            return path, False
        _ensure_private_directory(path.parent)
        with path.open("a", encoding="utf-8") as handle:
            path.chmod(0o600)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return path, True


def _read_events_unlocked() -> list[dict]:
    path = _event_path()
    if not path.exists():
        return []
    events = []
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise FeedbackError(f"cannot read event ledger {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FeedbackError(
                f"invalid event JSON at {path}:{line_number}: {exc}"
            ) from exc
        _validate_event(event)
        events.append(event)
    return events


def _read_events() -> list[dict]:
    if not _event_path().exists():
        return []
    with _file_lock(_event_lock_path(), shared=True, private=True):
        return _read_events_unlocked()


class EventLedger:
    """Validated append-only event seam with one-use capability enforcement."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.parent / ".events.lock"

    def _read_unlocked(self) -> list[dict]:
        if not self.path.exists():
            return []
        events: list[dict] = []
        try:
            lines = self.path.read_text().splitlines()
        except OSError as exc:
            raise FeedbackError(f"cannot read event ledger {self.path}: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FeedbackError(
                    f"invalid event JSON at {self.path}:{line_number}: {exc}"
                ) from exc
            _validate_event(event)
            events.append(event)
        return events

    def append(self, event: dict) -> Path:
        _validate_event(event)
        line = json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
        with _file_lock(self.lock_path, private=True):
            events = self._read_unlocked()
            if any(item.get("event_id") == event.get("event_id") for item in events):
                raise IntegrityConflict("event_id already exists in the ledger")
            if event.get("event_type") == "privacy.review.acknowledged":
                nonce = (event.get("payload") or {}).get("capability_nonce")
                if any(
                    item.get("event_type") == "privacy.review.acknowledged"
                    and (item.get("payload") or {}).get("capability_nonce") == nonce
                    for item in events
                ):
                    raise IntegrityConflict(
                        "operator privacy-review capability was already consumed"
                    )
            _ensure_private_directory(self.path.parent)
            with self.path.open("a", encoding="utf-8") as handle:
                self.path.chmod(0o600)
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        return self.path


@dataclass(frozen=True)
class LedgerIndex:
    """Lock-scoped, immutable authorities derived only from ledger events."""

    observations: Mapping[str, tuple[ObservationAuthority, ...]]
    dispositions: Mapping[str, DispositionAuthority]
    reviews: Mapping[str, ReviewAuthority]

    @classmethod
    def from_events(cls, events: list[dict]) -> "LedgerIndex":
        observations: dict[str, list[ObservationAuthority]] = {}
        dispositions: dict[str, DispositionAuthority] = {}
        reviews: dict[str, ReviewAuthority] = {}
        for event in events:
            payload = event.get("payload") or {}
            feedback_id = payload.get("feedback_id")
            if not isinstance(feedback_id, str) or not feedback_id:
                continue
            event_type = event.get("event_type")
            if event_type == "observation.recorded":
                digest = payload.get("note_digest") or {}
                body_sha256 = (
                    digest.get("sha256")
                    if isinstance(digest, dict)
                    and digest.get("canonicalization") == "body-v1"
                    else None
                )
                authority = ObservationAuthority(
                    feedback_id=feedback_id,
                    skill=(event.get("skill") or {}).get("name"),
                    kind=payload.get("kind"),
                    author=(event.get("actor") or {}).get("id"),
                    actor_type=(event.get("actor") or {}).get("type"),
                    signal=payload.get("signal"),
                    source=event.get("source"),
                    feature=payload.get("feature"),
                    impact=payload.get("impact"),
                    outcome=payload.get("outcome"),
                    invocation_id=event.get("invocation_id"),
                    session=(event.get("session") or {}).get("id"),
                    tags=tuple(event.get("tags") or ()),
                    note_sha256=payload.get("note_sha256"),
                    body_sha256=body_sha256,
                    entry_sha256=payload.get("entry_sha256"),
                    canonicalization=payload.get("canonicalization"),
                    note_file=payload.get("note_file"),
                    delivery=payload.get("delivery", "source"),
                    event_id=event.get("event_id"),
                )
                observations.setdefault(feedback_id, []).append(authority)
            elif event_type == "disposition.changed":
                dispositions[feedback_id] = DispositionAuthority(
                    feedback_id=feedback_id,
                    status=payload.get("status"),
                    rationale_sha256=payload.get("rationale_sha256"),
                    links_json=_canonical_json(payload.get("links") or {}),
                    event_id=event.get("event_id"),
                )
            elif event_type == "privacy.review.acknowledged":
                reviews[feedback_id] = ReviewAuthority(
                    feedback_id=feedback_id,
                    entry_sha256=payload.get("entry_sha256"),
                    findings_sha256=payload.get("findings_sha256"),
                    scanner_version=payload.get("scanner_version"),
                    event_id=event.get("event_id"),
                )
        return cls(
            observations=MappingProxyType(
                {key: tuple(value) for key, value in observations.items()}
            ),
            dispositions=MappingProxyType(dispositions),
            reviews=MappingProxyType(reviews),
        )

    @classmethod
    def read(cls) -> "LedgerIndex":
        path = _event_path()
        if not path.exists():
            return cls.from_events([])
        with _file_lock(_event_lock_path(), shared=True, private=True):
            return cls.from_events(_read_events_unlocked())

    def origins_for(self, feedback_id: str) -> tuple[ObservationAuthority, ...]:
        return self.observations.get(feedback_id, ())


def _write_events_unlocked(events: list[dict]) -> Path:
    _ensure_private_directory(FEEDBACK_HOME)
    path = _event_path()
    fd, raw_temp = tempfile.mkstemp(prefix=".events.", dir=FEEDBACK_HOME)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(
                    json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
        path.chmod(0o600)
        directory_fd = os.open(FEEDBACK_HOME, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def _read_object_sidecar(path: Path, label: str) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise FeedbackError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, dict) for key, item in value.items()
    ):
        raise FeedbackError(f"invalid {label} data: {path}")
    return value


def _read_delivery_sidecar(path: Path) -> dict[str, dict]:
    states = _read_object_sidecar(path, "feedback delivery")
    required = {
        "from",
        "to",
        "entry_sha256",
        "note_sha256",
        "delivered_at",
    }
    for feedback_id, state in states.items():
        if set(state) != required:
            raise FeedbackError(
                f"feedback delivery {path} entry {feedback_id!r} must contain "
                f"exactly {', '.join(sorted(required))}"
            )
        if not isinstance(state["from"], str) or not re.fullmatch(
            r"note-outbox/[^/]+/docs/feedback/[^/]+\.md", state["from"]
        ):
            raise FeedbackError(
                f"feedback delivery {path} entry {feedback_id!r} has invalid from"
            )
        if not isinstance(state["to"], str) or not re.fullmatch(
            r"docs/feedback/[^/]+\.md", state["to"]
        ):
            raise FeedbackError(
                f"feedback delivery {path} entry {feedback_id!r} has invalid to"
            )
        for key in ("entry_sha256", "note_sha256"):
            if not isinstance(state[key], str) or not re.fullmatch(
                r"[0-9a-f]{64}", state[key]
            ):
                raise FeedbackError(
                    f"feedback delivery {path} entry {feedback_id!r} has invalid {key}"
                )
        if not isinstance(state["delivered_at"], str):
            raise FeedbackError(
                f"feedback delivery {path} entry {feedback_id!r} has invalid delivered_at"
            )
        _parse_timestamp(state["delivered_at"], "delivery delivered_at")
    return states


def _managed_note_records(
    directory: Path,
) -> tuple[dict[str, list[dict]], dict[Path, str], list[str]]:
    records: dict[str, list[dict]] = {}
    contents: dict[Path, str] = {}
    unmanaged: list[str] = []
    if not directory.is_dir():
        return records, contents, unmanaged
    try:
        paths = sorted(directory.glob("*.md"))
    except OSError as exc:
        raise FeedbackError(
            f"cannot enumerate feedback notes {directory}: {exc}"
        ) from exc
    for path in paths:
        try:
            text = path.read_text()
        except OSError as exc:
            raise FeedbackError(f"cannot read feedback note {path}: {exc}") from exc
        contents[path] = text
        matches = list(
            re.finditer(
                r"(?ms)^### (?P<header>[^\n]+)\n\n(?P<body>.*?)(?=^### |\Z)",
                text,
            )
        )
        if not matches:
            if not _empty_managed_note_file(text):
                unmanaged.append(str(path))
            continue
        if not _empty_managed_note_file(_without_matches(text, matches)):
            unmanaged.append(str(path))
        for match in matches:
            header = match.group("header")
            body = match.group("body").strip()
            parts = [piece.strip() for piece in header.split("·")]
            metadata = {
                key: value
                for part in parts[3:]
                if "=" in part
                for key, value in [part.split("=", 1)]
            }
            feedback_id = metadata.get("id")
            if not feedback_id:
                unmanaged.append(f"{path}: structured entry without explicit id")
                continue
            block = f"### {header}\n\n{body}\n\n"
            records.setdefault(feedback_id, []).append(
                {
                    "id": feedback_id,
                    "path": path,
                    "filename": path.name,
                    "header": header,
                    "body": body,
                    "block": block,
                    "entry_sha256": _entry_sha256(header, body),
                    "note_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return records, contents, unmanaged


def _apply_delivery_plan(name: str, public: dict, transaction: dict) -> None:
    if not public["ready"]:
        raise FeedbackError(
            public["blocked_reason"]
            or "; ".join(public["conflicts"])
            or f"delivery plan for {name} is not ready"
        )
    if not public["entries"]:
        return

    destination: Path = transaction["destination"]
    destination.mkdir(parents=True, exist_ok=True)
    source_contents: dict[Path, str] = dict(transaction["source_contents"])
    outbox_records: dict[str, list[dict]] = transaction["outbox_records"]
    copied_ids = {entry["id"] for entry in public["entries"]}

    for entry in public["entries"]:
        if entry["note_action"] != "copy":
            continue
        record = outbox_records[entry["id"]][0]
        target = destination / record["filename"]
        content = source_contents.get(target)
        if content is None:
            content = (
                f"# Feedback — {name} — {target.stem}\n\n"
                "<!-- Agent observations. Triage actionable problems and preserve "
                "proven useful behavior. -->\n\n"
            )
        if content and not content.endswith("\n\n"):
            content = content.rstrip() + "\n\n"
        content += record["block"]
        _write_text_atomic(target, content)
        source_contents[target] = content

    source_statuses = dict(transaction["source_statuses"])
    for feedback_id in copied_ids:
        pending_status = transaction["outbox_statuses"].get(feedback_id)
        if pending_status is not None:
            source_statuses[feedback_id] = pending_status
    if source_statuses or transaction["source_status_path"].exists():
        _write_json_atomic(transaction["source_status_path"], source_statuses)

    delivered_at = _utc_now()
    delivery_states = dict(transaction["delivery_states"])
    for entry in public["entries"]:
        delivery_states.setdefault(
            entry["id"],
            {
                "from": f"note-outbox/{name}/docs/feedback/{entry['filename']}",
                "to": f"docs/feedback/{entry['filename']}",
                "entry_sha256": entry["entry_sha256"],
                "note_sha256": entry["note_sha256"],
                "delivered_at": delivered_at,
            },
        )
    _write_json_atomic(transaction["delivery_path"], delivery_states)

    verified_records, _, _ = _managed_note_records(destination)
    verified_statuses = _read_object_sidecar(
        transaction["source_status_path"], "feedback status"
    )
    verified_deliveries = _read_delivery_sidecar(transaction["delivery_path"])
    for entry in public["entries"]:
        records = verified_records.get(entry["id"], [])
        if (
            len(records) != 1
            or records[0]["entry_sha256"] != entry["entry_sha256"]
            or verified_deliveries.get(entry["id"], {}).get("entry_sha256")
            != entry["entry_sha256"]
        ):
            raise FeedbackError(
                f"destination verification failed for {entry['id']}; "
                "the outbox was retained"
            )
        pending_status = transaction["outbox_statuses"].get(entry["id"])
        if (
            pending_status is not None
            and verified_statuses.get(entry["id"]) != pending_status
        ):
            raise FeedbackError(
                f"destination disposition verification failed for {entry['id']}; "
                "the outbox was retained"
            )

    # Prune only after every destination artifact is durable and re-read. The
    # exact original file check protects against an uncooperative/manual writer
    # that does not honor Feedback's portfolio lock.
    records_by_path: dict[Path, list[dict]] = {}
    for feedback_id in copied_ids:
        record = outbox_records[feedback_id][0]
        records_by_path.setdefault(record["path"], []).append(record)
    for path, records in records_by_path.items():
        original = transaction["outbox_contents"][path]
        try:
            current = path.read_text()
        except OSError as exc:
            raise FeedbackError(
                f"cannot verify outbox ownership for {path}: {exc}"
            ) from exc
        if current != original:
            raise FeedbackError(
                f"outbox changed during delivery: {path}; destination is durable "
                "but the outbox was retained"
            )
        updated = original
        for record in sorted(records, key=lambda item: item["start"], reverse=True):
            updated = updated[: record["start"]] + updated[record["end"] :]
        _write_text_atomic(path, updated)

    outbox_statuses = dict(transaction["outbox_statuses"])
    for feedback_id in copied_ids:
        outbox_statuses.pop(feedback_id, None)
    if outbox_statuses or transaction["outbox_status_path"].exists():
        _write_json_atomic(
            transaction["outbox_status_path"], outbox_statuses, mode=0o600
        )


def _ledger_head(path: Path) -> str:
    """Content fingerprint of the append-only ledger (stable iff no write)."""
    try:
        return (
            "" if not path.is_file() else hashlib.sha256(path.read_bytes()).hexdigest()
        )
    except OSError as exc:
        raise FeedbackError(f"cannot read event ledger {path}: {exc}") from exc


def _require_authoritative_review(
    authorization: PromotionAuthorization, ledger_path: Path
) -> None:
    """A sealed operator privacy-review authority must exist on the current
    ledger for the exact (entry, findings, scanner) tuple — never re-derived."""
    if not ledger_path.is_file():
        raise IntegrityConflict("privacy review authority ledger is absent")
    try:
        lines = ledger_path.read_text().splitlines()
    except OSError as exc:
        raise FeedbackError(
            f"cannot read privacy review ledger {ledger_path}: {exc}"
        ) from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") != "privacy.review.acknowledged":
            continue
        payload = event.get("payload") or {}
        if (
            payload.get("feedback_id") == authorization.feedback_id
            and payload.get("entry_sha256") == authorization.entry_sha256
            and isinstance(payload.get("findings_sha256"), str)
            and payload.get("scanner_version") == authorization.privacy_scanner_version
        ):
            return
    raise IntegrityConflict(
        "no valid operator privacy review is bound to the delivery tuple"
    )


def _promote_record(authorization: PromotionAuthorization, source_text: str) -> None:
    """Write the origin-verified block to the destination, copy the status
    projection, record delivery state after the body is durable, then prune the
    outbox record whose bytes are still the exact authorized bytes."""
    destination = Path(authorization.destination_dir)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / authorization.filename

    if authorization.note_action == "copy":
        content = ""
        if target.exists():
            try:
                content = target.read_text()
            except OSError as exc:
                raise FeedbackError(
                    f"cannot read destination feedback {target}: {exc}"
                ) from exc
        if not content:
            content = (
                f"# Feedback — {authorization.skill} — {Path(target).stem}\n\n"
                "<!-- Agent observations. Triage actionable problems and preserve "
                "proven useful behavior. -->\n\n"
            )
        if not content.endswith("\n\n"):
            content = content.rstrip() + "\n\n"
        content += authorization.block
        _write_text_atomic(target, content)

    dst_status_path = Path(authorization.destination_status_path)
    if (
        authorization.status_action == "copy"
        and authorization.pending_status is not None
    ):
        statuses = _read_object_sidecar(dst_status_path, "feedback status")
        statuses[authorization.feedback_id] = authorization.pending_status
        _write_json_atomic(dst_status_path, statuses)

    delivery_path = Path(authorization.delivery_path)
    delivery_states = _read_delivery_sidecar(delivery_path)
    delivery_states.setdefault(
        authorization.feedback_id,
        {
            "from": f"note-outbox/{authorization.skill}/docs/feedback/{authorization.filename}",
            "to": f"docs/feedback/{authorization.filename}",
            "entry_sha256": authorization.entry_sha256,
            "note_sha256": authorization.note_sha256,
            "delivered_at": _utc_now(),
        },
    )
    _write_json_atomic(delivery_path, delivery_states)

    outbox_path = Path(authorization.source_path)
    # Locate THIS record's exact authorized bytes by content and prune only those:
    # pruning an earlier entry shifts later offsets, and concurrent appends land
    # elsewhere, so fixed offsets are unsafe. Un-findable bytes = tampered → abort.
    authorized_block = authorization.source_original[
        authorization.start : authorization.end
    ]
    index = source_text.find(authorized_block)
    if index == -1:
        raise IntegrityConflict(
            "outbox changed during promotion; destination is durable but outbox retained"
        )
    updated = source_text[:index] + source_text[index + len(authorized_block) :]
    _write_text_atomic(outbox_path, updated)

    outbox_status_path = Path(authorization.outbox_status_path)
    if outbox_status_path.exists():
        outbox_statuses = _read_object_sidecar(outbox_status_path, "feedback status")
        outbox_statuses.pop(authorization.feedback_id, None)
        _write_json_atomic(outbox_status_path, outbox_statuses, mode=0o600)


def apply_delivery(
    authorization: PromotionAuthorization, environment: Mapping | None = None
) -> None:
    """Origin-bound, TOCTOU-reclosed delivery of exactly one verified record.

    Holds the notes lock and the event lock across the entire re-verify + write so
    no event can advance the ledger and no writer can race the destination write.
    A moved ledger head, changed outbox bytes, or an invalidated privacy review
    aborts before any promotion — never re-derives authorization from on-disk
    bytes (R6)."""
    ledger_path = Path(authorization.ledger_path)
    event_lock = ledger_path.parent / ".events.lock"
    notes_lock = Path(authorization.notes_lock_path)
    with _file_lock(notes_lock, private=True), _file_lock(event_lock, private=True):
        # The append-only ledger guarantees the origin event is immutable once
        # written, so re-confirm it is still present by id rather than requiring a
        # frozen whole-ledger head — a concurrent unrelated record legitimately
        # advances the head without touching this record's origin authority.
        if not any(
            event.get("event_id") == authorization.origin_event_id
            and event.get("event_type") == "observation.recorded"
            for event in EventLedger(ledger_path)._read_unlocked()
        ):
            raise IntegrityConflict(
                "origin event missing since the delivery authorization"
            )
        source = Path(authorization.source_path)
        if not source.is_file():
            raise IntegrityConflict("outbox record is absent before promotion")
        try:
            source_text = source.read_text()
        except OSError as exc:
            raise FeedbackError(f"cannot read outbox record {source}: {exc}") from exc
        # Bind to THIS record's exact authorized bytes, located by content (not by
        # fixed offsets): pruning an earlier entry in the same daily file shifts
        # later offsets, and a concurrent unrelated append must not invalidate an
        # in-flight authorization (R6 = exact preauthorized bytes, scoped to the
        # record). Tampering this record's bytes makes them un-findable → conflict.
        authorized_block = authorization.source_original[
            authorization.start : authorization.end
        ]
        if authorized_block not in source_text:
            raise IntegrityConflict(
                "outbox record bytes changed since the delivery authorization"
            )
        if authorization.privacy_review_required:
            if (
                authorization.privacy_scanner_version
                != QUALITATIVE_PRIVACY_SCANNER_VERSION
            ):
                raise IntegrityConflict(
                    "privacy scanner version advanced; review must be redone"
                )
            _require_authoritative_review(authorization, ledger_path)
        _promote_record(authorization, source_text)


def _private_mode(path: Path, expected: int) -> tuple[bool, str | None]:
    if not path.exists():
        return True, None
    mode = path.stat().st_mode & 0o777
    return mode == expected, oct(mode)
