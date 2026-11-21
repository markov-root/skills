"""The component catalogue and the declarative adapter (tasks 0015 AC-4, 0017; ADR 0009).

A slide is data: `{id, component, with, builds}`. `with` holds the component's own arguments plus
slide-level keys (`title`, `sources`, `takeaway`, and for charts `rail`, `legend`). Values are
plain YAML/JSON; a few string forms are converted before the call:

- `"@<role>"` → that brand colour role (`@accent`, `@ink`, …);
- `"@date:YYYY-MM-DD"` → a spreadsheet date serial (date axes);
- `"@data:<file>"` → the parsed contents of a CSV/JSON file in the deck's `src/` (task 0017);
- mapping keys `"3"` → 3 and `"0,3"` → (0, 3) (per-point overrides).

Each catalogued component has a generated JSON Schema of its `with` (`schema_for`); a slide is
validated against it before anything renders.
"""

from __future__ import annotations

import csv
import inspect
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pptx.dml.color import RGBColor

from . import brand
from . import components as cx

# How the adapter calls a component: "chart" through chart_slide's draw(slide, box, stage);
# "panel" on a fresh frame slide per build step; "deck" builds its own slide(s).
KINDS = {
    "chart_xy": "chart",
    "chart_line": "chart",
    "chart_bar": "chart",
    "chain": "panel",
    "compare": "panel",
    "cards": "panel",
    "stat_in_context": "panel",
    "term": "panel",
    "timeline": "panel",
    "agent_grid": "panel",
    "pipeline": "panel",
    "screenshot": "panel",
    "quote_slide": "deck",
    "title_slide": "deck",
    "one_thing": "deck",
    "section_divider": "deck",
    "walk_slides": "deck",
}
INJECTED = {"slide", "prs", "base", "bx", "box_", "draw", "notes"}
SLIDE_KEYS = {
    "title": {"type": "string", "description": "slide title (sentence case)"},
    "sources": {
        "type": "array",
        "description": "footer sources: strings, or {publisher, title, when, url} "
        "or {publisher, dataset, data_to, url}",
        "items": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "publisher": {"type": "string"},
                        "title": {"type": "string"},
                        "when": {"type": "string"},
                        "dataset": {"type": "string"},
                        "data_to": {"type": "string"},
                        "url": {"type": "string"},
                        "text": {"type": "string"},
                        "short": {"type": "string"},
                    },
                },
            ]
        },
    },
    "takeaway": {
        "description": "the slide's key point: a sentence, or [lead, rest]",
        "oneOf": [
            {"type": "string"},
            {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
        ],
    },
}
CHART_KEYS = {
    "rail": {
        "type": "object",
        "description": "kwargs for the side rail (head, hero, unit, context, facts, note)",
    },
    "legend": {
        "type": "array",
        "description": "[[kind, colour, text]] under the chart",
    },
    "rail_side": {"enum": ["right", "left"]},
    "rail_sync": {
        "oneOf": [{"type": "boolean"}, {"type": "array", "items": {"type": "integer"}}]
    },
}
IMAGE_ARGS = ("png", "org_logo", "portrait_img")
FORWARDS = {"walk_slides": "timeline"}
COLOUR_REF = {
    "type": "string",
    "pattern": r"^@[a-z][a-z0-9_]*$",
    "description": "a colour role, e.g. @accent",
}


