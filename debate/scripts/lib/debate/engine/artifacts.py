"""Run artifact store — the file layout for one debate, with resume.

State lives in files, not the debaters (DATA.md: append-only, auditable source of truth).
A run is a directory; each step writes its output immediately, so an interrupted or expensive
run can resume by skipping steps whose output already exists (reproducibility / idempotency).

    runs/<task>/<measure>/<debate-name>/
      blinding.json   run.log   metrics.json   round_status.json
      round-1-propose/<id>.json   round-2-critique/<id>.json   round-3-revise/<id>.json
      round-4-redteam/<id>.json   round-5-respond/<id>.json
      round-escalate-<k>/<id>.json   round-respond-<k>/<id>.json   # dynamic escalation (ADR-0011)
      aggregate.json   gate.json   result.json   _invalid/    # _invalid/ quarantines rejected raw
    Each <id>.json has a sibling <id>.raw.txt (raw model text, cached before parse/validate).
    The panel roster (which models ran, ADR-0004) lives in result.json + metrics.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from debate._resources import resource_root

_REPO = resource_root().parent


class RunStore:
    def __init__(
        self,
        task: str,
        subject_id: str,
        debate_name: str,
        run_dir: Path | str | None = None,
    ):
        # A debate is a self-contained DIRECTORY (ADR-0006): when `run_dir` is given (the CLI's
        # `debates/<date>-<id>/`), the engine writes its rounds/result/metrics straight into it,
        # alongside the snapshotted run-spec + prompts + panel. Without it, fall back to the legacy
        # `runs/<task>/<subject>/<name>/` layout (keeps the engine unit tests unchanged).
        self.dir = Path(run_dir) if run_dir else _REPO / "runs" / task / subject_id / debate_name
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_file(self) -> Path:
        return self.dir / "run.log"

    def _path(self, round_name: str, debater_id: str | None) -> Path:
        if debater_id is None:  # single-output rounds (arbitrate)
            return self.dir / f"{round_name}.json"
        return self.dir / round_name / f"{debater_id}.json"

    def has(self, round_name: str, debater_id: str | None = None) -> bool:
        return self._path(round_name, debater_id).exists()

    def read(self, round_name: str, debater_id: str | None = None) -> dict:
        return json.loads(self._path(round_name, debater_id).read_text())

    # Raw model text is cached the instant a call returns, BEFORE parse/validate, so a
    # parse/schema/limit failure (or a prompt fix) never re-spends the expensive call.
    def _raw_path(self, round_name: str, debater_id: str | None) -> Path:
        return self._path(round_name, debater_id).with_suffix(".raw.txt")

    def has_raw(self, round_name: str, debater_id: str | None = None) -> bool:
        return self._raw_path(round_name, debater_id).exists()

    def read_raw(self, round_name: str, debater_id: str | None = None) -> str:
        return self._raw_path(round_name, debater_id).read_text()

    def write_raw(self, round_name: str, debater_id: str | None, text: str) -> None:
        path = self._raw_path(round_name, debater_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write(self, round_name: str, debater_id: str | None, obj: dict) -> Path:
        path = self._path(round_name, debater_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2))
        return path

    # L0 trace (ADR-0019/0020): one normalized CallRecord per call, cached beside its <id>.json so a
    # resume RE-READS it (a cache hit isn't lossy). `write_call_log` folds every sidecar into one
    # `calls.jsonl` at the end of the run — built by globbing the durable sidecars, so it is
    # resume-stable (no append duplication across re-runs).
    def _call_path(self, round_name: str, debater_id: str | None) -> Path:
        return self._path(round_name, debater_id).with_suffix(".call.json")

    def has_call_record(self, round_name: str, debater_id: str | None = None) -> bool:
        return self._call_path(round_name, debater_id).exists()

    def read_call_record(self, round_name: str, debater_id: str | None = None) -> dict:
        return json.loads(self._call_path(round_name, debater_id).read_text())

    def write_call_record(self, round_name: str, debater_id: str | None, obj: dict) -> None:
        path = self._call_path(round_name, debater_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2))

    def collect_call_records(self) -> list[dict]:
        """Every per-call L0 record on disk (subdir `<round>/<id>.call.json`), stably ordered."""
        return [json.loads(p.read_text()) for p in sorted(self.dir.glob("*/*.call.json"))]

    def write_jsonl(self, name: str, records: list[dict]) -> None:
        """Write a list of records as one JSON object per line (the L0/L1 trace streams)."""
        (self.dir / name).write_text("".join(json.dumps(r) + "\n" for r in records))

    def write_call_log(self) -> None:
        self.write_jsonl("calls.jsonl", self.collect_call_records())

    def write_meta(self, name: str, obj: dict) -> None:
        suffix = ".yaml" if name.endswith("yaml") else ".json"
        target = self.dir / (name if name.endswith((".yaml", ".json")) else f"{name}{suffix}")
        if target.suffix == ".yaml":
            target.write_text(yaml.safe_dump(obj, sort_keys=False))
        else:
            target.write_text(json.dumps(obj, indent=2))

    def rel(self) -> str:
        try:
            return str(self.dir.relative_to(_REPO))
        except ValueError:
            return str(self.dir)  # a self-contained debate dir may live outside the repo
