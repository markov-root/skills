"""Measured evaluation of an authored visual: one blocker, selected advisories.

The ADR 0004 clipped-content blocker is evaluated here from measured geometry
for every visual (blockers are skill-wide, not project-selected): text whose
glyph band, or an annotated data mark, extends past the canvas is absent from
the delivered frame. That is the only outcome that changes the exit status.
Every other gate is advisory and project-selected; unknown paint and absent
annotations stay explicitly unmeasured. The project supplies every numeric
advisory threshold.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import uuid
from pathlib import Path

import measure
import render
import config

GATES = config.MEASUREMENT_ADVISORIES
UNASSESSED = ("visual hierarchy", "communication", "aesthetic quality")
#: Sub-pixel slack for the blocker: layout rounding, not a design threshold.
CLIP_TOLERANCE_PX = 0.5
#: Primary families that name a role, not a font; any rendered face satisfies them.
GENERIC_FAMILIES = frozenset({
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded", "emoji", "math",
    "fangsong", "-apple-system", "blinkmacsystemfont",
})


class CheckError(Exception):
    """The check cannot run or cannot make its evidence artifacts."""


def _item(gate: str, frame: str, selector: str, outcome: str,
          measured: object, threshold: object, action: str, box: dict | None) -> dict:
    return {"gate": gate, "severity": "advisory", "frame": frame,
            "selector": selector, "outcome": outcome, "measured": measured,
            "threshold": threshold, "to_satisfy": action, "box": box}


def _decision(value: float | None, threshold: float | None, *, low_bad: bool) -> str:
    if value is None or threshold is None or not math.isfinite(value):
        return "not-measurable"
    return "finding" if (value < threshold if low_bad else value > threshold) else "pass"


def _overflow(rect: dict, canvas: dict) -> dict:
    top, bottom = rect["y"], rect["y"] + rect["height"]
    return {"left": max(0.0, -rect["x"]), "top": max(0.0, -top),
            "right": max(0.0, rect["x"] + rect["width"] - canvas["width"]),
            "bottom": max(0.0, bottom - canvas["height"])}


def _visible(rect: dict, inset_y: float, clip: dict | None) -> dict | None:
    """The glyph band of `rect` that an overflow-clipping ancestor lets paint."""
    left, right = rect["x"], rect["x"] + rect["width"]
    top, bottom = rect["y"] + inset_y, rect["y"] + rect["height"] - inset_y
    if clip is not None:
        left, right = max(left, clip["x"]), min(right, clip["x"] + clip["width"])
        top, bottom = max(top, clip["y"]), min(bottom, clip["y"] + clip["height"])
    if right <= left or bottom <= top:
        return None
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def _meets_canvas(rect: dict, canvas: dict) -> bool:
    return (rect["x"] < canvas["width"] and rect["x"] + rect["width"] > 0
            and rect["y"] < canvas["height"] and rect["y"] + rect["height"] > 0)


def clipped_content(report: dict) -> list[dict]:
    """ADR 0004 blocker 1 from measured geometry.

    Content means visible text and annotated data marks. A text line box spans
    the line height, whose half-leading may legitimately cross the edge while
    the glyphs do not, so each line is inset vertically to its font-size band
    before comparison. Text is first cut to its ancestors' overflow clip;
    text that never meets the canvas (off-screen accessibility text) and text
    bounded by `clip`/`clip-path` do not block. Decorative layers and images
    are not content here: a full-bleed background is a design choice, and
    geometry-overflow reports it.
    """
    blocking: list[dict] = []
    for frame_name, frame in report["frames"].items():
        canvas = frame.get("canvas") or report["canvas"]
        for selector, texts in frame["texts"].items():
            for text in texts:
                if text.get("clip_unknown"):
                    continue  # `clip`/`clip-path` bounds it in a way geometry cannot state
                size = text["computed_size_px"]
                lines = text.get("lines") or []
                line_height = lines[0]["height"] if lines else text["box"]["height"]
                # The per-line list is capped; the union box (inset by the same
                # half-leading at its first and last line) always covers the rest.
                rects = [*((line, max(0.0, (line["height"] - size) / 2)) for line in lines),
                         (text["box"], max(0.0, (line_height - size) / 2))]
                worst = {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
                for rect, inset in rects:
                    rect = _visible(rect, inset, text.get("clip_box"))
                    if rect is None or not _meets_canvas(rect, canvas):
                        # Already clipped away by an ancestor, or never on the
                        # canvas at all (off-screen accessibility text): not
                        # content the delivered frame was meant to show.
                        continue
                    for side, value in _overflow(rect, canvas).items():
                        worst[side] = max(worst[side], value)
                if max(worst.values()) > CLIP_TOLERANCE_PX:
                    blocking.append({
                        "condition": "clipped-content", "severity": "blocking",
                        "frame": frame_name, "selector": selector,
                        "content": text["content"][:80],
                        "measured": {k: round(v, 3) for k, v in worst.items()},
                        "threshold": {"canvas": canvas, "tolerance_px": CLIP_TOLERANCE_PX},
                        "to_satisfy": "Move or resize the text so every line lies inside the canvas.",
                        "box": text["box"]})
        annotation = frame["annotation"]
        for mark in annotation.get("marks", []) if annotation.get("present") else []:
            over = _overflow(mark["box"], canvas)
            if _meets_canvas(mark["box"], canvas) and max(over.values()) > CLIP_TOLERANCE_PX:
                blocking.append({
                    "condition": "clipped-content", "severity": "blocking",
                    "frame": frame_name, "selector": mark["selector"],
                    "content": f"data mark {mark['series']}={mark['value']}",
                    "measured": {k: round(v, 3) for k, v in over.items()},
                    "threshold": {"canvas": canvas, "tolerance_px": CLIP_TOLERANCE_PX},
                    "to_satisfy": "Fit the data mark inside the canvas (scale or domain).",
                    "box": mark["box"]})
    return blocking


def _font_outcome(text: dict, faces: list[dict]) -> tuple[str, object]:
    """Fallback verdict for the requested primary family, with what rendered."""
    requested = text.get("requested_font_family", "")
    primary = requested.split(",", 1)[0].strip().strip("\"'")
    used = [f for f in text["resolved_fonts"] if f["glyph_count"] > 0]
    names = [f["family"] for f in used]
    measured = {"requested": primary or None, "rendered": names or None}
    if not primary or not used:
        return "not-measurable", measured
    if primary.casefold() in GENERIC_FAMILIES:
        return "pass", measured
    if any(n.casefold() == primary.casefold() for n in names):
        return "pass", measured
    declared = [f for f in faces if f["family"].casefold() == primary.casefold()]
    if declared:
        statuses = {f["status"] for f in declared}
        measured["font_face_status"] = sorted(statuses)
        # CDP reports a webfont by its internal name, not the @font-face alias,
        # so a loaded alias plus a custom glyph source is the rendered webfont.
        if "loaded" in statuses and any(f["custom"] for f in used):
            return "pass", measured
        if statuses == {"error"}:
            return "finding", measured
        return "not-measurable", measured
    # A system family: CDP reports the platform's own family name, which can be
    # a longer variant of the requested one ("Inter" -> "Inter Variable"); a
    # prefix match in either direction is the same family, anything else is a
    # substitution (fontconfig or Chrome picked another face).
    wanted = primary.casefold()
    if any(n.casefold().startswith(wanted) or wanted.startswith(n.casefold()) for n in names):
        return "pass", measured
    return "finding", measured


def _colour_only(frame_name: str, frame: dict, limit: float | None) -> list[dict]:
    """WCAG 1.4.1-style check over annotated marks: is each series told apart
    by something other than colour — a distinct non-colour channel signature
    (element, dash, marker, pattern, symbol, declared shape) or a direct label
    (text equal to the series name within the project's distance limit)?"""
    annotation = frame["annotation"]
    if not annotation.get("present"):
        return [_item("colour-only-encoding", frame_name, "[data-series]", "not-measurable",
                      None, limit,
                      "Annotate marks with data-series and data-value to measure encoding.", None)]
    series: dict[str, list[dict]] = {}
    for mark in annotation["marks"]:
        series.setdefault(mark["series"], []).append(mark)
    if len(series) < 2:
        return [_item("colour-only-encoding", frame_name, "[data-series]", "pass",
                      {"series": list(series)}, limit,
                      "Nothing to do: a single series needs no colour distinction.", None)]

    def signature(marks: list[dict]) -> frozenset:
        return frozenset(tuple(sorted((m.get("channels") or {}).items())) for m in marks)

    def centre(b: dict) -> tuple[float, float]:
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    texts = [t for items in frame["texts"].values() for t in items]
    signatures = {name: signature(marks) for name, marks in series.items()}
    entries = []
    for name, marks in series.items():
        # A series is told apart only if no mark kind it uses is also used,
        # identically except for colour, by another series.
        sharing = sorted(o for o in series if o != name and signatures[o] & signatures[name])
        named = [t for t in texts if t["content"].strip().casefold() == name.casefold()]
        nearest = None
        if named:
            nearest = min(math.dist(centre(t["box"]), centre(m["box"]))
                          for t in named for m in marks)
        measured = {"series": name, "shares_non_colour_channels_with": sharing,
                    "nearest_name_label_px": None if nearest is None else round(nearest, 1)}
        if not sharing:
            outcome = "pass"
        elif nearest is not None and limit is None:
            outcome = "not-measurable"
        elif nearest is not None and nearest <= limit:
            outcome = "pass"
        else:
            outcome = "finding"
        action = ("Declare check_thresholds.direct_label_max_distance_px to judge direct labels."
                  if outcome == "not-measurable" else
                  f"Give series {name!r} a non-colour cue (dash, marker, pattern, shape) "
                  "or a direct label beside its marks; a colour-keyed legend does not count.")
        entries.append(_item("colour-only-encoding", frame_name, marks[0]["selector"], outcome,
                             measured, limit, action, marks[0]["box"]))
    return entries


def evaluate(report: dict, selected: tuple[str, ...], thresholds: dict[str, float]) -> dict:
    """Evaluate the blocker and only selected advisories. No rule is derived from knowledge/."""
    measure.validate_report(report)
    entries: list[dict] = []
    selected_set = set(selected) & set(GATES)
    for frame_name, frame in report["frames"].items():
        if "geometry-overflow" in selected_set:
            for selector, element in frame["elements"].items():
                overflow = element["overflow"]
                extent = max(overflow.values())
                entries.append(_item("geometry-overflow", frame_name, selector,
                                     "finding" if extent > 0 else "pass", overflow,
                                     {"canvas": report["canvas"]},
                                     "Keep the rendered bounds inside the declared canvas.",
                                     element["box"]))
        for selector, texts in frame["texts"].items():
            for text in texts:
                box = text["box"]
                if "effective-type-size" in selected_set:
                    threshold = thresholds.get("min_effective_px")
                    value = text.get("effective_size_px")
                    entries.append(_item("effective-type-size", frame_name, selector,
                                         _decision(value, threshold, low_bad=True), value,
                                         threshold,
                                         "Set a project type floor and make effective text size meet it.", box))
                if "text-contrast" in selected_set:
                    threshold = thresholds.get("contrast_min_ratio")
                    value = text.get("contrast_ratio")
                    entries.append(_item("text-contrast", frame_name, selector,
                                         _decision(value, threshold, low_bad=True), value,
                                         threshold,
                                         "Declare a project contrast floor and adjust actual foreground or background to meet it; inspect unsupported paint manually.", box))
                if "resolved-font-fallback" in selected_set:
                    outcome, measured_font = _font_outcome(text, frame.get("font_faces", []))
                    entries.append(_item("resolved-font-fallback", frame_name, selector,
                                         outcome, measured_font, measured_font["requested"],
                                         "Load the requested primary font or declare the actual fallback as the primary family.", box))
        if "label-collision" in selected_set:
            limit = thresholds.get("label_collision_max_area_px2")
            annotation = frame["annotation"]
            if not annotation.get("present"):
                entries.append(_item("label-collision", frame_name, "[data-series][data-value]",
                                     "not-measurable", None, limit,
                                     "Annotate marks with data-series and data-value to measure label collisions.", None))
            elif limit is None:
                entries.append(_item("label-collision", frame_name, "[data-series][data-value]",
                                     "not-measurable", None, None,
                                     "Declare check_thresholds.label_collision_max_area_px2.", None))
            else:
                for collision in annotation["collisions"]:
                    selector = collision["a"]
                    entries.append(_item("label-collision", frame_name, selector,
                                         _decision(collision["area"], limit, low_bad=False),
                                         collision["area"], limit,
                                         "Move the labels until their overlap area is within the project limit.",
                                         frame["elements"].get(selector, {}).get("box")))
        if "colour-only-encoding" in selected_set:
            entries.extend(_colour_only(frame_name, frame,
                                        thresholds.get("direct_label_max_distance_px")))
    if "stage-geometry" in selected_set:
        limit = thresholds.get("stage_max_drift_px")
        if limit is None:
            entries.append(_item("stage-geometry", "*", "*", "not-measurable", None,
                                 None, "Declare check_thresholds.stage_max_drift_px.", None))
        else:
            for diff in report["stage_diff"]:
                before, after = diff["before"], diff["after"]
                drift = (max(abs(before[k] - after[k]) for k in before)
                         if before is not None and after is not None else None)
                entries.append(_item("stage-geometry", diff["to"], diff["selector"],
                                     _decision(drift, limit, low_bad=False), drift, limit,
                                     "Keep the stage bounds within the project drift limit; check added or removed elements manually.",
                                     after or before))
    blocking = clipped_content(report)
    return {"command": "check", "schema_version": 1, "slug": report["slug"],
            "blocking": blocking,
            "selected_gates": [g for g in GATES if g in selected_set],
            "not_selected": [g for g in GATES if g not in selected_set],
            "unknown_selected": [g for g in selected if g not in GATES],
            "entries": entries,
            "summary": {"blocking": len(blocking),
                        **{state: sum(e["outcome"] == state for e in entries)
                           for state in ("finding", "pass", "not-measurable")}},
            "not_assessed": list(UNASSESSED)}


def _capture(report: dict, start: Path) -> dict[str, bytes]:
    """Capture each measured page again and require identical screenshot hashes."""
    cfg_module, cfg = render._load_config(start)
    visual, source, web_root = render.locate_visual(report["slug"], start, cfg)
    render.check_source_under_root(source, web_root)
    frames, _ = render.parse_manifest(source / render.MANIFEST_NAME)
    src_rel = source.resolve().relative_to(web_root.resolve()).as_posix()
    server = render._Server(web_root)
    images: dict[str, bytes] = {}
    try:
        chrome = render._Chrome(render.find_chrome())
        try:
            for frame in frames:
                url = server.url(src_rel, frame.url)
                signalled = render.page_implements_signal(server, src_rel, frame.url)
                target, sid = measure._open_frame(chrome, url, frame.name,
                                                  report["canvas"]["width"],
                                                  report["canvas"]["height"], signalled)
                try:
                    response = chrome._send_wait("Page.captureScreenshot", {"format": "png"}, sid, 60)
                    data = base64.b64decode(response["result"]["data"])
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != report["frames"][frame.name]["screenshot_sha256_before"]:
                        raise CheckError(f"frame {frame.name}: capture differs from measured screenshot")
                    images[frame.name] = data
                finally:
                    chrome._send("Target.closeTarget", {"targetId": target})
        finally:
            chrome.close()
    finally:
        server.close()
    return images


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)[:80]


