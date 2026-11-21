"""`present talk new|list|status|readme` (task 0004; specification §3, §4, §9)."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .. import formats
from ..console import Effects, Result, leaf
from ..context import (
    TALK_FILE,
    Repo,
    engineering_cli,
    load_talk,
    require_repo,
    require_talk,
    today,
    value,
)

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MODULE_ID = re.compile(r"^[0-9]{2}-[a-z0-9]+(-[a-z0-9]+)*$")
FORMATS = ("online", "onsite", "hybrid")

HEADER_START, HEADER_END = (
    "<!-- present:header:start -->",
    "<!-- present:header:end -->",
)
TABLE_START, TABLE_END = "<!-- present:talks:start -->", "<!-- present:talks:end -->"


# --------------------------------------------------------------------------- scaffold content


def _talk_yaml(slug: str, ns, modules: list[dict[str, Any]]) -> str:
    data: dict[str, Any] = {
        "schema_version": 1,
        "id": slug,
        "title": ns.title or _default_title(ns),
        "status": "preparing",
        "format": ns.format,
        "occasion": ns.occasion,
        "country": ns.country,
        "language": ns.language,
    }
    if ns.date:
        data["date"] = {"value": ns.date}
    if ns.minutes:
        data["slot_minutes"] = {"value": ns.minutes}
    data["modules"] = modules
    head = (
        "# Talk metadata (presentation specification §4). Normalised facts only; the evidence\n"
        "# lives beside it in promised.md, correspondence/ and materials/. Any field may be\n"
        "# {value: …, source: correspondence/<file>.md}.\n"
    )
    return head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def _default_title(ns) -> str:
    return f"{ns.format.capitalize()} {ns.occasion.replace('-', ' ')}, {ns.country.replace('-', ' ').title()}"


def header_block(talk: dict[str, Any]) -> str:
    date = value(talk.get("date")) or "date to be confirmed"
    slot = value(talk.get("slot_minutes"))
    aud = (talk.get("audience") or {}).get(
        "summary"
    ) or "audience to be recorded in audience/talk.yaml"
    mods = talk.get("modules", [])
    lines = [
        HEADER_START,
        f"# {talk['title']}",
        "",
        f"**{talk['format'].capitalize()} {talk['occasion']}, {talk['country'].replace('-', ' ').title()}** "
        f"· {date}"
        + (f" · {slot} min" if slot else "")
        + f" · status: **{talk['status']}**",
        "",
        f"Audience: {aud}",
        "",
        "| Module | Minutes | Script | Deck |",
        "| --- | --- | --- | --- |",
    ]
    for m in mods:
        lines.append(
            f"| `{m['id']}` {m['title']} | {m.get('minutes', '—')} | "
            f"{'yes' if m['script'] else 'none'} | {'yes' if m['deck'] else 'none'} |"
        )
    lines += [
        "",
        "_Generated from `audience/talk.yaml` by `present talk readme`; edit that file, not this block._",
        HEADER_END,
    ]
    return "\n".join(lines)


README_BODY = """
## Where things are

- `audience/` — what the audience told us: `talk.yaml` (facts), `promised.md`, `correspondence/`, `materials/`
- `modules/<nn-slug>/` — one script and one deck per module
- `visuals/` — this talk's visual pool (rendered by the visuals skill)
- `research/claims.md` — the one claims ledger; `research/notes/`, `research/literature/`
- `docs/` — records: start at `docs/README.md`, then the current handoff
- `delivery/` — one record per delivery (`present delivery record`)
"""

AGENTS_MD = """# AGENTS.md — {slug}

A standard-{standard} talk (the `presentation` skill owns the standard; load it first).

1. Read `docs/README.md`, then the `current` row of `docs/handoffs/README.md`.
2. Facts about the talk live in `audience/talk.yaml`; never restate them elsewhere.
3. Before drafting spoken text, load the writing skill's `presentation-voice` profile.
   Scripts hold only spoken words; claims and notes stand off in `annotations.yaml`.
4. Edit only `src/` folders; freeze with `present script bump` / `present deck build`.
5. Run `present talk status` and `present validate --talk {slug}` before finishing.

Keep `AGENTS.md` canonical; `CLAUDE.md` is a relative symlink to this file.
"""

CLAIMS_MD = """# Claims ledger

