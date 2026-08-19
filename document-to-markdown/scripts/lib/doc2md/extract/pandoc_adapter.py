"""Broad structured-document extraction through a bounded local Pandoc process."""

from __future__ import annotations

import shutil
import subprocess

from doc2md.core.models import (
    AdapterCapabilities,
    AttemptContext,
    AttemptTimedOutError,
    Candidate,
    ProvenanceTier,
    SourceDocument,
    TransformationRecord,
)
from doc2md.extract.textnorm import (
    TEXTNORM_VERSION,
    collapse_blank_lines,
    strip_invisibles,
)

_PANDOC_FORMATS = {
    "application/epub+zip": "epub",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/rtf": "rtf",
    "text/rtf": "rtf",
    "text/x-rst": "rst",
    "application/x-latex": "latex",
    "text/x-tex": "latex",
}
_PANDOC_TIMEOUT_SECONDS = 30.0


def _remaining_timeout(context: AttemptContext) -> float:
    context.raise_if_stopped()
    remaining = context.deadline - context.clock()
    if remaining <= 0:
        raise AttemptTimedOutError("attempt deadline exceeded")
    return min(_PANDOC_TIMEOUT_SECONDS, remaining)


def _short_error(stderr: bytes) -> str:
    text = stderr.decode("utf-8", errors="replace").strip()
    if not text:
        return "no diagnostic output"
    return text.splitlines()[0][:200]


def _pandoc_version(pandoc: str, context: AttemptContext) -> str:
    try:
        completed: subprocess.CompletedProcess[bytes] = subprocess.run(
            [pandoc, "--version"],
            capture_output=True,
            timeout=_remaining_timeout(context),
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AttemptTimedOutError("pandoc version probe timed out") from error
    if completed.returncode != 0:
        raise RuntimeError(
            f"pandoc version probe failed: {_short_error(completed.stderr)}"
        )
    first_line = completed.stdout.decode("utf-8", errors="replace").splitlines()
    if not first_line:
        raise RuntimeError("pandoc version probe produced no output")
    version_line = first_line[0].strip()
    if version_line.lower().startswith("pandoc "):
        version_line = version_line.split(maxsplit=1)[1]
    if not version_line:
        raise RuntimeError("pandoc version probe produced no version")
    return version_line


class PandocExtractor:
    """Convert explicitly allowlisted structured formats to GitHub-Flavored Markdown."""

    ADAPTER_ID = "pandoc"
    VERSION = "1"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_id=self.ADAPTER_ID,
            version=self.VERSION,
            media_types=frozenset(_PANDOC_FORMATS),
        )

    def extract(self, source: SourceDocument, context: AttemptContext) -> Candidate:
        context.raise_if_stopped()
        pandoc = shutil.which("pandoc")
        if pandoc is None:
            raise RuntimeError("pandoc not installed")
        try:
            input_format = _PANDOC_FORMATS[source.media_type]
        except KeyError as error:
            raise ValueError(
                f"unsupported media type for pandoc: {source.media_type}"
            ) from error

        try:
            completed: subprocess.CompletedProcess[bytes] = subprocess.run(
                [pandoc, "-f", input_format, "-t", "gfm", "--wrap=none"],
                input=source.data,
                capture_output=True,
                timeout=_remaining_timeout(context),
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AttemptTimedOutError("pandoc conversion timed out") from error
        if completed.returncode != 0:
            raise ValueError(
                f"pandoc conversion failed: {_short_error(completed.stderr)}"
            )
        if not completed.stdout:
            raise ValueError("pandoc produced no output")

        body = collapse_blank_lines(
            strip_invisibles(completed.stdout.decode("utf-8", errors="replace"))
        ).strip()
        if not body:
            raise ValueError("pandoc produced no extractable text")

        version = _pandoc_version(pandoc, context)
        label = f"pandoc {version}"
        context.raise_if_stopped()
        return Candidate(
            adapter_id=self.ADAPTER_ID,
            source_sha256=source.sha256,
            markdown=body + "\n",
            provenance_tier=ProvenanceTier.DETERMINISTIC_EXTRACTION,
            diagnostics=(label,),
            transformations=(
                TransformationRecord(
                    operation="strip-invisibles",
                    version=TEXTNORM_VERSION,
                    lossy=False,
                ),
            ),
            metadata={"extractor": label},
        )
