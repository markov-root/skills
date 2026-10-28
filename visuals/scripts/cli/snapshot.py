#!/usr/bin/env python3
"""Dataset snapshots: the data-provenance capability domain (task 0008).

A capability domain, not a command adapter. `data_cmd.py` is its only consumer.

This generalises the seven hand-written `sync-data.sh` scripts in the reference
corpus into one declared step. Those scripts each fetch or copy an upstream
input into a visual's data directory; what they mostly do NOT do is record what
was copied, from where, when, at what digest, and — the part that matters most —
what the dataset cannot support. The corpus's best `provenance.json`
(`metr-agent-workstreams`) records all of it; its thinnest records a URL, an
etag and a size. This module makes the best shape the only shape.

The provenance schema is **not invented here** (task 0008 non-goals): the field
names are the corpus's own. Three rules are added on top:

- **`limitations` is required and may not be empty** (criterion 5). A dataset
  whose limitations are unstated does not snapshot. Of the reference corpus's
  visuals only 7 of 25 recorded them (audit F9), and a graphic asserting
  something its data cannot support is the failure this prevents. There is no
  `--force` for this one: an escape hatch would make it advisory in practice.
- **Re-running with unchanged inputs is byte-identical apart from timestamps**
  (criterion 6), so a diff shows real change only. Everything is sorted and the
  volatile fields are confined to two keys.
- **A changed upstream digest is reported, never silently absorbed**
  (criterion 7). A dataset moving underneath a published graphic is a finding
  about the graphic, not routine bookkeeping.

What this module does not do: fetch from the network, and run the project's own
derive step. A snapshot records inputs the caller has already obtained. Deriving
is the project's business, and inventing a fetch layer here would put network
policy, retries and credentials inside a provenance recorder.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sources  # capability domain: sha256_file, so one digest implementation exists

#: Bumped only when the on-disk provenance shape changes incompatibly.
SCHEMA_VERSION = 1

PROVENANCE_NAME = "provenance.json"

#: The only keys whose value legitimately differs between two runs over
#: identical inputs. Criterion 6 is expressed as: ignore these, diff the rest.
VOLATILE_FIELDS = ("retrieved_at", "ingested_at")


class SnapshotError(Exception):
    """The snapshot cannot proceed. Raised for a contract violation the caller
    must fix (an absent input, missing limitations), never for a finding."""


@dataclass(frozen=True)
class DigestChange:
    """One input whose digest differs from the previous snapshot (criterion 7)."""

    name: str
    previous: str
    current: str


@dataclass(frozen=True)
class SnapshotResult:
    data_dir: Path
    provenance_path: Path
    inputs: tuple[str, ...]
    changes: tuple[DigestChange, ...]
    first_snapshot: bool


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def describe_input(
    path: Path, *, source_page: str, data_url: str | None, transform: str | None
) -> dict:
    """One input's recorded provenance. Deterministic for a fixed file: the
    volatile retrieval timestamp is the caller's, not read from the filesystem
    (an mtime would make an otherwise identical re-run differ)."""
    record = {
        "name": path.name,
        "source_page": source_page,
        "sha256": sources.sha256_file(path),
        "bytes": path.stat().st_size,
    }
    if data_url:
        record["data_url"] = data_url
    record["transform"] = transform or "None; exact upstream payload retained."
    return record


def build_provenance(
    *,
    inputs: list[dict],
    description: str,
    limitations: list[str],
    retrieved_at: str,
    ingested_at: str,
) -> dict:
    """Assemble the provenance document. Criterion 4's required fields are all
    present or this raises: source identity, upstream URL, byte size, sha256,
    both timestamps, the measurement description, and limitations."""
    if not limitations or not all(str(item).strip() for item in limitations):
        raise SnapshotError(
            "limitations is required and may not be empty — a dataset whose "
            "limitations are unstated does not snapshot; to pass: pass at least "
            "one --limitation naming what this data cannot support"
        )
    if not description.strip():
        raise SnapshotError(
            "a measurement description is required — to pass: pass --description "
            "stating what this dataset measures"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "description": description.strip(),
        "inputs": sorted(inputs, key=lambda record: record["name"]),
        "limitations": [str(item).strip() for item in limitations],
        "retrieved_at": retrieved_at,
        "ingested_at": ingested_at,
    }


def read_provenance(data_dir: Path) -> dict | None:
    """The previous snapshot, or None. An unreadable file is treated as absent
    so a corrupt provenance cannot block a re-snapshot that would fix it."""
    path = data_dir / PROVENANCE_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def digest_changes(previous: dict | None, current: dict) -> tuple[DigestChange, ...]:
    """Inputs whose digest moved since the previous snapshot (criterion 7)."""
    if not previous:
        return ()
    before = {
        record.get("name"): record.get("sha256")
        for record in previous.get("inputs", [])
        if isinstance(record, dict)
    }
    changes = []
    for record in current["inputs"]:
        was = before.get(record["name"])
        if was and was != record["sha256"]:
            changes.append(DigestChange(record["name"], was, record["sha256"]))
    return tuple(changes)


def stable_view(payload: dict) -> dict:
    """The provenance document with its volatile fields removed — the thing
    criterion 6 requires to be byte-identical across runs over unchanged inputs.
    Used by the re-run comparison and directly testable."""
    return {key: value for key, value in payload.items() if key not in VOLATILE_FIELDS}


def write_provenance(data_dir: Path, payload: dict) -> Path:
    """Deterministic serialisation: sorted keys, two-space indent, trailing
    newline. Two runs over unchanged inputs differ only in VOLATILE_FIELDS."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / PROVENANCE_NAME
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def snapshot(
    *,
    data_dir: Path,
    input_paths: list[Path],
    source_page: str,
    description: str,
    limitations: list[str],
    data_url: str | None = None,
    transform: str | None = None,
    retrieved_at: str | None = None,
) -> SnapshotResult:
    """Copy declared inputs into the visual's data directory and record their
    provenance (criterion 4). Raises SnapshotError before copying anything when
    the contract is not met — a partial snapshot is worse than none."""
    if not input_paths:
        raise SnapshotError(
            "no inputs declared; to pass: pass at least one --input PATH"
        )
    missing = [str(path) for path in input_paths if not path.is_file()]
    if missing:
        raise SnapshotError(
            f"declared input(s) do not exist: {', '.join(missing)}; to pass: "
            "retrieve them first — snapshot records inputs, it does not fetch them"
        )

    records = [
        describe_input(
            path, source_page=source_page, data_url=data_url, transform=transform
        )
        for path in input_paths
    ]
    names = [record["name"] for record in records]
    if len(set(names)) != len(names):
        raise SnapshotError(
            "two declared inputs share a filename and would overwrite each other "
            f"in the data directory: {', '.join(sorted(names))}; to pass: rename one"
        )

    # Built before any copy, so a contract violation leaves the tree untouched.
    now = _now()
    payload = build_provenance(
        inputs=records,
        description=description,
        limitations=limitations,
        retrieved_at=retrieved_at or now,
        ingested_at=now,
    )

    previous = read_provenance(data_dir)
    changes = digest_changes(previous, payload)

    data_dir.mkdir(parents=True, exist_ok=True)
    for path in input_paths:
        destination = data_dir / path.name
        if destination.resolve() != path.resolve():
            shutil.copy2(path, destination)

    provenance_path = write_provenance(data_dir, payload)
    return SnapshotResult(
        data_dir=data_dir,
        provenance_path=provenance_path,
        inputs=tuple(names),
        changes=changes,
        first_snapshot=previous is None,
    )