def emit_ladder(report: dict, measured: dict, images: dict[str, bytes],
                output: Path, margin: float | None) -> dict:
    """Contact sheet first, then only flagged full-resolution regions."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    if output.exists() and any(output.iterdir()):
        raise CheckError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    names = list(images)
    thumbs = []
    for name in names:
        with Image.open(io.BytesIO(images[name])) as image:
            height = max(1, round(image.height * 640 / image.width))
            thumbs.append(image.convert("RGB").resize((640, height), Image.Resampling.LANCZOS))
    columns = min(4, len(thumbs))
    rows = (len(thumbs) + columns - 1) // columns
    label_height, gutter = 28, 12
    cell_height = max(im.height for im in thumbs)
    sheet = Image.new("RGB", (columns * 640 + (columns + 1) * gutter,
                              rows * (cell_height + label_height) + (rows + 1) * gutter), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (name, thumb) in enumerate(zip(names, thumbs)):
        row, column = divmod(index, columns)
        x = gutter + column * (640 + gutter)
        y = gutter + row * (cell_height + label_height + gutter)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + cell_height + 6), name, fill="black")
    contact = output / "01-contact-sheet-640.png"
    sheet.save(contact)
    crops = []
    flagged = [*(b for b in measured.get("blocking", []) if b["box"]),
               *(e for e in measured["entries"] if e["outcome"] == "finding" and e["box"])]
    for index, entry in enumerate(flagged if margin is not None else ()):
        frame = entry["frame"]
        box = entry["box"]
        with Image.open(io.BytesIO(images[frame])) as image:
            left = max(0, math.floor(box["x"] - margin))
            top = max(0, math.floor(box["y"] - margin))
            right = min(image.width, math.ceil(box["x"] + box["width"] + margin))
            bottom = min(image.height, math.ceil(box["y"] + box["height"] + margin))
            if right <= left or bottom <= top:
                continue
            path = output / f"{index + 2:02d}-{_safe_name(frame)}-{_safe_name(entry['selector'])}.png"
            image.crop((left, top, right, bottom)).save(path)
            crops.append({"path": str(path), "frame": frame, "selector": entry["selector"],
                          "bounds": [left, top, right, bottom]})
    ladder = {"contact_sheet": str(contact), "crops": crops,
              "crop_margin_px": margin, "order": [str(contact), *(c["path"] for c in crops)],
              "crop_status": "available" if margin is not None else "not-measurable",
              "crop_reason": None if margin is not None else
              "Declare check_thresholds.crop_margin_px to make contextual crops."}
    measured["ladder"] = ladder
    (output / "check.json").write_text(json.dumps(measured, indent=2) + "\n")
    return ladder


def check_visual(slug: str, start: Path, output: Path | None = None) -> dict:
    cfg_module, cfg = render._load_config(start)
    if cfg is None:
        raise CheckError("an adopted project is required for project-selected gates")
    report = measure.measure_visual(slug=slug, start=start)
    result = evaluate(report, cfg.advisory_checks, cfg.check_thresholds)
    margin = cfg.check_thresholds.get("crop_margin_px")
    images = _capture(report, start)
    visual, _, _ = render.locate_visual(slug, start, cfg)
    destination = output or visual / "checks" / uuid.uuid4().hex
    emit_ladder(report, result, images, destination, margin)
    return result
