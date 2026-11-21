"""`present validate [--talk T] [--all]` (task 0010; specification §3–§9, §11).

Standard-1 talks get the full contract; `[legacy]` talks get loose structural checks (symlink
loops, dangling links). Findings carry stable codes and a severity; only `blocking` findings
(contract violations) fail the command. No aesthetic or density judgments.
"""

from __future__ import annotations

import errno
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .. import STANDARDS, annotate, claims, formats, library, schemas, store
from ..console import Effects, Result, leaf
from ..context import TALK_FILE, Repo, load_talk, require_repo, talk_of
from . import script as script_cmd

REQUIRED = (
    "README.md",
    "AGENTS.md",
    "audience/talk.yaml",
    "audience/promised.md",
    "modules",
    "research/claims.md",
    "docs/engineering.yaml",
    "docs/README.md",
    "delivery",
)
ROOT_FILES = {"README.md", "AGENTS.md", "CLAUDE.md"}
ABSOLUTE = re.compile(
    r"(?<![\w.:/~-])(?:/home/[^\s\"'`)]+|/Users/[^\s\"'`)]+|/mnt/[^\s\"'`)]+|/tmp/[^\s\"'`)]+|"
    r"[A-Za-z]:\\\\[^\s\"'`)]+)"
)
MACHINE_FILES = (".yaml", ".yml", ".json", ".toml")


class Findings:
    def __init__(self, talk: str):
        self.talk = talk
        self.items: list[dict[str, Any]] = []

    def add(self, code: str, severity: str, where: str, message: str, **extra) -> None:
        self.items.append(
            {
                "talk": self.talk,
                "code": code,
                "severity": severity,
                "where": where,
                "message": message,
                **extra,
            }
        )


# --------------------------------------------------------------------------- shared checks


