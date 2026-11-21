"""`present script new|bump|approve|show|check|annotate` (tasks 0007, 0018; ADR 0010; spec §5, §7).

A script is only what is said: `src/script.md` holds `## <slide-id>` headings and spoken text;
claims, notes and cues stand off in `src/annotations.yaml`.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .. import annotate, claims, formats, schemas, store
from ..console import Effects, Result, leaf
from ..context import Repo, require_artifact, require_repo, talk_of_artifact
from .doctor import NEIGHBOURS, find_neighbour

# Format findings that break the "spoken words only" contract block a bump; the rest are advisory.
BLOCKING_FORMAT = {
    "format_marker",
    "format_markup",
    "format_code_block",
    "format_heading_level",
    "format_slide_id",
    "format_duplicate_slide",
    "format_text_before_first_slide",
    "format_no_slides",
}

SCRIPT_MD = """## opening

"""


# --------------------------------------------------------------------------- loading


def manifest(art: Path) -> dict[str, Any]:
    data = formats.load(art / "script.yaml") or {}
    errs = schemas.errors("script", data)
    if errs:
        raise store.StoreError("manifest_invalid", f"script.yaml: {errs[0]}")
    return data


def script_text(art: Path, base: Path | None = None) -> str:
    """The whole script: src/script.md, or the manifest's ordered `sections`."""
    base = base or art / "src"
    sections = manifest(art).get("sections") if base == art / "src" else None
    if sections:
        return (
            "\n\n".join(
                (base / s).read_text(encoding="utf-8").strip("\n") for s in sections
            )
            + "\n"
        )
    path = base / "script.md"
    if not path.is_file():
        raise store.StoreError("script_missing", f"{path} does not exist.")
    return path.read_text(encoding="utf-8")


