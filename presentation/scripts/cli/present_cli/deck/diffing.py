"""Compare two rendered galleries slide by slide (task 0016). Reports change, never quality.

Slides are matched by (slide id, build step). A slide is `same` when its page PNGs are
byte-identical (or, for unrendered galleries, its slide XML is); otherwise the pixel difference
is measured and, when an output folder is given, old/new/diff crops of the changed region are
written there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load(folder: Path) -> dict[str, Any]:
    m = folder / "manifest.json"
    if not m.is_file():
        raise FileNotFoundError(
            f"{folder}: no manifest.json (not a `present components gallery` output)"
        )
    return json.loads(m.read_text())


def compare(old: Path, new: Path, out: Path | None = None) -> dict[str, Any]:
    a, b = load(old), load(new)
    key = lambda s: (s["id"], s["step"])  # noqa: E731
    sa, sb = {key(s): s for s in a["slides"]}, {key(s): s for s in b["slides"]}
    rows = []
    for k in sorted(set(sa) | set(sb), key=lambda k: (k[0], k[1])):
        x, y = sa.get(k), sb.get(k)
        row: dict[str, Any] = {
            "id": k[0],
            "step": k[1],
            "component": (y or x)["component"],
        }
        if x is None or y is None:
            row["status"] = "added" if x is None else "removed"
        elif x.get("png_sha256") and y.get("png_sha256"):
            if x["png_sha256"] == y["png_sha256"]:
                row["status"] = "same"
            else:
                row.update(
                    status="changed", **_pixels(old / x["png"], new / y["png"], out, k)
                )
        else:
            row["status"] = "same" if x["xml_sha256"] == y["xml_sha256"] else "changed"
            row["basis"] = "xml"
        rows.append(row)
    changed = sorted({r["component"] for r in rows if r["status"] != "same"})
    return {
        "old": {"components": a["components"], "tokens": a["tokens"]},
        "new": {"components": b["components"], "tokens": b["tokens"]},
        "slides": rows,
        "changed_components": changed,
        "counts": {
            s: sum(1 for r in rows if r["status"] == s)
            for s in ("same", "changed", "added", "removed")
        },
    }


def _pixels(pa: Path, pb: Path, out: Path | None, k) -> dict[str, Any]:
    from PIL import Image, ImageChops

    ia, ib = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
    if ia.size != ib.size:
        return {"pixels": None, "reason": f"size {ia.size} → {ib.size}"}
    d = ImageChops.difference(ia, ib)
    bbox = d.getbbox()
    r, g, b = d.split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), b).point(
        lambda v: 255 if v else 0
    )
    n = mask.histogram()[255]  # pixels that differ in any channel, by any amount
    info: dict[str, Any] = {"pixels": n, "bbox": list(bbox) if bbox else None}
    if out is not None and bbox:
        out.mkdir(parents=True, exist_ok=True)
        pad = 12
        box = (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(ia.width, bbox[2] + pad),
            min(ia.height, bbox[3] + pad),
        )
        stem = f"{k[0]}-{k[1]}"
        crops = {}
        for tag, im in (
            ("old", ia),
            ("new", ib),
            ("diff", d.point(lambda v: 255 if v else 0)),
        ):
            p = out / f"{stem}-{tag}.png"
            im.crop(box).save(p)
            crops[tag] = str(p)
        info["crops"] = crops
    return info
