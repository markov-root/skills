"""`present deck new|import|build|approve|show|check` (tasks 0008, 0017; ADRs 0004, 0007, 0009).

A deck is native editable pptx built from `src/slides.yaml` through the component library (or
from `src/build.py`, the escape hatch). Builds resolve their pins (the script version, the brand
tokens) and record them in the receipt; speaker notes come from the resolved script version.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .. import SKILL_ROOT, annotate, datasnap, formats, library, schemas, store
from ..console import Effects, Result, leaf
from ..context import Repo, require_artifact, require_repo
from . import script as script_cmd

COMPONENT_SCHEMAS = SKILL_ROOT / "assets" / "schemas" / "components"
DECK_FILES = ("deck.pptx", "deck.pdf", "contact-sheet.png", "slides.json")


def _start(res: Result, ns, *, must_exist: bool = True) -> tuple[Repo, Path] | None:
    repo = require_repo(res)
    if repo is None:
        return None
    art = require_artifact(res, repo, ns.ref, "deck", must_exist=must_exist)
    if art is None:
        return None
    return repo, art


def _err(res: Result, exc: store.StoreError) -> Result:
    return res.error(exc.code, exc.message, repairable=exc.repairable, next=exc.next)


def manifest(art: Path) -> dict[str, Any]:
    data = formats.load(art / "deck.yaml") or {}
    errs = schemas.errors("deck", data)
    if errs:
        raise store.StoreError("manifest_invalid", f"deck.yaml: {errs[0]}")
    return data


def tokens_file(repo: Repo) -> Path | None:
    rel = (repo.manifest.get("brand") or {}).get("tokens")
    return (repo.root / rel) if rel and (repo.root / rel).is_file() else None


# --------------------------------------------------------------------------- pins and notes


def resolve_script(art: Path, selector: str) -> tuple[Path, str] | None:
    """(script artifact, exact version) for a deck's `script:` selector; None for `none`."""
    if selector == "none":
        return None
    sart = art.parent / "script"
    if not (sart / "script.yaml").is_file():
        raise store.StoreError(
            "pin_unresolved",
            f"deck.yaml pins script {selector!r} but this module has no "
            "script artifact.",
            next="set script: none, or present script new <talk>/<module>",
        )
    if selector == "latest":
        v = store.latest(sart)
        if v is None:
            raise store.StoreError(
                "pin_unresolved",
                "script: latest, but the script has no version yet.",
                next="present script bump <ref> --note …",
            )
        return sart, v
    if selector not in store.complete_versions(sart):
        raise store.StoreError(
            "pin_unresolved",
            f"script version {selector} does not exist.",
            next="present script show <ref>",
        )
    return sart, selector


def notes_from(sart: Path, version: str) -> dict[str, str]:
    """Speaker notes per slide ID: the version's spoken text, then its note and cue annotations."""
    vdir = sart / f"v{version}"
    sc = annotate.parse_script((vdir / "script.md").read_text(encoding="utf-8"))
    resolved = (
        json.loads((vdir / "annotations.json").read_text(encoding="utf-8"))
        if (vdir / "annotations.json").is_file()
        else []
    )
    out = {}
    for sec in sc.sections:
        text = sec.body.strip()
        extra = [
            f"{a['kind'].capitalize()}: {a['text']}"
            for a in resolved
            if a["slide"] == sec.slide and a["kind"] in ("note", "cue")
        ]
        out[sec.slide] = text + ("\n\n" + "\n".join(extra) if extra else "")
    return out


def script_headings(art: Path, selector: str) -> list[str] | None:
    try:
        got = resolve_script(art, selector)
    except store.StoreError:
        got = None
    if got is not None:
        sart, v = got
        return [
            s.slide
            for s in annotate.parse_script(
                (sart / f"v{v}" / "script.md").read_text()
            ).sections
        ]
    sart = art.parent / "script"
    if (sart / "script.yaml").is_file():
        try:
            return [
                s.slide
                for s in annotate.parse_script(script_cmd.script_text(sart)).sections
            ]
        except store.StoreError:
            return None
    return None


# --------------------------------------------------------------------------- new

