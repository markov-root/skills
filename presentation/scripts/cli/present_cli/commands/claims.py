"""`present claims check|list|pin` (tasks 0006, 0022; ADR 0006): advisory concerns in tiers; flag,
never fix. `pin` is the one write: it records the exact versions of typed source references."""

from __future__ import annotations

from pathlib import Path

from .. import annotate, claims, formats, references, store
from ..console import Effects, Result, leaf
from ..context import DEFAULT_CLAIMS, load_talk, require_repo, require_talk
from . import script as script_cmd


def _configure_common(p):
    p.add_argument(
        "talk",
        nargs="?",
        help="talk folder; default the talk containing the working directory",
    )
    p.add_argument(
        "--ledger",
        type=Path,
        help="an explicit ledger file (e.g. a legacy CLAIMS.md); read-only",
    )
    p.add_argument("--id-pattern", help="override the claim ID regex for --ledger")


def _settings(res: Result, ns):
    """(repo or None, claims settings). With --ledger, a repository is optional."""
    if ns.ledger is not None:
        from ..repo import find_repo

        repo = require_repo(Result(command="probe")) if find_repo() else None
        cfg = dict(repo.claims if repo else DEFAULT_CLAIMS)
        if ns.id_pattern:
            cfg["id_pattern"] = ns.id_pattern
        return repo, cfg
    repo = require_repo(res)
    return repo, (repo.claims if repo else None)


def _talk_scripts(res: Result, repo, talk: Path) -> list[claims.ScriptInput]:
    data = load_talk(res, talk)
    if data is None:
        return []
    out = []
    for m in data["modules"]:
        art = talk / "modules" / m["id"] / "script"
        if not m["script"] or not (art / "script.yaml").is_file():
            continue
        try:
            text = script_cmd.script_text(art)
            anns = script_cmd.load_annotations(art / "src" / "annotations.yaml")
        except store.StoreError as exc:
            res.warn(exc.code, exc.message, next=exc.next)
            continue
        out.append(
            claims.ScriptInput(
                repo.rel(art / "src" / "script.md"), annotate.parse_script(text), anns
            )
        )
    return out


def _configure_check(p):
    _configure_common(p)
    p.add_argument(
        "--script",
        type=Path,
        action="append",
        help="an explicit script file (with --ledger); "
        "repeatable; its annotations are <dir>/annotations.yaml when present",
    )
    p.add_argument(
        "--tier", choices=claims.TIERS, action="append", help="show only these tiers"
    )


@leaf(
    "claims",
    "check",
    summary="advisory claim concerns in high/medium/low tiers",
    task="0006",
    configure=_configure_check,
    effects=Effects(
        description="Reads scripts, annotations and the claims ledger; never edits them. "
        "Resolves research:/dataset: source references through the read-only `research` "
        "and `datasets` CLIs when present."
    ),
)
def claims_check(ns, res: Result) -> Result:
    repo, cfg = _settings(res, ns)
    if cfg is None:
        return res
    if ns.ledger is not None:
        if not ns.ledger.is_file():
            return res.error(
                "file_not_found", f"{ns.ledger} does not exist", repairable=True
            )
        ledger = claims.load_ledger(ns.ledger, cfg["id_pattern"], cfg["statuses"])
        inputs = []
        for sp in ns.script or []:
            if not sp.is_file():
                return res.error(
                    "file_not_found", f"{sp} does not exist", repairable=True
                )
            ann = sp.parent / "annotations.yaml"
            anns = formats.load(ann) if ann.is_file() else []
            inputs.append(
                claims.ScriptInput(
                    str(sp),
                    annotate.parse_script(sp.read_text(encoding="utf-8")),
                    anns or [],
                )
            )
        label = str(ns.ledger)
    else:
        talk = require_talk(res, repo, ns.talk)
        if talk is None:
            return res
        ledger_path = claims.find_ledger(talk)
        if ledger_path is None:
            res.warn(
                "ledger_missing",
                f"{talk.name}/research/claims.md does not exist; every cited claim "
                "will be reported missing.",
                next=f"create {talk.name}/research/claims.md",
            )
        ledger = claims.load_ledger(ledger_path, cfg["id_pattern"], cfg["statuses"])
        inputs = _talk_scripts(res, repo, talk)
        label = talk.name
    report = claims.check(inputs, ledger, id_pattern=cfg["id_pattern"], talk_level=True)
    report["references"] = _resolve_sources(res, ledger, report)
    shown = [c for c in report["concerns"] if not ns.tier or c["tier"] in ns.tier]
    s = report["summary"]
    res.data = {
        "scope": label,
        "scripts": [i.label for i in inputs],
        "ledger": str(ledger.path) if ledger.path else None,
        "ledger_rows": len(ledger.rows),
        "blocking_tiers": cfg["blocking_tiers"],
        **report,
        "concerns": shown,
    }
    res.text.append(
        f"{label}: {len(inputs)} script(s), {len(ledger.rows)} ledger row(s) — concerns high "
        f"{s['high']} · medium {s['medium']} · low {s['low']} · licensed {s['licensed']}"
    )
    for c in shown:
        hint = c.get("suggestion")
        res.text.append(
            f"  [{c['tier']}] {c['code']} {c['where']}: {c['message']}"
            + (f" → suggest {hint['quote']!r}" if hint else "")
        )
    for lic in report["licensed"]:
        res.text.append(
            f"  [licensed] {lic['where']}: {lic['quote']!r} — {lic['licence']}"
        )
    res.text.append(
        "Advisory: flag these to the speaker; do not rewrite their framing."
    )
    blocked = claims.blocking(s, cfg["blocking_tiers"])
    if blocked:
        return res.error(
            "claims_blocking",
            f"concerns in blocking tier(s): {', '.join(blocked)}",
            repairable=True,
        )
    return res