@dataclass(frozen=True)
class Component:
    name: str
    kind: str
    fn: Callable[..., Any]

    @property
    def params(self) -> list[inspect.Parameter]:
        own = [
            p
            for p in inspect.signature(self.fn).parameters.values()
            if p.name not in INJECTED
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        if (
            self.name in FORWARDS
        ):  # **kwargs forwarded to another component (walk_slides → timeline)
            names = {p.name for p in own}
            own += [
                p
                for p in inspect.signature(
                    getattr(cx, FORWARDS[self.name])
                ).parameters.values()
                if p.name not in INJECTED | names | {"events", "upto", "walk"}
                and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            ]
        return own

    @property
    def builds_param(self) -> str | None:
        names = {p.name for p in self.params}
        return "upto" if "upto" in names else None


CATALOGUE: dict[str, Component] = {
    n: Component(n, k, getattr(cx, n)) for n, k in KINDS.items()
}


# Types of arguments that have no default to infer from (the library carries no annotations).
TYPE_HINTS = {
    "series": "array",
    "categories": "array",
    "steps_": "array",
    "columns": "array",
    "items": "array",
    "bars": "array",
    "events": "array",
    "agents": "array",
    "modules": "array",
    "parts": "array",
    "x_axis": "object",
    "y_axis": "object",
    "colors": "object",
    "value": "string",
    "what": "string",
    "word": "string",
    "definition": "string",
    "quote": "string",
    "who": "string",
    "lead": "string",
    "rest": "string",
    "png": "string",
    "org_logo": "string",
    "portrait_img": "string",
    "speakers": "array",  # ["Name · Role"] or [{name, role, photo}]
    "bubbles": "array",
    "legend": "array",
    "module_n": "integer",
    "module_on": "integer",
    "part_on": "integer",
}
DATA_REF = {"type": "string", "pattern": "^@data:"}


def _param_schema(p: inspect.Parameter) -> dict[str, Any]:
    d = p.default
    hint = TYPE_HINTS.get(p.name)
    if hint is not None and (d is inspect.Parameter.empty or d is None):
        return (
            {"anyOf": [{"type": hint}, DATA_REF]}
            if hint in ("array", "object")
            else {"type": hint}
        )
    if d is inspect.Parameter.empty or d is None:
        return {}
    if isinstance(d, Enum):
        return {"type": "string", "enum": sorted(m.name.lower() for m in type(d))}
    if isinstance(d, RGBColor):
        return dict(COLOUR_REF)
    if isinstance(d, bool):
        return {"type": "boolean"}
    if isinstance(d, (int, float)):
        return {"type": "number"}
    if isinstance(d, str):
        return {"type": "string"}
    if isinstance(d, (tuple, list)):
        return {"type": "array"}
    if isinstance(d, dict):
        return {"type": "object"}
    return {}


def schema_for(name: str) -> dict[str, Any]:
    """The JSON Schema of `with` for one component (generated from its signature)."""
    comp = CATALOGUE[name]
    props: dict[str, Any] = {}
    required = []
    for p in comp.params:
        if p.name in ("title", "sources"):
            continue  # slide-level keys below
        if p.name == "upto":
            continue  # set by `builds`
        props[p.name] = _param_schema(p)
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
    props.update(SLIDE_KEYS)
    if comp.kind == "chart":
        props.update(CHART_KEYS)
    if comp.kind == "panel":
        props["box"] = {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 4,
            "maxItems": 4,
            "description": "the component's box [x, y, w, h] in inches (default: the content area)",
        }
        props["overlays"] = overlay_schema()
        props["reveal"] = {
            "type": "boolean",
            "description": "builds reveal the component item by item (default true); false keeps it whole and builds only the overlays",
        }
    sig = {p.name for p in comp.params}
    if comp.kind != "deck" or "title" in sig:
        required.append("title")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"slides.yaml `with` for component {name} ({comp.kind})",
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": sorted(set(required)),
    }


# Primitives a panel slide may layer over its component, from a given build step. Geometry is in
# inches from the slide's top-left; colours are roles; fonts are "@font:<role>".
PRIMITIVES = ("text", "label", "box", "rule", "vrule", "line", "dot", "annotate")
INCH_KEYS = {"x", "y", "w", "h", "x1", "y1", "x2", "y2", "cx", "cy", "d"}


def _primitive_schema(name: str) -> dict[str, Any]:
    props, required = {}, []
    for p in inspect.signature(getattr(cx, name)).parameters.values():
        if p.name == "slide" or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        props[p.name] = {"type": "number"} if p.name in INCH_KEYS else _param_schema(p)
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": required,
    }


def overlay_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "description": "primitives drawn over the component: [{primitive, from, with}]",
        "items": {
            "type": "object",
            "required": ["primitive", "with"],
            "additionalProperties": False,
            "properties": {
                "primitive": {"enum": list(PRIMITIVES)},
                "from": {"type": "integer", "minimum": 1},
                "with": {"type": "object"},
            },
            "allOf": [
                {
                    "if": {"properties": {"primitive": {"const": n}}},
                    "then": {"properties": {"with": _primitive_schema(n)}},
                }
                for n in PRIMITIVES
            ],
        },
    }