def load_annotations(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = formats.load(path)
    data = [] if data is None else data
    errs = schemas.errors("annotations", data)
    if errs:
        raise store.StoreError(
            "annotations_invalid",
            f"{path.name}: {errs[0]}",
            next=f"present schema check {path}",
        )
    return data


def id_pattern(repo: Repo, art: Path) -> str:
    try:
        override = manifest(art).get("claims", {}).get("id_pattern")
    except store.StoreError:
        override = None
    return override or repo.claims["id_pattern"]


def ledger_for(repo: Repo, art: Path) -> claims.Ledger:
    return claims.load_ledger(
        claims.find_ledger(talk_of_artifact(art)),
        id_pattern(repo, art),
        repo.claims["statuses"],
    )


# --------------------------------------------------------------------------- outputs


def render_speaking(script: annotate.Script) -> str:
    """The same spoken words, with each heading shown as a reading label (no brackets)."""
    out = []
    for n, sec in enumerate(script.sections, 1):
        out.append(f"### {n} · {sec.slide}\n\n{sec.body.strip()}\n")
    return "\n".join(out)


def render_notes(script: annotate.Script, results: list[dict[str, Any]]) -> str:
    """Per slide: the spoken text, then its note and cue annotations (what the deck's notes hold)."""
    out = []
    for sec in script.sections:
        out.append(f"## {sec.slide}\n\n{sec.body.strip()}\n")
        extras = [
            r
            for r in results
            if r["slide"] == sec.slide and r["kind"] in ("note", "cue")
        ]
        for r in extras:
            flag = "" if r["state"] == "resolved" else f" ({r['state']})"
            out.append(f"- {r['kind']}{flag} — “{r['quote']}”: {r['text']}")
        if extras:
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def produce(art: Path, vdir: Path) -> None:
    text = script_text(art)
    script = annotate.parse_script(text)
    anns = load_annotations(art / "src" / "annotations.yaml")
    results = annotate.resolve(script, anns)
    (vdir / "script.md").write_text(text, encoding="utf-8")
    (vdir / "annotations.yaml").write_text(
        yaml.safe_dump(anns, sort_keys=False, allow_unicode=True) if anns else "[]\n",
        encoding="utf-8",
    )
    (vdir / "speaking.md").write_text(render_speaking(script), encoding="utf-8")
    (vdir / "notes.md").write_text(render_notes(script, results), encoding="utf-8")
    (vdir / "annotations.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- checks


def preservation(
    art: Path, text_after: Path, annotations: Path | None
) -> dict[str, Any]:
    """writing's lossless re-voice check against the latest version, when installed."""
    rel, used_for, hint = NEIGHBOURS["writing"]
    tool = find_neighbour("writing", rel)
    if tool is None:
        return {"state": "unavailable", "next": hint}
    try:
        prev = store.latest(art)
    except store.StoreError as exc:
        return {"state": "skipped", "reason": exc.code}
    if prev is None:
        return {"state": "skipped", "reason": "no previous version"}
    cmd = ["python3", str(tool), "--json"]
    if annotations is not None and annotations.is_file():
        cmd += ["--annotations", str(annotations)]
    cmd += [str(art / f"v{prev}" / "script.md"), str(text_after)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode not in (0, 1):
        return {
            "state": "error",
            "exit": proc.returncode,
            "stderr": proc.stderr.strip()[:300],
        }
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"state": "error", "reason": "unparseable output"}
    return {
        "state": "lossless" if proc.returncode == 0 else "loss",
        "against": prev,
        "report": report,
    }


def run_checks(repo: Repo, art: Path, *, frozen: Path | None = None) -> dict[str, Any]:
    """Format, annotations and claims for src/ (or a frozen version folder)."""
    if frozen is not None:
        text = (frozen / "script.md").read_text(encoding="utf-8")
        anns = load_annotations(frozen / "annotations.yaml")
    else:
        text = script_text(art)
        anns = load_annotations(art / "src" / "annotations.yaml")
    script = annotate.parse_script(text)
    results = annotate.resolve(script, anns)
    label = (
        repo.rel(art / "src" / "script.md")
        if frozen is None
        else repo.rel(frozen / "script.md")
    )
    report = claims.check(
        [claims.ScriptInput(label, script, anns)],
        ledger_for(repo, art),
        id_pattern=id_pattern(repo, art),
        talk_level=False,
    )
    return {
        "format": script.findings,
        "annotations": results,
        "anchor_counts": annotate.counts(results),
        "claims": report,
    }


# --------------------------------------------------------------------------- commands


def _ref(
    p,
    help_="<talk>/<module>, a module or artifact path; default from the working directory",
):
    p.add_argument("ref", nargs="?", help=help_)


def _start(res: Result, ns, *, must_exist: bool = True) -> tuple[Repo, Path] | None:
    repo = require_repo(res)
    if repo is None:
        return None
    art = require_artifact(res, repo, ns.ref, "script", must_exist=must_exist)
    if art is None:
        return None
    return repo, art


def _store_error(res: Result, exc: store.StoreError) -> Result:
    return res.error(exc.code, exc.message, repairable=exc.repairable, next=exc.next)


@leaf(
    "script",
    "new",
    summary="create a script artifact in a module",
    task="0007",
    configure=_ref,
    effects=Effects(
        writes=True,
        description="Writes script.yaml, src/script.md and src/annotations.yaml; "
        "never overwrites.",
    ),
)
def script_new(ns, res: Result) -> Result:
    got = _start(res, ns, must_exist=False)
    if got is None:
        return res
    repo, art = got
    if (art / "script.yaml").exists():
        return res.error(
            "artifact_exists",
            f"{repo.rel(art)}/script.yaml already exists.",
            repairable=False,
            next=f"present script check {repo.rel(art)}",
        )
    art.mkdir(parents=True, exist_ok=True)
    (art / "src").mkdir(exist_ok=True)
    written = []
    for rel, body in (
        ("script.yaml", "schema_version: 1\n"),
        ("src/script.md", SCRIPT_MD),
        ("src/annotations.yaml", "[]\n"),
    ):
        path = art / rel
        if path.exists():
            continue
        with path.open("x", encoding="utf-8") as fh:
            fh.write(body)
        written.append(repo.rel(path))
    keep = art / ".gitkeep"
    if keep.is_file() and keep.stat().st_size == 0:
        keep.unlink()
    res.data = {"artifact": repo.rel(art), "files": written}
    res.text.append(f"created {repo.rel(art)} ({len(written)} files)")
    res.text.append(
        "next: write src/script.md as '## <slide-id>' sections, then `present script check`"
    )
    return res


def _configure_check(p):
    _ref(p)


@leaf(
    "script",
    "check",
    summary="format, claims and preservation checks",
    task="0007",
    configure=_configure_check,
    effects=Effects(
        description="Reads the script, its annotations and the talk's claims ledger; runs "
        "writing's re-voice check when installed."
    ),
)
def script_check(ns, res: Result) -> Result:
    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    try:
        out = run_checks(repo, art)
    except store.StoreError as exc:
        return _store_error(res, exc)
    src = art / "src"
    if manifest(art).get("sections"):  # preservation compares whole scripts; never write into src/
        with tempfile.TemporaryDirectory(prefix="present-check-") as tmp:
            combined = Path(tmp) / "script.md"
            combined.write_text(script_text(art), encoding="utf-8")
            out["preservation"] = preservation(art, combined, src / "annotations.yaml")
    else:
        out["preservation"] = preservation(art, src / "script.md", src / "annotations.yaml")
    if out["preservation"]["state"] == "unavailable":
        res.warn(
            "capability_unavailable",
            "writing's lossless re-voice check is not installed; preservation "
            "was not checked.",
            next=out["preservation"]["next"],
        )
    elif out["preservation"]["state"] == "loss":
        res.warn(
            "preservation_loss",
            f"{len(out['preservation']['report'].get('losses', []))} item(s) lost "
            f"since v{out['preservation']['against']}",
            next="present -j script check",
        )
    res.data = {"artifact": repo.rel(art), **out}
    s = out["claims"]["summary"]
    res.text.append(
        f"{repo.rel(art)}: format {len(out['format'])} finding(s); anchors "
        + ", ".join(f"{k} {v}" for k, v in out["anchor_counts"].items())
        + f"; concerns high {s['high']} · medium {s['medium']} · low {s['low']} · licensed {s['licensed']}"
    )
    for f in out["format"]:
        res.text.append(f"  line {f['line']}: {f['code']}: {f['message']}")
    for c in out["claims"]["concerns"]:
        hint = c.get("suggestion")
        res.text.append(
            f"  [{c['tier']}] {c['code']} {c['where']}: {c['message']}"
            + (f" → suggest {hint['quote']!r}" if hint else "")
        )
    blocking_fmt = [f for f in out["format"] if f["code"] in BLOCKING_FORMAT]
    if blocking_fmt:
        return res.error(
            "script_format",
            f"{len(blocking_fmt)} format finding(s) break the spoken-words-only "
            "contract.",
            repairable=True,
            next="move markers and markup into src/annotations.yaml",
        )
    blocked = claims.blocking(s, repo.claims["blocking_tiers"])
    if blocked:
        return res.error(
            "claims_blocking",
            f"concerns in blocking tier(s): {', '.join(blocked)}",
            repairable=True,
        )
    return res


@leaf(
    "script",
    "annotate",
    summary="resolve stand-off annotations; orphans and re-anchor hints",
    task="0018",
    configure=_ref,
    effects=Effects(
        description="Reads src/script.md and src/annotations.yaml; never "
        "re-anchors anything."
    ),
)
def script_annotate(ns, res: Result) -> Result:
    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    try:
        script = annotate.parse_script(script_text(art))
        anns = load_annotations(art / "src" / "annotations.yaml")
    except store.StoreError as exc:
        return _store_error(res, exc)
    results = annotate.resolve(script, anns)
    res.data = {
        "artifact": repo.rel(art),
        "annotations": results,
        "counts": annotate.counts(results),
    }
    c = res.data["counts"]
    res.text.append(
        f"{repo.rel(art)}: {len(results)} annotation(s): resolved {c['resolved']}, "
        f"ambiguous {c['ambiguous']}, orphaned {c['orphaned']}"
    )
    for r in results:
        if r["state"] != "resolved":
            sug = r.get("suggestion")
            res.text.append(
                f"  #{r['index']} {r['state']} [{r['slide']}] {r['quote']!r}"
                + (f" → suggest {sug['quote']!r} ({sug['score']})" if sug else "")
            )
    if c["orphaned"] or c["ambiguous"]:
        res.warn(
            "annotations_unresolved",
            f"{c['orphaned']} orphaned, {c['ambiguous']} ambiguous",
            next="edit src/annotations.yaml (suggestions are never applied automatically)",
        )
    return res


def _configure_bump(p):
    _ref(p)
    p.add_argument(
        "--level",
        choices=store.LEVELS,
        default="patch",
        help="major: structure; minor: content; patch: no change in meaning (spec §5)",
    )
    p.add_argument("--note", required=True, help="one line for the CHANGELOG")
    p.add_argument("--version", help="explicit version (must be greater than latest)")


@leaf(
    "script",
    "bump",
    summary="freeze src/ into the next version",
    task="0007",
    configure=_configure_bump,
    effects=Effects(
        writes=True,
        description="Writes one new version folder, moves latest, appends CHANGELOG.",
    ),
)
def script_bump(ns, res: Result) -> Result:
    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    try:
        script = annotate.parse_script(script_text(art))
        load_annotations(art / "src" / "annotations.yaml")
        bad = [f for f in script.findings if f["code"] in BLOCKING_FORMAT]
        if bad:
            return res.error(
                "script_format",
                f"{bad[0]['code']} at line {bad[0]['line']}: {bad[0]['message']}",
                repairable=True,
                next=f"present script check {repo.rel(art)}",
            )
        extra = [art / "script.yaml"]
        out = store.bump(
            repo.root,
            art,
            kind="script",
            level=ns.level,
            note=ns.note,
            produce=produce,
            version=ns.version,
            standard=repo.standard,
            extra_inputs=extra,
        )
    except store.StoreError as exc:
        return _store_error(res, exc)
    res.data = {
        "artifact": repo.rel(art),
        "version": out.version,
        "previous": out.previous,
        "receipt": repo.rel(out.path / store.RECEIPT),
        "dirty": out.receipt["git"]["dirty"],
    }
    res.text.append(
        f"{repo.rel(art)}: v{out.version}"
        + (f" (from {out.previous})" if out.previous else "")
        + (
            " — built from uncommitted src/; commit and bump again before approval"
            if out.receipt["git"]["dirty"]
            else ""
        )
    )
    return res


def _configure_show(p):
    _ref(p)
    p.add_argument("--version", help="default: latest")
    p.add_argument("--verify", action="store_true", help="recompute every output hash")


@leaf(
    "script",
    "show",
    summary="show a version's receipt and approval",
    task="0007",
    configure=_configure_show,
    effects=Effects(description="Reads one artifact."),
)
def script_show(ns, res: Result) -> Result:
    return show_artifact(ns, res, "script")


def show_artifact(ns, res: Result, kind: str) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    art = require_artifact(res, repo, ns.ref, kind)
    if art is None:
        return res
    summ = store.summary(art)
    version = ns.version or summ["latest"]
    res.data = {"artifact": repo.rel(art), **summ}
    if version is None:
        res.text.append(f"{repo.rel(art)}: no versions yet")
        return res
    try:
        rec = store.receipt(art, version)
    except store.StoreError as exc:
        return _store_error(res, exc)
    res.data.update(
        {"version": version, "receipt": rec, "approved": version in summ["approved"]}
    )
    res.text.append(
        f"{repo.rel(art)} v{version} ({rec['level']}, {rec['created']}): {rec['note']}"
    )
    res.text.append(
        f"  approved: {'yes' if version in summ['approved'] else 'no'}; built from "
        f"{'uncommitted' if rec['git']['dirty'] else 'committed'} sources at {rec['git']['commit'] or 'no commit'}"
    )
    for p in summ["problems"]:
        res.warn(p["code"], p["message"])
    if ns.verify:
        bad = store.verify(repo.root, art, version)
        res.data["verify"] = bad
        if bad:
            return res.error(
                "version_unverified",
                f"{len(bad)} hash finding(s): {bad[0]['code']} {bad[0]['path']}",
                repairable=False,
            )
        res.text.append("  verify: every output hash matches")
    return res


def _configure_approve(p):
    _ref(p)
    p.add_argument("--version", help="default: latest")
    p.add_argument("--by", help="approver (default: git user.name)")
    p.add_argument("--note")


def git_user(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@leaf(
    "script",
    "approve",
    summary="record approval of a script version",
    task="0007",
    configure=_configure_approve,
    effects=Effects(writes=True, description="Appends to approvals.yaml."),
)
def script_approve(ns, res: Result) -> Result:
    got = _start(res, ns)
    if got is None:
        return res
    repo, art = got
    try:
        version = ns.version or store.latest(art)
        if version is None:
            return res.error(
                "version_not_found",
                "nothing to approve: no versions yet.",
                repairable=True,
                next=f"present script bump {repo.rel(art)} --note …",
            )
        out = run_checks(repo, art, frozen=art / f"v{version}")
        fmt = [f for f in out["format"] if f["code"] in BLOCKING_FORMAT]
        summary = out["claims"]["summary"]
        blocked = claims.blocking(summary, repo.claims["blocking_tiers"])
        if blocked:
            return res.error(
                "claims_blocking",
                f"v{version} has concerns in blocking tier(s) "
                f"{', '.join(blocked)} (presentations.toml [claims] blocking_tiers).",
                repairable=True,
                next=f"present script check {repo.rel(art)}",
            )
        entry = store.approve(
            repo.root,
            art,
            version,
            by=ns.by or git_user(repo.root),
            checks={
                "format": "ok" if not fmt else f"{len(fmt)} finding(s)",
                "anchors": out["anchor_counts"],
            },
            concerns=summary,
            note=ns.note,
        )
    except store.StoreError as exc:
        return _store_error(res, exc)
    res.data = {"artifact": repo.rel(art), "approval": entry}
    res.text.append(
        f"{repo.rel(art)} v{version} approved by {entry['by']} — concerns high {summary['high']} · "
        f"medium {summary['medium']} · low {summary['low']} · licensed {summary['licensed']}"
    )
    return res