One ledger for the whole talk (presentation specification §7). Spoken text cites rows through
stand-off anchors in each script's `src/annotations.yaml`; never through inline markers.

Statuses: `VERIFIED` (primary source checked) · `SECONDARY` (reported by a reliable secondary
source) · `SOFT` (judgement or estimate; do not word as fact) · `UNVERIFIED` (not yet checked).

| ID | Claim | Source | Status | Notes |
| --- | --- | --- | --- | --- |
"""

PROMISED_MD = """# What was promised

Quote the agreed structure exactly as it was circulated to the audience, with its source file
in `correspondence/` and the date. Nothing here is paraphrased.
"""

DOCS_ENGINEERING_YAML = """version: 1

# Per-talk record root (presentation specification §9). Created by `present talk new`.
# Declare a role (adr, task, lesson) when its first record is allocated: an empty declared role
# is a validator finding. Copy the commented blocks below into `roles:` when needed.

project:
  risk: low
  core_outcome: >-
    {title}: delivered from approved, traceable script and deck versions.

checks:
  document-validate:
    command: ["engineering", "document", "validate", "--project-root", "."]
    applies_to: ["**/*.md", "/engineering.yaml"]
    timeout_seconds: 120

docs:
  include: ["*.md", "handoffs/**/*.md", "adr/**/*.md", "tasks/**/*.md", "lessons/**/*.md"]
  currency:
    roles:
      - name: specification
        include: ["[0-9][0-9][0-9][0-9]-*.md"]
        index: "README.md"
        id_prefix_digits: 4
        contract: {{ version: 1, role: specification }}
      - name: handoff
        include: ["handoffs/[0-9][0-9][0-9][0-9]-*.md"]
        index: "handoffs/README.md"
        id_prefix_digits: 4
        contract: {{ version: 1, role: handoff }}
        states: ["current", "superseded"]
        current_state: "current"
      # - name: adr
      #   include: ["adr/[0-9][0-9][0-9][0-9]-*.md"]
      #   index: "adr/README.md"
      #   id_prefix_digits: 4
      #   contract: {{ version: 1, role: adr }}
      # - name: task
      #   include: ["tasks/[0-9][0-9][0-9][0-9]-*.md"]
      #   index: "tasks/README.md"
      #   id_prefix_digits: 4
      #   contract: {{ version: 1, role: task }}
      # - name: lesson
      #   include: ["lessons/[0-9][0-9][0-9][0-9]-*.md"]
      #   index: "lessons/README.md"
      #   id_prefix_digits: 4
      #   contract: {{ version: 1, role: lesson }}

task_inventory:
  include: ["tasks/[0-9][0-9][0-9][0-9]-*.md"]
  handoffs: ["handoffs/[0-9][0-9][0-9][0-9]-*.md"]
  decisions: ["adr/[0-9][0-9][0-9][0-9]-*.md"]
"""

DOCS_README = """# {slug} — docs

Reading order for anyone picking this talk up:

1. `../AGENTS.md`, then `handoffs/README.md` → its one `current` row.
2. `0001-outline.md` — beats and time budget per module. It locks before prose.
3. `../audience/talk.yaml` and `../audience/promised.md` — the facts and what was promised.

Records are governed by `engineering.yaml` (software-engineering document system). Allocate with
`engineering document new <role> --title "…" --project-root .`; validate before committing.

| Record | Role |
| --- | --- |
| [0001](0001-outline.md) | specification — outline |
"""

HANDOFFS_README = """# Handoffs

Exactly one handoff is `current`. When writing a new one, supersede the previous rather than
editing it.

| # | Status | Record |
| --- | --- | --- |
"""

OUTLINE_BODY = """# Specification: Outline — {title}

## Purpose

The beats and time budget of every module. It locks before prose: scripts follow it, and a change
here is a structural (MAJOR) change to the script that follows.

## Current behavior and contracts

{modules}

## Boundary cases

- Timing is advisory: when the beats overrun the slot, cut beats here, never mid-script.

## Evolution and divergence owners

Owned by whoever prepares the talk. Changes are recorded in the current handoff.
"""

HANDOFF_BODY = """# Handoff 0001: Talk scaffolded

## Outcome

`{slug}` was created by `present talk new` in the standard-{standard} layout. Nothing has been
written yet beyond the skeleton.

## Completed work

- The talk skeleton, `audience/talk.yaml` and this record root.

