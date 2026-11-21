"""Deck work that binds a brand runs here, in its own process (`python -m present_cli.deck.worker`),
because the token file is read once at import (brand.py). The parent passes PRESENT_TOKENS /
PRESENT_REPO in the environment and reads one JSON object from stdout.

    worker gallery <out dir> [--no-render]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fingerprint(pptx: Path) -> list[str]:
    """sha256 of each slide's XML, in deck order (renderer-independent)."""
    from pptx import Presentation

    return [_sha(s.part.blob) for s in Presentation(str(pptx)).slides]


def gallery(out: Path, render_it: bool = True) -> dict:
    from . import brand, components, gallery as g, render

    out.mkdir(parents=True, exist_ok=True)
    pptx, counts = g.build(out / "gallery.pptx")
    prints = fingerprint(pptx)
    slides, i = [], 0
    for sid, n in counts:
        comp = next(s["component"] for s in g.SLIDES if s["id"] == sid)
        for k in range(n):
            slides.append(
                {
                    "id": sid,
                    "component": comp,
                    "step": k + 1,
                    "page": i + 1,
                    "xml_sha256": prints[i],
                }
            )
            i += 1
    result = {
        "components": components.COMPONENTS_VERSION,
        "tokens": {**brand.identity(), "name": brand.TOKENS_NAME},
        "pptx": str(pptx),
        "slides": slides,
        "rendered": False,
    }
    if render_it:
        missing = render.missing_tools()
        if missing:
            result["unavailable"] = missing
        else:
            pdf = render.to_pdf(pptx, out)
            pngs = render.pages(pdf, out / "pages")
            for s, p in zip(slides, pngs):
                s["png"] = str(p.relative_to(out))
                s["png_sha256"] = _sha(p.read_bytes())
            render.contact_sheet(pngs, out / "contact-sheet.png")
            result.update(
                rendered=True,
                pdf=str(pdf),
                contact_sheet=str(out / "contact-sheet.png"),
            )
    (out / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str]) -> int:
    if not argv:
        print(json.dumps({"error": "usage: worker gallery <out> [--no-render]"}))
        return 2
    if argv[0] == "gallery":
        print(json.dumps(gallery(Path(argv[1]), "--no-render" not in argv)))
        return 0
    if argv[0] == "build":
        from . import build

        print(json.dumps(build.run(json.loads(Path(argv[1]).read_text()))))
        return 0
    print(json.dumps({"error": f"unknown verb {argv[0]}"}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
