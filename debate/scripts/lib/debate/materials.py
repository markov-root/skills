"""Materials pipeline (ADR-0009): fetch-then-pin a research corpus, then a cheap PREP pass writes a
one-paragraph abstract per source so the debate injects a MAP of summaries — not the full text of
every file (which is costly and drowns the signal). Each voice sees the map (title + abstract +
filename); the agentic CLI voices can open the full file on disk when they need the detail.

    materials/
      manifest.yaml            # sources[]: url, title, path, sha256, retrieved, media_type, summary
      <slug>.md                # extracted plain text (what gets read / summarised)
      raw/<slug>.pdf|.html     # the pinned original the .md was derived from

Fetch is idempotent (skips a source whose text file already exists); prep only summarises sources
that lack a `summary`. Both are per-source fault-isolated: one bad URL never aborts the batch.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import yaml

from debate.input_contracts import (
    InputContractError,
    load_materials_manifest_input,
    resolve_owned_path,
)

_UA = "Mozilla/5.0 (X11; Linux x86_64) debate-materials/1.0 (+research corpus fetch)"
_PREP_SYSTEM = (
    "You are a research librarian preparing a corpus for a debate panel. Given one source "
    "document, write a dense, neutral abstract (120-180 words) that states: what the document IS "
    "(type, author/issuer if evident), its central claim or purpose, and the specific facts, "
    "figures, positions, or provisions a debater could CITE from it. No preamble, no opinion, no "
    "markdown — just the abstract."
)


class _TextExtractor(HTMLParser):
    """Stdlib fallback HTML→text (used only when `trafilatura` is not installed): collect text,
    dropping script/style/nav noise. Rough but reproducible and dependency-free."""

    _SKIP = {"script", "style", "noscript", "head", "svg"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _html_to_text(html: str) -> str:
    try:
        import trafilatura  # optional, far better extraction; used if present

        if txt := trafilatura.extract(html, include_comments=False, include_tables=True):
            return txt
    except Exception:
        pass
    p = _TextExtractor()
    p.feed(html)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(p.parts))


def _pdf_to_text(pdf_path: Path) -> str:
    out = subprocess.run(
        ["pdftotext", "-nopgbrk", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return out.stdout if out.returncode == 0 else ""


def _slug(url: str, title: str | None) -> str:
    base = title or Path(urlparse(url).path).stem or urlparse(url).netloc
    s = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return s[:60] or "source"


def _load_manifest(materials: Path) -> dict:
    mf = materials / "manifest.yaml"
    doc = yaml.safe_load(mf.read_text()) if mf.exists() else {}
    try:
        return load_materials_manifest_input(doc or {}, source=mf).to_runtime()
    except InputContractError as exc:
        raise ValueError(str(exc)) from exc


def _save_manifest(materials: Path, doc: dict) -> None:
    canonical = load_materials_manifest_input(doc, source=materials / "manifest.yaml").model_dump(
        exclude_none=True, exclude_defaults=True
    )
    (materials / "manifest.yaml").write_text(
        yaml.safe_dump(canonical, sort_keys=False, allow_unicode=True)
    )


def fetch_sources(project: Path | str, *, timeout: float = 60.0) -> list[dict]:
    """Download every manifest source, convert to text, SHA-pin. Idempotent + fault-isolated.
    Returns a per-source report [{title, status, chars|error}]."""
    from debate.project import sha256_file

    materials = Path(project).resolve() / "materials"
    doc = _load_manifest(materials)
    materials.mkdir(parents=True, exist_ok=True)
    (materials / "raw").mkdir(exist_ok=True)
    sources = doc.get("sources") or []
    report: list[dict] = []

    for src in sources:
        url = src.get("url")
        if not url:
            continue
        title = src.get("title")
        slug = src.get("path", "").removesuffix(".md") or _slug(url, title)
        try:
            text_path = resolve_owned_path(materials, f"{slug}.md", kind="material text path")
            raw_path = resolve_owned_path(
                materials / "raw",
                f"{slug}.{'pdf' if url.lower().endswith('.pdf') else 'html'}",
                kind="material raw path",
            )
        except InputContractError as exc:
            report.append({"title": title or url, "status": "error", "error": str(exc)[:200]})
            continue
        if text_path.exists() and src.get("sha256"):
            report.append(
                {"title": title or slug, "status": "cached", "chars": len(text_path.read_text())}
            )
            continue
        try:
            content, ctype = _download(url, timeout)
            is_pdf = "pdf" in ctype or url.lower().endswith(".pdf")
            raw_path = resolve_owned_path(
                materials / "raw",
                f"{slug}.{'pdf' if is_pdf else 'html'}",
                kind="material raw path",
            )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(content)
            if is_pdf:
                text = _pdf_to_text(raw_path)
            else:
                text = _html_to_text(content.decode("utf-8", errors="replace"))
            text = text.strip()
            if not text:
                raise ValueError("no text extracted")
            text_path.write_text(text)
            src["path"] = f"{slug}.md"
            src["title"] = title or slug.replace("-", " ").title()
            src["media_type"] = "pdf" if is_pdf else "html"
            src["sha256"] = sha256_file(
                raw_path
            )  # raw bytes — a hostile reader re-downloads + hashes
            # content_sha256 pins the EXTRACTED text the debate actually injects (task-0027): the
            # consumer verifies it on load, so a drifted .md fails fast, not serving stale text.
            src["content_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            src["retrieved"] = _today()
            report.append({"title": src["title"], "status": "fetched", "chars": len(text)})
        except Exception as e:  # noqa: BLE001 — one bad URL must not abort the batch
            report.append({"title": title or url, "status": "error", "error": str(e)[:200]})
    doc["sources"] = sources
    _save_manifest(materials, doc)
    return report


def _download(url: str, timeout: float) -> tuple[bytes, str]:
    """GET a URL with stdlib urllib (no extra dependency; ADR-0009). Follows redirects by default;
    returns (body bytes, lowercased content-type)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})  # noqa: S310 — https research URLs
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read(), (resp.headers.get_content_type() or "").lower()


