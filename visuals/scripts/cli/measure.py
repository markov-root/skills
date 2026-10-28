"""Read-only browser scene measurement for authored-render frames.

The page probe reads DOM geometry and computed paint declarations. Font usage is
queried separately through CDP's CSS.getPlatformFontsForNode: unlike
getComputedStyle(fontFamily), that method reports the platform fonts which
actually rendered glyphs, including fallback after a failed @font-face source.
document.fonts.check() only answers whether a specified face is available and
can also report true for an absent family; it cannot identify glyph fallback.

Background composition is deliberately bounded. Unsupported paint syntax
returns null, never a fabricated colour or contrast. It handles the simple
solid, two-stop linear gradient, and full-cover ::before cases exercised by
task 0011 fixtures; image, blend-mode, filter, and partial pseudo geometries
remain unknown. The task record states the resulting AC-4 limitation.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import render

SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 1_000_000
MAX_SCRIPT_BYTES = 24_000
SCRIPT = Path(__file__).with_name("measure.js")


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


def _screenshot_hash(chrome: render._Chrome, sid: str) -> str:
    import base64  # noqa: PLC0415
    resp = chrome._send_wait("Page.captureScreenshot", {"format": "png"}, sid, 60)
    return hashlib.sha256(base64.b64decode(resp["result"]["data"])).hexdigest()


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
                bg = entry["background"]
                if bg is not None and (not isinstance(bg, dict) or not isinstance(bg.get("color"), str) or not isinstance(bg.get("rgba"), list) or len(bg["rgba"]) != 4 or not all(number(v) for v in bg["rgba"])):
                    raise MeasureError(f"frame {name!r} has invalid background")
                if entry.get("contrast_ratio") is not None and not number(entry["contrast_ratio"]):
                    raise MeasureError(f"frame {name!r} has invalid contrast ratio")
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
                    # Evaluate in a separate JS world. Page scripts can replace
                    # getComputedStyle/querySelectorAll on their own globals;
                    # invoking those replacements would execute page code and
                    # could mutate the artifact. The isolated world shares DOM
                    # nodes but has fresh native built-ins and prototypes.
                    frame_id = chrome._send_wait("Page.getFrameTree", session_id=sid)["result"]["frameTree"]["frame"]["id"]
                    context_id = chrome._send_wait("Page.createIsolatedWorld", {
                        "frameId": frame_id, "worldName": "visuals-measure-v1",
                    }, sid)["result"]["executionContextId"]
                    evaluated = chrome._send_wait("Runtime.evaluate", {
                        "expression": script, "returnByValue": True,
                        "awaitPromise": False, "timeout": 10_000,
                        "contextId": context_id,
                    }, sid, 15)
                    measured = _value(evaluated)
                    if not isinstance(measured, dict):
                        raise MeasureError(f"frame {frame.name!r}: probe returned no object")
                    if measured.get("error"):
                        raise MeasureError(f"frame {frame.name!r}: {measured['error']}")
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
                    report["frames"][frame.name] = measured
                finally:
                    chrome._send("Target.closeTarget", {"targetId": target})
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
