"""Portfolio index (task 0009): derive the per-project status view.

`visuals index` derives, from the store on disk, the state that audit 0001
(F5, F6) found maintained by hand and drifting: the status column in the
corpus's VISUALS-BRIEF.md and the state prose in HANDOFF.md. It is DERIVED,
never hand-maintained, and it reads none of that prose — replacing the
hand-maintenance is the point.

What it is NOT is as load-bearing as what it is: an index that ranks, scores,
or grades visuals would violate ADR 0004 (no command ranks designs) and carry
an aesthetic opinion this skill does not own. Every column here is mechanical
state — what exists, at which version, when rendered, on what inputs, and
whether a consumer manifest references it. A "quality score" column is a
defect in this skill, not a feature.

Staleness is computed from CONTENT, never from mtime. Three instruments,
each anchored in content the receipt already records:

1. theme — the receipt's `theme.tokens_digest` against a fresh re-resolution
   (the same canonical digest the render receipt records);
2. inputs — every file under the visual's `source*/` directories, compared
   against the git commit the receipt records, trusted ONLY when the receipt
   also records that the render ran on a clean worktree (a dirty worktree
   means the commit does not anchor the rendered inputs). Blob hashes are
   content addresses: moved mtimes with identical content stay fresh, and a
   changed file is named. `GIT_OPTIONAL_LOCKS=0` keeps git from writing the
   index — the command is read-only (criterion 6);
3. artifact drift — the receipt's per-frame sha256 against the delivered
   bytes (an immutable version modified after render).

When no content baseline exists — receipts that record no commit anchor, no
theme digest, and no frame hashes, which is every receipt in the reference
corpus today (zero-commit repository, audit F10) — staleness is reported as
`unknown` with the reason named. `unknown` is a legitimate verdict, not a
failure: it means "no content baseline exists to check against", and on a
corpus of uncommitted work it is the honest majority answer. Anomalies are
rows with their cause named, never omissions and never exit codes: the four
ADR 0004 blocking conditions are `validate`'s to gate, and an index that
exited non-zero on them would be a fifth gate by the back door.

Capability domain, not a command handler: `index_cmd.py` imports this module;
it never imports a handler, the dispatcher, or another adapter. Imports from
`validate.py` are limited to the names its owner pinned stable for this round
(seam contract): `discover_visuals`, `run_validation`, `visual_slug`, and —
promoted on request for the consumer column — `consumer_manifest_refs`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import store
import validate as validate_module
import visual_style

# Exit codes (architecture doc, "Command surface"). A completed run is 0:
# anomalies are data. 1 is deliberately absent from this command — gating the
# four ADR 0004 blocking conditions is `validate`'s job, and an index exit
# code would be a fifth gate by the back door.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3


class IndexBuildError(Exception):
    """A condition that prevents the index from running at all. The message
    names the cause; never a traceback."""


# ---------------------------------------------------------------------------
# staleness — content-based; mtime is never consulted
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangedInput:
    """One input whose content differs from what the current receipt records.
    `kind` classifies it: master | manifest | data | other | theme | artifact."""

    path: str
    kind: str

    def to_dict(self) -> dict:
        return {"path": self.path, "kind": self.kind}


@dataclass(frozen=True)
class Staleness:
    """The staleness verdict for one visual's current version.

    state is one of:
      no-renders  — no version rendered yet; nothing to be stale;
      fresh       — every checkable input verified unchanged against the
                    receipt's recorded content baseline;
      stale       — at least one changed input, each NAMED;
      unknown     — no content baseline exists (the receipt records no commit
                    anchor, theme digest, or frame hashes). A legitimate
                    verdict, not a failure: most receipts in an uncommitted
                    tree carry it (audit F10).
    """

    state: str
    reason: str
    changed_inputs: tuple[ChangedInput, ...] = ()

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "reason": self.reason,
            "changed_inputs": [c.to_dict() for c in self.changed_inputs],
        }


def _classify_input(src_dir: Path, path: Path) -> str:
    """A human kind for one input file, so 'which input changed' is readable."""
    rel = path.relative_to(src_dir)
    if rel.name == "frames.txt":
        return "manifest"
    if rel.suffix.lower() == ".html" and len(rel.parts) == 1:
        return "master"
    if rel.parts[0] == "data":
        return "data"
    return "other"


def _source_dirs(visual_dir: Path) -> list[Path]:
    """The visual's `source*/` directories, stable order."""
    return sorted(d for d in visual_dir.glob("source*") if d.is_dir())


