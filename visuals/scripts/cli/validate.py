"""Contract validation (task 0007): the four blocking conditions, the advisory set.

`visuals validate [<slug>]` walks an adopted project's artifact store, source
masters, source registry, and consumer manifest, and reports findings in two
categories fixed by ADR 0004:

- **Blocking** — exactly four conditions, each a correctness defect that makes
  the artifact broken as an artifact regardless of taste. The set is enumerated
  in `BLOCKING_CONDITIONS`; the drift-guard test
  (`tests/test_validate.py::test_blocking_set_is_exactly_the_four_adr_conditions`)
  fails if its size changes, because ADDING A FIFTH BLOCKING CONDITION REQUIRES
  AN ADR (ADR 0004), not a decision in this file.
- **Advisory** — every other finding: a severity, a location, and a remedy, and
  never an effect on the exit code. Which advisory checks run at all is the
  project's choice, declared in `visuals.toml` `advisory_checks`; the report
  names the checks that were NOT run, so a quiet report is distinguishable from
  a narrow one (criterion 3).

The corpus-facing advisory checks port the reference corpus's own
`visuals/validate.py` (audit 0001 F2: a validator that exists but is not wired
in, and whose single-level glob misses nested families and alternate masters).
Coverage here is deliberately wider: every master a manifest references plus
every HTML file directly inside a `source*/` directory of a visual — which is
what covers `incidents-only.html`, `combined.html`, and `source-v2/index.html`.

Capability domain, not a command handler: `validate_cmd.py` imports this
module; it never imports a handler, the dispatcher, or another adapter
(architecture doc, "Dependency direction"). Read-only: validates, never fixes.

The clipped-content instrument is structural for now — a delivered frame's
pixel dimensions against the canvas its own receipt declares — because the
scene report that would measure rendered geometry does not exist until tasks
0011/0012, which upgrade this check to measured geometry. No
measurement-derived findings are invented here (task 0007 non-goal).
"""

from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import config as config_module
import discovery  # capability domain: one definition of what a visual is
import sources  # capability domain: the source-registry contract lives there, once
import store
import visual_style

# ---------------------------------------------------------------------------
# The blocking set — the ADR 0004 contract. Do not extend without an ADR.
# ---------------------------------------------------------------------------

#: Exactly the four conditions that exit non-zero, skill-wide. The ORDER and
#: the NAMES are part of the contract the drift guard pins.
BLOCKING_CONDITIONS = (
    "clipped-content",  # delivered frame is not the canvas its receipt declares
    "missing-latest",  # no `latest`, or one that dangles
    "missing-receipt",  # a version directory with no receipt.json
    "malformed-name",  # the `.png.png` class of defect (audit F5)
)

#: The advisory checks this build can run. A project selects from this
#: vocabulary in its `visuals.toml`; anything else in the config is reported
#: as an advisory finding against the config, never silently ignored.
ADVISORY_CHECKS = (
    "consumer-join",
    "master-includes",
    "master-slide-geometry",
    "master-source-credit",
    "master-title-ownership",
    "source-registry",
    "store-integrity",
)

#: Project-wide checks: they read the project's registries, not one visual's
#: store, so a slug-scoped run does not execute them (and says so).
PROJECT_WIDE_CHECKS = ("consumer-join", "source-registry")

#: Exit codes (architecture doc, "Command surface").
EXIT_OK = 0
EXIT_BLOCKING = 1
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3


