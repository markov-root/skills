"""Quota math: burn-rate, ETA, action/binding, mark calibration. Pure functions +
one orchestrator (`build_reading`). Mirrors usage-check's logic with the fixes in
docs/lessons/0003.
"""

from __future__ import annotations

import itertools
import math
import time

from situational_awareness.quota import reader
from situational_awareness.quota.models import (
    DEFAULT_MAX_AGE_S,
    DEFAULT_THRESHOLDS,
    DEFAULT_WINDOW_S,
    EXIT_CONTINUE,
    EXIT_WAIT,
    EXIT_WIND_DOWN,
    QuotaReading,
    Window,
)

RESET_TOL = 60  # s — "same window" if |Δresets_at| < tol (fix #11)


def _clamp_pct(x) -> float:
    if x is None:  # fix #8 — present-but-null used_percentage → 0 (parity with .sh `// 0`)
        return 0.0
    return round(min(100.0, max(0.0, float(x))), 1)  # fix #6


def _resets_in(resets_at, now: float) -> int | None:
    if not resets_at:
        return None  # fix #1 — unknown is null, never -1
    return max(0, int(resets_at) - int(now))


def _same_window(r0, r1) -> bool:
    return r0 is not None and r1 is not None and abs(int(r0) - int(r1)) < RESET_TOL


def burn(rows: list[dict], ukey: str, rkey: str, window_s: int, now: float):
    """(%/min, samples). Sum positive deltas where the reset epoch is unchanged;
    both values come from the SAME filtered/sorted rows (fix #5)."""
    pts = [
        (r["ts"], float(r[ukey]), r.get(rkey))
        for r in rows
        if r.get("ts") is not None and r.get(ukey) is not None and r["ts"] >= now - window_s
    ]
    pts.sort(key=lambda p: p[0])
    if len(pts) < 2:
        return None, len(pts)
    total = sum(
        u1 - u0
        for (_, u0, r0), (_, u1, r1) in itertools.pairwise(pts)
        if _same_window(r0, r1) and u1 > u0
    )
    dmin = (pts[-1][0] - pts[0][0]) / 60.0
    if dmin <= 0:
        return None, len(pts)
    return round(total / dmin, 4) if total > 0 else 0.0, len(pts)


def eta(used: float, maxthr: float, rate: float | None) -> float | None:
    if rate is None or rate <= 0:
        return None
    d = maxthr - used
    return 0.0 if d <= 0 else round(d / rate, 1)


def mark_cost(marks: list[dict], label: str, provider: str = "claude-code"):
    """(mean 5h-% consumed per marked iteration, n) for a label."""
    rows = sorted(
        (
            (m["ts"], float(m["h5u"]), m.get("h5r"))
            for m in marks
            if m.get("label") == label
            and m.get("provider", "claude-code") == provider
            and m.get("h5u") is not None
            and m.get("ts") is not None
        ),
        key=lambda p: p[0],
    )
    deltas = [
        u1 - u0
        for (_, u0, r0), (_, u1, r1) in itertools.pairwise(rows)
        if _same_window(r0, r1) and u1 > u0
    ]
    if not deltas:
        return None, 0
    return round(sum(deltas) / len(deltas), 3), len(deltas)


def _ge(a, b) -> bool:
    return float(a) >= float(b)


def _binding(u5, u7, th, rin5, rin7, eta5, eta7, over, available5, available7) -> str:
    if available5 and not available7:
        return "five_hour"
    if available7 and not available5:
        return "seven_day"
    if over:
        b5 = available5 and _ge(u5, th["max_5h"])
        b7 = available7 and _ge(u7, th["max_7d"])
        if b5 and b7:
            return "five_hour" if (rin5 or 0) >= (rin7 or 0) else "seven_day"
        return "five_hour" if b5 else "seven_day"
    if eta5 is not None and eta7 is not None:
        return "five_hour" if eta5 <= eta7 else "seven_day"
    if eta5 is not None:
        return "five_hour"
    if eta7 is not None:
        return "seven_day"
    return "five_hour" if (th["max_5h"] - u5) <= (th["max_7d"] - u7) else "seven_day"