## Open work

1. Record the facts in `audience/talk.yaml` (date, slot, audience, contacts) with their sources.
2. Quote what was promised into `audience/promised.md`.
3. Write the outline in `docs/0001-outline.md`.

## Blockers

None.

## Resume

```sh
present talk status {slug}
```
"""


# --------------------------------------------------------------------------- helpers


def _modules(ns) -> list[dict[str, Any]]:
    if ns.module:
        out = []
        for spec in ns.module:
            mid, _, title = spec.partition(":")
            out.append(
                {
                    "id": mid,
                    "title": title or mid[3:].replace("-", " ").capitalize(),
                    "script": True,
                    "deck": True,
                }
            )
        return out
    n = ns.modules or 1
    if n == 1:
        return [{"id": "01-main", "title": "Main", "script": True, "deck": True}]
    return [
        {
            "id": f"{i:02d}-module-{i}",
            "title": f"Module {i}",
            "script": True,
            "deck": True,
        }
        for i in range(1, n + 1)
    ]


def scaffold_files(
    slug: str, ns, repo: Repo, modules: list[dict[str, Any]]
) -> dict[str, str]:
    """Relative path → content for every scaffolded file (records are allocated separately)."""
    talk = formats.loads_yaml(_talk_yaml(slug, ns, modules))
    files = {
        "README.md": header_block(talk) + "\n" + README_BODY,
        "AGENTS.md": AGENTS_MD.format(slug=slug, standard=repo.standard),
        "audience/talk.yaml": _talk_yaml(slug, ns, modules),
        "audience/promised.md": PROMISED_MD,
        "audience/correspondence/.gitkeep": "",
        "audience/materials/.gitkeep": "",
        "visuals/.gitkeep": "",
        "research/claims.md": CLAIMS_MD,
        "research/notes/.gitkeep": "",
        "research/literature/.gitkeep": "",
        "docs/engineering.yaml": DOCS_ENGINEERING_YAML.format(title=talk["title"]),
        "docs/README.md": DOCS_README.format(slug=slug),
        "docs/handoffs/README.md": HANDOFFS_README,
        "delivery/.gitkeep": "",
    }
    for m in modules:
        for kind in ("script", "deck"):
            if m[kind]:
                files[f"modules/{m['id']}/{kind}/.gitkeep"] = ""
    return files


def _owner() -> str:
    try:
        out = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or "maintainer"
    except Exception:
        return "maintainer"


def _allocate(eng: str, docs: Path, role: str, title: str) -> Path:
    proc = subprocess.run(
        [eng, "document", "new", role, "--title", title, "--project-root", str(docs)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    m = re.search(r"^Created (\S+)", proc.stdout, re.M)
    if proc.returncode != 0 or not m:
        raise RuntimeError(
            f"engineering document new {role} failed: {(proc.stdout + proc.stderr).strip()[:300]}"
        )
    return docs / m.group(1)


def _fill(path: Path, body: str, subs: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    end = text.index("\n---\n", 4) + 5
    front = text[:end]
    for old, new in subs.items():
        front = front.replace(old, new)
    path.write_text(front + "\n" + body, encoding="utf-8")


def allocate_records(
    eng: str,
    docs: Path,
    slug: str,
    title: str,
    standard: int,
    modules: list[dict[str, Any]],
) -> list[str]:
    owner = _owner()
    outline = _allocate(eng, docs, "specification", "Outline")
    mods = "\n".join(
        f"### `{m['id']}` — {m['title']}\n\n| Beat | Minutes | Slide IDs |\n| --- | --- | --- |\n"
        for m in modules
    )
    _fill(
        outline,
        OUTLINE_BODY.format(title=title, modules=mods),
        {
            "SPEC OWNER": owner,
            '"Specification record: Outline."': '"Beats and time budget per module."',
        },
    )
    handoff = _allocate(eng, docs, "handoff", "Talk scaffolded")
    _fill(
        handoff,
        HANDOFF_BODY.format(slug=slug, standard=standard),
        {
            "HANDOFF OWNER": owner,
            '"Handoff record: Talk scaffolded."': f'"{slug} scaffolded; record its facts next."',
            "REPOSITORY IDENTITY": slug,
            "COMMIT OR DIRTY-STATE IDENTITY": "uncommitted (present talk new)",
            "CURRENT OBJECTIVE": f"Prepare {slug}.",
            "open_work: [task:NNNN]": "open_work: []",
            "authority_refs: [AGENTS.md, docs/tasks/NNNN-title.md]": "authority_refs: [0001-outline.md]",
            "FIRST SAFE COMMAND": f"present talk status {slug}",
        },
    )
    with (docs / "handoffs" / "README.md").open("a", encoding="utf-8") as fh:
        fh.write(f"| [0001]({handoff.name}) | current | Talk scaffolded |\n")
    return [
        outline.relative_to(docs.parent).as_posix(),
        handoff.relative_to(docs.parent).as_posix(),
    ]


def _validate_docs(eng: str, docs: Path) -> list[str]:
    proc = subprocess.run(
        [eng, "document", "validate", "--project-root", str(docs)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if "No findings." in proc.stdout:
        return []
    return [
        ln.strip("- ") for ln in proc.stdout.splitlines() if ln.startswith("- ")
    ] or [proc.stdout.strip()[:300]]


# --------------------------------------------------------------------------- talk new


def _configure_new(p):
    p.add_argument(
        "slug",
        nargs="?",
        help="talk folder name; default <format>-<occasion>-<country>",
    )
    p.add_argument("--format", required=True, choices=FORMATS)
    p.add_argument(
        "--occasion",
        required=True,
        help="training | conference | briefing | meeting | panel | …",
    )
    p.add_argument("--country", required=True)
    p.add_argument("--title")
    p.add_argument("--language", default="en")
    p.add_argument("--date", help="YYYY-MM-DD")
    p.add_argument("--minutes", type=int, help="slot length in minutes")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--modules", type=int, help="number of modules (default 1: 01-main)")
    g.add_argument(
        "--module",
        action="append",
        metavar="NN-SLUG[:TITLE]",
        help="a named module; repeatable",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written; write nothing",
    )
    p.add_argument(
        "--allow-existing",
        action="store_true",
        help="add missing files to an existing directory; never overwrites",
    )


@leaf(
    "talk",
    "new",
    summary="create a talk in the standard layout",
    task="0004",
    configure=_configure_new,
    effects=Effects(
        writes=True,
        description="Writes a new talk directory (staged, then renamed into "
        "place); never overwrites. Runs `engineering document new` to allocate records.",
    ),
)
def talk_new(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    for field in ("occasion", "country"):
        if not SLUG.match(getattr(ns, field)):
            return res.error(
                "argument_invalid",
                f"--{field} must be kebab-case: {getattr(ns, field)!r}",
                repairable=True,
            )
    expected = f"{ns.format}-{ns.occasion}-{ns.country}"
    slug = ns.slug or expected
    if not SLUG.match(slug):
        return res.error(
            "argument_invalid",
            f"talk name must be kebab-case: {slug!r}",
            repairable=True,
        )
    if slug != expected:
        res.warn(
            "naming",
            f"{slug!r} differs from <format>-<occasion>-<country> = {expected!r}.",
            next="check the repository's naming ADR",
        )
    if ns.date and not re.match(r"^\d{4}-\d{2}-\d{2}$", ns.date):
        return res.error(
            "argument_invalid",
            f"--date must be YYYY-MM-DD: {ns.date!r}",
            repairable=True,
        )
    modules = _modules(ns)
    bad = [m["id"] for m in modules if not MODULE_ID.match(m["id"])]
    if bad or len({m["id"] for m in modules}) != len(modules):
        return res.error(
            "argument_invalid",
            f"module ids must be unique NN-kebab-case: {bad or 'duplicates'}",
            repairable=True,
        )
    if slug in repo.legacy:
        return res.error(
            "talk_legacy",
            f"{slug} is listed under [legacy]; moving it to a standard is an "
            "explicit, recorded act (specification §11).",
            repairable=False,
        )

    target = repo.root / slug
    exists = target.exists()
    if exists and not ns.allow_existing:
        return res.error(
            "talk_exists",
            f"{slug}/ already exists.",
            repairable=True,
            next=f"present talk new {slug} … --allow-existing  (adds missing files only)",
        )
    if exists and not target.is_dir():
        return res.error(
            "talk_exists", f"{slug} exists and is not a directory.", repairable=False
        )

    files = scaffold_files(slug, ns, repo, modules)
    talk_yaml = formats.loads_yaml(files["audience/talk.yaml"])
    eng = engineering_cli()
    has_records = exists and any(
        (target / "docs" / "handoffs").glob("[0-9][0-9][0-9][0-9]-*.md")
    )
    allocate = eng is not None and not has_records

    to_write = (
        [rel for rel in files if not (target / rel).exists()] if exists else list(files)
    )
    skipped = sorted(set(files) - set(to_write))
    links = (
        ["CLAUDE.md"]
        if not (target / "CLAUDE.md").is_symlink()
        and not (target / "CLAUDE.md").exists()
        else []
    )
    res.data = {
        "talk": slug,
        "path": repo.rel(target) if exists else slug,
        "dry_run": ns.dry_run,
        "files": sorted(to_write),
        "links": links,
        "skipped_existing": skipped,
        "records": "allocate"
        if allocate
        else ("existing" if has_records else "unavailable"),
        "modules": [m["id"] for m in modules],
    }
    if eng is None:
        res.warn(
            "capability_unavailable",
            "software-engineering `engineering` not found: docs/ is scaffolded "
            "but no outline or handoff is allocated.",
            next="install the software-engineering skill, then "
            "run `engineering document new specification --title Outline --project-root <talk>/docs`",
        )
    if ns.dry_run:
        res.text.append(
            f"would create {slug}/ ({len(to_write)} files"
            + (f", {len(skipped)} existing kept" if skipped else "")
            + ")"
        )
        res.text += [f"  {f}" for f in sorted(to_write)]
        return res

    stage = (
        target if exists else repo.root / f".present-new-{slug}-{secrets.token_hex(4)}"
    )
    try:
        for rel in to_write:
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("x", encoding="utf-8") as fh:  # "x": never overwrite
                fh.write(files[rel])
        if links:
            os.symlink("AGENTS.md", stage / "CLAUDE.md")
        records: list[str] = []
        if allocate:
            records = allocate_records(
                eng, stage / "docs", slug, talk_yaml["title"], repo.standard, modules
            )
        if not exists:
            os.rename(
                stage, target
            )  # atomic on one filesystem; the talk appears whole or not at all
    except Exception:
        if not exists:
            shutil.rmtree(stage, ignore_errors=True)
        raise
    res.data["records"] = records if allocate else res.data["records"]
    if eng is not None:
        findings = _validate_docs(eng, target / "docs")
        res.data["docs_findings"] = findings
        if findings:
            res.warn(
                "docs_findings",
                f"engineering document validate: {findings[0]}",
                next=f"engineering document validate --project-root {target / 'docs'}",
            )
    res.text.append(
        f"created {slug}/ ({len(to_write)} files"
        + (f", {len(records)} records" if allocate else "")
        + ")"
    )
    res.text.append(f"next: fill {slug}/audience/talk.yaml, then `present talk readme`")
    return res


# --------------------------------------------------------------------------- list / status


def _summary(talk_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data["id"],
        "folder": talk_dir.name,
        "title": data["title"],
        "status": data["status"],
        "date": value(data.get("date")),
        "format": data["format"],
        "occasion": data["occasion"],
        "country": data["country"],
        "modules": [m["id"] for m in data["modules"]],
    }


def _configure_list(p):
    p.add_argument("--status", choices=["preparing", "delivered", "cancelled"])


@leaf(
    "talk",
    "list",
    summary="list talks from audience/talk.yaml",
    task="0004",
    configure=_configure_list,
    effects=Effects(
        description="Reads presentations.toml and every audience/talk.yaml."
    ),
)
def talk_list(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    talks, invalid = [], []
    for t in repo.talks():
        probe = Result(command="probe")
        data = load_talk(probe, t)
        if data is None:
            invalid.append({"folder": t.name, "error": probe.errors[0]["message"]})
            continue
        if ns.status and data["status"] != ns.status:
            continue
        talks.append(_summary(t, data))
    for bad in invalid:
        res.warn(
            "talk_invalid",
            bad["error"],
            next=f"present schema check {bad['folder']}/{TALK_FILE.as_posix()}",
        )
    legacy = [n for n in repo.legacy if (repo.root / n).is_dir()]
    missing_legacy = [n for n in repo.legacy if not (repo.root / n).is_dir()]
    for n in missing_legacy:
        res.warn(
            "legacy_missing",
            f"[legacy] lists {n}, which is not a directory.",
            next="fix presentations.toml",
        )
    known = {t["folder"] for t in talks} | {b["folder"] for b in invalid} | set(repo.legacy)
    library = str(repo.manifest.get("library", {}).get("root", "library")).split("/")[0]
    other = sorted(p.name for p in repo.root.iterdir()
                   if p.is_dir() and p.name not in known and p.name not in ("docs", library)
                   and not p.name.startswith((".", "_")) and not ns.status)
    for name in other:
        res.warn("talk_unclassified", f"{name}/ is neither a standard-1 talk (no audience/talk.yaml) nor "
                 "listed under [legacy].", next=f"present talk new {name} … --allow-existing, or add it to [legacy]")
    res.data = {
        "repository": str(repo.root),
        "talks": talks,
        "invalid": invalid,
        "legacy": legacy,
        "unclassified": other,
    }
    for t in talks:
        res.text.append(
            f"{t['folder']:<32} {t['status']:<10} {t['date'] or '—':<11} {t['title']}"
        )
    if legacy and not ns.status:
        res.text.append(f"legacy ({len(legacy)}): {', '.join(legacy)}")
    if not talks and not legacy:
        res.text.append(
            "no talks yet: present talk new --format … --occasion … --country …"
        )
    return res


def artifact_state(art: Path) -> dict[str, Any]:
    """Light view of one artifact folder: manifest present, versions, latest (store details: task 0005)."""
    from .. import store  # local import: store is optional until task 0005 lands

    return store.summary(art)


def deliveries(talk_dir: Path) -> list[str]:
    d = talk_dir / "delivery"
    return sorted(p.name for p in d.glob("*.y*ml")) if d.is_dir() else []


def _configure_status(p):
    p.add_argument(
        "talk",
        nargs="?",
        help="talk folder; default the talk containing the working directory",
    )


@leaf(
    "talk",
    "status",
    summary="one talk's state, including delivery",
    task="0004",
    configure=_configure_status,
    effects=Effects(description="Reads one talk."),
)
def talk_status(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    talk_dir = require_talk(res, repo, ns.talk)
    if talk_dir is None:
        return res
    data = load_talk(res, talk_dir)
    if data is None:
        return res
    if data["id"] != talk_dir.name:
        res.warn(
            "id_mismatch",
            f"talk.yaml id {data['id']!r} differs from its folder {talk_dir.name!r}.",
            next=f"set id: {talk_dir.name} in {talk_dir.name}/{TALK_FILE.as_posix()}",
        )
    modules = []
    for m in data["modules"]:
        entry: dict[str, Any] = {"id": m["id"], "title": m["title"]}
        mdir = talk_dir / "modules" / m["id"]
        if not mdir.is_dir():
            res.warn(
                "module_missing",
                f"module {m['id']} is declared but modules/{m['id']}/ does not exist.",
                next=f"present script new {talk_dir.name}/{m['id']}",
            )
        for kind in ("script", "deck"):
            if m[kind]:
                entry[kind] = artifact_state(mdir / kind)
            else:
                entry[kind] = {"declared": False}
        modules.append(entry)
    recs = deliveries(talk_dir)
    date = value(data.get("date"))
    delivery: dict[str, Any] = {"records": recs}
    if data["status"] != "cancelled" and not recs and date:
        try:
            past = __import__("datetime").date.fromisoformat(date) < today()
        except ValueError:
            past = False
        if past or data["status"] == "delivered":
            delivery["missing"] = True
            res.warn(
                "delivery_missing",
                f"{talk_dir.name} was dated {date} but has no delivery record.",
                next=f"present delivery record {talk_dir.name} --date {date}",
            )
    elif data["status"] == "delivered" and not recs:
        res.warn(
            "delivery_missing",
            f"{talk_dir.name} is marked delivered but has no delivery record.",
            next=f"present delivery record {talk_dir.name}",
        )
    from .lesson import open_lessons

    open_count, lesson_total = open_lessons(talk_dir)
    res.data = {
        **_summary(talk_dir, data),
        "slot_minutes": value(data.get("slot_minutes")),
        "module_state": modules,
        "delivery": delivery,
        "lessons": {"open": open_count, "total": lesson_total},
    }
    res.text.append(f"{data['title']}  [{data['status']}]  {date or 'date TBC'}")
    for m in modules:
        parts = []
        for kind in ("script", "deck"):
            st = m[kind]
            if not st.get("declared", True):
                parts.append(f"{kind}: none")
            else:
                parts.append(
                    f"{kind}: {st.get('latest') or ('started' if st.get('exists') else 'not started')}"
                )
        res.text.append(f"  {m['id']:<24} " + "  ".join(parts))
    res.text.append(f"  delivery records: {len(recs)}")
    res.text.append(f"  lessons: {open_count} open of {lesson_total}"
                    + (f"  → present lesson list {talk_dir.name} --open" if open_count else ""))
    return res


# --------------------------------------------------------------------------- readme


def replace_block(text: str, start: str, end: str, block: str) -> str | None:
    """Replace start..end (inclusive) with block; None when the markers are absent or malformed."""
    i, j = text.find(start), text.find(end)
    if i < 0 or j < 0 or j < i or text.count(start) != 1 or text.count(end) != 1:
        return None
    return text[:i] + block + text[j + len(end) :]


def talks_table(repo: Repo) -> str:
    lines = [
        TABLE_START,
        "| Talk | Date | Status | Modules |",
        "| --- | --- | --- | --- |",
    ]
    for t in repo.talks():
        probe = Result(command="probe")
        data = load_talk(probe, t)
        if data is None:
            lines.append(f"| [`{t.name}`]({t.name}/) | — | invalid talk.yaml | — |")
            continue
        lines.append(
            f"| [`{t.name}`]({t.name}/) — {data['title']} | {value(data.get('date')) or 'TBC'} | "
            f"{data['status']} | {len(data['modules'])} |"
        )
    lines += ["", "_Standard-1 talks, generated by `present talk readme`._", TABLE_END]
    return "\n".join(lines)


def _configure_readme(p):
    p.add_argument("talk", nargs="?", help="one talk; default every standard-1 talk")
    p.add_argument(
        "--check",
        action="store_true",
        help="report drift without writing (exit 1 on drift)",
    )


@leaf(
    "talk",
    "readme",
    summary="regenerate README headers and the talk table",
    task="0004",
    configure=_configure_readme,
    effects=Effects(
        writes=True,
        description="Rewrites only the marked generated blocks of README.md files.",
    ),
)
def talk_readme(ns, res: Result) -> Result:
    repo = require_repo(res)
    if repo is None:
        return res
    targets = [require_talk(res, repo, ns.talk)] if ns.talk else repo.talks()
    if ns.talk and targets[0] is None:
        return res
    changed, unchanged, unmarked = [], [], []
    plans: list[tuple[Path, str]] = []
    for t in targets:
        data = load_talk(res, t)
        if data is None:
            return res
        readme = t / "README.md"
        text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        new = replace_block(text, HEADER_START, HEADER_END, header_block(data))
        if new is None:
            unmarked.append(
                repo.rel(readme) if readme.exists() else f"{t.name}/README.md"
            )
            continue
        (changed if new != text else unchanged).append(repo.rel(readme))
        if new != text:
            plans.append((readme, new))
    if not ns.talk:
        root_readme = repo.root / "README.md"
        text = root_readme.read_text(encoding="utf-8") if root_readme.is_file() else ""
        new = replace_block(text, TABLE_START, TABLE_END, talks_table(repo))
        if new is None:
            unmarked.append("README.md")
        else:
            (changed if new != text else unchanged).append("README.md")
            if new != text:
                plans.append((root_readme, new))
    for u in unmarked:
        res.warn(
            "markers_missing",
            f"{u}: no generated block markers; left untouched.",
            next=f"add {HEADER_START if u != 'README.md' else TABLE_START} … end markers where the block belongs",
        )
    res.data = {
        "changed": changed,
        "unchanged": unchanged,
        "unmarked": unmarked,
        "check": ns.check,
    }
    if ns.check:
        res.text.append(
            f"{len(changed)} README block(s) out of date"
            if changed
            else "README blocks up to date"
        )
        if changed:
            return res.error(
                "readme_drift",
                f"out of date: {', '.join(changed)}",
                repairable=True,
                next="present talk readme",
            )
        return res
    for path, new in plans:
        tmp = path.with_name(f".{path.name}.present-tmp")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, path)
    res.text.append(
        f"updated {len(changed)} README block(s); {len(unchanged)} already current"
    )
    return res