class ValidateError(Exception):
    """A condition that prevents validation from running at all. The message
    names the cause; never a traceback."""


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One reported finding. `condition` is the blocking condition or advisory
    check that produced it; `severity` is 'blocking' for the four ADR 0004
    conditions and otherwise 'high' | 'medium' | 'low'. The message ALWAYS
    names what would make it pass — a finding a reader cannot act on is a
    defect in this command (criterion 8), so every message carries a
    'to pass:' clause. The test suite enforces that marker."""

    condition: str
    severity: str  # "blocking" | "high" | "medium" | "low"
    location: str  # project-root-relative path or slug-scoped anchor
    message: str

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "severity": self.severity,
            "location": self.location,
            "message": self.message,
        }


@dataclass
class NotRun:
    """An advisory check that did not run, and why (criterion 3)."""

    check: str
    reason: str

    def to_dict(self) -> dict:
        return {"check": self.check, "reason": self.reason}


@dataclass
class Report:
    """Everything one validation run found, plus what it did not check."""

    root: Path
    scope: str  # "project" or "visual <slug>"
    visuals_scanned: tuple[str, ...]
    masters_scanned: int
    registry_entries: int
    findings: list[Finding] = field(default_factory=list)
    not_run: list[NotRun] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "blocking"]

    @property
    def advisory(self) -> list[Finding]:
        return [f for f in self.findings if f.severity != "blocking"]

    @property
    def exit_code(self) -> int:
        """ADR 0004: only the four blocking conditions affect the exit code.
        Fifty advisory findings and no blocking condition is exit 0."""
        return EXIT_BLOCKING if self.blocking else EXIT_OK

    def findings_by_location(self) -> dict[str, list[dict]]:
        """Criterion 7: findings keyed by location, for another tool to consume."""
        keyed: dict[str, list[dict]] = {}
        for f in sorted(self.findings, key=lambda f: (f.location, f.condition)):
            keyed.setdefault(f.location, []).append(f.to_dict())
        return keyed

    def to_json_dict(self) -> dict:
        return {
            "command": "validate",
            "schema_version": 1,
            "root": str(self.root),
            "scope": self.scope,
            "visuals_scanned": list(self.visuals_scanned),
            "masters_scanned": self.masters_scanned,
            "registry_entries": self.registry_entries,
            "exit_code": self.exit_code,
            "blocking_conditions": list(BLOCKING_CONDITIONS),
            "findings": self.findings_by_location(),
            "advisory_checks_not_run": [n.to_dict() for n in self.not_run],
            "summary": {"blocking": len(self.blocking), "advisory": len(self.advisory)},
        }

    def human(self) -> str:
        lines = [
            f"visuals validate — {self.root}",
            f"scope: {self.scope}; visuals: {len(self.visuals_scanned)}; "
            f"masters: {self.masters_scanned}; "
            f"source-registry entries: {self.registry_entries if 'source-registry' not in {n.check for n in self.not_run} else 'not checked'}",
        ]
        if self.blocking:
            lines.append(
                f"BLOCKING — {len(self.blocking)} finding(s), exit "
                f"{EXIT_BLOCKING}: broken as an artifact, independent of taste "
                "(ADR 0004):"
            )
            lines.extend(
                f"  [{f.condition}] {f.location}: {f.message}" for f in self.blocking
            )
        else:
            lines.append("BLOCKING — none of the four ADR 0004 conditions fired")
        if self.advisory:
            lines.append(
                f"advisory — {len(self.advisory)} finding(s), exit code "
                "unaffected (ADR 0004):"
            )
            lines.extend(
                f"  [{f.condition}] {f.location}: {f.message}" for f in self.advisory
            )
        if self.not_run:
            lines.append("advisory checks NOT run (a quiet report is not a clean one):")
            lines.extend(f"  {n.check} — {n.reason}" for n in self.not_run)
        run = sorted(set(ADVISORY_CHECKS) - {n.check for n in self.not_run})
        lines.append(
            f"summary: {len(self.blocking)} blocking, {len(self.advisory)} advisory; "
            "advisory checks run: "
            + (", ".join(run) or "(none)")
            + f"; exit {self.exit_code}"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# visual discovery — a visual is a directory that holds a store
# ---------------------------------------------------------------------------

#: Directory names never walked into: scaffold exemplars and deliberate
#: archives are not the project's live artifact store (see discover_visuals).
# Visual discovery lives in its own capability domain (task 0017 D2): `render`
# must resolve a slug to the SAME set of directories this module reports on, and
# two walks would drift. Re-exported here because these names were part of this
# module's surface before the extraction.
NON_VISUAL_DIR_NAMES = discovery.NON_VISUAL_DIR_NAMES
is_visual_dir = discovery.is_visual_dir
discover_visuals = discovery.discover_visuals


def masters_of(visual_dir: Path) -> tuple[Path, ...]:
    """The HTML masters of one visual, deduplicated, stable order.

    Two sources, so the corpus's alternate masters cannot escape (audit F6):

    1. every .html file DIRECTLY inside a `source*` directory of the visual —
       `source/`, and redesign generations like `source-v2/`. Flat, not
       recursive: frozen upstream reference copies live in their own
       subdirectories (`source/upstream-v2.2.0/`) and are deliberately not
       house masters.
    2. every .html file a frame manifest references — the render authority.
    """
    found: dict[str, Path] = {}
    for src_dir in sorted(visual_dir.glob("source*")):
        if not src_dir.is_dir():
            continue
        for html in sorted(src_dir.glob("*.html")):
            # keyed by path, not name: source-v2/index.html must not shadow
            # source/index.html — they are different masters
            found.setdefault(str(html.relative_to(visual_dir)), html)
    for manifest in sorted(visual_dir.glob("source*/frames.txt")):
        for url in _manifest_urls(manifest):
            candidate = (manifest.parent / url).resolve()
            if candidate.suffix.lower() == ".html" and candidate.is_file():
                found.setdefault(str(candidate.relative_to(visual_dir)), candidate)
    return tuple(found.values())


def missing_manifest_masters(visual_dir: Path) -> tuple[str, ...]:
    """HTML masters a frame manifest references that do not exist on disk —
    the render would fail loudly; validation reports it before that (advisory,
    store-integrity)."""
    missing: list[str] = []
    for manifest in sorted(visual_dir.glob("source*/frames.txt")):
        for url in _manifest_urls(manifest):
            candidate = (manifest.parent / url).resolve()
            if candidate.suffix.lower() == ".html" and not candidate.is_file():
                rel = f"{manifest.parent.name}/{url}"
                if rel not in missing:
                    missing.append(rel)
    return tuple(missing)


def _manifest_urls(manifest_path: Path) -> list[str]:
    """The URL column of a frame manifest; query strings stripped."""
    urls: list[str] = []
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return urls
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip():
            urls.append(parts[1].split("?", 1)[0].strip())
    return urls


# ---------------------------------------------------------------------------
# the four blocking conditions
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_VIEWPORT_RE = re.compile(r"(\d+)x(\d+)(?:\s*@\s*([\d.]+)x)?")


def _png_dims(path: Path) -> tuple[int, int] | None:
    """Width/height from a PNG's IHDR header, or None when not a readable PNG."""
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
    except OSError:
        return None
    if len(header) < 24 or not header.startswith(_PNG_MAGIC):
        return None
    return struct.unpack(">II", header[16:24])


