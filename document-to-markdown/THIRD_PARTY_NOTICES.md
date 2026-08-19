# Third-party notices

This skill's original instructions, references, and the bundled `doc2md` runtime code under
`scripts/lib/doc2md/` are licensed under Apache-2.0 (see [`LICENSE`](LICENSE)). Externally owned
sources referenced by the routing and provenance guidance are linked and synthesized, not copied.

## Bundled runtime and its optional dependencies

The runtime **core** (input detection, the plaintext and DOCX adapters, routing, quality, and the
artifact store) uses only the Python standard library. The optional HTML and PDF adapters are
lazily imported and pull the dependencies declared in `scripts/doc2md_cli.py` (pinned in
`scripts/doc2md_cli.py.lock`). These packages are **not** redistributed inside the skill; `uv`
fetches them from PyPI at first run. Their licenses:

| Package                             | Purpose                      | License          |
| ----------------------------------- | ---------------------------- | ---------------- |
| `trafilatura`                       | HTML main-content extraction | Apache-2.0       |
| `readability-lxml`                  | HTML thin-page rescue        | Apache-2.0       |
| `beautifulsoup4`, `lxml-html-clean` | HTML parsing helpers         | MIT / BSD-family |
| `requests`                          | Static HTTP fetch            | Apache-2.0       |
| **`pymupdf`**, **`pymupdf4llm`**    | PDF text/layout → Markdown   | **AGPL-3.0**     |

**AGPL notice.** `pymupdf`/`pymupdf4llm` are licensed under **AGPL-3.0**. doc2md uses them only for
**local, on-device** PDF extraction; the skill does not offer them (or a modified version) as a
network service, so the AGPL network-use obligation is not triggered by ordinary local use. Anyone
redistributing or hosting a derivative must comply with AGPL-3.0. The PDF adapter is optional: if
`pymupdf4llm` is absent, doc2md falls back to the permissively-licensed poppler `pdftotext -layout`
route, and the Apache-2.0 core continues to work without any AGPL dependency.

## Development-only dependencies

The private `dev/` factory pins development/test-only tools (`jsonschema`, `mypy`, `ruff`) that are
tracked there and never installed with the skill.