def _input_files(visual_dir: Path) -> list[tuple[Path, str, Path]]:
    """Every file under the visual's `source*/` directories as
    (path, kind, source_dir). Flat masters, redesign generations
    (`source-v2/`), manifests, and data directories are all inputs; a frozen
    upstream reference copy under `source/upstream-*/` is one too — if its
    content changed, the render inputs changed. Files outside `source*/` are
    not render inputs as far as the store records, and are not claimed."""
    inputs: list[tuple[Path, str, Path]] = []
    for src in _source_dirs(visual_dir):
        for path in sorted(src.rglob("*")):
            if path.is_file():
                inputs.append((path, _classify_input(src, path), src))
    return inputs


def _blob_sha1(path: Path) -> str | None:
    """The git blob hash of a file's current content, computed directly.

    Git blob hashes are content addresses (sha1 over the canonical blob
    header plus the bytes), computable with the stdlib — no subprocess per
    file, and identical to what `git ls-tree` reports for the same content."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\x00" + data).hexdigest()


def _tree_blobs(visual_dir: Path, commit: str, rel_dirs: list[str]) -> dict[str, str] | str:
    """Blob hashes for every file under `rel_dirs` (relative to the visual)
    at git commit `commit`. Returns a {relpath: blob_sha} map, or an error
    string when no baseline exists (not a repository, commit unknown). Runs
    with GIT_OPTIONAL_LOCKS=0 and only ever reads: ls-tree writes nothing,
    including no index refresh."""
    git = shutil.which("git")
    if git is None:
        return "git is not installed"
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    proc = subprocess.run(
        [git, "-C", str(visual_dir), "ls-tree", "-r", "-z", commit,
         "--", *rel_dirs],
        capture_output=True, env=env, timeout=60,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        return detail[0] if detail else f"git ls-tree failed (rc {proc.returncode})"
    blobs: dict[str, str] = {}
    for entry in proc.stdout.split(b"\x00"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split()
        if len(parts) < 3 or parts[1] != b"blob":
            continue
        blobs[path.decode("utf-8", "replace")] = parts[2].decode()
    return blobs


def _theme_digest(config_resolved) -> tuple[str, str] | tuple[None, None]:
    """The current resolved theme's tokens digest, mirroring the canonical
    form the render receipt records (render.py `_resolve_theme_receipt`:
    sha256 over json.dumps(tokens, sort_keys=True, default=str)). The two
    formulas MUST stay in lockstep — a divergence would report every theme as
    changed. Flagged to the coordinator for promotion into a shared helper;
    neither theme.py nor render.py is this round's file to edit."""
    try:
        import theme  # noqa: PLC0415  (contract layer, consumed lazily)
        resolved = theme.resolve_theme(config_resolved.theme, config_resolved)
    except Exception:
        return (None, None)
    tokens_json = json.dumps(resolved.tokens, sort_keys=True, default=str)
    digest = hashlib.sha256(tokens_json.encode()).hexdigest()
    return digest, resolved.name


