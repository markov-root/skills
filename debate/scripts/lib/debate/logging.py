"""Structured logging with a per-run correlation id (OBSERVABILITY.md).

Runs are long and multi-step; auditability is the project's #2 quality attribute. Every
log line carries a `run_id` so a whole debate can be reconstructed by grepping one id, and
each run also tees its log to a file beside its artifacts.

This is std-lib logging only — no metrics *infrastructure* (Prometheus/traces/SLOs; deliberately
not applied, see CONTRIBUTING §3). Record-only per-run accounting (cost/tokens/timing) does exist,
written to `metrics.json` by the debate loop from data the backends already return (ADR-0009) —
that's extraction, not an observability stack. UTC, ISO-8601 timestamps; stable field names.
"""

from __future__ import annotations

import logging
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s [%(run_id)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"


class _RunIdFilter(logging.Filter):
    """Default run_id so library log lines without one still format cleanly."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "run_id"):
            record.run_id = "-"
        return True


def configure(level: int = logging.INFO) -> None:
    """Idempotent root setup — UTC timestamps, run_id-aware console handler."""
    root = logging.getLogger()
    if getattr(root, "_cop_configured", False):
        return
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    formatter.converter = __import__("time").gmtime  # UTC
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(_RunIdFilter())
    root.addHandler(handler)
    root.setLevel(level)
    root._cop_configured = True  # type: ignore[attr-defined]


def run_logger(name: str, run_id: str, log_file: Path | None = None) -> logging.LoggerAdapter:
    """A logger bound to a run_id; optionally also writes to a per-run file."""
    configure()
    logger = logging.getLogger(name)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        fh.addFilter(_RunIdFilter())
        logger.addHandler(fh)
    return logging.LoggerAdapter(logger, {"run_id": run_id})