def _receipt_viewport(receipt: dict) -> tuple[int, int, float] | None:
    """(width, height, scale) from a receipt's viewport string — both the
    corpus's legacy format ("1920x972 @1x") and the current renderer's."""
    match = _VIEWPORT_RE.search(str(receipt.get("viewport", "")))
    if not match:
        return None
    scale = float(match.group(3)) if match.group(3) else 1.0
    return int(match.group(1)), int(match.group(2)), scale


def store_findings(visual_dir: Path, slug: str) -> list[Finding]:
    """The store-side checks: all four blocking conditions plus the
    store-integrity advisories that need no render."""
    findings: list[Finding] = []
    versions = store.existing_versions(visual_dir)

    # Blocker 2 — missing or dangling latest. Consumers import latest/ only
    # (CONVENTIONS §6); without a resolving pointer the join is silently broken.
    if versions:
        link = visual_dir / "latest"
        if not link.exists() and not link.is_symlink():
            findings.append(
                Finding(
                    "missing-latest",
                    "blocking",
                    slug,
                    f"no `latest` in {slug} (versions exist: "
                    f"{', '.join(versions)}) — consumers import latest/ only, "
                    "so the join is silently broken; to pass: complete a "
                    "render or bump (latest is repointed only after every "
                    "frame succeeded)",
                )
            )
        elif link.is_symlink() and not link.exists():
            findings.append(
                Finding(
                    "missing-latest",
                    "blocking",
                    slug,
                    f"`latest` in {slug} dangles: points at "
                    f"{os.readlink(link)!r}, which does not exist — to pass: "
                    "repoint latest at an existing version (complete a render "
                    "or bump), or remove the stale pointer",
                )
            )

    for version in versions:
        vpath = visual_dir / version
        where = f"{slug}/{version}"

        # Blocker 3 — absent receipt: no provenance, no reproduction.
        receipt_path = vpath / "receipt.json"
        if not receipt_path.is_file():
            findings.append(
                Finding(
                    "missing-receipt",
                    "blocking",
                    where,
                    f"{where} has no receipt.json — a version directory "
                    "without a receipt has no provenance and cannot be "
                    "reproduced or attributed; to pass: re-render this version "
                    "with the current renderer, which writes a hashed receipt",
                )
            )
        else:
            findings.extend(_receipt_findings(slug, version, vpath, receipt_path))

        # Blocker 4 — malformed output name (the .png.png class, audit F5).
        for path in sorted(vpath.rglob("*")):
            if path.is_file() and path.name.lower().endswith(".png.png"):
                findings.append(
                    Finding(
                        "malformed-name",
                        "blocking",
                        f"{slug}/{version}/{path.name}",
                        f"{path.name} in {slug}/{version} carries a doubled "
                        ".png.png extension (audit F5) — it corrupts ordering "
                        "and import; to pass: re-render the version with the "
                        "extension-free basename in the manifest (the renderer "
                        "normalises manifest extensions; the shipped file keeps "
                        "the defect until re-rendered)",
                    )
                )
    return findings


