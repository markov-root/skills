#!/usr/bin/env python3
"""Source registry: the attribution provenance capability domain (task 0008).

A capability domain, not a command adapter. Two consumers import it:

  sources_cmd.py   `visuals sources list|add|verify`
  validate.py      the advisory source-registry layer of `visuals validate`

Both must agree on what a valid registry is, so the contract lives here **once**.
The registry schema is not invented here: it generalises the shape the reference
corpus already uses (`visuals/_shared/sources.json`), which is the corpus's
strongest existing provenance practice (audit F9). This module adds enforcement,
not a new vocabulary.

What the contract requires, and why each rule exists:

- **https provenance, not prose.** `homepage` and `logo_source` must be https
  URLs. The corpus's `transluce` row records its provenance as a sentence about
  a sibling repository (audit F2); a reader cannot re-fetch a sentence. This is
  the one rule that rejects an entry the corpus currently contains, and doing so
  is the point of the task.
- **Hash-locked assets.** Every declared asset is re-hashed and compared with the
  recorded digest, so an asset changing under a published graphic is visible.
- **The untransformed original is retained.** When an asset was transformed, the
  registry keeps both files, both digests, and a prose description of the
  transform — the shape the corpus already uses for its logo assets.
- **Logos are inert.** An SVG asset is scanned for five kinds of active or
  external content. A logo is a shape, not a program.

Findings are returned, never raised and never printed: this module has no
opinion about severity, exit codes, or formatting. Under ADR 0004 a
source-registry finding is **advisory** — the caller decides, and `validate`
reports it without affecting its exit code.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

#: Bumped only when the on-disk registry shape changes incompatibly.
SCHEMA_VERSION = 1

#: Every entry declares all of these. Optional: original_logo,
#: original_logo_sha256, transform, logo_height, logo_render.
REQUIRED_SOURCE_FIELDS = {
    "name",
    "homepage",
    "logo",
    "logo_kind",
    "logo_width",
    "logo_source",
    "logo_sha256",
    "retrieved",
}

#: The five active/external-content cases, kept separate so `sources verify` can
#: name which one fired. `validate` reports their union under one message.
SVG_VIOLATIONS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "script",
        "a <script> element",
        re.compile(r"<script\b", re.IGNORECASE),
    ),
    (
        "foreign-object",
        "a <foreignObject> element",
        re.compile(r"<foreignObject\b", re.IGNORECASE),
    ),
    (
        "embedded-image",
        "an embedded <image> element",
        re.compile(r"<image\b", re.IGNORECASE),
    ),
    (
        "event-handler",
        "an inline event-handler attribute",
        re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE),
    ),
    (
        "external-reference",
        "an external or data-URI reference",
        re.compile(r"(?:xlink:)?href\s*=\s*[\"'](?:https?:|data:)", re.IGNORECASE),
    ),
)

#: Retained for `validate`, which reports the five cases as one finding.
DANGEROUS_SVG = re.compile(
    "|".join(pattern.pattern for _, _, pattern in SVG_VIOLATIONS), re.IGNORECASE
)


@dataclass(frozen=True)
class SourceFinding:
    """One registry defect. `code` is stable and machine-readable; `message`
    always names what would make it pass (the report contract of ADR 0004)."""

    code: str
    location: str
    message: str


class RegistryError(Exception):
    """The registry cannot be read or written at all — distinct from a finding
    about its contents, and the only failure this module raises."""


# ---------------------------------------------------------------------------
# hashing and reading
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Digest a file in bounded memory. Duplicated deliberately from store.py:
    the contract layer must not depend on the authored-render engine's store."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_registry(registry_path: Path) -> dict:
    """Read a registry, or raise RegistryError. A missing file is an error here;
    callers that treat absence as a finding (validate) check first."""
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"no source registry at {registry_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(
            f"source registry {registry_path.name} is unreadable ({exc})"
        ) from exc
    if not isinstance(payload, dict):
        raise RegistryError(
            f"source registry {registry_path.name} is not a JSON object"
        )
    return payload


def write_registry(registry_path: Path, payload: dict) -> None:
    """Write the registry deterministically: sorted keys, two-space indent,
    trailing newline. A re-write with unchanged content is a no-op diff."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    registry_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# verification (criteria 1 and 2)