def _resolve_sources(res: Result, ledger: claims.Ledger, report: dict) -> dict:
    """Add source-reference concerns to `report`; one capability_unavailable per missing CLI."""
    resolver = references.Resolver()
    extra = references.source_concerns(ledger, resolver)
    report["concerns"] += extra
    for c in extra:
        report["summary"][c["tier"]] += 1
    refs = [ref for _, ref in references.ledger_refs(ledger)]
    for name, why in sorted(resolver.unavailable.items()):
        kind = "dataset" if name == "datasets" else name
        n = sum(1 for r in refs if r.kind == kind)
        res.warn(
            "capability_unavailable",
            f"{why}; {n} {kind}: reference(s) not checked.",
            next=references.install_hint(name),
        )
    return {
        "found": len(refs),
        "unchecked": sum(
            1 for r in refs if ("datasets" if r.kind == "dataset" else r.kind) in resolver.unavailable
        ),
        "unavailable": sorted(resolver.unavailable),
    }


def _configure_list(p):
    _configure_common(p)
    p.add_argument("--status", help="only rows with this status")


@leaf(
    "claims",
    "list",
    summary="print the claims ledger",
    task="0006",
    configure=_configure_list,
    effects=Effects(description="Reads the claims ledger."),
)
def claims_list(ns, res: Result) -> Result:
    repo, cfg = _settings(res, ns)
    if cfg is None:
        return res
    if ns.ledger is not None:
        path = ns.ledger
        if not path.is_file():
            return res.error(
                "file_not_found", f"{path} does not exist", repairable=True
            )
    else:
        talk = require_talk(res, repo, ns.talk)
        if talk is None:
            return res
        path = claims.find_ledger(talk)
        if path is None:
            return res.error(
                "ledger_missing",
                f"{talk.name}/research/claims.md does not exist",
                repairable=True,
            )
    ledger = claims.load_ledger(path, cfg["id_pattern"], cfg["statuses"])
    rows = [
        r
        for r in ledger.rows.values()
        if not ns.status or r.status == ns.status.upper()
    ]
    res.data = {
        "ledger": str(path),
        "rows": [r.__dict__ for r in rows],
        "problems": ledger.problems,
        "skipped_tables": ledger.skipped_tables,
        "counts": {
            st: sum(1 for r in ledger.rows.values() if r.status == st)
            for st in cfg["statuses"]
        },
    }
    for r in rows:
        res.text.append(f"{r.id:<8} {r.status:<11} {r.claim[:90]}")
    res.text.append(
        f"{len(ledger.rows)} row(s); "
        + ", ".join(f"{k} {v}" for k, v in res.data["counts"].items())
    )
    for p in ledger.problems:
        res.warn("ledger_row_invalid", f"{path.name}:{p['line']}: {p['message']}")
    return res


def _configure_pin(p):
    p.add_argument(
        "talk",
        nargs="?",
        help="talk folder; default the talk containing the working directory",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="write the resolved versions into the ledger (default: dry run, writes nothing)",
    )


@leaf(
    "claims",
    "pin",
    summary="write the exact resolved version into unpinned research:/dataset: sources",
    task="0022",
    configure=_configure_pin,
    effects=Effects(
        writes=True,
        description="Dry run by default: resolves unpinned research:/dataset: references in the "
        "ledger's Source cells and lists the edits. --apply rewrites only those references in "
        "research/claims.md; every other byte is kept.",
    ),
)
def claims_pin(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    cfg = repo.claims
    talk = require_talk(res, repo, ns.talk)
    if talk is None:
        return res
    path = claims.find_ledger(talk)
    if path is None:
        return res.error(
            "ledger_missing",
            f"{talk.name}/research/claims.md does not exist",
            repairable=True,
        )
    ledger = claims.load_ledger(path, cfg["id_pattern"], cfg["statuses"])
    resolver = references.Resolver()
    changes, skipped = references.pin_changes(ledger, resolver)
    for name, why in sorted(resolver.unavailable.items()):
        res.warn("capability_unavailable", f"{why}; its references stay unpinned.",
                 next=references.install_hint(name))
    text = path.read_text(encoding="utf-8")
    written = False
    if ns.apply and changes:
        out = text
        for line in sorted({c["line"] for c in changes}):
            col = references.source_column(out, line)
            out = references.apply_pins(out, [c for c in changes if c["line"] == line], col)
        if out != text:
            path.write_text(out, encoding="utf-8")
            written = True
    res.data = {
        "ledger": repo.rel(path),
        "dry_run": not ns.apply,
        "written": written,
        "changes": changes,
        "skipped": skipped,
    }
    for c in changes:
        res.text.append(f"  {c['claim']} (line {c['line']}): {c['from']} → {c['to']}")
    for s_ in skipped:
        res.text.append(f"  {s_['claim']} (line {s_['line']}): {s_['reference']} not pinned — "
                        f"{s_['status']}{': ' + s_['message'] if s_['message'] else ''}")
    verb = "pinned" if written else "would pin"
    res.text.append(f"{repo.rel(path)}: {verb} {len(changes)} reference(s); "
                    f"{len(skipped)} left unpinned"
                    + ("" if ns.apply else " (dry run; --apply writes)"))
    return res