EXAMPLE_SLIDE = {
    "component": "one_thing",
    "with": {"lead": "Replace this lead,", "rest": "and this rest."},
}


def _configure_new(p):
    script_cmd._ref(p)


@leaf(
    "deck",
    "new",
    summary="create a deck artifact in a module",
    task="0008",
    configure=_configure_new,
    effects=Effects(
        writes=True,
        description="Writes deck.yaml and a working src/slides.yaml; never overwrites.",
    ),
)
def deck_new(ns, res: Result) -> Result:
    got = _start(res, ns, must_exist=False)
    if got is None:
        return res
    repo, art = got
    if (art / "deck.yaml").exists():
        return res.error(
            "artifact_exists",
            f"{repo.rel(art)}/deck.yaml already exists.",
            repairable=False,
        )
    has_script = (art.parent / "script" / "script.yaml").is_file()
    heads = script_headings(art, "latest") if has_script else None
    ids = heads or ["opening"]
    slides = [{"id": i, **json.loads(json.dumps(EXAMPLE_SLIDE))} for i in ids]
    slides[0]["with"]["kicker"] = (
        "Example: one slide per script heading; edit components and arguments"
    )
    (art / "src").mkdir(parents=True, exist_ok=True)
    files = {
        "deck.yaml": yaml.safe_dump(
            {"schema_version": 1, "script": "latest" if has_script else "none"},
            sort_keys=False,
        ),
        "src/slides.yaml": "# One entry per slide; `id` equals the script heading it is spoken over.\n"
        "# Components and their arguments: present components gallery; schemas in the\n"
        '# skill\'s assets/schemas/components/. Colours are roles: "@accent", "@ink".\n'
        + yaml.safe_dump(slides, sort_keys=False, allow_unicode=True),
    }
    written = []
    for rel, body in files.items():
        with (art / rel).open("x", encoding="utf-8") as fh:
            fh.write(body)
        written.append(repo.rel(art / rel))
    (art / ".gitkeep").unlink(missing_ok=True)
    res.data = {"artifact": repo.rel(art), "files": written, "slides": ids}
    res.text.append(
        f"created {repo.rel(art)} ({len(ids)} example slide(s) keyed to "
        f"{'the script headings' if heads else 'a placeholder id'})"
    )
    return res


# --------------------------------------------------------------------------- build


def _configure_build(p):
    script_cmd._ref(p)
    p.add_argument("--level", choices=store.LEVELS, default="patch")
    p.add_argument(
        "--note", help="one line for the CHANGELOG (required unless --dry-run)"
    )
    p.add_argument("--version")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="build and check in a temporary folder; write nothing",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="with --dry-run: keep the preview (pptx, PDF, contact sheet and full-size page "
        "PNGs) in this folder, outside the repository",
    )


def _render(staged: Path, res: Result, keep_pages: bool = False) -> list[str]:
    from ..deck import render

    if os.environ.get("PRESENT_NO_RENDER") == "1":
        res.warn(
            "render_skipped", "PRESENT_NO_RENDER=1: the version holds the pptx only."
        )
        return []
    missing = render.missing_tools()
    if missing:
        for tool, hint in missing.items():
            res.warn(
                "capability_unavailable",
                f"{tool} not found: the version holds the pptx only (no PDF or "
                "contact sheet).",
                next=hint,
            )
        return []
    pdf = render.to_pdf(staged / "deck.pptx", staged)
    pages = render.pages(pdf, staged / "_pages", dpi=50)
    render.contact_sheet(pages, staged / "contact-sheet.png")
    shutil.rmtree(staged / "_pages")
    if keep_pages:  # a preview: full-size pages for review (never stored in a version)
        render.pages(pdf, staged / "pages", dpi=110)
    return [pdf.name, "contact-sheet.png"]