def symlink_findings(f: Findings, repo: Repo, root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if not p.is_symlink():
                continue
            target = os.readlink(p)
            try:
                resolved = p.resolve(strict=True)
            except (RuntimeError, OSError) as exc:
                if not isinstance(exc, RuntimeError) and exc.errno != errno.ELOOP:
                    f.add("symlink_dangling", "warning", repo.rel_any(p), f"dangling symlink: {name} -> {target}")
                    continue
                f.add(
                    "symlink_loop",
                    "warning",
                    repo.rel_any(p),
                    f"symlink loop: {name} -> {target}",
                )
                continue
            if resolved == p.parent.resolve() or resolved in p.parent.resolve().parents:
                f.add(
                    "symlink_loop",
                    "warning",
                    repo.rel_any(p),
                    f"symlink points at its own ancestor: {name} -> {target}",
                )
            elif os.path.isabs(target):
                f.add(
                    "symlink_absolute",
                    "warning",
                    repo.rel_any(p),
                    f"absolute symlink target: {target}",
                )


def absolute_path_findings(f: Findings, repo: Repo, talk: Path, severity: str,
                           only: set[str] | None = None) -> None:
    for p in sorted(talk.rglob("*")):
        if only is not None and repo.rel_any(p) not in only:
            continue
        if p.is_symlink() or not p.is_file() or p.suffix.lower() not in MACHINE_FILES:
            continue
        if any(part.startswith(".") for part in p.relative_to(talk).parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            m = ABSOLUTE.search(line)
            if m:
                f.add(
                    "absolute_path",
                    severity,
                    f"{repo.rel_any(p)}:{n}",
                    f"absolute path {m.group(0)!r}; "
                    "files in the repository use repository-relative paths",
                )
                break


def _schema(f: Findings, repo: Repo, path: Path, name: str) -> Any:
    try:
        data = formats.load(path)
    except Exception as exc:
        f.add("file_unparseable", "blocking", repo.rel_any(path), str(exc)[:200])
        return None
    if name == "annotations" and data is None:
        data = []
    errs = schemas.errors(name, data)
    if errs:
        f.add(
            "schema_invalid",
            "blocking",
            repo.rel_any(path),
            f"{name}: {errs[0]}",
            errors=errs,
        )
        return None
    return data


# --------------------------------------------------------------------------- standard-1


def artifact_findings(
    f: Findings, repo: Repo, art: Path, kind: str, schema: str | None = None
) -> None:
    rel = repo.rel_any(art)
    manifest = art / f"{kind}.yaml"
    if not manifest.is_file():
        return
    _schema(f, repo, manifest, schema or kind)
    if not (art / "src").is_dir():
        f.add("src_missing", "blocking", rel, f"{kind} artifact has no src/")
    summ = store.summary(art)
    for p in summ["problems"]:
        sev = (
            "blocking"
            if p["code"]
            in (
                "latest_not_symlink",
                "latest_invalid",
                "latest_dangling",
                "latest_incomplete",
            )
            else "warning"
        )
        f.add(p["code"], sev, rel, p["message"])
    if summ["versions"] and summ["latest"] is None and not summ["problems"]:
        f.add(
            "latest_missing",
            "blocking",
            rel,
            "versions exist but there is no latest symlink",
        )
    for v in summ["versions"]:
        rp = art / f"v{v}" / store.RECEIPT
        rec = _schema(f, repo, rp, "receipt")
        if rec is None:
            continue
        if rec.get("version") != v or rec.get("artifact") != repo.rel_any(art):
            f.add(
                "receipt_mismatch",
                "blocking",
                repo.rel_any(rp),
                "receipt version/artifact does not match its folder",
            )
        for bad in store.verify(repo.root, art, v):
            since = bad["code"] == "pin_since_changed"
            f.add(
                f"receipt_{bad['code']}",
                "info" if since else "blocking",
                bad["path"],
                f"v{v}: built with an earlier {bad['path']} (a rebuild would use the current one)"
                if since
                else f"v{v}: {bad['code'].replace('_', ' ')}",
            )
    if (art / "approvals.yaml").is_file():
        data = _schema(f, repo, art / "approvals.yaml", "approvals")
        for a in (data or {}).get("approvals", []):
            vd = art / f"v{a['version']}"
            if not vd.is_dir():
                f.add(
                    "approval_unknown_version",
                    "blocking",
                    repo.rel_any(art / "approvals.yaml"),
                    f"approval of v{a['version']}, which does not exist",
                )
            elif (
                store.is_complete(vd)
                and store.receipt_digest(art, a["version"]) != a["checks"]["digest"]
            ):
                f.add(
                    "approval_stale",
                    "blocking",
                    repo.rel_any(art / "approvals.yaml"),
                    f"approval of v{a['version']} records a different receipt digest",
                )
    if kind == "script":
        ann = art / "src" / "annotations.yaml"
        if ann.is_file():
            _schema(f, repo, ann, "annotations")
        try:
            sc = annotate.parse_script(script_cmd.script_text(art))
            for fd in sc.findings:
                if fd["code"] in script_cmd.BLOCKING_FORMAT:
                    f.add(
                        fd["code"], "blocking", f"{rel}/src:{fd['line']}", fd["message"]
                    )
        except store.StoreError as exc:
            f.add(exc.code, "blocking", rel, exc.message)


def handoff_findings(f: Findings, repo: Repo, talk: Path) -> None:
    hdir = talk / "docs" / "handoffs"
    current = []
    for p in sorted(hdir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        head = p.read_text(encoding="utf-8").split("\n---\n", 1)[0]
        if re.search(r"^status: current\s*$", head, re.M):
            current.append(p.name)
    if len(current) != 1:
        f.add(
            "handoff_current_count",
            "blocking" if len(current) > 1 else "warning",
            repo.rel_any(hdir),
            f"{len(current)} current handoff(s); exactly one is current"
            + (f": {', '.join(current)}" if current else ""),
        )


def standard_talk(repo: Repo, talk: Path) -> Findings:
    f = Findings(talk.name)
    for rel in REQUIRED:
        if not (talk / rel).exists():
            f.add(
                "layout_missing",
                "blocking",
                f"{talk.name}/{rel}",
                f"required by the talk layout (spec §3)",
            )
    for p in sorted(talk.iterdir()):
        if p.is_file() and p.name not in ROOT_FILES:
            f.add(
                "layout_root_file",
                "blocking",
                repo.rel_any(p),
                "the talk root holds only README.md, "
                "AGENTS.md (+ CLAUDE.md) and folders; generated files live in version folders",
            )
    claude = talk / "CLAUDE.md"
    if claude.exists() and not (
        claude.is_symlink() and os.readlink(claude) == "AGENTS.md"
    ):
        f.add(
            "claude_md_not_symlink",
            "warning",
            repo.rel_any(claude),
            "CLAUDE.md should be a relative symlink to AGENTS.md",
        )
    res = Result(command="probe")
    data = load_talk(res, talk)
    if data is None:
        f.add(
            "talk_invalid",
            "blocking",
            f"{talk.name}/{TALK_FILE.as_posix()}",
            res.errors[0]["message"],
        )
        return f
    if data["id"] != talk.name:
        f.add(
            "talk_id_mismatch",
            "blocking",
            f"{talk.name}/{TALK_FILE.as_posix()}",
            f"id {data['id']!r} differs from the folder name",
        )
    pinned = data.get("standard", repo.standard)
    if pinned not in STANDARDS:
        f.add(
            "standard_unsupported",
            "blocking",
            talk.name,
            f"pins standard {pinned}, which this release cannot validate ({STANDARDS})",
        )
    declared = {m["id"]: m for m in data["modules"]}
    mods = talk / "modules"
    present_dirs = (
        sorted(p.name for p in mods.iterdir() if p.is_dir()) if mods.is_dir() else []
    )
    for name in present_dirs:
        if name not in declared:
            f.add(
                "module_undeclared",
                "blocking",
                f"{talk.name}/modules/{name}",
                "module folder not declared "
                "in talk.yaml (no sibling variant folders; a variant is a version or a new module)",
            )
    for mid, m in declared.items():
        mdir = mods / mid
        if not mdir.is_dir():
            f.add(
                "module_missing",
                "warning",
                f"{talk.name}/modules/{mid}",
                "declared module has no folder",
            )
            continue
        for child in sorted(mdir.iterdir()):
            if child.name not in ("script", "deck") and not child.name.startswith("."):
                f.add(
                    "module_extra",
                    "blocking",
                    repo.rel_any(child),
                    "a module holds only script/ and deck/",
                )
        for kind in ("script", "deck"):
            art = mdir / kind
            if m[kind]:
                artifact_findings(f, repo, art, kind)
            elif (art / f"{kind}.yaml").exists():
                f.add(
                    "artifact_undeclared",
                    "blocking",
                    repo.rel_any(art),
                    f"talk.yaml declares {kind}: false",
                )
    for p in (
        sorted((talk / "delivery").glob("*.y*ml"))
        if (talk / "delivery").is_dir()
        else []
    ):
        _schema(f, repo, p, "delivery")
    led_path = claims.find_ledger(talk)
    if led_path is not None:
        led = claims.load_ledger(
            led_path, repo.claims["id_pattern"], repo.claims["statuses"]
        )
        for pr in led.problems:
            f.add(
                f"ledger_{pr['code']}",
                "warning",
                f"{repo.rel_any(led_path)}:{pr['line']}",
                pr["message"],
            )
        inputs = []
        for mid, m in declared.items():
            art = mods / mid / "script"
            if m["script"] and (art / "script.yaml").is_file():
                try:
                    inputs.append(
                        claims.ScriptInput(
                            repo.rel_any(art),
                            annotate.parse_script(script_cmd.script_text(art)),
                            script_cmd.load_annotations(
                                art / "src" / "annotations.yaml"
                            ),
                        )
                    )
                except store.StoreError:
                    pass
        report = claims.check(inputs, led, id_pattern=repo.claims["id_pattern"])
        blocked = claims.blocking(report["summary"], repo.claims["blocking_tiers"])
        f.add(
            "claims_gate",
            "blocking" if blocked else "info",
            talk.name,
            "concerns "
            + ", ".join(f"{k} {v}" for k, v in report["summary"].items())
            + (f"; blocking tiers {blocked}" if blocked else ""),
            summary=report["summary"],
        )
    for item in library.talk_findings(repo, talk):
        f.add(item["code"], item["severity"], item["where"], item["message"])
    handoff_findings(f, repo, talk)
    absolute_path_findings(f, repo, talk, "blocking")
    symlink_findings(f, repo, talk)
    for item in f.items:  # a loop inside a standard-1 talk breaks the contract
        if item["code"] == "symlink_loop":
            item["severity"] = "blocking"
    return f


def changed_since_listed(repo: Repo, talk: Path) -> set[str] | None:
    """Files under `talk` changed since the newest commit that listed it under [legacy], plus
    uncommitted ones. None when git cannot say."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo.root), *args], capture_output=True, text=True, timeout=60)

    needle = f'"{talk.name}"'
    log = git("log", "--format=%H", "-S", needle, "--", "presentations.toml")
    if log.returncode != 0:
        return None
    listed = None
    for commit in log.stdout.split():  # newest first: the latest commit that (re)added the name
        shown = git("show", f"{commit}:presentations.toml")
        if shown.returncode == 0 and needle in shown.stdout:
            listed = commit
            break
    rel = repo.rel_any(talk)
    out: set[str] = set()
    if listed is not None:
        diff = git("diff", "--name-only", listed, "--", rel)
        if diff.returncode != 0:
            return None
        out |= {ln for ln in diff.stdout.splitlines() if ln}
    status = git("status", "--porcelain", "--untracked-files=all", "--", rel)
    out |= {ln[3:] for ln in status.stdout.splitlines() if len(ln) > 3}
    return out


def legacy_talk(repo: Repo, talk: Path) -> Findings:
    """Loose checks (spec §11): symlink loops anywhere; absolute paths only in files changed since
    the talk was listed, so dated historical records are never reported."""
    f = Findings(talk.name)
    symlink_findings(f, repo, talk)
    changed = changed_since_listed(repo, talk)
    if changed is None:
        f.add("legacy_history_unavailable", "info", talk.name, "git history unavailable; absolute-path "
              "check skipped for this legacy talk")
    elif changed:
        absolute_path_findings(f, repo, talk, "warning", only=changed)
    return f


def library_findings(repo: Repo) -> Findings:
    """The library itself (ADR 0011): each slide item's store contract, every manifest, and items
    that no talk pins (a warning; a retired item is expected to be unused)."""
    lib = library.root(repo)
    f = Findings(lib.name)
    used = library.usage(repo)
    for it in library.items(repo):
        d, where = it["dir"], repo.rel_any(it["dir"])
        try:
            m = library.manifest(d, it["kind"])
        except store.StoreError as exc:
            f.add(exc.code, "blocking", where, exc.message)
            continue
        if it["kind"] == "slides":
            artifact_findings(f, repo, d, "library-slide", schema="library-item")
        if it["name"] not in used and not m.get("retired"):
            f.add("library_unused", "warning", where, f"{it['name']}: no talk pins this item")
    if lib.is_dir():
        symlink_findings(f, repo, lib)
    return f


# --------------------------------------------------------------------------- command


def _configure(p):
    p.add_argument("--talk", action="append", help="validate this talk (repeatable)")
    p.add_argument(
        "--all",
        action="store_true",
        help="every talk, standard-1 and legacy (default outside a talk)",
    )
    p.add_argument(
        "--severity",
        choices=["blocking", "warning", "info"],
        help="show only this severity",
    )


@leaf(
    "validate",
    summary="validate talks against their pinned standard",
    task="0010",
    configure=_configure,
    effects=Effects(
        description="Reads talks, manifests, receipts and ledgers; recomputes hashes."
    ),
)
def validate(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    targets: list[tuple[str, Path]] = []
    repo_wide = False
    if ns.talk:
        for name in ns.talk:
            p = repo.root / name
            if not p.is_dir():
                return res.error(
                    "talk_not_found",
                    f"no talk folder {name!r}",
                    repairable=True,
                    next="present talk list",
                )
            targets.append((name, p))
    elif not ns.all and (inside := talk_of(repo, Path.cwd())) is not None:
        targets.append((inside.name, inside))
    else:
        repo_wide = True
        targets = [
            (p.name, p)
            for p in sorted(repo.root.iterdir())
            if p.is_dir()
            and not p.name.startswith((".", "_"))
            and p.name
            not in (
                "docs",
                str(repo.manifest.get("library", {}).get("root", "library")),
            )
        ]
    talks_out = []
    all_items: list[dict[str, Any]] = []
    for name, path in targets:
        if name in repo.legacy:
            kind = "legacy"
            f = legacy_talk(repo, path)
        elif (path / TALK_FILE).is_file():
            kind = "standard"
            f = standard_talk(repo, path)
        else:
            kind = "unclassified"
            f = Findings(name)
            f.add(
                "talk_unclassified",
                "warning",
                name,
                "neither a standard-1 talk nor listed under [legacy]",
            )
        items = [i for i in f.items if not ns.severity or i["severity"] == ns.severity]
        all_items += items
        counts = {
            s: sum(1 for i in f.items if i["severity"] == s)
            for s in ("blocking", "warning", "info")
        }
        talks_out.append({"talk": name, "kind": kind, "counts": counts})
    if repo_wide and library.root(repo).is_dir():
        f = library_findings(repo)
        items = [i for i in f.items if not ns.severity or i["severity"] == ns.severity]
        all_items += items
        talks_out.append({"talk": f.talk, "kind": "library", "counts": {
            s: sum(1 for i in f.items if i["severity"] == s) for s in ("blocking", "warning", "info")}})
    if ns.all or not ns.talk:
        for n in repo.legacy:
            if not (repo.root / n).is_dir():
                all_items.append(
                    {
                        "talk": n,
                        "code": "legacy_missing",
                        "severity": "warning",
                        "where": "presentations.toml",
                        "message": f"[legacy] lists {n}, which is not a directory",
                    }
                )
    blocking = [i for i in all_items if i["severity"] == "blocking"]
    res.data = {
        "talks": talks_out,
        "findings": all_items,
        "counts": {
            s: sum(1 for i in all_items if i["severity"] == s)
            for s in ("blocking", "warning", "info")
        },
    }
    for t in talks_out:
        c = t["counts"]
        res.text.append(
            f"{t['talk']:<32} {t['kind']:<12} blocking {c['blocking']} · warning {c['warning']} · info {c['info']}"
        )
    for i in all_items:
        res.text.append(f"  [{i['severity']}] {i['code']} {i['where']}: {i['message']}")
    if blocking:
        return res.error(
            "validation_failed",
            f"{len(blocking)} blocking finding(s)",
            repairable=True,
            next="present -j validate for the full list",
        )
    return res