# ---------------------------------------------------------------------------


def verify_registry(registry_path: Path) -> tuple[list[SourceFinding], int]:
    """Re-hash and re-check every declared asset. Returns (findings, entry count).

    Message strings are the single origin for both consumers; `validate` wraps
    them unchanged so one contract cannot drift into two.
    """
    if not registry_path.is_file():
        return (
            [
                SourceFinding(
                    "registry-missing",
                    str(registry_path),
                    "no source registry at paths.source_registry — attribution "
                    "provenance cannot be checked; to pass: point "
                    "paths.source_registry in visuals.toml at the project's "
                    "source registry (e.g. visuals/_shared/sources.json), or "
                    "create one",
                )
            ],
            0,
        )
    try:
        payload = load_registry(registry_path)
    except RegistryError as exc:
        return (
            [
                SourceFinding(
                    "registry-unreadable",
                    str(registry_path),
                    f"{exc} — to pass: fix the JSON so the registry parses",
                )
            ],
            0,
        )
    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        return (
            [
                SourceFinding(
                    "registry-no-sources-table",
                    str(registry_path),
                    "source registry has no sources table; to pass: declare "
                    "sources as a JSON object of per-source entries under "
                    '"sources"',
                )
            ],
            0,
        )
    findings: list[SourceFinding] = []
    base = registry_path.parent
    for source_id, source in sorted(sources.items()):
        findings.extend(verify_entry(source_id, source, base, registry_path.name))
    return findings, len(sources)


def verify_entry(
    source_id: str, source: object, base: Path, registry_name: str
) -> list[SourceFinding]:
    """Every rule for one entry. Split out so `add` can reject before writing."""
    location = f"{registry_name}: {source_id}"
    if not isinstance(source, dict):
        return [
            SourceFinding(
                "entry-not-an-object",
                location,
                f"{source_id}: registry entry is not an object; to pass: "
                "make it an object of the declared fields",
            )
        ]
    missing = REQUIRED_SOURCE_FIELDS - source.keys()
    if missing:
        return [
            SourceFinding(
                "entry-missing-fields",
                location,
                f"{source_id}: missing registry fields: "
                f"{', '.join(sorted(missing))} — to pass: declare them "
                "(the registry schema: name, homepage, logo, logo_kind, "
                "logo_width, logo_source, logo_sha256, retrieved)",
            )
        ]

    findings: list[SourceFinding] = []
    if not str(source["homepage"]).startswith("https://"):
        findings.append(
            SourceFinding(
                "homepage-not-https",
                location,
                f"{source_id}: homepage is not an https URL "
                f"({source['homepage']!r}) — provenance must name a "
                "first-party https source; to pass: replace it with the "
                "organisation's https homepage",
            )
        )
    if not str(source["logo_source"]).startswith("https://"):
        findings.append(
            SourceFinding(
                "provenance-not-a-url",
                location,
                f"{source_id}: logo_source is not an https URL "
                f"({source['logo_source']!r}) — provenance must identify "
                "the first-party https page the logo came from; to pass: "
                "replace the prose with the https URL",
            )
        )
    if source["logo_kind"] not in {"mark", "wordmark"}:
        findings.append(
            SourceFinding(
                "logo-kind-invalid",
                location,
                f"{source_id}: logo_kind is {source['logo_kind']!r}, "
                "expected mark or wordmark; to pass: declare which",
            )
        )
    if source.get("logo_render", "mask") not in {"mask", "image"}:
        findings.append(
            SourceFinding(
                "logo-render-invalid",
                location,
                f"{source_id}: logo_render is "
                f"{source.get('logo_render')!r}, expected mask or image; "
                "to pass: declare how the logo renders",
            )
        )
    if (
        not isinstance(source["logo_width"], int)
        or not 24 <= source["logo_width"] <= 200
    ):
        findings.append(
            SourceFinding(
                "logo-width-out-of-range",
                location,
                f"{source_id}: logo_width is {source['logo_width']!r}, "
                "expected an integer from 24 to 200; to pass: set the "
                "rendered width within that range",
            )
        )
    if "logo_height" in source and (
        not isinstance(source["logo_height"], int)
        or not 20 <= source["logo_height"] <= 48
    ):
        findings.append(
            SourceFinding(
                "logo-height-out-of-range",
                location,
                f"{source_id}: logo_height is {source['logo_height']!r}, "
                "expected an integer from 20 to 48; to pass: set the "
                "rendered height within that range",
            )
        )
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(source["retrieved"])):
        findings.append(
            SourceFinding(
                "retrieved-not-a-date",
                location,
                f"{source_id}: retrieved is {source['retrieved']!r}, "
                "expected YYYY-MM-DD; to pass: record the retrieval date",
            )
        )

    logo = (base / str(source["logo"])).resolve()
    if not logo.is_file():
        findings.append(
            SourceFinding(
                "asset-missing",
                location,
                f"{source_id}: declared logo {source['logo']!r} does not "
                "exist on disk; to pass: restore the asset or fix the path",
            )
        )
    else:
        recorded = source.get("logo_sha256")
        if recorded and sha256_file(logo) != recorded:
            findings.append(
                SourceFinding(
                    "digest-mismatch",
                    location,
                    f"{source_id}: logo {source['logo']!r} does not match "
                    "its recorded sha256 — the asset changed since the "
                    "digest was written; to pass: re-fetch the recorded "
                    "asset, or re-record the digest and the retrieval date "
                    "if the change is intended",
                )
            )
        if logo.suffix.lower() == ".svg":
            findings.extend(svg_findings(location, logo))

    if "original_logo" in source:
        findings.extend(_transformed_pair_findings(source_id, source, base, location))
    return findings