@leaf(
    "deck",
    "build",
    summary="resolve pins, build, render PDF and contact sheet, store a version",
    task="0008",
    configure=_configure_build,
    effects=Effects(
        writes=True,
        description="Writes one version folder (pptx, PDF, contact sheet, receipt), "
        "moves latest; runs LibreOffice locally. --dry-run writes nothing in the repository.",
    ),
)
def deck_build(ns, res: Result) -> Result:
    from ..deck import run

    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    if not ns.dry_run and not (ns.note or "").strip():
        return res.error(
            "note_missing",
            "every version needs --note (it becomes the CHANGELOG line).",
            repairable=True,
        )
    if ns.out is not None:
        out_dir = ns.out.resolve()
        if not ns.dry_run:
            return res.error(
                "usage", "--out keeps a preview and needs --dry-run.", repairable=True
            )
        if out_dir == repo.root or repo.root in out_dir.parents:
            return res.error(
                "preview_inside_repository",
                f"{out_dir} is inside the repository; a preview is never stored there.",
                repairable=True,
                next="pass --out under ~/.cache/present/preview/",
            )
    try:
        m = manifest(art)
        build_kind = m.get("build", "slides.yaml")
        entry = art / "src" / build_kind
        if not entry.is_file():
            return res.error(
                "src_missing",
                f"{repo.rel(entry)} does not exist.",
                repairable=True,
                next=f"present deck new {repo.rel(art.parent)}",
            )
        script_pin = resolve_script(art, m["script"])
        notes = notes_from(*script_pin) if script_pin else {}
        uses, lib_pins, lib_retired = library.resolve_deck(
            repo, library.load_slides(entry) if build_kind == "slides.yaml" else None, m
        )
    except store.StoreError as exc:
        return _err(res, exc)
    tok = tokens_file(repo)
    pins: dict[str, Any] = {}
    visual_dirs: dict[str, str] = {}
    if m.get("visuals"):
        from .. import visuals_link as vl

        talk = art.parent.parent.parent
        for key, selector in m["visuals"].items():
            try:
                pin = vl.resolve(repo.root, talk, key, selector)
            except vl.VisualsError as exc:
                return res.error(
                    exc.code,
                    f"deck.yaml visuals {key}: {exc.message}",
                    repairable=True,
                    next=exc.next,
                )
            pins[f"visual:{key}"] = {
                "selector": selector,
                "resolved": pin.resolved,
                "path": repo.rel(pin.receipt),
                "sha256": store.sha256(pin.receipt),
            }
            visual_dirs[key] = str(pin.folder)
            if not pin.indexed:
                res.warn(
                    "visuals_index_unavailable",
                    f"{key}: its project has no visuals.toml (legacy); "
                    "resolved from its latest link.",
                )
    if script_pin:
        sart, v = script_pin
        pins["script"] = {
            "selector": m["script"],
            "resolved": v,
            "path": repo.rel(sart / f"v{v}" / store.RECEIPT),
            "sha256": store.receipt_digest(sart, v),
        }
    pins.update(lib_pins)
    for name in lib_retired:
        res.warn(
            "library_retired",
            f"{name} is retired; validate blocks a talk that pins it.",
            next="pin its replacement",
        )
    if tok is not None:
        tdoc = json.loads(tok.read_text())
        pins["tokens"] = {
            "selector": "latest",
            "resolved": tdoc.get("version", "0.0.0"),
            "path": repo.rel(tok),
            "sha256": store.sha256(tok),
        }
    with tempfile.TemporaryDirectory(prefix="present-deck-") as tmp:
        staged = Path(tmp)
        try:  # dataset: references → src/data/ snapshots before anything builds (task 0022)
            data_map, data_recs = datasnap.prepare_deck(
                art / "src",
                build_kind,
                out=staged / "data-staged",
                write=not ns.dry_run,
            )
        except datasnap.SnapshotError as exc:
            return res.error(exc.code, exc.message, repairable=True, next=exc.next)
        for rec in data_recs:
            rec["path"] = repo.rel(art / "src" / rec["path"])
        job = {
            "src": str(art / "src"),
            "out": str(staged / "deck.pptx"),
            "build": build_kind,
            "notes": notes,
            "visuals": visual_dirs,
            "library": uses,
            "datasets": data_map,
        }
        (staged / "job.json").write_text(json.dumps(job))
        try:
            built = run.worker(
                ["build", str(staged / "job.json")], tokens=tok, repo=repo.root
            )
        except run.WorkerError as exc:
            problems = exc.data.get("problems") or []
            res.data = {"artifact": repo.rel(art), "problems": problems}
            res.text += [f"  {p}" for p in problems]
            code = {
                "slides_invalid": "slides_invalid",
                "slide_failed": "slide_failed",
            }.get(str(exc), "build_failed")
            return res.error(
                code,
                problems[0] if problems else str(exc),
                repairable=True,
                next=None if problems else exc.detail[-300:] or None,
            )
        (staged / "job.json").unlink()
        (staged / "slides.json").write_text(
            json.dumps(built["slides"], indent=2) + "\n"
        )
        rendered = _render(staged, res, keep_pages=bool(ns.dry_run and ns.out))
        ids = list(dict.fromkeys(p["id"] for p in built["slides"]))
        res.data = {
            "artifact": repo.rel(art),
            "dry_run": ns.dry_run,
            "slides": len(built["slides"]),
            "ids": ids,
            "pins": pins,
            "versions": built["versions"],
            "rendered": bool(rendered),
            "custom": built["custom"],
            "data": built["data"],
            "datasets": data_recs,
        }
        for o in built.get("overruns", [])[:20]:
            res.warn(
                "content_into_footer_clearance",
                f"{o['id']} step {o['step']}: {o['shape']} ends {o['by_in']} in below the content "
                "bottom (keep 0.32 in clear above the footer).",
            )
        missing_notes = [i for i in ids if script_pin and i not in notes]
        if missing_notes:
            res.warn(
                "notes_missing",
                f"no script section for slide(s) {', '.join(missing_notes)}; their notes are empty.",
                next=f"present deck check {repo.rel(art)}",
            )
        if ns.dry_run:
            if ns.out:
                out_dir = ns.out.resolve()
                shutil.copytree(staged, out_dir, dirs_exist_ok=True)
                res.data["preview"] = str(out_dir)
                res.text.append(
                    f"dry run: {len(built['slides'])} slides built; preview in {out_dir} "
                    "(nothing written in the repository)"
                )
                return res
            res.text.append(
                f"dry run: {len(built['slides'])} slides built and discarded; nothing written"
            )
            return res

        def produce(_art: Path, vdir: Path) -> None:
            for name in DECK_FILES:
                if (staged / name).is_file():
                    shutil.copyfile(staged / name, vdir / name)

        tools = {
            "engine": built["versions"]["engine"],
            "components": built["versions"]["components"],
            "tokens": built["versions"]["tokens"],
        }
        try:
            out = store.bump(
                repo.root,
                art,
                kind="deck",
                level=ns.level,
                note=ns.note,
                produce=produce,
                version=ns.version,
                pins=pins,
                tools=tools,
                standard=repo.standard,
                extra_inputs=[art / "deck.yaml"],
                datasets=data_recs,
            )
        except store.StoreError as exc:
            return _err(res, exc)
    res.data.update(
        version=out.version,
        previous=out.previous,
        receipt=repo.rel(out.path / store.RECEIPT),
    )
    res.text.append(
        f"{repo.rel(art)}: v{out.version}, {len(built['slides'])} slides"
        + (f", script {pins['script']['resolved']}" if "script" in pins else "")
        + ("" if rendered else " (pptx only: renderer unavailable)")
    )
    return res


