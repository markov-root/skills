"""One bounded, unpublished render-and-probe iteration against a visual's brief.

The author owns revisions between invocations. This module never edits a master,
selects a design, or promotes latest. Findings are evidence, not exit gates.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import config
import check
import measure
import probe
import render
import store


class ImproveUnavailable(Exception):
    """The iteration cannot run; no agreement is implied."""


def _load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "runs": [{"iterations": []}]}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImproveUnavailable(f"cannot read {path}: {exc}") from exc
    if (not isinstance(state, dict) or state.get("schema_version") != 1
            or not isinstance(state.get("runs"), list) or not state["runs"]
            or any(not isinstance(run, dict) or not isinstance(run.get("iterations"), list)
                   for run in state["runs"])):
        raise ImproveUnavailable(f"invalid improvement state at {path}")
    return state


def _save(path: Path, state: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".improvement-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _criteria(probe_report: dict) -> list[dict]:
    entries = []
    for frame in probe_report["frames"]:
        comparison = frame["comparison"]
        items = [("open", probe_report["claim"], comparison.get("open", {}))]
        items.extend((q["id"], q["expected"], comparison.get("targeted", {}).get(q["id"], {}))
                     for q in probe_report["questions"])
        for key, expected, result in items:
            status = result.get("status")
            outcome = {"pass": "agreed", "fail": "disagreed"}.get(status, "not-determinable")
            entries.append({"frame": frame["frame"], "criterion": key,
                            "expected": expected, "outcome": outcome,
                            "observed": (frame["cold"].get("claim") if key == "open" else
                                         frame["cold"].get("answers", {}).get(key)),
                            "reason": result.get("reason", "")})
    for item in probe_report["not_determinable"]:
        entries.append({"frame": None, "criterion": item["criterion"],
                        "expected": None, "observed": None,
                        "outcome": "not-determinable", "reason": item["reason"]})
    return entries


def run(slug: str, start: Path, *, execute: bool = False,
        new_run: bool = False, binary: str = "codex") -> dict:
    try:
        cfg = config.resolve_config(start)
        if cfg is None:
            raise ImproveUnavailable("an adopted project (visuals.toml) is required")
        visual = probe.resolve_visual(cfg.root, slug)
        brief = (visual / "BRIEF.md").read_text(encoding="utf-8")
        claim, questions = probe.parse_intent(brief)
    except (config.ConfigError, probe.ProbeUnavailable, OSError) as exc:
        raise ImproveUnavailable(str(exc)) from exc
    if not questions:
        raise ImproveUnavailable(
            "BRIEF.md needs at least one explicit '- Q: … | A: …' acceptance pair"
        )
    path = visual / "improvement.json"
    state = _load(path)
    if new_run:
        state["runs"].append({"iterations": []})
    iterations = state["runs"][-1]["iterations"]
    cap = cfg.improve_max_iterations
    previous = iterations[-1] if iterations else None
    if previous and all(c["outcome"] == "agreed" for c in previous["criteria"]):
        phase = "agreement"
    elif len(iterations) >= cap:
        phase = "cap-reached"
    else:
        phase = "ready"
    try:
        _, source, _ = render.locate_visual(slug, start, cfg)
        frame_count = len(render.parse_manifest(source / render.MANIFEST_NAME)[0])
    except (render.RenderError, store.StoreError) as exc:
        raise ImproveUnavailable(str(exc)) from exc
    report = {"schema_version": 1, "slug": slug, "mode": "execute" if execute else "dry-run",
              "phase": phase, "iteration": len(iterations) + (phase == "ready"),
              "max_iterations": cap, "previous": previous,
              "cost": "two fresh Codex calls per frame; quota amount varies" if execute else "none",
              "estimated_agent_calls": 2 * frame_count if phase == "ready" else 0,
              "not_assessed": ["visual hierarchy", "aesthetic quality", "completeness outside explicit acceptance"]}
    if not execute or phase != "ready":
        return report

    try:
        outcome = render.render_visual(slug=slug, start=start, publish=False)
    except (render.RenderError, store.StoreError) as exc:
        raise ImproveUnavailable(str(exc)) from exc
    mechanical = None
    if cfg.advisory_checks:
        try:
            checked = check.check_visual(slug, start)
            mechanical = {"summary": checked["summary"], "ladder": checked["ladder"]}
        except (check.CheckError, config.ConfigError, measure.MeasureError,
                render.RenderError, OSError) as exc:
            mechanical = {"unavailable": str(exc)}
    try:
        probe_report = probe.run(visual, execute=True, version=outcome.version, binary=binary)
        criteria = _criteria(probe_report)
    except probe.ProbeUnavailable as exc:
        criteria = [{"frame": None, "criterion": "probe", "expected": None,
                     "observed": None, "outcome": "not-determinable", "reason": str(exc)}]
    record = {"version": outcome.version, "criteria": criteria,
              "receipt": str(outcome.version_dir / "receipt.json"),
              "mechanical_check": mechanical}
    iterations.append(record)
    try:
        _save(path, state)
    except OSError as exc:
        raise ImproveUnavailable(
            f"unpublished version {outcome.version} exists, but cannot save {path}: {exc}"
        ) from exc
    report["current"] = record
    report["phase"] = ("agreement" if all(c["outcome"] == "agreed" for c in criteria)
                       else "cap-reached" if len(iterations) >= cap else "revise")
    return report