def _transformed_pair_findings(
    source_id: str, source: dict, base: Path, location: str
) -> list[SourceFinding]:
    """Criterion 2: a transformed asset keeps its untransformed original, that
    original's own digest, and a prose description of what was done to it."""
    findings: list[SourceFinding] = []
    original = (base / str(source["original_logo"])).resolve()
    if not original.is_file():
        findings.append(
            SourceFinding(
                "original-missing",
                location,
                f"{source_id}: declared original logo "
                f"{source['original_logo']!r} does not exist — the "
                "untransformed original must be retained (audit F9); "
                "to pass: restore it or fix the path",
            )
        )
    else:
        recorded = source.get("original_logo_sha256")
        if recorded and sha256_file(original) != recorded:
            findings.append(
                SourceFinding(
                    "original-digest-mismatch",
                    location,
                    f"{source_id}: original logo "
                    f"{source['original_logo']!r} does not match its "
                    "recorded sha256; to pass: re-fetch the recorded "
                    "original, or re-record the digest if the change "
                    "is intended",
                )
            )
    if not source.get("transform"):
        findings.append(
            SourceFinding(
                "transform-undescribed",
                location,
                f"{source_id}: transformed logo has no transform "
                "description — the registry records what was done to "
                "the original; to pass: describe the transform",
            )
        )
    return findings


def svg_violations(text: str) -> list[tuple[str, str]]:
    """Which of the five active/external-content cases this SVG contains.

    Returned as (code, human phrase) pairs in declaration order, so a caller can
    name the specific violation rather than only that something matched.
    """
    return [
        (code, phrase)
        for code, phrase, pattern in SVG_VIOLATIONS
        if pattern.search(text)
    ]


def svg_findings(location: str, logo: Path) -> list[SourceFinding]:
    """One finding per SVG asset, naming every case that fired.

    `validate` renders these as a single source-registry finding, so the message
    is the union phrasing it already used; the codes carry the detail.
    """
    try:
        text = logo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [
            SourceFinding(
                "svg-unreadable",
                location,
                f"SVG asset {logo.name} is unreadable; to pass: restore the asset",
            )
        ]
    violations = svg_violations(text)
    if not violations:
        return []
    return [
        SourceFinding(
            "svg-active-content",
            location,
            f"SVG asset {logo.name} contains active or external content "
            "(script, foreignObject, image, event handler, or an "
            "http(s)/data href) — a logo must be inert; to pass: replace "
            "it with a static SVG (paths and fills only)",
        )
    ]