def staleness_of(
    visual_dir: Path,
    current_version: str | None,
    receipt: dict | None,
    config_resolved,
) -> Staleness:
    """The staleness verdict for one visual's current version. Content-based;
    mtime is never consulted (a touched file with identical content is not
    stale). See the module docstring for the three instruments and the honest
    `unknown`."""
    if current_version is None:
        return Staleness(
            "no-renders",
            "no version rendered yet — staleness is defined against a "
            "receipt, and none exists",
        )
    if receipt is None:
        return Staleness(
            "unknown",
            f"no readable receipt.json in {current_version} — no content "
            "baseline to check against",
        )

    changed: list[ChangedInput] = []
    notes: list[str] = []
    inputs_checked = False

    # --- instrument 2: git-anchored inputs (the primary one) ---------------
    repository = receipt.get("repository") or {}
    commit = repository.get("commit") or receipt.get("commit")
    worktree = repository.get("worktree") or receipt.get("worktree")
    if not commit or commit == "uncommitted":
        notes.append(
            "receipt records no commit anchor (commit 'uncommitted' or "
            "absent) — master and data inputs not comparable (zero-commit "
            "repository, audit F10)"
        )
    elif worktree != "clean":
        notes.append(
            f"render ran on a {worktree!r} worktree, so the recorded commit "
            "does not anchor the rendered inputs"
        )
    else:
        rel_dirs = [d.name for d in _source_dirs(visual_dir)]
        blobs = _tree_blobs(visual_dir, commit, rel_dirs)
        if isinstance(blobs, str):
            notes.append(f"git baseline unavailable: {blobs}")
        else:
            current: dict[str, tuple[str, str]] = {}
            for path, _kind, src in _input_files(visual_dir):
                rel = path.relative_to(visual_dir).as_posix()
                current[rel] = (_blob_sha1(path), _classify_input(src, path))
            for rel in sorted(set(blobs) | set(current)):
                if rel not in current:
                    changed.append(ChangedInput(f"{rel} (deleted)", "other"))
                elif rel not in blobs:
                    changed.append(
                        ChangedInput(f"{rel} (added since render)", current[rel][1]))
                else:
                    sha, kind = current[rel]
                    if sha != blobs[rel]:
                        changed.append(ChangedInput(rel, kind))
            inputs_checked = True

    # --- instrument 1: theme digest ----------------------------------------
    digest = (receipt.get("theme") or {}).get("tokens_digest")
    if digest:
        current_digest, _name = _theme_digest(config_resolved)
        if current_digest is None:
            notes.append("receipt records a theme digest but the theme did "
                         "not re-resolve — theme comparability unknown")
        elif current_digest != digest:
            changed.append(ChangedInput(
                "resolved theme (tokens digest differs from the receipt)",
                "theme"))
        else:
            notes.append("theme tokens digest matches the receipt")
    else:
        notes.append("receipt records no theme tokens digest — theme not "
                     "comparable (legacy receipt)")

    # --- instrument 3: artifact drift ---------------------------------------
    frames = [f for f in (receipt.get("frames") or []) if isinstance(f, dict)]
    hashed = [f for f in frames if f.get("sha256")]
    if hashed:
        version_dir = visual_dir / current_version
        for f in hashed:
            path = version_dir / str(f["name"])
            if not path.is_file():
                continue  # a missing frame is store-integrity's finding, not staleness
            if store.sha256_file(path) != f["sha256"]:
                changed.append(ChangedInput(
                    f"{current_version}/{f['name']} (content hash no longer "
                    "matches the receipt — the immutable version was modified "
                    "after render)", "artifact"))
    else:
        notes.append("receipt records no per-frame content hashes — artifact "
                     "drift not comparable (legacy receipt)")

    if changed:
        reason = "inputs differ from what the receipt records"
        if notes:
            reason += "; " + "; ".join(notes)
        return Staleness("stale", reason, tuple(changed))
    if inputs_checked:
        reason = "all recorded inputs verified unchanged against the receipt's commit"
        if notes:
            reason += "; " + "; ".join(notes)
        return Staleness("fresh", reason)
    return Staleness("unknown", "no content baseline: " + "; ".join(notes))


# ---------------------------------------------------------------------------
# rows and the report
# ---------------------------------------------------------------------------