def prep_summaries(
    project: Path | str, *, backend: str = "claude_code", model: str | None = None
) -> list[dict]:
    """Write a cached abstract for every fetched source that lacks one, via a cheap model. Default
    backend is the remote, subscription-backed claude_code CLI. Fault-isolated. Returns a
    per-source report."""
    from debate.backends import build_debater

    materials = Path(project).resolve() / "materials"
    doc = _load_manifest(materials)
    sources = doc.get("sources") or []
    spec = {"id": "prep", "backend": backend}
    if model:
        spec["model"] = model
    librarian = build_debater(spec)
    report: list[dict] = []
    for src in sources:
        path = src.get("path")
        if not path:
            continue
        try:
            text_path = resolve_owned_path(materials, path, kind="material source path")
        except InputContractError as exc:
            report.append({"title": src.get("title"), "status": "error", "error": str(exc)[:200]})
            continue
        if not text_path.exists():
            continue
        if src.get("summary"):
            report.append({"title": src.get("title"), "status": "cached"})
            continue
        text = text_path.read_text()
        # Cap the prep input so a huge PDF doesn't blow the context/cost of the cheap prep call.
        user = f"SOURCE: {src.get('title')}\nURL: {src.get('url')}\n\n{text[:40000]}"
        try:
            summary = librarian.generate(_PREP_SYSTEM, user).strip()
            src["summary"] = summary
            report.append(
                {"title": src.get("title"), "status": "summarised", "chars": len(summary)}
            )
        except Exception as e:  # noqa: BLE001
            report.append({"title": src.get("title"), "status": "error", "error": str(e)[:200]})
    doc["sources"] = sources
    _save_manifest(materials, doc)
    return report


def render_map(materials: Path | str) -> str:
    """The MAP injected into the debate: one entry per source (title · file · url · abstract). This
    is what a voice reads to know WHAT is in the corpus and WHERE — not the full text (ADR-0009)."""
    materials = Path(materials).resolve()
    doc = _load_manifest(materials)
    sources = [s for s in (doc.get("sources") or []) if s.get("path")]
    if not sources:
        return ""
    parts = [
        "MATERIALS MAP — the research corpus available to this debate. Cite a source by its file "
        "name; the full text of each file lives in this project's materials/ folder (agentic "
        "voices may open it for detail). Ground new claims in these sources.",
    ]
    for s in sources:
        summary = s.get("summary") or "(no abstract yet — run `debate materials prep`)"
        parts.append(
            f"\n----- {s.get('title')}  [file: {s['path']}]  {s.get('url', '')}\n{summary}"
        )
    return "\n".join(parts)


def _today() -> str:
    import datetime

    return datetime.date.today().isoformat()