# --------------------------------------------------------------------------- import


def _configure_import(p):
    script_cmd._ref(p)
    p.add_argument("file", type=Path, help="an external .pptx or .pdf")
    p.add_argument("--note", required=True)
    p.add_argument("--level", choices=store.LEVELS, default="patch")


@leaf(
    "deck",
    "import",
    summary="create a deck version from an external pptx/pdf",
    task="0008",
    configure=_configure_import,
    effects=Effects(
        writes=True,
        description="Copies the file into src/ and writes one version with origin: external.",
    ),
)
def deck_import(ns, res: Result) -> Result:
    got = _start(res, ns, must_exist=False)
    if got is None:
        return res
    repo, art = got
    f: Path = ns.file
    if not f.is_file() or f.suffix.lower() not in (".pptx", ".pdf"):
        return res.error(
            "file_invalid", f"{f}: need an existing .pptx or .pdf", repairable=True
        )
    (art / "src").mkdir(parents=True, exist_ok=True)
    if not (art / "deck.yaml").exists():
        (art / "deck.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "script": "none"}, sort_keys=False)
        )
    target = art / "src" / f"imported{f.suffix.lower()}"
    shutil.copyfile(f, target)
    (art / ".gitkeep").unlink(missing_ok=True)

    def produce(_art: Path, vdir: Path) -> None:
        from ..deck import render

        name = "deck" + f.suffix.lower()
        shutil.copyfile(target, vdir / name)
        if render.missing_tools():
            return
        pdf = (
            vdir / "deck.pdf"
            if name == "deck.pdf"
            else render.to_pdf(vdir / name, vdir)
        )
        with tempfile.TemporaryDirectory(prefix="present-import-") as tmp:
            pages = render.pages(pdf, Path(tmp), dpi=50)
            render.contact_sheet(pages, vdir / "contact-sheet.png")

    try:
        out = store.bump(
            repo.root,
            art,
            kind="deck",
            level=ns.level,
            note=ns.note,
            produce=produce,
            origin="external",
            standard=repo.standard,
            extra_inputs=[art / "deck.yaml"],
        )
    except store.StoreError as exc:
        return _err(res, exc)
    res.data = {"artifact": repo.rel(art), "version": out.version, "origin": "external"}
    res.text.append(
        f"{repo.rel(art)}: v{out.version} imported from {f.name} (origin: external)"
    )
    return res


