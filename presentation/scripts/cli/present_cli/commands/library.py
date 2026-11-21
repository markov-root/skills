"""`present library list|show|bump|promote` (task 0019; ADR 0011; specification §13).

Library slides follow the store contract (§5) with receipt kind `library-slide`; library visuals
are visuals projects moved under `library/visuals/` (their versions stay the visuals skill's).
Talks pin library items; `promote` moves a talk-local item into the library, records where it came
from, and rewrites the talk's pin, so no copy is left behind.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from .. import formats, library, store
from ..console import Effects, Result, leaf
from ..context import TALK_FILE, Repo, now_iso, require_artifact, require_repo

# Slide argument keys that name a file in the deck's src/ (mirrors deck.declare.IMAGE_ARGS, which
# this process must not import: importing the deck package binds a brand).
FILE_ARGS = ("png", "org_logo", "portrait_img")


def _err(res: Result, exc: store.StoreError) -> Result:
    return res.error(exc.code, exc.message, repairable=exc.repairable, next=exc.next)


def _versions(d: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "versions": store.complete_versions(d),
        "latest": None,
        "problems": [],
    }
    try:
        out["latest"] = store.latest(d)
    except store.StoreError as exc:
        out["problems"].append({"code": exc.code, "message": exc.message})
    return out


def _describe(
    repo: Repo, it: dict[str, Any], used: dict[str, list[str]]
) -> dict[str, Any]:
    d: Path = it["dir"]
    row: dict[str, Any] = {
        "name": it["name"],
        "kind": it["kind"],
        "id": it["id"],
        "path": repo.rel(d),
    }
    try:
        m = library.manifest(d, it["kind"])
        row["manifest_problem"] = None
    except store.StoreError as exc:
        m, row["manifest_problem"] = {}, exc.message
    row.update(
        title=m.get("title"),
        retired=bool(m.get("retired")),
        retired_note=m.get("retired_note"),
        derived_from=m.get("derived_from"),
        used_by=used.get(it["name"], []),
        **_versions(d),
    )
    return row


def _find(res: Result, repo: Repo, ref: str) -> dict[str, Any] | None:
    parsed = library.parse_ref(ref)
    if parsed is None:
        res.error(
            "item_not_found",
            f"{ref!r} is not library/slides/<id> or library/visuals/<slug>.",
            repairable=True,
            next="present library list",
        )
        return None
    kind, ident, _sel = parsed
    d = library.item_dir(repo, kind, ident)
    if not d.is_dir():
        res.error(
            "item_not_found",
            f"no library item {library.pin_name(kind, ident)}.",
            repairable=True,
            next="present library list",
        )
        return None
    return {"kind": kind, "id": ident, "name": library.pin_name(kind, ident), "dir": d}


# --------------------------------------------------------------------------- list / show


def _configure_list(p):
    p.add_argument(
        "--kind", choices=tuple(library.KINDS), help="only slides or only visuals"
    )


@leaf(
    "library",
    "list",
    summary="list library items, their versions and the talks that pin them",
    task="0019",
    configure=_configure_list,
    effects=Effects(description="Reads library/ and every talk's deck pins."),
)
def library_list(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    used = library.usage(repo)
    rows = [
        _describe(repo, it, used)
        for it in library.items(repo)
        if not ns.kind or it["kind"] == ns.kind
    ]
    res.data = {"root": repo.rel_any(library.root(repo)), "items": rows}
    if not rows:
        res.text.append(f"no library items under {repo.rel_any(library.root(repo))}/")
    for r in rows:
        res.text.append(
            f"{r['name']:<40} latest {r['latest'] or '-':<8} {len(r['versions'])} version(s) · "
            f"used by {len(r['used_by'])}" + (" · RETIRED" if r["retired"] else "")
        )
    return res


def _configure_show(p):
    p.add_argument("item", help="library/slides/<id> or library/visuals/<slug>")
    p.add_argument("--version", help="default: latest")


@leaf(
    "library",
    "show",
    summary="show a library item: manifest, versions, receipt and users",
    task="0019",
    configure=_configure_show,
    effects=Effects(description="Reads one library item and every talk's deck pins."),
)
def library_show(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    it = _find(res, repo, ns.item)
    if it is None:
        return res
    row = _describe(repo, it, library.usage(repo))
    version = ns.version or row["latest"]
    if version is not None:
        try:
            row["receipt"] = store.receipt(it["dir"], version)
        except store.StoreError as exc:
            return _err(res, exc)
        row["version"] = version
    res.data = row
    res.text.append(
        f"{row['name']} ({row['path']}): latest {row['latest'] or 'none'}; "
        f"versions {', '.join(row['versions']) or 'none'}"
    )
    if row["retired"]:
        res.text.append(
            f"  RETIRED{': ' + row['retired_note'] if row['retired_note'] else ''}"
        )
    if row["derived_from"]:
        res.text.append(f"  derived from {row['derived_from']}")
    res.text.append(f"  used by: {', '.join(row['used_by']) or 'no talk'}")
    if row["manifest_problem"]:
        res.warn("manifest_invalid", row["manifest_problem"])
    for p in row["problems"]:
        res.warn(p["code"], p["message"])
    return res


# --------------------------------------------------------------------------- bump


def _configure_bump(p):
    p.add_argument("item", help="library/slides/<id>")
    p.add_argument("--level", choices=store.LEVELS, default="patch")
    p.add_argument("--note", required=True, help="one line for the item's CHANGELOG")
    p.add_argument("--version", help="explicit next version (default: from --level)")


def _bump_slide(
    repo: Repo, d: Path, *, level: str, note: str, version: str | None = None
):
    m = library.manifest(d, "slides")
    if m.get("retired"):
        raise store.StoreError(
            "item_retired",
            f"{d.name} is retired; a retired item takes no new versions.",
            next="create a new item, or set retired: false deliberately",
        )
    frag = library.load_slides(d / "src" / "slides.yaml")
    errs = (
        library.fragment_errors(d.name, frag)
        if frag is not None
        else [f"{d.name}: src/slides.yaml is missing or not a list of slides"]
    )
    if errs:
        raise store.StoreError("fragment_invalid", errs[0])

    def produce(art: Path, vdir: Path) -> None:
        store.copy_tree(art / "src", vdir)

    return store.bump(
        repo.root,
        d,
        kind="library-slide",
        level=level,
        note=note,
        produce=produce,
        version=version,
        standard=repo.standard,
        extra_inputs=[d / library.SLIDE_MANIFEST],
    )


@leaf(
    "library",
    "bump",
    summary="freeze a library slide's src/ into its next version",
    task="0019",
    configure=_configure_bump,
    effects=Effects(
        writes=True,
        description="Writes one version folder and receipt, moves latest, "
        "appends the item's CHANGELOG. Talks pinning @latest change at their next build.",
    ),
)
def library_bump(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    it = _find(res, repo, ns.item)
    if it is None:
        return res
    if it["kind"] != "slides":
        return res.error(
            "wrong_kind",
            "library visuals are versioned by the visuals skill "
            "(visuals bump/publish), not by present.",
            repairable=True,
        )
    try:
        out = _bump_slide(
            repo, it["dir"], level=ns.level, note=ns.note, version=ns.version
        )
    except store.StoreError as exc:
        return _err(res, exc)
    used = library.usage(repo).get(it["name"], [])
    res.data = {
        "item": it["name"],
        "version": out.version,
        "previous": out.previous,
        "receipt": repo.rel(out.path / store.RECEIPT),
        "used_by": used,
    }
    res.text.append(
        f"{it['name']}: v{out.version}; pinned by {len(used)} slide(s), which pick it up "
        "at their next build when they pin @latest"
    )
    return res


# --------------------------------------------------------------------------- promote


def _configure_promote(p):
    p.add_argument(
        "item",
        help="a talk visual (<talk>/visuals/<slug>), or with --slide a deck "
        "(<talk>/<module>)",
    )
    p.add_argument("--slide", help="promote this slide ID of the deck's slides.yaml")
    p.add_argument(
        "--as", dest="as_id", help="library id (default: the slug or slide ID)"
    )
    p.add_argument("--note", help="the first version's note (slides)")


def _file_refs(value: Any, key: str | None = None) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            out |= _file_refs(v, k)
    elif isinstance(value, list):
        for v in value:
            out |= _file_refs(v)
    elif isinstance(value, str):
        if value.startswith("@data:"):
            out.add(value[len("@data:") :])
        elif key in FILE_ARGS:
            out.add(value)
    return out


def _dump_keeping_header(path: Path, data: Any) -> None:
    """Rewrite a YAML file, keeping its leading comment block (the rest is regenerated)."""
    head = []
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        if not line.startswith("#"):
            break
        head.append(line)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        "".join(head) + yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _write_manifest(d: Path, kind: str, ident: str, derived: str, origin: str) -> None:
    doc = {
        "schema_version": 1,
        "id": ident,
        "retired": False,
        "derived_from": derived,
        "promoted": {"from": origin, "at": now_iso()},
    }
    (d / library.KINDS[kind]).write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8"
    )


def _promote_visual(res: Result, repo: Repo, src: Path, ident: str) -> Result:
    talk = src.parent.parent
    slug = src.name
    dest = library.item_dir(repo, "visuals", ident)
    if dest.exists():
        return res.error(
            "item_exists", f"{repo.rel_any(dest)} already exists.", repairable=False
        )
    try:
        latest = store.latest(src)
    except store.StoreError:
        latest = None
    origin = repo.rel(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(
        dest
    )  # a move, never a copy: the history (versions, latest) travels with it
    _write_manifest(
        dest, "visuals", ident, f"{origin}@{latest}" if latest else origin, origin
    )
    rewritten = []
    for t in repo.talks():
        for dy in sorted((t / "modules").glob("*/deck/deck.yaml")):
            m = formats.load(dy) or {}
            vis = dict(m.get("visuals") or {})
            keys = [k for k in vis if k == origin or (t == talk and k == slug)]
            if not keys:
                continue
            lib = dict(m.get("library") or {})
            for k in keys:
                lib[ident] = vis.pop(k)
            m = {**m, "library": lib}
            if vis:
                m["visuals"] = vis
            else:
                m.pop("visuals", None)
            _dump_keeping_header(dy, m)
            rewritten.append(repo.rel(dy))
    res.data = {
        "item": library.pin_name("visuals", ident),
        "from": origin,
        "path": repo.rel(dest),
        "rewritten": rewritten,
    }
    res.text.append(
        f"moved {origin} → {repo.rel(dest)}; pins rewritten in "
        f"{', '.join(rewritten) or 'no deck'}"
    )
    return res


def _promote_slide(
    res: Result, repo: Repo, art: Path, sid: str, ident: str, note: str | None
) -> Result:
    sy = art / "src" / "slides.yaml"
    slides = library.load_slides(sy)
    if slides is None:
        return res.error(
            "src_missing",
            f"{repo.rel_any(sy)} is missing or not a list.",
            repairable=True,
        )
    idx = next(
        (i for i, s in enumerate(slides) if isinstance(s, dict) and s.get("id") == sid),
        None,
    )
    if idx is None:
        return res.error(
            "slide_not_found", f"{repo.rel(sy)} has no slide {sid!r}.", repairable=True
        )
    sl = slides[idx]
    if "use" in sl or sl.get("component") == "custom":
        return res.error(
            "slide_not_promotable",
            f"{sid}: only declarative component slides can be "
            "promoted (not use: or component: custom).",
            repairable=False,
        )
    bad = library.fragment_errors(sid, [sl])
    if bad:
        return res.error("fragment_invalid", bad[0], repairable=True)
    dest = library.item_dir(repo, "slides", ident)
    if dest.exists():
        return res.error(
            "item_exists", f"{repo.rel_any(dest)} already exists.", repairable=False
        )
    refs = _file_refs(sl.get("with", {}))
    others: set[str] = set()
    for i, s in enumerate(slides):
        if i != idx and isinstance(s, dict):
            others |= _file_refs(s.get("with", {}))
    for r in refs:
        if not (art / "src" / r).is_file():
            return res.error(
                "file_missing",
                f"{sid} names {r}, which is not in {repo.rel(art)}/src/.",
                repairable=True,
            )
    try:
        latest = store.latest(art)
    except store.StoreError:
        latest = None
    origin = repo.rel(art)
    (dest / "src").mkdir(parents=True)
    moved, copied = [], []
    for r in sorted(refs):
        target = dest / "src" / r
        target.parent.mkdir(parents=True, exist_ok=True)
        if r in others:  # still used by another slide of this deck: it must stay
            shutil.copyfile(art / "src" / r, target)
            copied.append(r)
        else:
            (art / "src" / r).rename(target)
            moved.append(r)
    (dest / "src" / "slides.yaml").write_text(
        yaml.safe_dump([sl], sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    _write_manifest(
        dest,
        "slides",
        ident,
        f"{origin}@{latest}" if latest else origin,
        f"{repo.rel(sy)}#{sid}",
    )
    try:
        out = _bump_slide(
            repo,
            dest,
            level="major",
            note=note or f"promoted from {origin} slide {sid}",
        )
    except store.StoreError as exc:
        return _err(res, exc)
    use = f"{library.pin_name('slides', ident)}@latest"
    slides[idx] = {"id": sid, "use": use}
    _dump_keeping_header(sy, slides)
    if copied:
        res.warn(
            "data_shared",
            f"{', '.join(copied)} also used by other slides of {origin}: copied, "
            "not moved.",
            next="pin the library slide from those slides too, then remove the file",
        )
    res.data = {
        "item": library.pin_name("slides", ident),
        "from": f"{repo.rel(sy)}#{sid}",
        "path": repo.rel(dest),
        "version": out.version,
        "use": use,
        "moved": moved,
        "copied": copied,
    }
    res.text.append(
        f"{repo.rel(sy)}#{sid} → {repo.rel(dest)} v{out.version}; the slide now reads "
        f"use: {use}"
    )
    return res


@leaf(
    "library",
    "promote",
    summary="move a talk-local slide or visual into the library",
    task="0019",
    configure=_configure_promote,
    effects=Effects(
        writes=True,
        description="Moves files into library/ (no copy left behind), "
        "records derived_from, rewrites the talk's pin; a slide gets its first version.",
    ),
)
def library_promote(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    lib_root = library.root(repo).resolve()
    if ns.slide:
        art = require_artifact(res, repo, ns.item, "deck")
        if art is None:
            return res
        ident = ns.as_id or ns.slide
    else:
        cands = [Path.cwd() / ns.item, repo.root / ns.item]
        src = next((c.resolve() for c in cands if c.is_dir()), None)
        if (
            src is None
            or src.parent.name != "visuals"
            or not (src.parent.parent / TALK_FILE).is_file()
            or lib_root in src.parents
        ):
            return res.error(
                "item_not_promotable",
                f"{ns.item}: expected a talk visual "
                "<talk>/visuals/<slug> (or a deck with --slide <id>).",
                repairable=True,
            )
        ident = ns.as_id or src.name
    if library.parse_ref(f"slides/{ident}") is None:
        return res.error(
            "id_invalid",
            f"{ident!r} is not a lowercase hyphenated id.",
            repairable=True,
            next="pass --as <id>",
        )
    if ns.slide:
        return _promote_slide(res, repo, art, ns.slide, ident, ns.note)
    return _promote_visual(res, repo, src, ident)