_LATEST_CAUSE_JOIN = (
    "consumers import latest/ only, so the join is silently broken"
)


def _latest_state(
    vdir: Path, versions: tuple[str, ...]
) -> tuple[str, str | None, str | None, str | None]:
    """(latest_status, latest_target, current_version, cause) for one visual.

    Anomalies are recorded with their cause, never omitted (criterion 3)."""
    if not versions:
        return ("no-versions", None, None,
                "never rendered — no version directories exist")
    link = vdir / "latest"
    if not link.exists() and not link.is_symlink():
        return ("absent", None, None,
                f"no `latest`; versions exist: {', '.join(versions)} — "
                + _LATEST_CAUSE_JOIN)
    if link.is_symlink() and not link.exists():
        target = os.readlink(link)
        return ("dangling", target, None,
                f"`latest` dangles: points at {target!r}, which does not "
                f"exist — " + _LATEST_CAUSE_JOIN)
    target = os.readlink(link) if link.is_symlink() else "latest"
    if not store.VERSION_RE.match(target):
        return ("resolving", target, None,
                f"`latest` points at {target!r}, which is not a vX.Y.Z "
                "version directory")
    return ("resolving", target, target, None)


def _frame_count(vdir: Path, current_version: str | None) -> int:
    """Delivered frames in the current version, counted on disk (criterion 1:
    matching what is on disk). The contact sheet is a diagnostic, not a
    frame; previews live under previews/ and are not matched by the top-level
    glob."""
    if current_version is None:
        return 0
    return sum(
        1 for p in (vdir / current_version).glob("*.png")
        if p.name != "contact-sheet.png"
    )


@dataclass
class Row:
    """One visual's derived state. Everything here is mechanical state;
    nothing ranks, scores, or grades (ADR 0004)."""

    slug: str
    join_slug: str  # slug as the consumer manifest names it (its visuals base)
    path: str  # project-root-relative
    layout: str  # "top" | "nested"
    style: str | None  # declared in this visual's BRIEF.md, never inferred
    versions: tuple[str, ...]
    latest_status: str  # "resolving" | "dangling" | "absent" | "no-versions"
    latest_target: str | None
    current_version: str | None
    frames: int
    rendered_at: str | None
    staleness: Staleness
    blocking_findings: int
    advisory_findings: int
    consumer_referenced: bool
    cause: str | None = None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "join_slug": self.join_slug,
            "path": self.path,
            "layout": self.layout,
            "style": self.style,
            "versions": list(self.versions),
            "latest_status": self.latest_status,
            "latest_target": self.latest_target,
            "current_version": self.current_version,
            "frames": self.frames,
            "rendered_at": self.rendered_at,
            "staleness": self.staleness.to_dict(),
            "findings": {
                "blocking": self.blocking_findings,
                "advisory": self.advisory_findings,
            },
            "consumer_referenced": self.consumer_referenced,
            "cause": self.cause,
        }


