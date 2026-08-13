"""The materials data-contract — CONSUMER side (task-0027; ADR-0015).

Acquisition is a provider concern; the debate is a consumer that reads only
`materials/manifest.yaml` and imports nothing from any provider (`debate/materials.py` is the
reference provider). This module is the boundary the consumer enforces:

- `corpus_version` / `manifest_digest` — the frozen evidence-universe id a run records, so an
  artifact states WHICH universe it used;
- `verify_corpus` — fail-fast integrity check (a drifted `.md` whose `content_sha256` no longer
  matches is refused, not silently served as stale text);
- `source_in_manifest` — the frozen-universe membership primitive (a cited source not in the
  manifest is out of bounds);
- `quote_grade` — the GRADED verbatim gate (exact / stitched / near_miss / none) with SYMMETRIC
  markup normalization, so extraction artifacts don't cause false rejects.

Pure + stdlib-only, so the gate is testable with a $0 deterministic probe (no models, no network).
Wiring the quote gate over live debater citations (via the task's grounding referee) and the
search-mode `visited_urls.jsonl` are follow-ups that need citation parsing / backend URL capture.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from debate.input_contracts import (
    InputContractError,
    load_materials_manifest_input,
    resolve_owned_path,
)


class MaterialsError(RuntimeError):
    """A materials-contract boundary violation — raised to fail a run fast (never serve stale)."""


_TAG = re.compile(r"<[^>]+>")  # whole HTML/XML tags (drop the tag NAME too, not just the brackets)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")  # any run of punctuation / markup glyphs / whitespace


def normalize(text: str) -> str:
    """Symmetric normalization applied to BOTH a source and a quote before comparison: lowercase,
    remove whole HTML tags, then collapse every run of non-alphanumeric characters (markdown
    emphasis, table glyphs, punctuation, wrapped whitespace) to a single space. So a quote that
    differs from the source only by an extraction artifact — a stray `*`, a `<em>`, a comma, a
    wrapped line — still matches (artifacts must not cause false rejects)."""
    return _NON_ALNUM.sub(" ", _TAG.sub(" ", (text or "").lower())).strip()


def _words(text: str) -> list[str]:
    return normalize(text).split()


def load_manifest(project: Path | str) -> dict:
    """Read `<project>/materials/manifest.yaml` (or {} if absent). Consumer-only, no imports."""
    mf = Path(project) / "materials" / "manifest.yaml"
    if not mf.exists():
        return {}
    try:
        return load_materials_manifest_input(
            yaml.safe_load(mf.read_text()) or {}, source=mf
        ).to_runtime()
    except InputContractError as exc:
        raise MaterialsError(str(exc)) from exc


def included_sources(manifest: dict) -> list[dict]:
    """Sources with `status != exclude` (default included) — the live evidence universe."""
    return [s for s in (manifest.get("sources") or []) if s.get("status", "include") != "exclude"]


def manifest_digest(manifest: dict) -> str:
    """A deterministic 12-hex digest of the included sources' identity + text hashes — the
    fingerprint of the exact evidence universe, independent of YAML key order."""
    parts = sorted(
        f"{s.get('id') or s.get('path')}:{s.get('content_sha256') or s.get('sha256') or ''}"
        for s in included_sources(manifest)
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


def corpus_version(manifest: dict) -> str | None:
    """The frozen evidence-universe id: the provider's `corpus_version` if set, else the digest.
    None when there is no corpus at all (a debate with no materials)."""
    if not manifest.get("sources"):
        return None
    return str(manifest.get("corpus_version") or manifest_digest(manifest))


def source_in_manifest(manifest: dict, ref: str) -> bool:
    """Frozen-universe membership: is `ref` (a source id or path) an included source? (Rule 1.)"""
    ref = (ref or "").strip()
    return any(ref in (s.get("id"), s.get("path")) for s in included_sources(manifest))


def verify_corpus(project: Path | str) -> dict:
    """Fail-fast integrity check on load (Rule 2): every included source with a `path` +
    `content_sha256` must hash-match the on-disk extracted text. Raises `MaterialsError` on a drift
    or a missing file. Returns `{corpus_version, manifest_digest, n_sources}` for provenance. A
    corpus with no manifest / no sources is a no-op (n_sources=0) — materials are optional.
    """
    project = Path(project)
    manifest = load_manifest(project)
    sources = included_sources(manifest)
    for s in sources:
        path, want = s.get("path"), s.get("content_sha256")
        if not path or not want:
            continue  # not yet fetched/pinned — nothing to verify (a provider fills these)
        try:
            f = resolve_owned_path(
                project / "materials", path, kind=f"manifest source {s.get('id') or path!r}"
            )
        except InputContractError as exc:
            raise MaterialsError(str(exc)) from exc
        if not f.exists():
            raise MaterialsError(
                f"manifest source {s.get('id') or path!r}: text file {path} missing"
            )
        got = hashlib.sha256(f.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if got != want:
            raise MaterialsError(
                f"manifest source {s.get('id') or path!r}: content_sha256 drift — {path} on disk "
                f"({got[:12]}) does not match the pinned hash ({want[:12]}); re-fetch or re-pin."
            )
    return {
        "corpus_version": corpus_version(manifest),
        "manifest_digest": manifest_digest(manifest) if sources else None,
        "n_sources": len(sources),
    }


_NEAR_MISS_MIN_WORDS = (
    8  # a contiguous run this long → a locatable near-miss (medium), not a reject
)
_STITCH_MIN_WORDS = (
    3  # each `...`-joined fragment must be at least this long to count as legitimate
)


def quote_grade(quote: str, source_text: str) -> str:
    """Grade a debater quote against the source text it claims (Rule 3), after symmetric markup
    normalization: `exact` (contiguous run), `stitched` (`...`-joined fragments each >= 3 words, all
    present, in order), `near_miss` (a long contiguous run present — carries a repair span, flagged
    not failed), or `none` (unsupported). Deterministic; no model call."""
    src = normalize(source_text)
    q = normalize(quote)
    if not q:
        return "none"
    if q in src:
        return "exact"
    # stitched: fragments separated by an ellipsis, each a real phrase, each present, left-to-right
    frags = [normalize(f) for f in re.split(r"\.\.\.+|…", quote) if normalize(f)]
    if len(frags) >= 2 and all(len(f.split()) >= _STITCH_MIN_WORDS for f in frags):
        cursor = 0
        if all((idx := src.find(f, cursor)) >= 0 and (cursor := idx + len(f)) for f in frags):
            return "stitched"
    # near_miss: the longest contiguous window of the quote that appears verbatim in the source
    words = q.split()
    for size in range(len(words), _NEAR_MISS_MIN_WORDS - 1, -1):
        if any(" ".join(words[i : i + size]) in src for i in range(len(words) - size + 1)):
            return "near_miss"
    return "none"
