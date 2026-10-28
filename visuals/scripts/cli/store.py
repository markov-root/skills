"""Artifact store — immutable version directories, `latest`, receipts, previews.

The store owns the mechanical bookkeeping audit 0001 F5 found done by hand and
done badly: version identity derived rather than typed, `latest` repointed
atomically only after every frame succeeded, a receipt with per-frame content
hashes (new relative to the reference corpus — what makes reproduction
checkable), and automatic 640px previews plus a contact sheet.

Immutability is absolute. A version directory is never modified: every render
builds into a private staging directory that is atomically renamed into place
only after all of its content exists. A failure anywhere removes the staging
directory and leaves the previous `latest` intact. The stage-and-commit and
repoint operations are race-safe re-checking at the commit boundary.

Stdlib only; Pillow is imported lazily by the preview functions (the render
command's PEP 723 header declares it), so the store degrades honestly when
previews cannot be produced instead of failing the render.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

# Version directories are `vX.Y.Z`. Derivation reads the store; it is never
# hand-supplied (audit F5: version identity typed in up to four places).
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class StoreError(Exception):
    """A blocking store failure. The message names the cause; never a traceback."""


# --------------------------------------------------------------------------
# version identity — derived once, from the directories that exist
# --------------------------------------------------------------------------


def existing_versions(visual_dir: Path) -> tuple[str, ...]:
    """All version directory names under a visual, sorted ascending semver."""
    found: list[tuple[tuple[int, int, int], str]] = []
    if visual_dir.is_dir():
        for entry in visual_dir.iterdir():
            if entry.is_dir() and (m := VERSION_RE.match(entry.name)):
                found.append(((int(m[1]), int(m[2]), int(m[3])), entry.name))
    found.sort()
    return tuple(name for _, name in found)


def derive_next_version(visual_dir: Path, level: str = "patch") -> str:
    """Derive the next version from the existing directories. Never hand-supplied.

    Base when no versions exist is 0.0.0: `bump patch` -> v0.0.1, `minor` ->
    v0.1.0, `major` -> v1.0.0. An unknown level is a caller defect.
    """
    if level not in ("patch", "minor", "major"):
        raise StoreError(f"unknown version level {level!r} (expected patch, minor, or major)")
    versions = existing_versions(visual_dir)
    latest = VERSION_RE.match(versions[-1]) if versions else None
    major, minor, patch = (
        (int(latest[1]), int(latest[2]), int(latest[3])) if latest else (0, 0, 0)
    )
    if level == "patch":
        patch += 1
    elif level == "minor":
        minor += 1
        patch = 0
    else:
        major += 1
        minor = 0
        patch = 0
    return f"v{major}.{minor}.{patch}"


# --------------------------------------------------------------------------
# staging + atomic commit — a version directory is never partially written
# --------------------------------------------------------------------------


def stage_and_commit(
    visual_dir: Path, version: str, builder: Callable[[Path], None]
) -> Path:
    """Build a version directory out of sight and commit it atomically.

    `builder(staging_dir)` must populate the staging directory completely —
    frames, previews, receipt. Only when it returns does the staging directory
    get renamed into place, so a mid-run failure can never leave a partial
    version directory (criterion 1: no partial write, ever). The target is
    re-checked at commit time; a target that exists is refused, never
    overwritten.
    """
    target = visual_dir / version
    if target.exists():
        raise StoreError(
            f"refusing to render into existing version directory {target} "
            "(version directories are immutable — render or bump to the next derived version)"
        )
    staging = visual_dir / f".staging-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)
    try:
        builder(staging)
        if target.exists():  # re-check: someone may have committed while we built
            raise StoreError(f"refusing to overwrite {target}: version appeared during render")
        os.rename(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def repoint_latest(visual_dir: Path, version: str) -> None:
    """Point `latest` at `version`, atomically, only after every frame succeeded.

    The swap is a symlink create-then-rename, so `latest` is never absent and
    never dangles mid-swap (consumers import `latest/` only). A failed render
    never calls this — the previous `latest` stays intact (criterion 6).
    """
    link = visual_dir / "latest"
    tmp = visual_dir / f".latest-{uuid.uuid4().hex[:8]}"
    os.symlink(version, tmp)
    try:
        os.rename(tmp, link)  # atomic replace over the existing pointer, if any
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def publish_version(visual_dir: Path, version: str) -> None:
    """Promote a reviewed immutable version after checking its recorded frames."""
    if not VERSION_RE.fullmatch(version):
        raise StoreError(f"malformed version {version!r} (expected vX.Y.Z)")
    target = visual_dir / version
    if not target.is_dir() or target.is_symlink():
        raise StoreError(f"version {version!r} is absent or is a symlink")
    receipt_path = target / "receipt.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        frames = receipt["frames"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise StoreError(f"cannot read receipt {receipt_path}: {exc}") from exc
    if not isinstance(frames, list) or not frames:
        raise StoreError(f"receipt {receipt_path} has no frames")
    for frame in frames:
        if not isinstance(frame, dict):
            raise StoreError(f"receipt {receipt_path} has a malformed frame")
        name, expected = frame.get("name"), frame.get("sha256")
        if (not isinstance(name, str) or Path(name).name != name
                or not name.endswith(".png") or not isinstance(expected, str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected)):
            raise StoreError(f"receipt {receipt_path} has a malformed frame record")
        image = target / name
        if not image.is_file() or sha256_file(image) != expected:
            raise StoreError(f"frame {image} is missing or differs from its receipt")
    repoint_latest(visual_dir, version)


# --------------------------------------------------------------------------
# receipts — provenance with per-frame content hashes
# --------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_state(root: Path) -> dict[str, str]:
    """Commit + worktree state of the project root, honestly recorded.

    An exported tree with no `.git` reports `uncommitted` rather than failing
    (port of render.sh). Note the corpus caveat (audit F10): a repository with
    zero commits makes this field anchor nothing — the state is recorded, not
    invented.
    """
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip() or "uncommitted"
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {"commit": "uncommitted", "worktree": "unknown"}
    return {"commit": commit, "worktree": "dirty" if dirty else "clean"}


@dataclass(frozen=True)
class FrameReceipt:
    name: str  # output basename, normalised, with .png
    bytes_: int
    sha256: str
    readiness: str  # "signal" | "fallback-budget"


def build_receipt(
    *,
    rendered_at: str,
    source: str,
    manifest: str,
    root_rel: str | None,
    canvas_profile: dict | None,
    viewport: str,
    renderer: dict,
    repository: dict,
    theme: dict | None,
    frames: list[FrameReceipt],
    warnings: list[str],
) -> dict:
    """Assemble the receipt (criterion 3). Content hashes are the new thing.

    Resolved theme records name, resolution steps, and a digest of the token
    table — never the tokens themselves. A value written in two places is a
    defect (audit F7), and the receipt must not become a second copy of the
    theme. When config/theme resolution is unavailable, fields are null with a
    `resolution: unavailable` note — honest degradation, not a stub.
    """
    receipt: dict = {
        "schema_version": 1,
        "rendered_at": rendered_at,
        "source": source,
        "manifest": manifest,
        "root": root_rel,
        "canvas_profile": canvas_profile,
        "viewport": viewport,
        "renderer": renderer,
        "repository": repository,
        "theme": theme,
        "frames": [
            {
                "name": f.name,
                "bytes": f.bytes_,
                "sha256": f.sha256,
                "readiness": f.readiness,
            }
            for f in frames
        ],
    }
    if warnings:
        receipt["warnings"] = list(warnings)
    return receipt


def write_receipt(version_dir: Path, receipt: dict) -> Path:
    path = version_dir / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# previews — automatic, every render, never opt-in (audit F5 mechanised)
# --------------------------------------------------------------------------


def _pillow():
    try:
        from PIL import Image, ImageDraw  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - uv entrypoint declares Pillow
        raise StoreError(
            "previews need Pillow; the render command's uv entrypoint declares it — "
            "run the command through `visuals render`, not a bare import"
        ) from exc
    return Image, ImageDraw


def emit_previews(
    version_dir: Path, frame_names: list[str], preview_width: int,
    colors: dict[str, str] | None = None,
) -> list[Path]:
    """Write a preview-width PNG per frame, plus a contact sheet for multi-frame visuals.

    Previews are diagnostic artifacts for the 640px legibility check the corpus
    READMEs call decisive; they live under `previews/` so consumers importing
    frame files see only the delivered frames. Deterministic: same frames in,
    same preview bytes out.
    """
    Image, ImageDraw = _pillow()
    preview_dir = version_dir / "previews"
    preview_dir.mkdir(exist_ok=True)
    written: list[Path] = []
    thumbs: list[tuple[str, object]] = []
    for name in frame_names:
        src = version_dir / f"{name}.png"
        im = Image.open(src).convert("RGB")
        w, h = im.size
        ph = max(1, round(h * preview_width / w))
        thumb = im.resize((preview_width, ph), Image.Resampling.LANCZOS)
        out = preview_dir / f"{name}-{preview_width}.png"
        thumb.save(out, format="PNG")
        written.append(out)
        thumbs.append((name, thumb))
    if len(frame_names) > 1:
        written.append(_contact_sheet(Image, ImageDraw, version_dir, thumbs, colors))
    return written


# Contact-sheet colours are mechanical defaults — PIL named colours, never hex
# literals: hex belongs to the theme token vocabulary (theme task), not to the
# store. When the render pipeline resolves a theme it passes its background and
# text roles in via `colors`.
_SHEET_DEFAULT_COLORS = {"background": "white", "label": "black"}


def _contact_sheet(
    Image, ImageDraw, version_dir: Path, thumbs, colors: dict[str, str] | None,
) -> Path:
    """A mechanical contact sheet: flat ground, fixed grid, filename labels.

    Grid geometry is bookkeeping, not composition — no spacing opinion beyond
    a uniform gutter, and the sheet is a diagnostic, not a deliverable.
    """
    sheet_colors = colors or _SHEET_DEFAULT_COLORS
    cols = min(4, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    cell_w = max(t.size[0] for _, t in thumbs)
    cell_h = max(t.size[1] for _, t in thumbs)
    label_h, gutter = 28, 12
    sheet = Image.new(
        "RGB",
        (cols * cell_w + (cols + 1) * gutter, rows * (cell_h + label_h) + (rows + 1) * gutter),
        sheet_colors["background"],
    )
    draw = ImageDraw.Draw(sheet)
    for i, (name, thumb) in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = gutter + c * (cell_w + gutter)
        y = gutter + r * (cell_h + label_h + gutter)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + cell_h + 6), name, fill=sheet_colors["label"])
    out = version_dir / "contact-sheet.png"
    sheet.save(out, format="PNG")
    return out


# --------------------------------------------------------------------------
# commit + worktree helpers shared by the render pipeline
# --------------------------------------------------------------------------


def chrome_version_of(chrome: str) -> str:
    try:
        proc = subprocess.run(
            [chrome, "--version"], capture_output=True, text=True, timeout=30
        )
        return proc.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
