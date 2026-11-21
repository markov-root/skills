"""Worker side of `present deck build` (tasks 0008, 0017): slides.yaml (or src/build.py) → pptx,
speaker notes from the resolved script version, slide-ID bookkeeping. Runs with the brand bound.

job = {"src": <deck src dir>, "out": <pptx path>, "build": "slides.yaml"|"build.py",
       "notes": {slide_id: text}}
Returns {"slides": [{"id", "step"}], "data": [files used], "custom": [ids], "versions": {...}}.

`component: custom` calls `render(prs, base, slide, cx, dk)` in src/custom.py; `build: build.py`
calls `build(prs, base, cx, dk)` in src/build.py, which returns [(slide_id, [slides])].
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .. import library
from . import brand, components as cx, declare, frame, kit as dk


class SlideError(Exception):
    """A declared slide that cannot be built; raised before anything renders."""


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate_slides(
    slides: list[dict[str, Any]], src: Path, uses: dict[str, str] | None = None
) -> list[str]:
    """Every problem in a slides.yaml, each naming the slide ID and field; [] when buildable.

    `uses` maps a `use:` slide's ID to its resolved, frozen library version folder."""
    from .. import schemas

    errs = [f"slides.yaml: {e}" for e in schemas.errors("slides", slides)]
    if errs:
        return errs
    seen: set[str] = set()
    for sl in slides:
        sid = sl["id"]
        if sid in seen:
            errs.append(f"{sid}: duplicate slide id")
        seen.add(sid)
        if "use" in sl:
            if sid not in (uses or {}):
                errs.append(f"{sid}: use: {sl['use']} was not resolved")
                continue
            frag = library.fragment(Path(uses[sid]))
            fe = library.fragment_errors(sid, frag)
            errs += fe or validate_slides(frag, Path(uses[sid]))
            continue
        comp = sl["component"]
        if comp == "custom":
            if not (src / "custom.py").is_file():
                errs.append(
                    f"{sid}: component custom needs src/custom.py with render(prs, base, slide, cx, dk)"
                )
            continue
        if comp not in declare.CATALOGUE:
            errs.append(
                f"{sid}: unknown component {comp!r} (present components gallery lists them)"
            )
            continue
        v = Draft202012Validator(declare.schema_for(comp))
        for e in sorted(
            v.iter_errors(sl.get("with", {})), key=lambda e: list(e.absolute_path)
        ):
            field = "/".join(str(p) for p in e.absolute_path) or "(with)"
            errs.append(f"{sid}: with.{field}: {e.message}")
    return errs


def run(job: dict[str, Any]) -> dict[str, Any]:
    src, out = Path(job["src"]), Path(job["out"])
    notes: dict[str, str] = job.get("notes") or {}
    prs, base = frame.new_deck()
    order: list[Any] = []
    pages: list[dict[str, Any]] = []
    data_used: set[str] = set()
    declare.VISUALS = {k: Path(v) for k, v in (job.get("visuals") or {}).items()}  # task 0009
    custom: list[str] = []
    if job.get("build", "slides.yaml") == "build.py":
        mod = _load_module(src / "build.py", "deck_build")
        made = mod.build(prs, base, cx, dk)
        for sid, slides in made:
            for k, s in enumerate(slides, 1):
                order.append(s)
                pages.append({"id": sid, "step": k})
    else:
        slides = yaml.safe_load((src / "slides.yaml").read_text(encoding="utf-8")) or []
        if job.get("datasets"):  # dataset: references → their snapshots (task 0022)
            from ..datasnap import substitute

            try:
                slides, used = substitute(slides, job["datasets"], src)
            except ValueError as exc:
                return {"error": "slides_invalid", "problems": [str(exc)]}
            data_used |= used
        uses: dict[str, str] = job.get("library") or {}
        problems = validate_slides(slides, src, uses)
        if problems:
            return {"error": "slides_invalid", "problems": problems}
        custom_mod = (
            _load_module(src / "custom.py", "deck_custom")
            if (src / "custom.py").is_file()
            else None
        )
        section = None  # (number, name) of the current one-row contents section
        for sl in slides:
            if "use" in sl:  # a library slide: its frozen fragment, under this slide's ID
                made = []
                for fsl in library.fragment(Path(uses[sl["id"]])):
                    try:
                        made += declare.render_slide(
                            prs, base, fsl, src=Path(uses[sl["id"]]), data_used=None
                        )
                    except (ValueError, KeyError, TypeError) as exc:
                        return {
                            "error": "slide_failed",
                            "problems": [f"{sl['id']} ({sl['use']}): {type(exc).__name__}: {exc}"],
                        }
            elif sl["component"] == "custom":
                made = list(custom_mod.render(prs, base, sl, cx, dk))
                custom.append(sl["id"])
            else:
                try:
                    made = declare.render_slide(
                        prs, base, sl, src=src, data_used=data_used
                    )
                except (ValueError, KeyError, TypeError) as exc:
                    return {
                        "error": "slide_failed",
                        "problems": [f"{sl['id']}: {type(exc).__name__}: {exc}"],
                    }
            if sl.get("component") == "section_divider":
                w_ = sl.get("with", {})
                mods, on = w_.get("modules"), w_.get("module_on")
                if isinstance(mods, list) and isinstance(on, int) and not w_.get("parts"):
                    section = (on + 1, mods[on])
            elif section is not None:
                for s in made:
                    frame.section_kicker(s, *section)
            for k, s in enumerate(made, 1):
                order.append(s)
                pages.append({"id": sl["id"], "step": k})
    for s, p in zip(order, pages):
        if p["id"] in notes:
            dk.set_notes(s, notes[p["id"]])
    frame.finish(prs, order)
    overruns = []  # advisory: shapes that run into the clearance above the footer (1.2.0)
    limit = cx.Y1 + int(0.02 * cx.IN)
    for s, p in zip(order, pages):
        names = {sh.name for sh in s.shapes}
        if "frame-left" not in names:
            continue  # full-bleed slides have no footer
        for sh in s.shapes:
            if sh.name.startswith(("frame-", "source-footer")) or sh.top is None:
                continue
            if sh.top < dk.FOOTER_TOP and sh.top + sh.height > limit:
                overruns.append(
                    {"id": p["id"], "step": p["step"], "shape": sh.name,
                     "by_in": round((sh.top + sh.height - cx.Y1) / cx.IN, 2)}
                )
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    return {
        "slides": pages,
        "data": sorted(data_used),
        "custom": custom,
        "overruns": overruns,
        "versions": {
            "engine": dk.ENGINE_VERSION,
            "components": cx.COMPONENTS_VERSION,
            "tokens": brand.identity(),
        },
    }
