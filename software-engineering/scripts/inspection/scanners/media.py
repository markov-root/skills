"""ExifTool-backed inspection of selected privacy-sensitive media metadata."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path

from ...execution import run_process
from ..models import (
    METADATA_FIELDS,
    ActiveFinding,
    InspectionLayer,
    finding_status,
    privacy_finding,
    reportable_path,
    safe_path,
)
from ..tooling import tool_evidence

MAX_FILES = 20_000
MAX_FINDINGS = 1_000
MAX_OUTPUT_BYTES = 5_000_000


def run_media_metadata(root: Path, media: Sequence[str]) -> InspectionLayer:
    started = time.monotonic()
    tool = tool_evidence("exiftool", ("exiftool", "-ver"), network="none", root=root)
    if not media:
        return InspectionLayer(
            "media-metadata",
            "privacy",
            "not_applicable",
            False,
            ("tracked and unignored media files",),
            (),
            tool,
            round((time.monotonic() - started) * 1000),
            reason="no supported media files found",
        )
    if tool.executable is None:
        return InspectionLayer(
            "media-metadata",
            "privacy",
            "unavailable",
            True,
            ("tracked and unignored media files",),
            (),
            tool,
            round((time.monotonic() - started) * 1000),
            reason="ExifTool is unavailable for applicable media",
        )
    findings: list[ActiveFinding] = []
    truncated = len(media) > MAX_FILES
    for offset in range(0, min(len(media), MAX_FILES), 100):
        batch = tuple(media[offset : offset + 100])
        command = (
            tool.executable,
            "-json",
            "-Author",
            "-Creator",
            "-GPSLatitude",
            "-GPSLongitude",
            "-OwnerName",
            "-SerialNumber",
            *batch,
        )
        result = run_process(
            command,
            root=root,
            timeout_seconds=60,
            max_output_bytes=MAX_OUTPUT_BYTES,
        )
        try:
            payload = json.loads(result.stdout) if result.status == "passed" else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if result.stdout_truncated or not isinstance(payload, list):
            return InspectionLayer(
                "media-metadata",
                "privacy",
                "unavailable",
                True,
                ("tracked and unignored media files",),
                tuple(findings),
                tool,
                round((time.monotonic() - started) * 1000),
                truncated=truncated or result.stdout_truncated,
                reason="ExifTool output was unavailable, malformed, or truncated",
            )
        for item in payload:
            if not isinstance(item, dict):
                continue
            path = reportable_path(safe_path(root, item.get("SourceFile")))
            for field in sorted(METADATA_FIELDS):
                value = item.get(field)
                if value in (None, ""):
                    continue
                findings.append(
                    privacy_finding(
                        "privacy.media-metadata",
                        f"media contains {field} metadata",
                        str(value),
                        source="media-metadata",
                        path=path,
                    )
                )
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    return InspectionLayer(
        "media-metadata",
        "privacy",
        "unavailable" if truncated else finding_status(findings),
        True,
        ("tracked and unignored media files",),
        tuple(findings[:MAX_FINDINGS]),
        tool,
        round((time.monotonic() - started) * 1000),
        truncated=truncated or len(findings) > MAX_FINDINGS,
        reason=(
            f"media metadata findings reached the {MAX_FINDINGS} finding bound" if truncated else ""
        ),
        limitations=("Only the declared privacy-sensitive metadata fields were inspected.",),
    )
