"""Filesystem artifact store: atomic, content-addressed run bundles.

Layout (see ``public/references/contract.md``)::

    <DOC2MD_HOME>/runs/<run-id>/
        document.md      selected Markdown with queryable frontmatter
        result.json      authoritative public result (written by the CLI after convert)
        raw/             source bytes when retention permits
        attempts/        candidate outputs and diagnostics

Every file is written via a temp file + ``os.replace`` so on-disk bytes never disagree with a
partially written bundle.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from doc2md.core.models import ArtifactReceipt, Attempt, SourceDocument
from doc2md.store.frontmatter import outline_is_inline, render_document
from doc2md.store.project import Acquisition, project_frontmatter

_DEFAULT_HOME = "~/.local/share/doc2md"


def default_home() -> Path:
    return Path(os.environ.get("DOC2MD_HOME", _DEFAULT_HOME)).expanduser()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


class FilesystemArtifactStore:
    """Persist a selected result and its evidence behind an owned artifact boundary."""

    def __init__(
        self,
        *,
        acquisition: Acquisition,
        home: Path | None = None,
        run_id: str | None = None,
    ) -> None:
        self._acquisition = acquisition
        self._home = home if home is not None else default_home()
        self._run_id = run_id

    def run_id_for(self, source: SourceDocument) -> str:
        return self._run_id if self._run_id is not None else source.sha256[:16]

    def bundle_path(self, run_id: str) -> Path:
        return self._home / "runs" / run_id

    def persist(
        self,
        source: SourceDocument,
        winner: Attempt,
        attempts: Sequence[Attempt],
    ) -> ArtifactReceipt:
        if winner.candidate is None:
            raise ValueError("cannot persist a winner without a candidate")
        run_id = self.run_id_for(source)
        bundle = self.bundle_path(run_id)

        _atomic_write_bytes(bundle / "raw" / "source.bin", source.data)

        for attempt in attempts:
            if attempt.candidate is not None:
                _atomic_write_text(
                    bundle / "attempts" / f"{attempt.adapter_id}.md",
                    attempt.candidate.markdown,
                )
            if attempt.diagnostics:
                _atomic_write_text(
                    bundle / "attempts" / f"{attempt.adapter_id}.diagnostics.txt",
                    "\n".join(attempt.diagnostics) + "\n",
                )

        fields, outline = project_frontmatter(
            source=source,
            candidate=winner.candidate,
            quality=winner.quality,
            acquisition=self._acquisition,
            run_id=run_id,
        )
        if not outline_is_inline(outline):
            _atomic_write_text(
                bundle / f"{run_id}.outline.json",
                json.dumps(outline, indent=2, ensure_ascii=False) + "\n",
            )
        document = render_document(fields, winner.candidate.markdown)
        _atomic_write_text(bundle / "document.md", document)

        return ArtifactReceipt(run_id=run_id, bundle_path=str(bundle))
