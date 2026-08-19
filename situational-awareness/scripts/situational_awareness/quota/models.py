"""Quota data shapes + constants. JSON schema mirrors usage-check's --json output
(feature parity), with the bug-fixes from docs/lessons/0003 baked in."""

from __future__ import annotations

from dataclasses import dataclass

# thresholds (used%); defaults match usage-check
DEFAULT_THRESHOLDS = {"warn_5h": 80.0, "max_5h": 90.0, "warn_7d": 80.0, "max_7d": 90.0}
DEFAULT_WINDOW_S = 1800  # burn-rate lookback
DEFAULT_MAX_AGE_S = 900  # staleness cutoff

# exit codes (mirror usage-check exactly — load-bearing for gates)
EXIT_CONTINUE = 0
EXIT_WIND_DOWN = 11
EXIT_WAIT = 10
EXIT_NO_DATA = 3
EXIT_ERROR = 2


@dataclass
class Window:
    """One rate-limit window (five_hour / seven_day)."""

    name: str
    used_pct: float
    remaining_pct: float
    resets_at: int | None
    resets_in_s: int | None  # None when unknown (fix #1 — never -1)
    burn_pct_per_min: float | None
    eta_min_to_max: float | None
    available: bool = True

    def to_dict(self) -> dict:
        return {
            "used_pct": self.used_pct,
            "remaining_pct": self.remaining_pct,
            "resets_at": self.resets_at,
            "resets_in_s": self.resets_in_s,
            "burn_pct_per_min": self.burn_pct_per_min,
            "eta_min_to_max": self.eta_min_to_max,
            "available": self.available,
        }


@dataclass
class QuotaReading:
    status: str  # ok | no_cache | no_rate_limits
    action: str  # continue | wind_down | wait_for_reset
    binding: str  # five_hour | seven_day
    seconds_until_ok: int
    stale: bool
    age_seconds: int | None  # None when unknown (fix #2 ⇒ stale)
    five_hour: Window
    seven_day: Window
    thresholds: dict
    forecast: dict
    exit_code: int = EXIT_CONTINUE
    provider: str = "claude-code"
    source: str = "statusline"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "action": self.action,
            "binding": self.binding,
            "seconds_until_ok": self.seconds_until_ok,
            "stale": self.stale,
            "age_seconds": self.age_seconds,
            "five_hour": self.five_hour.to_dict(),
            "seven_day": self.seven_day.to_dict(),
            "thresholds": self.thresholds,
            "forecast": self.forecast,
            "provider": self.provider,
            "source": self.source,
        }
