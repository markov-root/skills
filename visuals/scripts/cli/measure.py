"""Read-only browser scene measurement for authored-render frames.

The page probe reads DOM geometry and computed paint declarations. Font usage is
queried separately through CDP's CSS.getPlatformFontsForNode: unlike
getComputedStyle(fontFamily), that method reports the platform fonts which
actually rendered glyphs, including fallback after a failed @font-face source.
document.fonts.check() only answers whether a specified face is available and
can also report true for an absent family; it cannot identify glyph fallback.

Background composition has two instruments. The in-page probe composes CSS
paint for the bounded cases it can prove (solid, two-stop linear gradient,
full-cover ::before) and returns null for anything else. The twin-render pixel
oracle covers the rest: it loads the same frame in a SECOND browser target,
makes only glyph paint transparent there (text fill, stroke, shadow,
decoration — properties that cannot move layout), proves the twin's element
geometry equals the measured page's, and samples the rendered pixels behind
each text line. Images, filters, blend modes, and partial pseudo-elements are
therefore read from what Chrome actually painted, not re-derived from CSS.
The measured page itself is never touched, so the byte-identical screenshot
proof (criterion 8) is unaffected.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
from pathlib import Path

import render

SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 1_000_000
MAX_SCRIPT_BYTES = 24_000
SCRIPT = Path(__file__).with_name("measure.js")
#: Upper bound on pixels sampled per text entry; a stride keeps cost bounded.
MAX_SAMPLES_PER_TEXT = 4096
PIXEL_METHOD = "twin-render-pixel-sample"
#: Max per-channel difference at the CSS sample point for the two instruments
#: to count as agreeing (antialiasing and colour rounding, not a design value).
CSS_AGREEMENT_TOLERANCE = 3
#: Applied to the twin target only. Every property here paints glyphs and none
#: affects layout; the twin's geometry is compared with the measured page's
#: before any pixel is trusted. Do not add ::first-letter/::first-line: a rule
#: on them creates a separate first-letter box and moves text (the geometry
#: guard caught exactly that). The properties are inherited, so `*` reaches
#: those pseudo-elements anyway.
GLYPH_HIDING_CSS = """
*, *::before, *::after {
  -webkit-text-fill-color: transparent !important;
  -webkit-text-stroke-color: transparent !important;
  text-shadow: none !important;
  text-decoration-color: transparent !important;
  text-emphasis-color: transparent !important;
  caret-color: transparent !important;
  transition: none !important;
}
text, tspan, textPath { fill: transparent !important; stroke: transparent !important; }
"""


class MeasureError(Exception):
    """A named measurement error; no findings or severity semantics."""


def _value(resp: dict) -> object:
    result = resp.get("result", {}).get("result", {})
    if resp.get("result", {}).get("exceptionDetails"):
        raise MeasureError("instrumentation raised a browser exception")
    return result.get("value")


def _open_frame(chrome: render._Chrome, url: str, name: str, width: int,
                height: int, signalled: bool) -> tuple[str, str]:
    create = chrome._send("Target.createTarget", {"url": url})
    chrome._pending_url = url
    target, sid = chrome._await_session(create)
    try:
        chrome._send_wait("Page.enable", session_id=sid)
        chrome._send_wait("Runtime.enable", session_id=sid)
        chrome._send_wait("DOM.enable", session_id=sid)
        chrome._send_wait("CSS.enable", session_id=sid)
        chrome._send_wait("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1,
            "mobile": False,
        }, sid)
        chrome._wait_load(sid, name, url)
        if signalled:
            chrome._wait_ready(sid, name, url, render.DEFAULT_READINESS_TIMEOUT_S)
            chrome._wait_settled(sid, name, url, render.DEFAULT_READINESS_TIMEOUT_S)
        else:
            chrome._send_wait("Runtime.evaluate", {
                "expression": "document.fonts.ready.then(() => true)",
                "awaitPromise": True, "returnByValue": True,
            }, sid)
        return target, sid
    except Exception:
        chrome._send("Target.closeTarget", {"targetId": target})
        raise


def _screenshot_png(chrome: render._Chrome, sid: str) -> bytes:
    resp = chrome._send_wait("Page.captureScreenshot", {"format": "png"}, sid, 60)
    return base64.b64decode(resp["result"]["data"])


def _screenshot_hash(chrome: render._Chrome, sid: str) -> str:
    return hashlib.sha256(_screenshot_png(chrome, sid)).hexdigest()


def _evaluate_probe(chrome: render._Chrome, sid: str, script: str, name: str) -> dict:
    # Evaluate in a separate JS world. Page scripts can replace
    # getComputedStyle/querySelectorAll on their own globals; invoking those
    # replacements would execute page code and could mutate the artifact. The
    # isolated world shares DOM nodes but has fresh native built-ins.
    frame_id = chrome._send_wait("Page.getFrameTree", session_id=sid)["result"]["frameTree"]["frame"]["id"]
    context_id = chrome._send_wait("Page.createIsolatedWorld", {
        "frameId": frame_id, "worldName": "visuals-measure-v1",
    }, sid)["result"]["executionContextId"]
    evaluated = chrome._send_wait("Runtime.evaluate", {
        "expression": script, "returnByValue": True,
        "awaitPromise": False, "timeout": 10_000, "contextId": context_id,
    }, sid, 15)
    measured = _value(evaluated)
    if not isinstance(measured, dict):
        raise MeasureError(f"frame {name!r}: probe returned no object")
    if measured.get("error"):
        raise MeasureError(f"frame {name!r}: {measured['error']}")
    return measured


def _parse_css_rgba(value: object) -> tuple[float, float, float, float] | None:
    import re  # noqa: PLC0415
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)", value.strip())
    if not m:
        return None
    alpha = 1.0 if m.group(4) is None else float(m.group(4))
    return float(m.group(1)), float(m.group(2)), float(m.group(3)), alpha


def _luminance(rgb: tuple[float, ...]) -> float:
    def linear(n: float) -> float:
        n /= 255
        return n / 12.92 if n <= 0.04045 else ((n + 0.055) / 1.055) ** 2.4
    return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2])


def _contrast(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    x, y = _luminance(a), _luminance(b)
    return round((max(x, y) + 0.05) / (min(x, y) + 0.05), 3)


def _pixel_background(image, entry: dict) -> dict | None:
    """Sample the twin's pixels behind one text entry's line boxes.

    Returns the sampled luminance range, the worst (minimum) and median
    contrast of the text colour over every sampled pixel, and the worst pixel;
    None when no pixel lies inside the canvas. Contrast is null, with a stated
    reason, when the painted text colour is not knowable from CSS (an effect
    on the text or an ancestor, or a non-plain fill such as clipped gradient).
    """
    width, height = image.size
    rects = []
    for rect in entry.get("lines") or [entry["box"]]:
        x0 = max(0, math.floor(rect["x"]))
        y0 = max(0, math.floor(rect["y"]))
        x1 = min(width, math.ceil(rect["x"] + rect["width"]))
        y1 = min(height, math.ceil(rect["y"] + rect["height"]))
        if x1 > x0 and y1 > y0:
            rects.append((x0, y0, x1, y1))
    area = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects)
    if not area:
        return None
    # A square grid step bounds the sample count without materialising
    # every coordinate of a large text box.
    step = max(1, math.ceil(math.sqrt(area / MAX_SAMPLES_PER_TEXT)))
    pixels = image.load()
    sampled = sorted((pixels[x, y][:3] for x0, y0, x1, y1 in rects
                      for y in range(y0, y1, step) for x in range(x0, x1, step)),
                     key=_luminance)
    darkest, median, lightest = sampled[0], sampled[len(sampled) // 2], sampled[-1]
    fg = _parse_css_rgba(entry.get("foreground"))
    result: dict = {"method": PIXEL_METHOD, "samples": len(sampled),
                    "darkest": list(darkest), "median": list(median),
                    "lightest": list(lightest), "contrast_min": None,
                    "contrast_median": None}
    effects = entry.get("foreground_effects") or []
    if "background-clip:text" in effects:
        # The glyphs are the element's own background, which the twin still
        # paints; the samples include glyph pixels and cannot stand for the
        # ground behind the text.
        result["glyph_paint_visible"] = True
        result["contrast_unknown_reason"] = (
            "the glyphs are painted with the element's background (background-clip: text)")
    elif effects:
        result["contrast_unknown_reason"] = (
            "the text's painted colour is transformed by " + ", ".join(effects)
            + " on it or an ancestor")
    elif fg is None or fg[3] == 0:
        result["contrast_unknown_reason"] = "the text colour is not a plain colour"
    else:
        def actual(bg: tuple[int, ...]) -> tuple[float, ...]:
            a = fg[3] * entry.get("foreground_opacity", 1)
            return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3))
        # The worst case is the background pixel whose luminance is closest
        # to the text's, which can be a mid-tone, so every sample is scored.
        ratios = sorted((_contrast(actual(px), px), px) for px in sampled)
        result["contrast_min"] = ratios[0][0]
        result["contrast_median"] = ratios[len(ratios) // 2][0]
        result["worst"] = list(ratios[0][1])
    return result


def _twin_backgrounds(chrome: render._Chrome, url: str, name: str, width: int,
                      height: int, signalled: bool, script: str,
                      measured: dict) -> dict:
    """Run the pixel oracle for one frame; return its status record.

    Mutates only `measured["texts"]` entries (adding `background_pixels`, and
    filling `background`/`contrast_ratio` where CSS composition was unknown).
    """
    from PIL import Image  # noqa: PLC0415  (declared by the uv command header)
    target, sid = _open_frame(chrome, url, name, width, height, signalled)
    try:
        frame_id = chrome._send_wait("Page.getFrameTree", session_id=sid)["result"]["frameTree"]["frame"]["id"]
        sheet = chrome._send_wait("CSS.createStyleSheet", {"frameId": frame_id}, sid)
        sheet_id = sheet.get("result", {}).get("styleSheetId")
        if not sheet_id:
            return {"status": "unavailable", "reason": "twin stylesheet could not be created"}
        chrome._send_wait("CSS.setStyleSheetText", {"styleSheetId": sheet_id,
                                                    "text": GLYPH_HIDING_CSS}, sid)
        twin = _evaluate_probe(chrome, sid, script, name)
        original_boxes = {k: v["box"] for k, v in measured["elements"].items()}
        twin_boxes = {k: v["box"] for k, v in twin["elements"].items()}
        if original_boxes != twin_boxes:
            changed = sorted(k for k in original_boxes.keys() | twin_boxes.keys()
                             if original_boxes.get(k) != twin_boxes.get(k))
            return {"status": "unavailable",
                    "reason": "twin geometry differs from the measured page",
                    "differing_selectors": changed[:10]}
        png = _screenshot_png(chrome, sid)
    finally:
        chrome._send("Target.closeTarget", {"targetId": target})
    with Image.open(io.BytesIO(png)) as raw:
        image = raw.convert("RGB")
    sampled = 0
    for entries in measured["texts"].values():
        for entry in entries:
            pixels = _pixel_background(image, entry)
            entry["background_pixels"] = pixels
            if pixels is None:
                continue
            sampled += 1
            if pixels.get("glyph_paint_visible"):
                continue  # the samples are not the ground; leave CSS (or null) standing
            css_bg = entry["background"]
            if css_bg is not None and css_bg.get("sample"):
                sample = css_bg["sample"]
                px = image.getpixel((min(image.width - 1, int(sample["x"])),
                                     min(image.height - 1, int(sample["y"]))))
                pixels["css_delta"] = max(abs(px[i] - css_bg["rgba"][i]) for i in range(3))
                if pixels["css_delta"] <= CSS_AGREEMENT_TOLERANCE:
                    continue  # both instruments agree; keep the exact CSS value
                # The painted pixel at the CSS sample point contradicts the CSS
                # composition (an SVG shape, a layer CSS cannot see): the
                # pixels are what the reader sees, so they win, and the
                # discarded CSS colour stays on record.
                pixels["css_overruled"] = css_bg["color"]
            entry["background"] = {
                "color": "rgb({}, {}, {})".format(*pixels["median"]),
                "rgba": [*pixels["median"], 1], "method": PIXEL_METHOD,
            }
            entry["contrast_ratio"] = pixels["contrast_min"]
    return {"status": "ok", "method": PIXEL_METHOD, "texts_sampled": sampled,
            "twin_geometry": "identical"}


def _font_usage(chrome: render._Chrome, sid: str, parent: str,
                root_id: int) -> list[dict]:
    queried = chrome._send_wait("DOM.querySelector", {
        "nodeId": root_id, "selector": parent,
    }, sid)
    node_id = queried.get("result", {}).get("nodeId")
    if not node_id:
        raise MeasureError(f"selector no longer resolves during font query: {parent}")
    raw = chrome._send_wait("CSS.getPlatformFontsForNode", {"nodeId": node_id}, sid)
    return [{"family": f["familyName"], "glyph_count": f["glyphCount"],
             "custom": f["isCustomFont"]} for f in raw["result"]["fonts"]]


def _stage_diff(reports: dict[str, dict]) -> list[dict]:
    names = list(reports)
    if len(names) < 2:
        return []
    base = reports[names[0]]["elements"]
    differences: list[dict] = []
    for name in names[1:]:
        other = reports[name]["elements"]
        for selector in sorted(base.keys() | other.keys()):
            a = base.get(selector, {}).get("box")
            b = other.get(selector, {}).get("box")
            if a != b:
                differences.append({"from": names[0], "to": name,
                                    "selector": selector, "before": a, "after": b})
    return differences


def validate_report(report: dict) -> None:
    """Validate the version-1 report contract before it escapes the command.

    This is intentionally stdlib-only: the command runs without a JSON Schema
    dependency, but malformed browser output fails closed rather than silently
    becoming an agent-facing report.
    """
    def number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def box(value: object) -> bool:
        return (isinstance(value, dict) and set(value) == {"x", "y", "width", "height"}
                and all(number(v) for v in value.values())
                and value["width"] >= 0 and value["height"] >= 0)

    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION:
        raise MeasureError("report schema version is invalid")
    if not isinstance(report.get("slug"), str) or not report["slug"]:
        raise MeasureError("report slug is invalid")
    canvas = report.get("canvas")
    if not isinstance(canvas, dict) or not all(number(canvas.get(k)) and canvas[k] > 0
                                                 for k in ("width", "height")):
        raise MeasureError("report canvas is invalid")
    if canvas.get("delivery_scale") is not None and not number(canvas["delivery_scale"]):
        raise MeasureError("report delivery scale is invalid")
    if not isinstance(report.get("frames"), dict) or not isinstance(report.get("stage_diff"), list):
        raise MeasureError("report frames or stage_diff has an invalid type")
    for name, frame in report["frames"].items():
        if not isinstance(name, str) or not isinstance(frame, dict):
            raise MeasureError("report frame entry is invalid")
        if not isinstance(frame.get("elements"), dict) or not isinstance(frame.get("texts"), dict):
            raise MeasureError(f"frame {name!r} lacks selector-keyed measurements")
        if not isinstance(frame.get("annotation"), dict) or not isinstance(frame["annotation"].get("present"), bool):
            raise MeasureError(f"frame {name!r} annotation is invalid")
        for selector, entry in frame["elements"].items():
            if not isinstance(selector, str) or not isinstance(entry, dict) or not box(entry.get("box")):
                raise MeasureError(f"frame {name!r} has invalid element geometry")
            overflow = entry.get("overflow")
            if not isinstance(overflow, dict) or set(overflow) != {"left", "top", "right", "bottom"} or not all(number(v) and v >= 0 for v in overflow.values()):
                raise MeasureError(f"frame {name!r} has invalid overflow")
            if not isinstance(entry.get("overlaps"), list):
                raise MeasureError(f"frame {name!r} has invalid overlaps")
        for key, entries in frame["texts"].items():
            if not isinstance(key, str) or not isinstance(entries, list):
                raise MeasureError(f"frame {name!r} has invalid text entry")
            for entry in entries:
                if not isinstance(entry, dict) or "resolved_fonts" not in entry or "background" not in entry:
                    raise MeasureError(f"frame {name!r} has incomplete text measurements")
                if entry.get("parent_selector") != key or not isinstance(entry.get("content"), str) or not box(entry.get("box")):
                    raise MeasureError(f"frame {name!r} has invalid text locator or geometry")
                if not number(entry.get("computed_size_px")) or not isinstance(entry.get("resolved_fonts"), list):
                    raise MeasureError(f"frame {name!r} has invalid text font data")
                for font in entry["resolved_fonts"]:
                    if not isinstance(font, dict) or not isinstance(font.get("family"), str) or not isinstance(font.get("glyph_count"), int) or not isinstance(font.get("custom"), bool):
                        raise MeasureError(f"frame {name!r} has invalid platform font usage")
                pixels = entry.get("background_pixels")
                if pixels is not None and (not isinstance(pixels, dict) or pixels.get("method") != PIXEL_METHOD or not all(isinstance(pixels.get(k), list) and len(pixels[k]) == 3 for k in ("darkest", "median", "lightest"))):
                    raise MeasureError(f"frame {name!r} has invalid pixel background")
                bg = entry["background"]
                if bg is not None and (not isinstance(bg, dict) or not isinstance(bg.get("color"), str) or not isinstance(bg.get("rgba"), list) or len(bg["rgba"]) != 4 or not all(number(v) for v in bg["rgba"])):
                    raise MeasureError(f"frame {name!r} has invalid background")
                if entry.get("contrast_ratio") is not None and not number(entry["contrast_ratio"]):
                    raise MeasureError(f"frame {name!r} has invalid contrast ratio")
        oracle = frame.get("pixel_oracle")
        if oracle is not None and (not isinstance(oracle, dict) or oracle.get("status") not in {"ok", "unavailable"}):
            raise MeasureError(f"frame {name!r} has invalid pixel oracle status")
        for field in ("screenshot_sha256_before", "screenshot_sha256_after"):
            if field in frame and (not isinstance(frame[field], str) or len(frame[field]) != 64):
                raise MeasureError(f"frame {name!r} has invalid screenshot digest")
    for diff in report["stage_diff"]:
        if not isinstance(diff, dict) or not all(isinstance(diff.get(k), str) for k in ("from", "to", "selector")) or not (diff.get("before") is None or box(diff["before"])) or not (diff.get("after") is None or box(diff["after"])):
            raise MeasureError("report stage diff is invalid")


def measure_visual(*, slug: str, start: Path,
                   max_bytes: int = MAX_REPORT_BYTES) -> dict:
    """Measure every manifest frame and compare each later stage with the first.

    No render artifact is written. A before/after screenshot SHA-256 pair per
    frame supplies the byte-identical non-perturbation evidence. The bounded
    probe is evaluated once; page-authored callbacks are never invoked by it.
    """
    if not 1 <= max_bytes <= MAX_REPORT_BYTES:
        raise MeasureError(f"max_bytes must be 1..{MAX_REPORT_BYTES}")
    script = SCRIPT.read_text(encoding="utf-8")
    if len(script.encode()) > MAX_SCRIPT_BYTES:
        raise MeasureError("instrumentation exceeds its 24 KB source bound")
    cfg_module, cfg = render._load_config(Path(start))
    visual, source, web_root = render.locate_visual(slug, Path(start), cfg)
    render.check_source_under_root(source, web_root)
    frames, _warnings = render.parse_manifest(source / render.MANIFEST_NAME)
    if cfg:
        profile = cfg.canvas_profiles[cfg.default_profile]
        width, height = profile.width, profile.height
        scale = profile.delivery_scale
    else:
        width, height = render._env_viewport()
        scale = None
    src_rel = source.resolve().relative_to(web_root.resolve()).as_posix()
    report: dict = {"schema_version": SCHEMA_VERSION, "slug": slug,
                    "canvas": {"width": width, "height": height,
                               "delivery_scale": scale},
                    "frames": {}, "stage_diff": [],
                    "limits": {"max_report_bytes": max_bytes,
                               "max_elements_per_frame": 1600,
                               "max_texts_per_frame": 600}}
    server = render._Server(web_root)
    try:
        chrome = render._Chrome(render.find_chrome())
        try:
            for frame in frames:
                url = server.url(src_rel, frame.url)
                signalled = render.page_implements_signal(server, src_rel, frame.url)
                target, sid = _open_frame(chrome, url, frame.name, width, height, signalled)
                try:
                    before = _screenshot_hash(chrome, sid)
                    measured = _evaluate_probe(chrome, sid, script, frame.name)
                    root_id = chrome._send_wait("DOM.getDocument", session_id=sid)["result"]["root"]["nodeId"]
                    cached: dict[str, list[dict]] = {}
                    for parent, entries in measured["texts"].items():
                        cached[parent] = _font_usage(chrome, sid, parent, root_id)
                        for entry in entries:
                            entry["resolved_fonts"] = cached[parent]
                            entry["effective_size_px"] = (
                                round(entry["computed_size_px"] * scale, 3)
                                if scale is not None else None
                            )
                    after = _screenshot_hash(chrome, sid)
                    if before != after:
                        raise MeasureError(
                            f"frame {frame.name!r}: measurement changed screenshot bytes"
                        )
                    measured["screenshot_sha256_before"] = before
                    measured["screenshot_sha256_after"] = after
                finally:
                    chrome._send("Target.closeTarget", {"targetId": target})
                try:
                    measured["pixel_oracle"] = _twin_backgrounds(
                        chrome, url, frame.name, width, height, signalled, script, measured)
                except (MeasureError, render.RenderError) as exc:
                    # The oracle is an extra instrument: its failure leaves the
                    # CSS measurements standing and says why, never aborts.
                    if isinstance(exc, render.RenderUnavailable):
                        raise
                    measured["pixel_oracle"] = {"status": "unavailable",
                                                "reason": f"twin render failed: {exc}"}
                report["frames"][frame.name] = measured
        finally:
            chrome.close()
    finally:
        server.close()
    report["stage_diff"] = _stage_diff(report["frames"])
    validate_report(report)
    report["report_bytes"] = 0
    for _ in range(4):  # decimal digit count converges after at most one change
        encoded = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        if report["report_bytes"] == len(encoded):
            break
        report["report_bytes"] = len(encoded)
    else:
        raise MeasureError("report byte count did not converge")
    if len(encoded) > max_bytes:
        raise MeasureError(
            f"report would be {len(encoded)} bytes, above the {max_bytes}-byte bound; "
            "narrow the master or raise the bound up to 1000000"
        )
    return report