@dataclass
class IndexReport:
    """Everything one index run derived, plus the consumer join in both
    directions (criterion 4: no separate command needed)."""

    root: Path
    rows: list[Row] = field(default_factory=list)
    manifest_path: Path | None = None
    manifest_references: tuple[str, ...] = ()
    manifest_unreadable: str | None = None
    blocking_findings: int = 0
    advisory_findings: int = 0

    @property
    def anomalous(self) -> list[Row]:
        return [r for r in self.rows if r.cause]

    def _dangling(self) -> list[str]:
        """Manifest references naming no visual on disk (audit F6 direction 1)."""
        on_disk = {r.join_slug for r in self.rows}
        return sorted(ref for ref in self.manifest_references if ref not in on_disk)

    def _unreferenced(self) -> list[str]:
        """Built visuals with a resolving `latest` no entry references
        (audit F6 direction 2). The slugs are the manifest's own names for
        them (relative to its visuals base), not the project-root form."""
        return [
            r.join_slug for r in self.rows
            if r.latest_status == "resolving" and r.join_slug not in self.manifest_references
        ]

    def to_json_dict(self) -> dict:
        return {
            "command": "index",
            "schema_version": 1,
            "root": str(self.root),
            "visuals": [r.to_dict() for r in self.rows],
            "consumer_manifest": {
                "path": str(self.manifest_path) if self.manifest_path else None,
                "references": list(self.manifest_references),
                "dangling": self._dangling(),
                "unreferenced": self._unreferenced(),
                "unreadable": self.manifest_unreadable,
            },
            "summary": {
                "visuals": len(self.rows),
                "with_renders": sum(1 for r in self.rows if r.current_version),
                "stale": sum(1 for r in self.rows if r.staleness.state == "stale"),
                "fresh": sum(1 for r in self.rows if r.staleness.state == "fresh"),
                "staleness_unknown": sum(
                    1 for r in self.rows if r.staleness.state == "unknown"),
                "anomalous": len(self.anomalous),
                "blocking_findings": self.blocking_findings,
                "advisory_findings": self.advisory_findings,
            },
        }

    def human(self) -> str:
        lines = [
            f"visuals index — {self.root}",
            f"visuals: {len(self.rows)}; with renders: "
            f"{sum(1 for r in self.rows if r.current_version)}; nested "
            f"families: {sum(1 for r in self.rows if r.layout == 'nested')}",
        ]
        if self.rows:
            width = max(len(r.slug) for r in self.rows)
            lines.append("")
            header = (
                f"{'visual':<{width}}  {'style':<18} {'version':<9} {'frames':>6} "
                f"{'staleness':<10} {'consumer':<8} {'findings':>9}"
            )
            lines.append(header)
            lines.append("-" * len(header))
            for r in self.rows:
                version = r.current_version or "-"
                frames = str(r.frames) if r.current_version else "-"
                consumer = (
                    "yes" if r.consumer_referenced else
                    "no" if r.consumer_referenced is False else "n/a")
                findings = f"{r.blocking_findings}B/{r.advisory_findings}A"
                slug = r.slug + (" (nested)" if r.layout == "nested" else "")
                lines.append(
                    f"{slug:<{width + len(' (nested)')}}  {(r.style or '-'):<18} {version:<9} {frames:>6} "
                    f"{r.staleness.state:<10} {consumer:<8} {findings:>9}"
                )
        else:
            lines.append("no visuals found — an adopted project with no store "
                         "yet; an empty set, not a failure")
        if self.anomalous:
            lines.append("")
            lines.append("anomalies (rows above, with their cause — never omitted, "
                         "never an exit code):")
            lines.extend(f"  {r.slug}: {r.cause}" for r in self.anomalous)
        stale = [r for r in self.rows if r.staleness.state == "stale"]
        if stale:
            lines.append("")
            lines.append("stale (named inputs changed since the current render):")
            for r in stale:
                named = ", ".join(
                    f"{c.kind}: {c.path}" for c in r.staleness.changed_inputs)
                lines.append(f"  {r.slug}: {named}")
        unknown = [r for r in self.rows if r.staleness.state == "unknown"]
        if unknown:
            lines.append("")
            lines.append(
                "staleness unknown (no content baseline — a legitimate verdict, "
                "not a failure; most receipts in an uncommitted tree carry it):")
            seen: dict[str, list[str]] = {}
            for r in unknown:
                seen.setdefault(r.staleness.reason, []).append(r.slug)
            for reason, slugs in seen.items():
                shown = ", ".join(slugs[:3])
                if len(slugs) > 3:
                    shown += f", and {len(slugs) - 3} more (see --json for the full list)"
                lines.append(f"  {len(slugs)} visual(s) ({shown}): {reason}")
        if self.manifest_path is not None:
            lines.append("")
            lines.append(
                f"consumer manifest: {self.manifest_path.name} — "
                f"{len(self.manifest_references)} visual(s) referenced")
            if self.manifest_unreadable:
                lines.append(f"  unreadable: {self.manifest_unreadable}")
            dangling = self._dangling()
            if dangling:
                lines.append("  referenced but not on disk (F6 direction 1): "
                             + ", ".join(dangling))
            unref = self._unreferenced()
            if unref:
                lines.append("  built but unreferenced (F6 direction 2): "
                             + ", ".join(unref))
        lines.append("")
        lines.append(
            "staleness legend: fresh = recorded inputs verified unchanged; "
            "STALE = named inputs changed since the current render; unknown = "
            "no content baseline exists to check against (the receipt records "
            "no commit anchor, theme digest, or frame hashes); no-renders = no "
            "version rendered yet. mtimes are never consulted.")
        lines.append(
            "nested = a visual inside a family directory (e.g. "
            "hm-mechanism-briefing/demos-mechanism), discovered by walking the "
            "tree; the slug carries its path.")
        lines.append(
            "read-only: derived from the store on disk; ranks, scores and "
            "grades nothing (ADR 0004).")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def build_index(config_resolved) -> IndexReport:
    """Derive the portfolio index for an adopted project. Read-only."""
    root: Path = config_resolved.root
    visual_dirs = validate_module.discover_visuals(root)

    # One severity implementation: the per-visual blocking/advisory counts come
    # from validate's own machinery (its owner pinned `run_validation` stable
    # for this round), bucketed by the slug convention its findings use.
    validation = validate_module.run_validation(config_resolved, slug=None)

    manifest_path = config_resolved.registry_paths["consumer_manifest"]
    refs = validate_module.consumer_manifest_refs(manifest_path)
    # The manifest's refs name slugs relative to ITS visuals/ base, not the
    # project root — the join runs in that namespace, the row slug in the
    # root-relative one that validate's findings use. The base helper is
    # validate's (promoted public alias of its private _visuals_base).
    base = validate_module.visuals_base(manifest_path, root)

    report = IndexReport(
        root=root, manifest_path=manifest_path,
        manifest_references=tuple(refs),
    )
    report.blocking_findings = len(validation.blocking)
    report.advisory_findings = len(validation.advisory)
    if manifest_path.is_file():
        try:
            manifest_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report.manifest_unreadable = str(exc)

    for vdir in visual_dirs:
        report.rows.append(
            _row_for(vdir, root, base, refs, validation, config_resolved))
    report.rows.sort(key=lambda r: r.slug)
    return report