# Component length arguments that the library takes in EMU; slides.yaml gives them in inches.
LENGTH_PARAMS = {"box_h", "value_w", "desc_w", "logo_h"}


def coerce(fn, kw: dict[str, Any], lengths: set[str]) -> dict[str, Any]:
    """Inches → EMU for length arguments; enum names ("right") → the enum a default is drawn from."""
    sig = inspect.signature(fn).parameters
    out = {}
    for k, v in kw.items():
        default = sig[k].default if k in sig else None
        if k in lengths and isinstance(v, (int, float)) and not isinstance(v, bool):
            v = int(v * cx.IN)
        elif isinstance(v, str) and isinstance(default, Enum):
            v = type(default)[v.upper()]
        out[k] = v
    return out


def draw_overlay(slide, ov: dict[str, Any]) -> None:
    fn = getattr(cx, ov["primitive"])
    fn(slide, **coerce(fn, ov["with"], INCH_KEYS))


def all_schemas() -> dict[str, dict[str, Any]]:
    return {n: schema_for(n) for n in sorted(CATALOGUE)}


# --------------------------------------------------------------------------- value conversion


def _load_data(src: Path, rel: str) -> Any:
    p = (src / rel).resolve()
    if src.resolve() not in p.parents:
        raise ValueError(f"@data:{rel} is outside the deck's src/")
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    if p.suffix == ".csv":
        with p.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return [{k: _num(v) for k, v in r.items()} for r in rows]
    raise ValueError(f"@data:{rel}: only .csv and .json are supported")


def _num(v: str) -> Any:
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


VISUALS: dict[str, Path] = {}  # visual key → resolved version folder, set per build (task 0009)


def visual_frame(slide_id: str, arg: str, ref: str) -> Path:
    """`<key>` → the version's first PNG frame; `<key>/<frame>` → that frame (with or without .png)."""
    key, _, frame = _split_key(ref)
    vdir = VISUALS.get(key)
    if vdir is None:
        raise ValueError(f"{slide_id}: {arg} @visual:{key} is not pinned in deck.yaml `visuals:`")
    if frame:
        cand = [vdir / frame, vdir / f"{frame}.png"]
        hit = next((c for c in cand if c.is_file()), None)
        if hit is None:
            raise ValueError(f"{slide_id}: {arg} @visual:{ref}: no frame {frame!r} in {vdir.name}")
        return hit
    frames = sorted(vdir.glob("*.png"))
    if not frames:
        raise ValueError(f"{slide_id}: {arg} @visual:{key}: {vdir.name} holds no PNG frame")
    return frames[0]


def _split_key(ref: str) -> tuple[str, str, str]:
    """Keys may themselves contain '/' (cross-talk paths): the longest pinned key wins."""
    for key in sorted(VISUALS, key=len, reverse=True):
        if ref == key:
            return key, "", ""
        if ref.startswith(key + "/"):
            return key, "/", ref[len(key) + 1:]
    key, _, frame = ref.partition("/")
    return key, "/", frame