# --------------------------------------------------------------------------- approve / show / check


def _configure_approve(p):
    script_cmd._ref(p)
    p.add_argument("--version")
    p.add_argument("--by")
    p.add_argument("--note")


@leaf(
    "deck",
    "approve",
    summary="record approval of a deck version",
    task="0008",
    configure=_configure_approve,
    effects=Effects(writes=True, description="Appends to approvals.yaml."),
)
def deck_approve(ns, res: Result) -> Result:
    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    try:
        version = ns.version or store.latest(art)
        if version is None:
            return res.error(
                "version_not_found",
                "nothing to approve: no versions yet.",
                repairable=True,
            )
        rec = store.receipt(art, version)
        pin = rec["inputs"].get("pins", {}).get("script")
        checks: dict[str, Any] = {"origin": rec.get("origin", "built")}
        if pin:
            sart = art.parent / "script"
            if pin["resolved"] not in store.approved_versions(sart):
                return res.error(
                    "script_unapproved",
                    f"v{version} was built from script {pin['resolved']}, which is "
                    "not approved.",
                    repairable=True,
                    next=f"present script approve {repo.rel(sart)} "
                    f"--version {pin['resolved']}",
                )
            checks["script"] = pin["resolved"]
        vpins = {
            k[len("visual:") :]: v
            for k, v in rec["inputs"].get("pins", {}).items()
            if k.startswith("visual:")
        }
        if vpins:
            from .. import visuals_link as vl

            talk = art.parent.parent.parent
            for key, vp in vpins.items():
                try:
                    now = vl.resolve(repo.root, talk, key, "latest")
                    published = store.parse(vp["resolved"]) <= store.parse(now.resolved)
                except vl.VisualsError:
                    published = False
                if not published:
                    return res.error(
                        "visual_unpublished",
                        f"v{version} uses visual {key} v{vp['resolved']}, which is not a published version.",
                        repairable=True,
                        next=f"present visual publish {key} v{vp['resolved']}",
                    )
            checks["visuals"] = {k: v["resolved"] for k, v in vpins.items()}
        entry = store.approve(
            repo.root,
            art,
            version,
            by=ns.by or script_cmd.git_user(repo.root),
            checks=checks,
            note=ns.note,
        )
    except store.StoreError as exc:
        return _err(res, exc)
    res.data = {"artifact": repo.rel(art), "approval": entry}
    res.text.append(f"{repo.rel(art)} v{version} approved by {entry['by']}")
    return res


def _configure_show(p):
    script_cmd._ref(p)
    p.add_argument("--version")
    p.add_argument("--verify", action="store_true")


