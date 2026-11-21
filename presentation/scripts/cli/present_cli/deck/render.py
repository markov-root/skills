"""PDF, page PNGs and a contact sheet from a pptx, through LibreOffice (tasks 0008, 0016).

Needs `soffice` (LibreOffice), `pdftoppm` (poppler) and, for the contact sheet, ImageMagick
`montage`; `missing_tools()` names whichever is absent so callers degrade honestly. A throwaway
LibreOffice profile per call keeps renders independent of any open LibreOffice and of each other.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

TOOLS = {
    "soffice": "LibreOffice (sudo apt install libreoffice-impress)",
    "pdftoppm": "poppler (sudo apt install poppler-utils)",
    "montage": "ImageMagick (sudo apt install imagemagick)",
}


def soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def missing_tools() -> dict[str, str]:
    found = {
        "soffice": soffice(),
        "pdftoppm": shutil.which("pdftoppm"),
        "montage": shutil.which("montage"),
    }
    return {k: TOOLS[k] for k, v in found.items() if not v}


def to_pdf(pptx: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="present-lo-") as prof:
        subprocess.run(
            [
                soffice(),
                f"-env:UserInstallation=file://{prof}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out),
                str(pptx),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
    pdf = out / (pptx.stem + ".pdf")
    if not pdf.is_file():
        raise RuntimeError(f"LibreOffice produced no PDF for {pptx.name}")
    return pdf


def pages(pdf: Path, out: Path, dpi: int = 60) -> list[Path]:
    """One PNG per page, named page-NN.png (1-based)."""
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="present-pages-") as tmp:
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(Path(tmp) / "p")],
            check=True,
            timeout=600,
        )
        made = sorted(
            Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[1])
        )
        result = []
        for i, p in enumerate(made, 1):
            dest = out / f"page-{i:02d}.png"
            shutil.move(str(p), dest)
            result.append(dest)
    return result


def contact_sheet(pngs: list[Path], dest: Path, tile: str = "6x") -> Path:
    subprocess.run(
        [
            "montage",
            *map(str, pngs),
            "-tile",
            tile,
            "-geometry",
            "+4+4",
            "-background",
            "gray60",
            str(dest),
        ],
        check=True,
        timeout=600,
    )
    return dest