def convert(
    value: Any, src: Path | None = None, data_used: set[str] | None = None
) -> Any:
    if isinstance(value, str) and value.startswith("@"):
        if value.startswith("@visual:"):  # resolved by the image-argument step (task 0009)
            return value
        if value.startswith("@date:"):
            return cx.serial(value[6:])
        if value.startswith("@font:"):
            return brand.font(value[6:])
        if value.startswith("@data:"):
            if src is None:
                raise ValueError("@data: needs a deck src/ folder")
            if data_used is not None:
                data_used.add(value[6:])
            return _load_data(src, value[6:])
        return brand.color(value[1:])
    if isinstance(value, list):
        return [convert(v, src, data_used) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and re.fullmatch(r"\d+", k):
                k = int(k)
            elif isinstance(k, str) and re.fullmatch(r"\d+,\d+", k):
                k = tuple(int(x) for x in k.split(","))
            out[k] = convert(v, src, data_used)
        return out
    return value


def sources(items: list[Any] | None) -> list[Any]:
    out = []
    for s in items or []:
        if isinstance(s, str):
            out.append(s)
        elif "dataset" in s:
            out.append(
                cx.dataset(
                    s["publisher"], s["dataset"], s["data_to"], url=s.get("url"), short=s.get("short")
                )
            )
        elif "text" in s:
            out.append(cx.link(s["text"], s.get("url"), short=s.get("short")))
        else:
            out.append(
                cx.src(s["publisher"], s["title"], s["when"], url=s.get("url"), short=s.get("short"))
            )
    return out


# --------------------------------------------------------------------------- the adapter

PANEL_BOX = (
    cx.X0,
    cx.Y0 + int(0.65 * cx.IN),
    cx.X1 - cx.X0,
    cx.Y1 - cx.Y0 - int(0.65 * cx.IN),
)
FULL_BOX = (cx.X0, cx.Y0, cx.X1 - cx.X0, cx.Y1 - cx.Y0)


def render_slide(
    prs,
    base,
    slide: dict[str, Any],
    *,
    src: Path | None = None,
    data_used: set[str] | None = None,
) -> list[Any]:
    """Draw one declared slide; returns its build slides (one per `builds` stage)."""
    comp = CATALOGUE[slide["component"]]
    try:
        w = convert(dict(slide.get("with", {})), src, data_used)
    except brand.TokenError as exc:
        raise ValueError(f"unknown colour role: {exc}") from exc
    for key in IMAGE_ARGS:  # image files are named relative to the deck's src/
        v = w.get(key)
        if isinstance(v, str) and v.startswith("@visual:"):  # a pinned visual's frame (task 0009)
            w[key] = visual_frame(slide["id"], key, v[len("@visual:"):])
            continue
        if isinstance(v, str) and Path(v).suffix.lower() in (".png", ".jpg", ".jpeg"):
            if src is None or not (src / v).is_file():
                raise ValueError(f"{slide['id']}: {key} {v!r} not found in src/")
            w[key] = (src / v).resolve()
            if data_used is not None:
                data_used.add(v)
    for sp in w.get("speakers") or []:  # title_slide speaker photos live in src/ too
        if isinstance(sp, dict) and isinstance(sp.get("photo"), str):
            if src is None or not (src / sp["photo"]).is_file():
                raise ValueError(f"{slide['id']}: speaker photo {sp['photo']!r} not found in src/")
            sp["photo"] = (src / sp["photo"]).resolve()
            if data_used is not None:
                data_used.add(str(sp["photo"].relative_to(src.resolve())))
    title = w.pop("title", None)
    srcs = sources(w.pop("sources", None))
    takeaway = w.pop("takeaway", None)
    if isinstance(takeaway, list):
        takeaway = tuple(takeaway)
    stages = len(slide.get("builds", [])) or 1
    w = coerce(comp.fn, w, LENGTH_PARAMS)
    if comp.kind == "chart":
        rail = w.pop("rail", None)
        legend = w.pop("legend", None)
        side = w.pop("rail_side", "right")
        sync = w.pop("rail_sync", False)
        args = w

        def draw(s, box, stage):
            return comp.fn(s, box, **args)

        return list(
            cx.chart_slide(
                prs,
                base,
                title,
                srcs,
                draw,
                rail_spec=rail,
                takeaway_text=takeaway or title,
                stages=stages,
                rail_side=side,
                rail_sync=sync,
                legend=[tuple(x) for x in legend] if legend else None,
            )
        )
    if comp.kind == "panel":
        box = PANEL_BOX if takeaway else FULL_BOX

        overlays = w.pop("overlays", [])
        reveal = w.pop("reveal", True)
        if "box" in w:  # an explicit component box, in inches
            box = tuple(int(v * cx.IN) for v in w.pop("box"))

        def draw_panel(s, k):
            kw = dict(w)
            if comp.builds_param and stages > 1 and reveal:
                kw["upto"] = k
            if comp.name == "screenshot":
                comp.fn(s, kw.pop("png"), box, **kw)
            else:
                comp.fn(s, box, **kw)
            for ov in overlays:
                if k >= ov.get("from", 1):
                    draw_overlay(s, ov)

        return list(
            cx.steps(prs, base, title, srcs, stages, draw_panel, takeaway_text=takeaway)
        )
    sig = inspect.signature(comp.fn).parameters
    kw = dict(w)
    if "title" in sig:
        kw["title"] = title
    if "sources" in sig:
        kw["sources"] = srcs
    out = comp.fn(prs, base, **kw)
    return list(out) if isinstance(out, (list, tuple)) else [out]
