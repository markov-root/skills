"""Deck data from `dataset:` references, as snapshots (task 0022; portfolio ADR 0006 decision 3).

A `slides.yaml` value may be a dataset reference, written in the canonical grammar
`dataset:<id>[@<release>][.<table>][#<key>]` (task 0024); the aliases `data:` and the old
`/<table>` separator are accepted and never emitted — snapshots and receipts record the
canonical form:

- `"dataset:<id>[@<release>].<table>"` → the table's rows, a list of row mappings;
- `"dataset:<id>[@<release>].<table>#<key>"` → that one row, a mapping;
- `{from: "dataset:…", column: <name>}` → that column only (a list for a table, a value for a row).

Before a build the CLI process snapshots each reference into the deck's `src/data/` as one JSON
file holding the release, every row's Datasets reference and the rows, and records it in
`src/data/datasets.lock.json` with the file's sha256. A later build reuses the lock entry and never
queries the datasets CLI again, so a rebuild runs without it. The lock is a lockfile: an unpinned
reference keeps the release it was first snapshotted at until its lock entry is removed. The
worker swaps each reference for the snapshot's rows (`substitute`); this module binds no brand.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import references

LOCK = "data/datasets.lock.json"
SELECT_LIMIT = "10000"


class SnapshotError(Exception):
    def __init__(self, code: str, message: str, next: str | None = None):
        super().__init__(message)
        self.code, self.message, self.next = code, message, next


def _ref_of(value: Any) -> tuple[str, str | None] | None:
    """(reference text, column) when `value` is a deck data reference; `data:` is an
    accepted alias of the canonical `dataset:` prefix."""
    if isinstance(value, str) and value.startswith(("dataset:", "data:")):
        return value, None
    if (
        isinstance(value, dict)
        and isinstance(value.get("from"), str)
        and value["from"].startswith(("dataset:", "data:"))
        and set(value) <= {"from", "column"}
    ):
        return value["from"], value.get("column")
    return None


def collect(slides: Any) -> list[str]:
    """Every distinct dataset reference in a parsed slides.yaml, in file order."""
    found: list[str] = []

    def walk(v: Any) -> None:
        hit = _ref_of(v)
        if hit is not None:
            if hit[0] not in found:
                found.append(hit[0])
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(slides)
    return found


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _filename(ref: references.Ref, release: str) -> str:
    name = f"{ref.target}@{release}.{ref.table}"
    if ref.row:
        name += "." + hashlib.sha256(ref.row.encode()).hexdigest()[:12]
    return f"data/{name}.json"


def _fetch(ref: references.Ref, resolver: references.Resolver) -> dict[str, Any]:
    """The snapshot document for one reference, through `datasets releases` and `select`/`get`."""
    if not ref.table:
        raise SnapshotError(
            "data_reference_invalid",
            f"{ref.raw}: deck data needs a table "
            "(dataset:<id>[@<release>].<table>[#<key>])",
        )
    r = resolver.resolve(ref)
    if r.status == "unavailable":
        raise SnapshotError(
            "capability_unavailable",
            f"{ref.raw} has no snapshot yet and {r.message or 'the datasets CLI is unavailable'}",
            next=references.install_hint("datasets"),
        )
    if r.status != "ok":
        raise SnapshotError("source_unresolved", f"{ref.raw}: {r.message}")
    release = r.cited
    if ref.row:
        code, env = resolver.call("datasets", "get", references.row_ref(ref, release))
        items = [((env or {}).get("data") or {}).get("result") or {}]
    else:
        code, env = resolver.call(
            "datasets",
            "select",
            f"{ref.target}@{release}.{ref.table}",
            "--limit",
            SELECT_LIMIT,
        )
        items = [
            i.get("record") or {}
            for i in ((env or {}).get("data") or {}).get("items") or []
        ]
    if env is None:
        raise SnapshotError(
            "capability_unavailable",
            resolver.unavailable.get("datasets", ""),
            next=references.install_hint("datasets"),
        )
    meta = ((env.get("data") or {}).get("meta") or {}) if env else {}
    # datasets contract 0.5 (research ADR 0008): a JSON page with more rows exits 0 with
    # meta.complete false; contract 0.4 exited 8. Accept both.
    if code == 8 or (code == 0 and meta.get("complete") is False):
        raise SnapshotError(
            "data_too_large",
            f"{ref.raw}: more than {SELECT_LIMIT} rows; cite a smaller table",
        )
    if code != 0:
        raise SnapshotError("source_unresolved", references._diagnostic(env, ref.raw))
    prov = (((env.get("data") or {}).get("meta") or {}).get("provenance") or {}).get(
        ref.target
    )
    return {
        "schema_version": 1,
        "reference": ref.text(),  # canonical form, whatever alias the slide wrote
        "dataset": ref.target,
        "release": release,
        "table": ref.table,
        "row": ref.row,
        "provenance": prov,
        "rows": [{"ref": i.get("ref"), "row": i.get("row")} for i in items],
    }


def prepare(
    src: Path,
    slides: Any,
    *,
    out: Path,
    write: bool,
    resolver: references.Resolver | None = None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Snapshot every dataset reference in `slides`.

    Returns ({reference: absolute snapshot path}, receipt records). With `write`, new snapshots and
    the lock go into `src/data/`; otherwise (a dry run) new snapshots go under `out` and the
    repository is untouched. Raises SnapshotError before anything is built.
    """
    wanted = collect(slides)
    if not wanted:
        return {}, []
    lock_path = src / LOCK
    lock = (
        json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}
    )
    entries: dict[str, Any] = dict(lock.get("snapshots") or {})
    resolver = resolver or references.Resolver()
    mapping: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    changed = False
    for text in wanted:
        ref = references.parse_one(text)
        if ref is None or ref.kind != "dataset":
            raise SnapshotError(
                "data_reference_invalid", f"{text!r} is not a dataset: reference"
            )
        entry = entries.get(text)
        if entry is not None:
            p = src / entry["path"]
            if not p.is_file():
                raise SnapshotError(
                    "snapshot_missing",
                    f"{entry['path']} (snapshot of {text}) is missing",
                    next=f"restore it, or remove {text!r} from src/{LOCK} to snapshot again",
                )
            if _sha(p) != entry["sha256"]:
                raise SnapshotError(
                    "snapshot_changed",
                    f"src/{entry['path']} no longer matches its lock hash",
                    next=f"restore it, or remove {text!r} from src/{LOCK} to snapshot again",
                )
            mapping[text] = str(p)
        else:
            doc = _fetch(ref, resolver)
            rel = _filename(ref, doc["release"])
            body = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            dest = (src if write else out) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
            entry = {
                "dataset": doc["dataset"],
                "release": doc["release"],
                "table": doc["table"],
                "row": doc["row"],
                "path": rel,
                "rows": len(doc["rows"]),
                "sha256": _sha(dest),
            }
            entries[text] = entry
            mapping[text] = str(dest)
            changed = True
        records.append(
            {
                "reference": ref.text(),  # canonical form, whatever alias the slide wrote
                **{
                    k: entry[k]
                    for k in ("dataset", "release", "table", "path", "rows", "sha256")
                },
                **({"row": entry["row"]} if entry.get("row") else {}),
            }
        )
    if changed and write:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(
            json.dumps(
                {"schema_version": 1, "snapshots": entries}, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
    return mapping, records


def substitute(slides: Any, mapping: dict[str, str], src: Path) -> tuple[Any, set[str]]:
    """(slides with every dataset reference replaced by its snapshot rows, src-relative files used).

    Runs in the worker; a reference without a snapshot raises ValueError naming it."""
    used: set[str] = set()
    cache: dict[str, Any] = {}

    def rows_of(text: str) -> Any:
        if text not in mapping:
            raise ValueError(f"{text}: no snapshot (the build did not prepare it)")
        if text not in cache:
            p = Path(mapping[text])
            cache[text] = json.loads(p.read_text(encoding="utf-8"))
            try:
                used.add(p.resolve().relative_to(src.resolve()).as_posix())
            except ValueError:
                pass  # a dry run's staged snapshot is outside src/
        return cache[text]

    def walk(v: Any) -> Any:
        hit = _ref_of(v)
        if hit is not None:
            doc = rows_of(hit[0])
            rows = [r["row"] for r in doc["rows"]]
            col = hit[1]
            if col is not None:
                missing = [i for i, r in enumerate(rows) if col not in r]
                if missing:
                    raise ValueError(f"{hit[0]}: no column {col!r}")
                rows = [r[col] for r in rows]
            if doc.get("row"):
                return rows[0] if rows else None
            return rows
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return walk(slides), used


def prepare_deck(
    src: Path, build_kind: str, *, out: Path, write: bool
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """`prepare` for a deck's src/slides.yaml; nothing for a build.py deck or unreadable YAML
    (the worker reports that one, naming the problem)."""
    import yaml

    if build_kind != "slides.yaml" or not (src / "slides.yaml").is_file():
        return {}, []
    try:
        slides = yaml.safe_load((src / "slides.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}, []
    return prepare(src, slides, out=out, write=write)
