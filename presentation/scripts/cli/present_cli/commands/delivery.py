"""`present delivery record|list` (task 0011; ADR 0004; specification §8).

The default assumption is that latest was delivered; the record pins what latest *was*, because
latest keeps moving. Nothing is copied into the repository: versions are immutable.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .. import formats, schemas, store
from ..console import Effects, Result, leaf
from ..context import load_talk, require_repo, require_talk, today

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def snapshot(art: Path) -> dict[str, Any] | None:
    """{version, approved, receipt_sha256} for an artifact's latest version, or None."""
    if not art.is_dir():
        return None
    v = store.latest(art)
    if v is None:
        return None
    return {
        "version": v,
        "approved": v in store.approved_versions(art),
        "receipt_sha256": store.receipt_digest(art, v),
    }


def _configure_record(p):
    p.add_argument(
        "talk",
        nargs="?",
        help="talk folder; default the talk containing the working directory",
    )
    p.add_argument(
        "--module", action="append", help="record only these modules (repeatable)"
    )
    p.add_argument("--date", help="YYYY-MM-DD (default today)")
    p.add_argument("--note")
    p.add_argument(
        "--materialize",
        type=Path,
        metavar="DIR",
        help="also write speaking copies and deck files to DIR, outside the repository",
    )


@leaf(
    "delivery",
    "record",
    summary="record what was latest when a talk was delivered",
    task="0011",
    configure=_configure_record,
    effects=Effects(
        writes=True,
        description="Writes one delivery/<date>[-<module>].yaml (never overwrites); "
        "--materialize copies outputs to a directory outside the repository.",
    ),
)
def delivery_record(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    talk = require_talk(res, repo, ns.talk)
    if talk is None:
        return res
    data = load_talk(res, talk)
    if data is None:
        return res
    date = ns.date or today().isoformat()
    if not DATE.match(date):
        return res.error(
            "argument_invalid", f"--date must be YYYY-MM-DD: {date!r}", repairable=True
        )
    declared = {m["id"]: m for m in data["modules"]}
    wanted = ns.module or list(declared)
    unknown = [m for m in wanted if m not in declared]
    if unknown:
        return res.error(
            "module_unknown",
            f"not declared in talk.yaml: {', '.join(unknown)}",
            repairable=True,
            next=f"present talk status {talk.name}",
        )
    if ns.materialize is not None:
        target = ns.materialize.resolve()
        if target == repo.root.resolve() or repo.root.resolve() in target.parents:
            return res.error(
                "materialize_inside_repo",
                f"{ns.materialize} is inside the repository; "
                "materialised copies belong outside the tracked tree.",
                repairable=True,
                next="--materialize /media/usb/talk or another directory outside the repo",
            )
    modules: dict[str, Any] = {}
    unversioned = []
    try:
        for mid in wanted:
            entry: dict[str, Any] = {}
            for kind in ("script", "deck"):
                if declared[mid][kind]:
                    snap = snapshot(talk / "modules" / mid / kind)
                    if snap is not None:
                        entry[kind] = snap
            if entry:
                modules[mid] = entry
            else:
                unversioned.append(mid)
    except store.StoreError as exc:
        return res.error(
            exc.code, exc.message, repairable=exc.repairable, next=exc.next
        )
    suffix = f"-{wanted[0]}" if ns.module and len(wanted) == 1 else ""
    path = talk / "delivery" / f"{date}{suffix}.yaml"
    if path.exists():
        return res.error(
            "delivery_exists",
            f"{repo.rel(path)} already exists; delivery records are immutable.",
            repairable=True,
            next="--module <id> for a per-module record, or --date",
        )
    from ..context import now_iso

    record = {
        "schema_version": 1,
        "talk": data["id"],
        "date": date,
        "recorded": now_iso(),
        "modules": modules,
    }
    if ns.note:
        record["note"] = ns.note
    errs = schemas.errors("delivery", record)
    if errs:
        return res.error("delivery_invalid", f"internal: {errs[0]}", repairable=False)
    for mid in unversioned:
        res.warn(
            "nothing_versioned",
            f"module {mid} has no script or deck version; recorded as delivered "
            "without artifacts.",
            next=f"present script bump {talk.name}/{mid} --note …",
        )
    for mid, e in modules.items():
        for kind, snap in e.items():
            if not snap["approved"]:
                res.warn(
                    "delivered_unapproved",
                    f"{mid} {kind} v{snap['version']} is not approved; recorded as "
                    "approved: false.",
                )
    path.parent.mkdir(exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(record, sort_keys=False, allow_unicode=True))
    (path.parent / ".gitkeep").unlink(missing_ok=True)
    res.data = {"record": repo.rel(path), **record}
    res.text.append(
        f"recorded {repo.rel(path)}: "
        + (
            ", ".join(
                f"{mid} "
                + " ".join(
                    f"{k} {s['version']}{'' if s['approved'] else ' (unapproved)'}"
                    for k, s in e.items()
                )
                for mid, e in modules.items()
            )
            or "no versioned artifacts"
        )
    )
    if data["status"] != "delivered":
        res.text.append(
            f"next: set status: delivered in {talk.name}/audience/talk.yaml, then `present talk readme`"
        )
    if ns.materialize is not None:
        res.data["materialized"] = materialize(
            talk, modules, ns.materialize.resolve() / talk.name / date
        )
        res.text.append(
            f"materialised {len(res.data['materialized'])} file(s) to {ns.materialize}"
        )
    return res


MATERIAL = {
    "script": ("speaking.md", "notes.md"),
    "deck": ("deck.pptx", "deck.pdf", "contact-sheet.png"),
}


def materialize(talk: Path, modules: dict[str, Any], dest: Path) -> list[str]:
    written = []
    for mid, e in modules.items():
        for kind, snap in e.items():
            vdir = talk / "modules" / mid / kind / f"v{snap['version']}"
            for name in MATERIAL[kind]:
                src = vdir / name
                if src.is_file():
                    out = dest / mid / f"{kind}-{snap['version']}-{name}"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if out.exists():
                        continue  # never overwrite
                    shutil.copyfile(src, out)
                    written.append(str(out))
    return written


def _configure_list(p):
    p.add_argument("talk", nargs="?")


@leaf(
    "delivery",
    "list",
    summary="list delivery records",
    task="0011",
    configure=_configure_list,
    effects=Effects(description="Reads one talk's delivery/ folder."),
)
def delivery_list(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    talk = require_talk(res, repo, ns.talk)
    if talk is None:
        return res
    records = []
    for p in sorted((talk / "delivery").glob("*.y*ml")):
        data = formats.load(p)
        errs = schemas.errors("delivery", data)
        records.append(
            {
                "file": repo.rel(p),
                "valid": not errs,
                "errors": errs,
                **(
                    {"date": data.get("date"), "modules": data.get("modules", {})}
                    if isinstance(data, dict)
                    else {}
                ),
            }
        )
        if errs:
            res.warn("delivery_invalid", f"{repo.rel(p)}: {errs[0]}")
    res.data = {"talk": talk.name, "records": records}
    for r in records:
        mods = r.get("modules", {})
        res.text.append(
            f"{r['file']}: "
            + (
                ", ".join(
                    f"{mid} " + " ".join(f"{k} {s['version']}" for k, s in e.items())
                    for mid, e in mods.items()
                )
                or "—"
            )
        )
    if not records:
        res.text.append(f"{talk.name}: no delivery records")
    return res