@leaf(
    "deck",
    "show",
    summary="show a version's receipt and resolved pins",
    task="0008",
    configure=_configure_show,
    effects=Effects(description="Reads one artifact."),
)
def deck_show(ns, res: Result) -> Result:
    res = script_cmd.show_artifact(ns, res, "deck")
    rec = res.data.get("receipt")
    if rec:
        for name, pin in rec["inputs"].get("pins", {}).items():
            res.text.append(
                f"  pin {name}: {pin['selector']} → {pin['resolved']} ({pin['path']})"
            )
        t = rec["tools"]
        res.text.append(
            f"  engine {t.get('engine')} · components {t.get('components')} · tokens "
            f"{(t.get('tokens') or {}).get('version')} {(t.get('tokens') or {}).get('sha256', '')[:12]}"
        )
    return res


def component_errors(slides: list[dict[str, Any]]) -> list[str]:
    """Validation against the shipped component schemas (no brand binding in this process)."""
    errs = [f"slides.yaml: {e}" for e in schemas.errors("slides", slides)]
    if errs:
        return errs
    for sl in slides:
        comp = sl.get("component")
        if comp in (None, "custom"):
            continue
        sp = COMPONENT_SCHEMAS / f"{comp}.schema.json"
        if not sp.is_file():
            errs.append(f"{sl['id']}: unknown component {comp!r}")
            continue
        v = Draft202012Validator(json.loads(sp.read_text()))
        for e in sorted(
            v.iter_errors(sl.get("with", {})), key=lambda e: list(e.absolute_path)
        ):
            errs.append(
                f"{sl['id']}: with.{'/'.join(map(str, e.absolute_path)) or '(with)'}: {e.message}"
            )
    return errs


def _configure_check(p):
    script_cmd._ref(p)


@leaf(
    "deck",
    "check",
    summary="slide IDs against script headings; custom usage",
    task="0008",
    configure=_configure_check,
    effects=Effects(
        description="Reads deck.yaml, src/slides.yaml and the pinned script."
    ),
)
def deck_check(ns, res: Result) -> Result:
    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    try:
        m = manifest(art)
    except store.StoreError as exc:
        return _err(res, exc)
    if m.get("build", "slides.yaml") != "slides.yaml":
        res.warn(
            "custom_build",
            "build: build.py — slide IDs are known only after a build.",
            next="present deck build --dry-run",
        )
        res.data = {"artifact": repo.rel(art), "build": "build.py"}
        return res
    slides = (
        yaml.safe_load((art / "src" / "slides.yaml").read_text(encoding="utf-8")) or []
    )
    errs = component_errors(slides)
    ids = [s.get("id") for s in slides]
    heads = script_headings(art, m["script"]) if m["script"] != "none" else None
    missing = [h for h in heads if h not in ids] if heads is not None else []
    extra = [i for i in ids if heads is not None and i not in heads]
    common_deck = [i for i in ids if heads and i in heads]
    common_script = [h for h in (heads or []) if h in ids]
    custom = [s["id"] for s in slides if s.get("component") == "custom"]
    res.data = {
        "artifact": repo.rel(art),
        "slides": ids,
        "script_headings": heads,
        "missing": missing,
        "extra": extra,
        "order_matches": common_deck == common_script,
        "custom": custom,
        "errors": errs,
    }
    res.text.append(
        f"{repo.rel(art)}: {len(ids)} slides; script headings "
        + (
            "n/a"
            if heads is None
            else f"{len(heads)}; missing {len(missing)}, extra {len(extra)}, "
            f"order {'matches' if common_deck == common_script else 'differs'}"
        )
    )
    if missing:
        res.warn(
            "slides_missing", f"script sections with no slide: {', '.join(missing)}"
        )
    if extra:
        res.warn(
            "slides_extra",
            f"slides with no script section (no notes): {', '.join(extra)}",
        )
    if heads is not None and common_deck != common_script:
        res.warn("order_differs", "slide order differs from the script's section order")
    if custom:
        res.warn(
            "custom_used",
            f"component custom (src/custom.py) on: {', '.join(custom)}",
            next="promote a recurring custom slide to a component",
        )
    for e in errs:
        res.text.append(f"  {e}")
    if errs:
        return res.error("slides_invalid", errs[0], repairable=True)
    return res
