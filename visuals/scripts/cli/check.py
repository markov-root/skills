"""Project-selected advisory evaluation of a measured authored visual.

No finding changes an exit status. Unknown paint and absent annotations stay
explicitly unmeasured. The project supplies every numeric gate threshold.
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


def evaluate(report: dict, selected: tuple[str, ...], thresholds: dict[str, float]) -> dict:
    """Evaluate only selected checks. No rule is derived from knowledge/."""
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
                    requested = text.get("requested_font_family", "")
                    primary = requested.split(",", 1)[0].strip().strip("\"'")
                    used = [f["family"] for f in text["resolved_fonts"] if f["glyph_count"] > 0]
                    # CDP reports a font's internal family name, which may
                    # differ from an @font-face alias or a system alias. A
                    # mismatch alone is not proof of fallback.
                    outcome = ("pass" if primary and any(
                        f.casefold() == primary.casefold() for f in used)
                        else "not-measurable")
                    entries.append(_item("resolved-font-fallback", frame_name, selector,
                                         outcome, used or None, primary or None,
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
            entries.append(_item("colour-only-encoding", frame_name, "[data-series]",
                                 "not-measurable", None, None,
                                 "Inspect the encoding manually; this scene report does not identify colour channels or redundant encodings.", None))
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
    return {"command": "check", "schema_version": 1, "slug": report["slug"],
            "selected_gates": [g for g in GATES if g in selected_set],
            "not_selected": [g for g in GATES if g not in selected_set],
            "unknown_selected": [g for g in selected if g not in GATES],
            "entries": entries,
            "summary": {state: sum(e["outcome"] == state for e in entries)
                        for state in ("finding", "pass", "not-measurable")},
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
    flagged = (e for e in measured["entries"] if e["outcome"] == "finding" and e["box"])
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
