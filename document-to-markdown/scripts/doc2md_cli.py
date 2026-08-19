#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<4"
# dependencies = [
#   "trafilatura>=2.0,<3",
#   "readability-lxml>=0.8.4.1,<0.9",
#   "beautifulsoup4>=4.12,<5",
#   "lxml-html-clean>=0.4,<0.5",
#   "pymupdf4llm>=0.0.17,<2",
#   "pymupdf>=1.24,<2",
#   "requests>=2.31,<3",
# ]
# ///
"""Portable entry point for the bundled doc2md package.

The core (plaintext + DOCX) is pure standard library; the dependencies above enable the optional
HTML (trafilatura/readability) and PDF (pymupdf4llm) adapters. pymupdf4llm/pymupdf are AGPL-3.0 and
are used locally only — see THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))


if __name__ == "__main__":
    main = importlib.import_module("doc2md.cli").main
    raise SystemExit(main())
