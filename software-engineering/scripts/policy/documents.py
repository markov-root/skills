"""Manifest-level contracts for adopted document roles.

This module deliberately owns only declared policy.  The document domain owns
parsing, validation, authoring, and lifecycle behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

DOCUMENT_METADATA_KEY = "engineering_document"
HANDOFF_STATES = ("current", "superseded")


@dataclass(frozen=True)
class DocumentContractPolicy:
    version: int
    role: str
    carrier: str = "frontmatter"
    metadata_key: str = DOCUMENT_METADATA_KEY
