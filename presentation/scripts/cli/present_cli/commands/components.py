"""`present components gallery|diff` (task 0016): every component rendered for review, and a
per-component change report between two galleries. Change is reported, never quality."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .. import formats
from ..console import Effects, Result, leaf
from ..repo import MARKER, find_repo


def resolve_tokens(
    res: Result, explicit: Path | None
) -> tuple[Path | None, Path | None, str]:
    """(token file or None for neutral, repository root, label)."""
    repo = find_repo()
    if explicit is not None:
        if not explicit.is_file():
            res.error("file_not_found", f"{explicit} does not exist", repairable=True)
            return None, repo, ""
        return explicit.resolve(), repo, str(explicit)
    if repo is not None:
        manifest = formats.load(repo / MARKER)
        rel = (manifest.get("brand") or {}).get("tokens")
        if rel and (repo / rel).is_file():
            return (repo / rel).resolve(), repo, rel
        if rel:
            res.warn(
                "tokens_missing",
                f"presentations.toml names {rel}, which does not exist; using the neutral tokens.",
                next=f"create {rel} (token schema: present schema list)",
            )
    return None, repo, "neutral"


def _configure_gallery(p):
    p.add_argument(
        "--tokens",
        type=Path,
        help="token file (default: the repository's brand.tokens, else neutral)",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="output folder (default: ~/.cache/present/gallery/<version>-<tokens>)",
    )
    p.add_argument(
        "--no-render",
        action="store_true",
        help="build and fingerprint the pptx only (no LibreOffice)",
    )


@leaf(
    "components",
    "gallery",
    summary="render every component into a contact sheet",
    task="0016",
    configure=_configure_gallery,
    effects=Effects(
        writes=True,
        description="Writes gallery.pptx, PDF, page PNGs, contact sheet and manifest.json "
        "to --out (default a per-user cache, never the repository); runs LibreOffice locally.",
    ),
)
def gallery(ns, res: Result) -> Result:
    from ..deck import render, run

    tokens, repo, label = resolve_tokens(res, ns.tokens)
    if res.errors:
        return res
    tag = hashlib.sha256(tokens.read_bytes()).hexdigest()[:12] if tokens else "neutral"
    out = (
        ns.out
        or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "present"
        / "gallery"
        / tag
    ).resolve()
    if repo is not None and (out == repo.resolve() or repo.resolve() in out.parents):
        return res.error(
            "out_inside_repo",
            f"{out} is inside the repository; galleries are review output.",
            repairable=True,
            next="--out <a folder outside the repository>",
        )
    if (out / "manifest.json").exists():
        return res.error(
            "out_exists",
            f"{out} already holds a gallery; galleries are not overwritten.",
            repairable=True,
            next="--out <new folder>, or remove the old one",
        )
    missing = {} if ns.no_render else render.missing_tools()
    if missing:
        for tool, hint in missing.items():
            res.warn(
                "capability_unavailable",
                f"{tool} not found; the gallery is built and fingerprinted but not rendered.",
                next=hint,
            )
    try:
        data = run.worker(
            ["gallery", str(out)]
            + (["--no-render"] if ns.no_render or missing else []),
            tokens=tokens,
            repo=repo,
        )
    except run.WorkerError as exc:
        return res.error(
            "gallery_failed", str(exc), repairable=False, next=exc.detail[-300:] or None
        )
    comps = sorted({s["component"] for s in data["slides"]})
    res.data = {
        **data,
        "out": str(out),
        "tokens_label": label,
        "component_count": len(comps),
    }
    res.text.append(
        f"gallery: {len(comps)} components, {len(data['slides'])} slides, components {data['components']}, "
        f"tokens {label} ({data['tokens']['sha256'][:12]})"
    )
    res.text.append(
        f"  {data.get('contact_sheet') or (str(out) + '/gallery.pptx (not rendered)')}"
    )
    return res


def _configure_diff(p):
    p.add_argument("old", type=Path, help="an earlier gallery folder")
    p.add_argument("new", type=Path, help="a later gallery folder")
    p.add_argument(
        "--out", type=Path, help="write old/new/diff crops of each changed slide here"
    )


@leaf(
    "components",
    "diff",
    summary="diff two component galleries",
    task="0016",
    configure=_configure_diff,
    effects=Effects(
        writes=True,
        description="Reads two gallery folders; writes crops only when --out is given.",
    ),
)
def diff(ns, res: Result) -> Result:
    from ..deck import diffing

    try:
        report = diffing.compare(ns.old, ns.new, ns.out)
    except FileNotFoundError as exc:
        return res.error(
            "gallery_not_found",
            str(exc),
            repairable=True,
            next="present components gallery --out <dir>",
        )
    res.data = report
    c = report["counts"]
    res.text.append(
        f"{c['same']} same · {c['changed']} changed · {c['added']} added · {c['removed']} removed"
    )
    for r in report["slides"]:
        if r["status"] != "same":
            res.text.append(
                f"  {r['status']:<8} {r['id']} step {r['step']} ({r['component']})"
                + (
                    f": {r['pixels']} px in {r.get('bbox')}"
                    if r.get("pixels") is not None
                    else ""
                )
            )
    if report["changed_components"]:
        res.text.append(
            "changed components: " + ", ".join(report["changed_components"])
        )
    return res