def build_reading(
    rate_limits: dict,
    age: int | None,
    history: list[dict],
    marks: list[dict],
    *,
    thresholds=None,
    window_s=DEFAULT_WINDOW_S,
    max_age=DEFAULT_MAX_AGE_S,
    fail_on_warn=False,
    label=None,
    now: float | None = None,
    provider="claude-code",
    source="statusline",
) -> QuotaReading:
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    now = now if now is not None else time.time()

    fh = rate_limits.get("five_hour") or {}
    sd = rate_limits.get("seven_day") or {}
    available5 = bool(fh) and fh.get("available", True) is not False
    available7 = bool(sd) and sd.get("available", True) is not False
    u5 = _clamp_pct(fh.get("used_percentage", 0))
    u7 = _clamp_pct(sd.get("used_percentage", 0))
    r5 = fh.get("resets_at") or None
    r7 = sd.get("resets_at") or None
    rin5, rin7 = _resets_in(r5, now), _resets_in(r7, now)

    rate5, _ = burn(history, "h5u", "h5r", window_s, now)
    rate7, _ = burn(history, "d7u", "d7r", window_s, now)
    eta5, eta7 = eta(u5, th["max_5h"], rate5), eta(u7, th["max_7d"], rate7)

    over, sec_ok = False, 0
    if available5 and _ge(u5, th["max_5h"]):
        over, sec_ok = True, max(sec_ok, rin5 or 0)
    if available7 and _ge(u7, th["max_7d"]):
        over, sec_ok = True, max(sec_ok, rin7 or 0)
    if over:
        action, exit_code = "wait_for_reset", EXIT_WAIT
    elif (available5 and _ge(u5, th["warn_5h"])) or (available7 and _ge(u7, th["warn_7d"])):
        action, sec_ok = "wind_down", 0
        exit_code = EXIT_WIND_DOWN if fail_on_warn else EXIT_CONTINUE
    else:
        action, sec_ok, exit_code = "continue", 0, EXIT_CONTINUE

    binding = _binding(u5, u7, th, rin5, rin7, eta5, eta7, over, available5, available7)

    if label is None and marks:
        label = marks[-1].get("label")
    cost, costn, iters = None, 0, None
    if label and marks:
        cost, costn = mark_cost(marks, label, provider)
        if cost and cost > 0:
            headroom = th["max_5h"] - u5
            iters = max(0, math.floor(headroom / cost)) if headroom > 0 else 0

    stale = age is None or age > max_age  # fix #2
    # samples = count of ALL in-window history rows (matches the .sh `nsamp`: "how much
    # history do we have", independent of per-window nulls)
    nsamp = sum(1 for h in history if h.get("ts") is not None and h["ts"] >= now - window_s)
    forecast = {
        "samples": nsamp,
        "window_s": window_s,
        "iteration": {
            "label": label,
            "cost_pct_per_iter": cost,
            "samples": costn,
            "iters_left": iters,
        },
    }
    return QuotaReading(
        status="ok",
        action=action,
        binding=binding,
        seconds_until_ok=int(sec_ok),
        stale=stale,
        age_seconds=age,
        five_hour=Window("five_hour", u5, round(100 - u5, 1), r5, rin5, rate5, eta5, available5),
        seven_day=Window("seven_day", u7, round(100 - u7, 1), r7, rin7, rate7, eta7, available7),
        thresholds=th,
        forecast=forecast,
        exit_code=exit_code,
        provider=provider,
        source=source,
    )


def read_quota(*, provider="claude-code", session_path=None, **kw) -> QuotaReading | dict:
    """Top-level: load files and build a reading, or a degraded dict (status+exit)."""
    now = kw.get("now")
    rate_limits, age, status = reader.load_latest(
        now=now, provider=provider, session_path=session_path
    )
    if status != "ok":
        d = {"status": status, "action": "unknown", "provider": provider}
        if age is not None:
            d["age_seconds"] = age
        return d
    is_claude = provider == "claude-code"
    return build_reading(
        rate_limits,
        age,
        reader.load_history() if is_claude else [],
        reader.load_marks(),
        provider=provider,
        source="statusline" if is_claude else "transcript",
        **kw,
    )