# ---------------------------------------------------------------------------
# add (criteria 2 and 3)
# ---------------------------------------------------------------------------


def build_entry(
    *,
    name: str,
    homepage: str,
    logo: Path,
    logo_kind: str,
    logo_width: int,
    logo_source: str,
    retrieved: str,
    registry_dir: Path,
    logo_height: int | None = None,
    logo_render: str | None = None,
    original_logo: Path | None = None,
    transform: str | None = None,
) -> dict:
    """Assemble one entry, hashing the assets. Paths are recorded relative to the
    registry so the registry stays portable; digests are computed here rather
    than accepted from the caller, because a caller-supplied digest verifies
    nothing."""
    entry: dict = {
        "name": name,
        "homepage": homepage,
        "logo": _relative(logo, registry_dir),
        "logo_kind": logo_kind,
        "logo_width": logo_width,
        "logo_source": logo_source,
        "logo_sha256": sha256_file(logo) if logo.is_file() else "",
        "retrieved": retrieved,
    }
    if logo_height is not None:
        entry["logo_height"] = logo_height
    if logo_render is not None:
        entry["logo_render"] = logo_render
    if original_logo is not None:
        entry["original_logo"] = _relative(original_logo, registry_dir)
        entry["original_logo_sha256"] = (
            sha256_file(original_logo) if original_logo.is_file() else ""
        )
    if transform is not None:
        entry["transform"] = transform
    return entry


def _relative(path: Path, base: Path) -> str:
    """Registry-relative POSIX path, falling back to the absolute path when the
    asset lives outside the registry directory (which verify_entry will then
    report as it would any other unreachable asset)."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def add_entry(
    registry_path: Path, source_id: str, entry: dict, *, force: bool = False
) -> list[SourceFinding]:
    """Verify then write. Returns findings; **writes nothing when any finding is
    returned** unless `force`.

    This is criterion 3's mechanism: an entry whose provenance is prose rather
    than a URL never reaches disk. `force` exists so a project can record an
    entry it knows is imperfect, but it is explicit at the call site and the
    finding is still reported.
    """
    if registry_path.is_file():
        payload = load_registry(registry_path)
    else:
        payload = {"schema_version": SCHEMA_VERSION, "sources": {}}
    sources = payload.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise RegistryError("source registry has no sources table")
    if source_id in sources and not force:
        return [
            SourceFinding(
                "entry-exists",
                f"{registry_path.name}: {source_id}",
                f"{source_id}: already in the registry — to pass: choose "
                "another id, or pass --force to replace the entry",
            )
        ]

    findings = verify_entry(source_id, entry, registry_path.parent, registry_path.name)
    if findings and not force:
        return findings

    sources[source_id] = entry
    payload.setdefault("schema_version", SCHEMA_VERSION)
    write_registry(registry_path, payload)
    return findings


def list_entries(registry_path: Path) -> list[dict]:
    """Every entry with its verification status, for `sources list`. Read-only."""
    payload = load_registry(registry_path)
    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        raise RegistryError("source registry has no sources table")
    rows = []
    for source_id, source in sorted(sources.items()):
        findings = verify_entry(
            source_id, source, registry_path.parent, registry_path.name
        )
        rows.append(
            {
                "id": source_id,
                "name": source.get("name") if isinstance(source, dict) else None,
                "homepage": source.get("homepage")
                if isinstance(source, dict)
                else None,
                "logo": source.get("logo") if isinstance(source, dict) else None,
                "retrieved": source.get("retrieved")
                if isinstance(source, dict)
                else None,
                "transformed": isinstance(source, dict) and "original_logo" in source,
                "ok": not findings,
                "findings": [f.code for f in findings],
            }
        )
    return rows
