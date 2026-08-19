# Changelog

This changelog records changes to the installable `document-to-markdown` Agent Skill artifact.

## 0.3.0 — 2026-08-11

- PDF preflight (Task 0024): detect encryption (refused, not crashed), page count, and text-layer
  coverage before extraction; surface `pages`/`text_coverage` and a doc-info date into provenance.
- Honest dates (Task 0025): harvested dates are plausibility-bounded and provenance-tagged
  (`value`/`via`/`confidence`); the observed current-year Jan-1 parser sentinel is rejected with a
  diagnostic instead of surfaced as a fact.
- Extraction fidelity (Task 0026): strip pymupdf4llm picture-text comment noise while preserving
  real content and the PDF hyperlinks appendix.
- pandoc adapter (Task 0030): optional broad-format route (EPUB, ODT, RTF, LaTeX, reStructuredText)
  via a local `pandoc` subprocess; reported unavailable and skipped when `pandoc` is absent.
- Batch (Task 0035): `doc2md batch MANIFEST [--resume]` converts a newline-delimited manifest
  sequentially with per-item fault isolation and content-addressed resume. (Outbound MCP deferred.)
- Robustness: backend stdout banners (e.g. pymupdf) are confined to stderr so the stdout result
  contract stays pipe-safe.

## 0.2.0 — 2026-08-11

- The `doc2md` CLI is now real and bundled: `scripts/doc2md` (uv launcher) + `scripts/doc2md_cli.py`
  (PEP 723, locked) + `scripts/lib/doc2md/` (the runtime package). `convert`, `plan`, `show`,
  `doctor`, `contract`, and `version` work end-to-end.
- Extraction ladder implemented at parity with the CoP Dataset / Research Database pipelines:
  HTML via trafilatura with a readability rescue (links + tables, boilerplate stripped); PDF via
  pymupdf4llm with a PDF-link-annotation appendix, a `pdftotext -layout` fallback with
  running-header/footer removal, and a >10 MB memory guard; DOCX via a hardened stdlib zip/XML
  reader; and a plaintext/Markdown passthrough. Extraction stays extractive — a PDF with no text
  layer is reported as needing OCR, never fabricated.
- Every converted document carries a deterministic, queryable YAML frontmatter (Task 0023):
  identity, dual raw/body-only hashes, provenance tier, quality flags, shape metrics, harvested
  provenance-tagged metadata, and a heading outline. It is a projection of the authoritative
  `result.json` and holds no generative inference by default.
- Optional HTML/PDF backends are lazily imported and fetched by `uv`; `pymupdf4llm`/`pymupdf` are
  AGPL-3.0 (local use only) and disclosed in `THIRD_PARTY_NOTICES.md`.

## 0.1.0 — 2026-08-02

- Initial refactor into the standardized `{public,dev}` workspace layout. The skill remains a
  planning scaffold: the `doc2md` CLI and converter adapters are target behavior until Task 0018
  confirms installation, so the artifact ships only the agent contract plus routing/provenance
  references.
- Bundled `LICENSE` and `THIRD_PARTY_NOTICES.md` so they ship with the published skill.
