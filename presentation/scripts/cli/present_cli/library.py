"""The repository library (task 0019; ADR 0011; specification §13).

Layout, under `[library] root` (default `library/`) of the consumer repository::

    library/slides/<id>/      library-slide.yaml   src/slides.yaml (+ data)   vX.Y.Z/   latest
                              approvals.yaml   CHANGELOG.md        — the store contract (§5)
    library/visuals/<slug>/   a visuals project item (source/, vX.Y.Z/, latest), plus an
                              optional library-visual.yaml

`library-slide.yaml` / `library-visual.yaml` follow `library-item.schema.json`: identity,
`retired`, `derived_from` and `promoted`. A slide item's `src/slides.yaml` is a fragment: one or
more declarative slides (no `use:`, no `component: custom`), with any `@data:` files beside it.

Talks pin, never copy: `use: library/slides/<id>@<selector>` in `slides.yaml`, and
`library: {<slug>: <selector>}` in `deck.yaml` for library visuals. A build resolves every
selector to an exact version and records it in the deck receipt.

This module holds no brand and no deck imports, so both the CLI process and the deck worker
import it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from . import formats, schemas, store

SLIDE_MANIFEST = "library-slide.yaml"
VISUAL_MANIFEST = "library-visual.yaml"
KINDS = {"slides": SLIDE_MANIFEST, "visuals": VISUAL_MANIFEST}
PIN = re.compile(r"^library/(slides|visuals)/([a-z0-9]+(?:-[a-z0-9]+)*)(?:@(.+))?$")


def root(repo) -> Path:
    return repo.root / str((repo.manifest.get("library") or {}).get("root", "library"))


def item_dir(repo, kind: str, ident: str) -> Path:
    return root(repo) / kind / ident


def pin_name(kind: str, ident: str) -> str:
    """The repository-independent name a pin uses (`library/<kind>/<id>`)."""
    return f"library/{kind}/{ident}"


def parse_ref(ref: str) -> tuple[str, str, str | None] | None:
    """`library/slides/x@latest` → ("slides", "x", "latest"); also accepts `slides/x`."""
    ref = ref.strip().rstrip("/")
    if not ref.startswith("library/"):
        ref = "library/" + ref
    m = PIN.match(ref)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def items(repo) -> list[dict[str, Any]]:
    out = []
    for kind in KINDS:
        base = root(repo) / kind
        if not base.is_dir():
            continue
        for d in sorted(
            p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
            out.append(
                {"kind": kind, "id": d.name, "name": pin_name(kind, d.name), "dir": d}
            )
    return out


def manifest(d: Path, kind: str) -> dict[str, Any]:
    """The item manifest; {} for a visual without one. Raises StoreError when invalid."""
    path = d / KINDS[kind]
    if not path.is_file():
        if kind == "slides":
            raise store.StoreError(
                "manifest_missing",
                f"{path.name} missing in {d.name}: a library slide needs one "
                "(schema_version: 1, id: <folder name>).",
            )
        return {}
    data = formats.load(path) or {}
    errs = schemas.errors("library-item", data)
    if errs:
        raise store.StoreError("manifest_invalid", f"{path.name}: {errs[0]}")
    if data["id"] != d.name:
        raise store.StoreError(
            "manifest_invalid",
            f"{path.name}: id {data['id']!r} differs from the folder {d.name!r}",
        )
    return data


def retired(d: Path, kind: str) -> bool:
    try:
        return bool(manifest(d, kind).get("retired"))
    except store.StoreError:
        return False


# --------------------------------------------------------------------------- resolution


def resolve(d: Path, selector: str, name: str) -> str:
    """Exact version for `latest` or `X.Y.Z`; StoreError `pin_unresolved` otherwise."""
    if not d.is_dir():
        raise store.StoreError(
            "pin_unresolved",
            f"{name}: no such library item.",
            next="present library list",
        )
    if selector == "latest":
        v = store.latest(d)
        if v is None:
            raise store.StoreError(
                "pin_unresolved",
                f"{name}@latest: the item has no version yet.",
                next=f"present library bump {name} --note …",
            )
        return v
    if selector not in store.complete_versions(d):
        raise store.StoreError(
            "pin_unresolved",
            f"{name}@{selector}: no such version.",
            next=f"present library show {name}",
        )
    return selector


def pin_record(repo, d: Path, selector: str, version: str) -> dict[str, str]:
    return {
        "selector": selector,
        "resolved": version,
        "path": repo.rel(d / f"v{version}" / store.RECEIPT),
        "sha256": store.receipt_digest(d, version),
    }


def resolve_deck(
    repo, slides: list[dict[str, Any]] | None, deck_manifest: dict[str, Any]
):
    """Resolve a deck's library pins. Returns (uses, pins, retired):

    - uses: {slide_id: frozen version folder} for the worker;
    - pins: receipt pins keyed by the pin text (`library/slides/<id>@<selector>`, or
      `library/visuals/<slug>` for deck.yaml's `library:` block);
    - retired: names of pinned items marked retired (a warning at build; blocking in validate).
    """
    uses: dict[str, str] = {}
    pins: dict[str, dict[str, str]] = {}
    gone: list[str] = []
    for sl in slides or []:
        if not isinstance(sl, dict) or "use" not in sl:
            continue
        parsed = parse_ref(str(sl["use"]))
        if parsed is None or parsed[0] != "slides" or parsed[2] is None:
            raise store.StoreError(
                "pin_unresolved",
                f"{sl.get('id')}: use {sl['use']!r} is not library/slides/<id>@<selector>",
            )
        _, ident, sel = parsed
        d = item_dir(repo, "slides", ident)
        v = resolve(d, sel, pin_name("slides", ident))
        uses[sl["id"]] = str(d / f"v{v}")
        pins[str(sl["use"])] = pin_record(repo, d, sel, v)
        if retired(d, "slides"):
            gone.append(pin_name("slides", ident))
    for slug, sel in (deck_manifest.get("library") or {}).items():
        d = item_dir(repo, "visuals", slug)
        v = resolve(d, sel, pin_name("visuals", slug))
        pins[pin_name("visuals", slug)] = pin_record(repo, d, sel, v)
        if retired(d, "visuals"):
            gone.append(pin_name("visuals", slug))
    return uses, pins, sorted(set(gone))


def load_slides(path: Path) -> list[Any] | None:
    """A slides.yaml as a list, or None when unreadable (the worker then reports why)."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, list) else None


# --------------------------------------------------------------------------- worker side


def fragment(vdir: Path) -> list[dict[str, Any]]:
    """The slides of one frozen library-slide version."""
    return (
        yaml.safe_load((Path(vdir) / "slides.yaml").read_text(encoding="utf-8")) or []
    )


def fragment_errors(sid: str, frag: Any) -> list[str]:
    errs = [f"{sid}: library fragment: {e}" for e in schemas.errors("slides", frag)]
    if errs:
        return errs
    for s in frag:
        if "use" in s:
            errs.append(
                f"{sid}: library fragment slide {s['id']} uses another library item (not allowed)"
            )
        elif s.get("component") == "custom":
            errs.append(
                f"{sid}: library fragment slide {s['id']} is component custom (library slides are declarative)"
            )
    return errs


# --------------------------------------------------------------------------- usage


def talk_pins(repo, talk: Path) -> list[dict[str, Any]]:
    """Every library pin in a talk's working decks: {name, selector, where}."""
    out = []
    mods = talk / "modules"
    for deck in sorted(mods.glob("*/deck")) if mods.is_dir() else []:
        sy = deck / "src" / "slides.yaml"
        if sy.is_file():
            try:
                slides = yaml.safe_load(sy.read_text(encoding="utf-8")) or []
            except yaml.YAMLError:
                slides = []
            for sl in slides if isinstance(slides, list) else []:
                if isinstance(sl, dict) and isinstance(sl.get("use"), str):
                    p = parse_ref(sl["use"])
                    if p:
                        out.append(
                            {
                                "name": pin_name(p[0], p[1]),
                                "selector": p[2] or "latest",
                                "where": f"{repo.rel_any(sy)}#{sl.get('id')}",
                            }
                        )
        dy = deck / "deck.yaml"
        if dy.is_file():
            try:
                m = formats.load(dy) or {}
            except Exception:
                m = {}
            for slug, sel in (
                (m.get("library") or {}) if isinstance(m, dict) else {}
            ).items():
                out.append(
                    {
                        "name": pin_name("visuals", slug),
                        "selector": str(sel),
                        "where": repo.rel_any(dy),
                    }
                )
    return out


def usage(repo) -> dict[str, list[str]]:
    """{item name: [where it is pinned]} across every standard talk."""
    out: dict[str, list[str]] = {}
    for talk in repo.talks():
        for p in talk_pins(repo, talk):
            out.setdefault(p["name"], []).append(p["where"])
    return out


def talk_findings(repo, talk: Path) -> list[dict[str, str]]:
    """Pins in a standard talk to retired or unresolvable library items (all blocking)."""
    out = []
    for p in talk_pins(repo, talk):
        kind, ident = p["name"].split("/")[1:]
        d = item_dir(repo, kind, ident)
        try:
            resolve(d, p["selector"], p["name"])
        except store.StoreError as exc:
            out.append(
                {
                    "code": "library_pin_unresolved",
                    "severity": "blocking",
                    "where": p["where"],
                    "message": exc.message,
                }
            )
            continue
        if retired(d, kind):
            note = (manifest(d, kind).get("retired_note") or "").strip()
            out.append(
                {
                    "code": "library_pin_retired",
                    "severity": "blocking",
                    "where": p["where"],
                    "message": f"pins {p['name']}, which is retired"
                    + (f": {note}" if note else ""),
                }
            )
    return out