def _receipt_findings(
    slug: str, version: str, vpath: Path, receipt_path: Path
) -> list[Finding]:
    """Receipt-vs-artifact checks: the clipped-content blocker plus the
    store-integrity advisories."""
    where = f"{slug}/{version}"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Finding(
                "store-integrity",
                "high",
                where,
                f"receipt.json in {slug}/{version} is unreadable ({exc}) — "
                "provenance cannot be checked; to pass: re-render this version "
                "so a valid receipt replaces it",
            )
        ]
    findings: list[Finding] = []
    viewport = _receipt_viewport(receipt)
    if viewport is None:
        findings.append(
            Finding(
                "store-integrity",
                "medium",
                where,
                f"receipt.json in {slug}/{version} declares no parseable "
                f"viewport (found {receipt.get('viewport')!r}) — the "
                "clipped-content condition cannot be evaluated for it; to "
                "pass: re-render with the current renderer, whose receipts "
                "record 'WIDTHxHEIGHT @scale'",
            )
        )
    for frame in receipt.get("frames", []):
        name = frame.get("name") if isinstance(frame, dict) else None
        if not name:
            continue
        path = vpath / str(name)
        if not path.is_file():
            findings.append(
                Finding(
                    "store-integrity",
                    "high",
                    f"{where}/{name}",
                    f"receipt in {slug}/{version} names frame {name!r} but no "
                    "such file exists in the version directory — consumers "
                    f"importing latest/{name} get nothing; to pass: re-render "
                    "the version so the receipt and the files agree",
                )
            )
            continue
        if path.stat().st_size == 0:
            findings.append(
                Finding(
                    "store-integrity",
                    "high",
                    f"{where}/{name}",
                    f"frame {name!r} in {slug}/{version} is 0 bytes — nothing "
                    "was delivered; to pass: re-render this version",
                )
            )
        if viewport is None:
            continue
        dims = _png_dims(path)
        if dims is None:
            findings.append(
                Finding(
                    "store-integrity",
                    "high",
                    f"{where}/{name}",
                    f"frame {name!r} in {slug}/{version} is not a readable PNG "
                    "— the delivered artifact cannot be verified against the "
                    "declared canvas; to pass: re-render this version",
                )
            )
            continue
        width, height = dims
        vw, vh, scale = viewport
        if width != round(vw * scale) or height != round(vh * scale):
            findings.append(
                Finding(
                    "clipped-content",
                    "blocking",
                    f"{where}/{name}",
                    f"delivered frame {name} is {width}x{height} but its "
                    f"receipt declares canvas {vw}x{vh} @{scale:g}x — content "
                    "outside the declared frame is absent from the delivered "
                    "artifact, or the receipt misdescribes it (ADR 0004 "
                    "blocker 1; measured-geometry evaluation arrives with "
                    "task 0012); to pass: re-render this version so the frame "
                    "matches the declared canvas",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# advisory: master contract (ported from the reference corpus's own validator)
# ---------------------------------------------------------------------------

#: The corpus's contract for every render master (its visuals/validate.py):
#: the shared system stylesheet and source-credit include, the visual-slide
#: geometry, exactly one source-credit element, and no renderer-owned title.
SHARED_CSS_INCLUDE = "../../_shared/visual-system.css"
SHARED_JS_INCLUDE = "../../_shared/source-credit.js"
_RENDERER_TITLE_RE = re.compile(r"<h[1-6]\b|class=[\"'][^\"']*\bkicker", re.IGNORECASE)


def master_findings(
    slug: str, html: Path, text: str, selected: set[str]
) -> list[Finding]:
    """The master-contract advisories, each with its remedy. Conditions are the
    reference corpus's own (audit F2); each runs only when the project
    selects it."""
    findings: list[Finding] = []
    location = f"{slug}: {html.name}"
    if "master-includes" in selected:
        if SHARED_CSS_INCLUDE not in text:
            findings.append(
                Finding(
                    "master-includes",
                    "high",
                    location,
                    f"missing shared visual-system.css include — "
                    f"every master carries {SHARED_CSS_INCLUDE}; to pass: link "
                    "the shared stylesheet from this master's <head>",
                )
            )
        if SHARED_JS_INCLUDE not in text:
            findings.append(
                Finding(
                    "master-includes",
                    "high",
                    location,
                    f"missing shared source-credit.js include — "
                    f"every master loads {SHARED_JS_INCLUDE}; to pass: include "
                    "the shared source-credit script",
                )
            )
    if "master-slide-geometry" in selected:
        if (
            'class="slide visual-slide"' not in text
            and 'slide.className = "visual-slide"' not in text
        ):
            findings.append(
                Finding(
                    "master-slide-geometry",
                    "high",
                    location,
                    f"slide does not adopt visual-slide geometry "
                    "— the shared geometry (safe area, footer band) is what "
                    "the canvas profile declares; to pass: mark the slide "
                    'element with class="slide visual-slide" (or set '
                    'slide.className = "visual-slide")',
                )
            )
    if "master-source-credit" in selected:
        count = text.count("<source-credit")
        if count != 1:
            findings.append(
                Finding(
                    "master-source-credit",
                    "high",
                    location,
                    f"expected exactly one source-credit element, "
                    f"found {count} — attribution is mandatory on every "
                    "delivered frame; to pass: place exactly one "
                    "<source-credit> element in the master",
                )
            )
    if "master-title-ownership" in selected:
        if _RENDERER_TITLE_RE.search(text):
            findings.append(
                Finding(
                    "master-title-ownership",
                    "high",
                    location,
                    f"visible renderer title found — the deck "
                    "owns the title, so a renderer-visible <h1>-<h6> or "
                    "kicker duplicates it; to pass: remove the renderer-"
                    "visible title and let the deck's own title band carry it",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# advisory: source registry (criterion 5)
# ---------------------------------------------------------------------------

#: The source-registry contract lives in sources.py so `visuals sources verify`
#: and this advisory layer cannot drift apart (task 0008). Re-exported here
#: because both names were part of this module's surface before the split.
REQUIRED_SOURCE_FIELDS = sources.REQUIRED_SOURCE_FIELDS
DANGEROUS_SVG = sources.DANGEROUS_SVG


def source_registry_findings(registry_path: Path) -> tuple[list[Finding], int]:
    """Validate the declared source registry. Returns (findings, entry count).

    Every rule — re-hashing each declared asset, requiring https provenance
    rather than prose, retaining the untransformed original of a transformed
    asset, and scanning SVG assets for active or external content — belongs to
    the `sources` capability domain. This function adapts its findings into this
    module's severity vocabulary and nothing more: a second implementation of
    the registry contract would be a value written in two places, which is the
    defect audit F7 records for themes.

    Severity stays advisory under ADR 0004; the caller never lets it reach the
    exit code.
    """
    raw, count = sources.verify_registry(registry_path)
    return (
        [
            Finding("source-registry", "high", finding.location, finding.message)
            for finding in raw
        ],
        count,
    )


# ---------------------------------------------------------------------------
# advisory: consumer join (criterion 4) — reconciliation in BOTH directions
# ---------------------------------------------------------------------------

_CONSUMER_REF_RE = re.compile(
    r"visuals/([A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)*)/latest"
)


def consumer_manifest_refs(manifest_path: Path) -> list[str]:
    """The visual slugs a consumer manifest references, in file order, deduplicated.

    Public because the reconciliation and any status view over it must read the
    manifest the same way; an unreadable or absent manifest yields no refs, and
    the caller reports that condition in its own vocabulary.
    """
    try:
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    refs: list[str] = []
    for match in _CONSUMER_REF_RE.finditer(text):
        slug = match.group(1).strip("/")
        if slug not in refs:
            refs.append(slug)
    return refs


def consumer_join_findings(
    manifest_path: Path, root: Path, visual_dirs: tuple[Path, ...]
) -> list[Finding]:
    """Reconcile the consumer manifest against the visuals on disk.

    Both directions (criterion 4, audit F6): a manifest entry naming a visual
    that does not exist, AND a built visual with a resolving `latest` that no
    manifest entry references. Drift is reported; the manifest's editorial
    content is not maintained here (architecture, "Consumer join")."""
    if not manifest_path.is_file():
        return [
            Finding(
                "consumer-join",
                "high",
                str(manifest_path),
                "no consumer manifest at paths.consumer_manifest — the "
                "documented join between deck and assets cannot be reconciled; "
                "to pass: point paths.consumer_manifest in visuals.toml at the "
                "manifest that references visuals/<slug>/latest",
            )
        ]
    # Probed here so an unreadable manifest is reported as its own finding:
    # consumer_manifest_refs() degrades to no refs, which would otherwise look
    # like a manifest that references nothing.
    try:
        manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [
            Finding(
                "consumer-join",
                "high",
                str(manifest_path),
                f"consumer manifest is unreadable ({exc}); to pass: fix the "
                "file or its path in visuals.toml",
            )
        ]
    # One read rule for the manifest: reconciliation and any status view over the
    # same manifest must agree on which slugs it references.
    refs = consumer_manifest_refs(manifest_path)
    base = _visuals_base(manifest_path, root)
    on_disk = {_visual_slug(vd, base): vd for vd in visual_dirs}

    findings: list[Finding] = []
    for slug in refs:
        target = base / "visuals" / slug
        if not _exists_as_visual(target):
            findings.append(
                Finding(
                    "consumer-join",
                    "high",
                    f"{manifest_path.name}: {slug}",
                    f"the consumer manifest names visuals/{slug}/latest, "
                    "which does not exist on disk — a deck row that renders "
                    "nothing (audit F6 direction 1); to pass: build the "
                    "visual, or update the manifest to the visual that "
                    "replaced it",
                )
            )
    referenced = set(refs)
    for slug, vdir in sorted(on_disk.items()):
        latest = vdir / "latest"
        if not (latest.is_symlink() and latest.exists()):
            continue  # no resolving latest: not a built, joinable visual
        if slug not in referenced:
            findings.append(
                Finding(
                    "consumer-join",
                    "medium",
                    slug,
                    f"visual {slug} has a resolving `latest` but appears "
                    "nowhere in the consumer manifest — the documented join is "
                    "stale in the other direction (audit F6 direction 2); to "
                    "pass: reference it as visuals/"
                    f"{slug}/latest from the manifest, or record its real "
                    "delivery state there",
                )
            )
    return findings


def _exists_as_visual(path: Path) -> bool:
    """True when the manifest's referenced visual directory exists on disk.
    A directory that exists but holds no visual store is still 'does not
    exist' as a visual; a directory that exists with a dangling latest is the
    blocking missing-latest condition's to name, not the join's."""
    return path.is_dir() and is_visual_dir(path)


def _visuals_base(manifest_path: Path, root: Path) -> Path:
    """The directory the manifest's `visuals/<slug>/latest` references resolve
    against: the manifest's directory, its parent, or the project root — the
    first one that actually holds a `visuals/` directory."""
    for candidate in (manifest_path.parent, manifest_path.parent.parent, root):
        if (candidate / "visuals").is_dir():
            return candidate
    return root


#: Public alias. Manifest references and on-disk visuals only join when both are
#: named against the SAME base, and that base is not the project root whenever
#: the manifest sits beside its own `visuals/` directory — which is the reference
#: corpus's layout. Any consumer of the join needs this rule, so it is part of
#: this module's surface rather than a private another module reaches into
#: (task 0009).
visuals_base = _visuals_base


def _visual_slug(visual_dir: Path, base: Path) -> str:
    """A visual's slug as the manifest would name it (relative to base; the
    leading `visuals/` is dropped so references and disk join on one form)."""
    try:
        rel = visual_dir.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        rel = visual_dir.name
    return rel.removeprefix("visuals/")


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


#: Public alias. The slug naming rule must have exactly one implementation, and
#: a status view over the same visuals needs it (task 0009), so it is part of
#: this module's surface rather than a private another module reaches into.
visual_slug = _visual_slug


def run_validation(
    config_resolved: config_module.ResolvedConfig, slug: str | None = None
) -> Report:
    """Validate an adopted project (or one visual of it). Read-only.

    The advisory set actually run is the project's own selection
    (`advisory_checks` in visuals.toml); checks not selected — or not run
    because a slug scopes the run to one visual — are named in the report
    (criterion 3). Exit code: 1 only when one of the FOUR blocking conditions
    fired; advisory findings never affect it (criterion 2, ADR 0004).
    """
    root: Path = config_resolved.root
    selected = list(config_resolved.advisory_checks)
    unknown = [name for name in selected if name not in ADVISORY_CHECKS]
    selected_set = {name for name in selected if name in ADVISORY_CHECKS}

    report = Report(
        root=root,
        scope="project" if slug is None else f"visual {slug}",
        visuals_scanned=(),
        masters_scanned=0,
        registry_entries=0,
    )

    if slug is not None:
        visual_dirs = _visuals_for_slug(root, slug)
    else:
        visual_dirs = discover_visuals(root)
    slugs = tuple(_visual_slug(v, root) for v in visual_dirs)
    report.visuals_scanned = slugs

    # --- the four blocking conditions + the per-visual advisories ----------
    for vdir, vslug in zip(visual_dirs, slugs):
        report.findings.extend(store_findings(vdir, vslug))
        style_name, style_error = visual_style.declared_style(vdir)
        if style_error:
            report.findings.append(Finding(
                "visual-style", "high", f"{vslug}/BRIEF.md",
                f"{style_error}; to pass: keep at most one style: <name> line in BRIEF.md",
            ))
        elif style_name is not None and style_name not in config_resolved.styles:
            declared = ", ".join(sorted(config_resolved.styles)) or "(none)"
            report.findings.append(Finding(
                "visual-style", "high", f"{vslug}/BRIEF.md",
                f"style {style_name!r} is not declared in visuals.toml "
                f"(declared: {declared}); to pass: declare it in the project "
                "config or change this visual's style",
            ))
        masters = masters_of(vdir)
        report.masters_scanned += len(masters)
        if "store-integrity" in selected_set:
            for rel in missing_manifest_masters(vdir):
                report.findings.append(
                    Finding(
                        "store-integrity",
                        "medium",
                        f"{vslug}: {rel}",
                        f"frame manifest references {rel}, which does not "
                        "exist on disk — the render would fail loudly; to "
                        "pass: restore the master or fix the manifest line",
                    )
                )
        master_checks = selected_set & {
            "master-includes",
            "master-slide-geometry",
            "master-source-credit",
            "master-title-ownership",
        }
        if master_checks:
            for html in masters:
                try:
                    text = html.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    report.findings.append(
                        Finding(
                            "store-integrity",
                            "high",
                            f"{vslug}: {html.name}",
                            f"master {html.name} is unreadable ({exc}) — to "
                            "pass: restore the file",
                        )
                    )
                    continue
                report.findings.extend(master_findings(vslug, html, text, selected_set))
        if "store-integrity" in selected_set:
            report.findings.extend(_store_integrity_scan(vdir, vslug))

    # --- project-wide advisory checks --------------------------------------
    if slug is None:
        if "source-registry" in selected_set:
            findings, entries = source_registry_findings(
                config_resolved.registry_paths["source_registry"]
            )
            report.findings.extend(findings)
            report.registry_entries = entries
        if "consumer-join" in selected_set:
            report.findings.extend(
                consumer_join_findings(
                    config_resolved.registry_paths["consumer_manifest"],
                    root,
                    visual_dirs,
                )
            )
    else:
        for check in PROJECT_WIDE_CHECKS:
            report.not_run.append(
                NotRun(
                    check,
                    f"project-wide check skipped: run was scoped to visual {slug!r}",
                )
            )

    # Every advisory check that did not run is named (criterion 3), whether it
    # was unselected or skipped — a quiet report must be distinguishable from
    # a narrow one.
    for name in ADVISORY_CHECKS:
        if name in selected_set:
            continue
        if slug is not None and name in PROJECT_WIDE_CHECKS:
            continue  # already reported with the slug-scoping reason
        if not any(n.check == name for n in report.not_run):
            report.not_run.append(
                NotRun(name, "not selected by project config (advisory_checks)")
            )

    # Unknown advisory check names are a defect in the CONFIG, reported
    # advisory so a typo cannot add a blocker (ADR 0004: the four are fixed).
    for name in unknown:
        report.findings.append(
            Finding(
                "config-advisory-set",
                "high",
                str(config_resolved.path),
                f"advisory_checks names {name!r}, which this build does not "
                f"know (known: {', '.join(ADVISORY_CHECKS)}) — the check was "
                "NOT run, so its silence means nothing; to pass: correct the "
                "name in visuals.toml",
            )
        )
    return report


def _store_integrity_scan(visual_dir: Path, slug: str) -> list[Finding]:
    """Whole-version-directory scans the receipt cannot do: zero-byte files
    and non-PNG frame files. Companion to _receipt_findings."""
    findings: list[Finding] = []
    for version in store.existing_versions(visual_dir):
        for path in sorted((visual_dir / version).rglob("*")):
            if not path.is_file() or path.name == "receipt.json":
                continue
            if path.suffix.lower() != ".png":
                continue
            location = f"{slug}/{version}/{path.name}"
            if path.stat().st_size == 0:
                findings.append(
                    Finding(
                        "store-integrity",
                        "high",
                        location,
                        f"{path.name} in {slug}/{version} is 0 bytes — the "
                        "delivered artifact is empty; to pass: re-render this "
                        "version",
                    )
                )
            elif _png_dims(path) is None:
                findings.append(
                    Finding(
                        "store-integrity",
                        "high",
                        location,
                        f"{path.name} in {slug}/{version} is not a readable "
                        "PNG — the delivered artifact cannot be verified; to "
                        "pass: re-render this version",
                    )
                )
    return findings


def _visuals_for_slug(root: Path, slug: str) -> tuple[Path, ...]:
    """The visual directory a slug names: <root>/visuals/<slug>, <root>/<slug>,
    or a unique visual whose directory NAME is <slug> anywhere under the root
    (an adopted corpus may keep its visuals under nested paths)."""
    for candidate in (root / "visuals" / slug, root / slug):
        if is_visual_dir(candidate):
            return (candidate.resolve(),)
    matches = [v for v in discover_visuals(root) if v.name == slug]
    if len(matches) == 1:
        return (matches[0].resolve(),)
    if len(matches) > 1:
        raise ValidateError(
            f"slug {slug!r} matches more than one visual: "
            + ", ".join(_visual_slug(m, root) for m in matches)
            + " — use the fuller path form"
        )
    raise ValidateError(
        f"no visual {slug!r} under {root} (tried visuals/{slug} and {slug}; "
        "no visual directory of that name exists)"
    )
