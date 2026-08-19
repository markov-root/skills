"""Quota CLI — usage-check parity (ADR-0005). Exit codes mirror usage-check:
0 continue · 11 wind_down (with --fail-on-warn) · 10 wait_for_reset · 3 no data · 2 error.

Deltas from the .sh (docs/lessons/0003 + audit 0001): fixed the flagged bugs; `--wait`
polls in short increments instead of one 6h sleep; `--refresh` actually waits for a
fresh write (feature-detects instead of pinning a version).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

from situational_awareness import registry
from situational_awareness.quota import analysis, reader
from situational_awareness.quota.models import DEFAULT_THRESHOLDS, EXIT_ERROR, EXIT_NO_DATA

_LABELS = {"five_hour": "5-hour", "seven_day": "weekly"}


def _fmt_dur(s: int | None) -> str:
    """Match the .sh: hours never roll into days (e.g. 90000s -> '25h00m')."""
    if s is None:
        return "n/a"
    s = int(s)
    if s < 60:
        return f"{s}s"
    m, _sec = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def _clock(epoch) -> str:
    """Local wall-clock reset time (parity: the .sh shows 'resets HH:MM ...')."""
    if not epoch:
        return "unknown"
    try:
        return datetime.datetime.fromtimestamp(int(epoch)).strftime("%H:%M")
    except (OverflowError, OSError, ValueError):
        return "unknown"


def _human(r) -> str:
    def win(w, burn_dp, max_thr):
        if not w.available:
            return f"  {_LABELS[w.name]:7}: unavailable from this provider"
        burn = (
            f"{w.burn_pct_per_min:.{burn_dp}f}%/min"
            if w.burn_pct_per_min is not None
            else "burn n/a"
        )
        eta = f"ETA→{int(max_thr)}% {_fmt_dur(int(w.eta_min_to_max * 60)) if w.eta_min_to_max else 'n/a'}"
        return (
            f"  {_LABELS[w.name]:7}: {w.remaining_pct:.0f}% left (used {w.used_pct:.0f}%) · "
            f"resets {_clock(w.resets_at)} in {_fmt_dur(w.resets_in_s)} · {burn} · {eta}"
        )

    stale = ""
    if r.stale:
        stale = f"  (STALE {r.age_seconds}s)" if r.age_seconds is not None else "  (STALE)"
    lines = [
        f"{r.provider} quota{stale} ({r.source})",
        win(r.five_hour, 2, r.thresholds["max_5h"]),
        win(r.seven_day, 3, r.thresholds["max_7d"]),
        f"  binding: {r.binding}",
    ]
    it = r.forecast["iteration"]
    if it["cost_pct_per_iter"] and it["iters_left"] is not None:
        lines.append(
            f"  iters  : ~{it['cost_pct_per_iter']}%/cycle (label {it['label']!r}, "
            f"n={it['samples']}) → ~{it['iters_left']} cycles left"
        )
    act = r.action
    if act == "wait_for_reset":
        act += f" — stop; {r.binding} resets in {_fmt_dur(r.seconds_until_ok)}"
    elif act == "wind_down":
        act += " — finish current item, checkpoint (soft threshold hit)"
    lines.append(f"  ACTION : {act}")
    return "\n".join(lines)


def _validate_thresholds(th: dict) -> str | None:  # fix #9
    for k, v in th.items():
        if not (0 <= v <= 100):
            return f"{k}={v} out of range [0,100]"
    if th["warn_5h"] >= th["max_5h"] or th["warn_7d"] >= th["max_7d"]:
        return "warn threshold must be < max threshold"
    return None


def _maybe_refresh(quiet: bool) -> None:
    """Best-effort live refresh: nudge a fresh statusline write and WAIT for it
    (fix #3 — the .sh fired-and-forgot, a race). Feature-detects (fix #8): if the
    binary/flag isn't there, we just proceed on cache."""
    try:
        before = reader.LATEST.stat().st_mtime
    except OSError:
        before = 0.0
    claude = shutil.which("claude")
    if claude is None:
        if not quiet:
            print(
                "usage-check: --refresh unavailable (no claude binary); using cache",
                file=sys.stderr,
            )
        return
    try:
        subprocess.Popen(
            [claude, "-p", "/usage"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except OSError:
        if not quiet:
            print("usage-check: --refresh failed to launch claude; using cache", file=sys.stderr)
        return
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            if reader.LATEST.stat().st_mtime > before:
                return
        except OSError:
            pass
    if not quiet:
        print("usage-check: --refresh saw no fresh write within 10s; using cache", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="usage-check", description="Report provider subscription quota (5h + weekly)."
    )
    ap.add_argument("--provider", choices=("claude-code", "codex", "opencode"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="exit code only")
    ap.add_argument("--forecast", action="store_true", help="note when history is insufficient")
    ap.add_argument("--fail-on-warn", action="store_true", help="exit 11 in the soft zone")
    ap.add_argument("--warn-5h", type=float, default=DEFAULT_THRESHOLDS["warn_5h"])
    ap.add_argument("--max-5h", type=float, default=DEFAULT_THRESHOLDS["max_5h"])
    ap.add_argument("--warn-7d", type=float, default=DEFAULT_THRESHOLDS["warn_7d"])
    ap.add_argument("--max-7d", type=float, default=DEFAULT_THRESHOLDS["max_7d"])
    ap.add_argument("--window", type=int, default=1800, help="burn-rate lookback (s)")
    ap.add_argument("--max-age", type=int, default=900, help="staleness cutoff (s)")
    ap.add_argument("--mark", metavar="LABEL", help="record a calibration mark and exit")
    ap.add_argument("--label", help="which mark label to calibrate from")
    ap.add_argument(
        "--refresh", action="store_true", help="nudge a fresh statusline write and wait for it"
    )
    ap.add_argument("--wait", action="store_true", help="if wait_for_reset, poll until reset")
    ap.add_argument("--max-wait", type=int, default=21600)
    args = ap.parse_args(argv)
    provider_name = args.provider or (
        "codex" if os.environ.get("CODEX_THREAD_ID") else "claude-code"
    )
    provider = registry.get(provider_name)
    session_path = provider.locate("current") if provider_name != "claude-code" else None

    th = {
        "warn_5h": args.warn_5h,
        "max_5h": args.max_5h,
        "warn_7d": args.warn_7d,
        "max_7d": args.max_7d,
    }
    err = _validate_thresholds(th)
    if err:
        print(f"usage-check: {err}", file=sys.stderr)
        return EXIT_ERROR

    if args.mark:
        return _do_mark(args.mark, args.quiet, provider_name, session_path)

    if args.refresh and provider_name == "claude-code":
        _maybe_refresh(args.quiet)

    kw = {
        "thresholds": th,
        "window_s": args.window,
        "max_age": args.max_age,
        "fail_on_warn": args.fail_on_warn,
        "label": args.label,
    }
    try:
        r = analysis.read_quota(provider=provider_name, session_path=session_path, **kw)
    except Exception as e:  # noqa: BLE001
        if not args.quiet:
            print(f"usage-check: error: {e}", file=sys.stderr)
        return EXIT_ERROR

    if isinstance(r, dict):  # degraded (no_cache / no_rate_limits)
        if not args.quiet:
            (
                print(json.dumps(r))
                if args.json
                else print(
                    f"usage-check: {r['status']} (Pro/Max only, after first API response)",
                    file=sys.stderr,
                )
            )
        return EXIT_NO_DATA

    if args.wait and r.action == "wait_for_reset":
        return _do_wait(r, args)

    if not args.quiet:
        if args.json:
            print(json.dumps(r.to_dict(), indent=2))
        else:
            print(_human(r))
            if (
                args.forecast
                and r.five_hour.burn_pct_per_min is None
                and r.seven_day.burn_pct_per_min is None
            ):
                print(
                    f"  burn   : insufficient history ({r.forecast['samples']} samples "
                    f"in {r.forecast['window_s']}s window; need ≥2)"
                )
    return r.exit_code


def _do_mark(label: str, quiet: bool, provider: str, session_path) -> int:
    rate_limits, _, status = reader.load_latest(provider=provider, session_path=session_path)
    if status != "ok":
        print(f"usage-check: cannot mark — {status}", file=sys.stderr)
        return EXIT_NO_DATA
    fh = rate_limits.get("five_hour") or {}
    sd = rate_limits.get("seven_day") or {}
    if fh.get("available", True) is False or fh.get("used_percentage") is None:
        if not quiet:
            print(
                f"usage-check: cannot mark — {provider} exposes no five-hour window",
                file=sys.stderr,
            )
        return EXIT_NO_DATA
    rec = {
        "ts": int(time.time()),
        "label": label,
        "provider": provider,
        "h5u": fh.get("used_percentage"),
        "h5r": fh.get("resets_at"),
        "d7u": sd.get("used_percentage"),
        "d7r": sd.get("resets_at"),
    }
    reader.append_mark(rec)
    if not quiet:
        print(f"marked {label!r} @ 5h={rec['h5u']}% 7d={rec['d7u']}%")
    return 0


def _do_wait(r, args) -> int:
    # fix #4 — poll in short increments instead of one long blocking sleep
    if r.seconds_until_ok > args.max_wait:
        if not args.quiet:
            print(
                f"usage-check: reset {_fmt_dur(r.seconds_until_ok)} away (> --max-wait); not waiting",
                file=sys.stderr,
            )
        return r.exit_code
    deadline = time.time() + r.seconds_until_ok + 30
    while time.time() < deadline:
        time.sleep(min(30, max(1, deadline - time.time())))
    if not args.quiet:
        print("usage-check: window elapsed — re-run to confirm", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
