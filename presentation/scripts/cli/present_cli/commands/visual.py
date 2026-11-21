"""`present visual new|render|publish|show` (task 0009): thin delegations to the visuals CLI.

The talk's `visuals/` folder is the visuals project (visuals task 0026 layout). `present`
adopts it on first use (`visuals init`) and writes the brand theme from the token file
(ADR 0008), then hands every operation to `visuals` unchanged. visuals' own output is
returned in `data.visuals`.
"""

from __future__ import annotations

from pathlib import Path

from .. import visuals_link as vl
from ..console import Effects, Result, leaf
from ..context import Repo, require_repo, require_talk


def _common(p):
    p.add_argument("slug", help="the visual's slug in this talk's visuals/ project")
    p.add_argument(
        "--talk", help="talk folder; default the talk containing the working directory"
    )


def _ctx(res: Result, ns) -> tuple[Repo, Path] | None:
    repo = require_repo(res)
    if repo is None:
        return None
    talk = require_talk(res, repo, ns.talk)
    if talk is None:
        return None
    if vl.cli() is None:
        res.error(
            "capability_unavailable",
            "the visuals CLI is not installed; visuals cannot be "
            "created, rendered or published.",
            repairable=True,
            next=vl.NEIGHBOURS["visuals"][2],
        )
        return None
    return repo, talk


def _tokens(repo: Repo) -> Path | None:
    rel = repo.manifest.get("brand", {}).get("tokens")
    p = repo.root / rel if rel else None
    return p if p is not None and p.is_file() else None


def _delegate(res: Result, project: Path, *args: str) -> Result:
    try:
        proc = vl.run(project, *args)
    except vl.VisualsError as exc:
        return res.error(exc.code, exc.message, repairable=True, next=exc.next)
    res.data["visuals"] = {
        "args": list(args),
        "exit": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
    }
    res.text += [ln for ln in proc.stdout.splitlines() if ln.strip()][-12:]
    if proc.returncode != 0:
        return res.error(
            "visuals_failed",
            f"visuals {args[0]} exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[:300]}",
            repairable=True,
            next=f"run `visuals {args[0]} --help` in {project}",
        )
    return res


def _configure_new(p):
    _common(p)
    p.add_argument(
        "--kind",
        default="diagram",
        choices=["presentation", "poster", "figure", "diagram"],
        help="visuals kind (selects the canvas profile); default diagram",
    )


@leaf(
    "visual",
    "new",
    summary="create a visual (delegates to visuals)",
    task="0009",
    configure=_configure_new,
    effects=Effects(
        writes=True,
        description="Adopts <talk>/visuals/ with `visuals init` on first use, writes "
        "the brand theme generated from the token file, then runs `visuals new`.",
    ),
)
def visual_new(ns, res: Result) -> Result:
    got = _ctx(res, ns)
    if got is None:
        return res
    repo, talk = got
    project = talk / "visuals"
    project.mkdir(exist_ok=True)
    res.data = {"project": repo.rel(project)}
    if not (project / "visuals.toml").is_file():
        try:
            vl.run(project, "init", check=True)
        except vl.VisualsError as exc:
            return res.error(exc.code, exc.message, repairable=True, next=exc.next)
        (project / ".gitkeep").unlink(missing_ok=True)
        res.data["adopted"] = True
    tok = _tokens(repo)
    if tok is not None:
        path, name, sha = vl.write_theme(project, tok)
        res.data["theme"] = {"name": name, "path": repo.rel(path), "tokens_sha256": sha}
    else:
        res.warn(
            "tokens_missing",
            "no brand token file; the visual uses visuals' neutral theme.",
            next="set [brand] tokens in presentations.toml",
        )
    return _delegate(res, project, "new", ns.kind, ns.slug)


def _configure_render(p):
    _common(p)
    p.add_argument("--into", help="render into this new version (vX.Y.Z)")
    p.add_argument(
        "--unpublished", action="store_true", help="keep latest unchanged for review"
    )


@leaf(
    "visual",
    "render",
    summary="render a visual version (delegates to visuals)",
    task="0009",
    configure=_configure_render,
    effects=Effects(
        writes=True,
        description="Runs `visuals render` (headless Chrome, locally): a new immutable "
        "version; refreshes the generated brand theme first.",
    ),
)
def visual_render(ns, res: Result) -> Result:
    got = _ctx(res, ns)
    if got is None:
        return res
    repo, talk = got
    project = talk / "visuals"
    res.data = {"project": repo.rel(project)}
    tok = _tokens(repo)
    if tok is not None and (project / "visuals.toml").is_file():
        path, name, sha = vl.write_theme(project, tok)
        res.data["theme"] = {"name": name, "tokens_sha256": sha}
    args = (
        ["render", ns.slug]
        + (["--into", ns.into] if ns.into else [])
        + (["--unpublished"] if ns.unpublished else [])
    )
    return _delegate(res, project, *args)


def _configure_publish(p):
    _common(p)
    p.add_argument("version", help="vX.Y.Z to publish (becomes latest)")


@leaf(
    "visual",
    "publish",
    summary="publish a visual version (delegates to visuals)",
    task="0009",
    configure=_configure_publish,
    effects=Effects(
        writes=True,
        description="Runs `visuals publish`: verifies hashes, repoints latest.",
    ),
)
def visual_publish(ns, res: Result) -> Result:
    got = _ctx(res, ns)
    if got is None:
        return res
    repo, talk = got
    v = ns.version if ns.version.startswith("v") else f"v{ns.version}"
    res.data = {"project": repo.rel(talk / "visuals")}
    return _delegate(res, talk / "visuals", "publish", ns.slug, v)


@leaf(
    "visual",
    "show",
    summary="show a visual's published version",
    task="0009",
    configure=_common,
    effects=Effects(description="Reads `visuals index --json` for the talk's project."),
)
def visual_show(ns, res: Result) -> Result:
    got = _ctx(res, ns)
    if got is None:
        return res
    repo, talk = got
    try:
        pin = vl.resolve(repo.root, talk, ns.slug, "latest")
    except vl.VisualsError as exc:
        return res.error(exc.code, exc.message, repairable=True, next=exc.next)
    res.data = {
        "slug": ns.slug,
        "published": pin.resolved,
        "folder": repo.rel(pin.folder),
        "receipt": repo.rel(pin.receipt),
        "frames": sorted(p.name for p in pin.folder.glob("*.png")),
    }
    res.text.append(
        f"{ns.slug}: published v{pin.resolved} ({len(res.data['frames'])} frame(s)) — pin it in "
        f"deck.yaml `visuals: {{{ns.slug}: latest}}`, use it as `@visual:{ns.slug}`"
    )
    return res