def receipt_of(version_dir: Path) -> dict | None:
    """Parse one version's receipt, or None when absent/unreadable."""
    path = version_dir / "receipt.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _row_for(
    vdir: Path,
    root: Path,
    base: Path,
    refs: list[str],
    validation,
    config_resolved,
) -> Row:
    slug = validate_module.visual_slug(vdir, root)
    join_slug = validate_module.visual_slug(vdir, base)
    versions = store.existing_versions(vdir)

    latest_status, latest_target, current_version, cause = _latest_state(vdir, versions)

    receipt = receipt_of(vdir / current_version) if current_version else None
    staleness = staleness_of(vdir, current_version, receipt, config_resolved)

    blocking = advisory = 0
    for f in validation.findings:
        if (f.location == slug or f.location.startswith(slug + "/")
                or f.location.startswith(slug + ":")):
            if f.severity == "blocking":
                blocking += 1
            else:
                advisory += 1

    return Row(
        slug=slug,
        join_slug=join_slug,
        path=vdir.resolve().relative_to(root.resolve()).as_posix(),
        layout="nested" if "/" in join_slug else "top",
        style=visual_style.declared_style(vdir)[0],
        versions=versions,
        latest_status=latest_status,
        latest_target=latest_target,
        current_version=current_version,
        frames=_frame_count(vdir, current_version),
        rendered_at=(receipt or {}).get("rendered_at"),
        staleness=staleness,
        blocking_findings=blocking,
        advisory_findings=advisory,
        consumer_referenced=join_slug in refs,
        cause=cause,
    )
