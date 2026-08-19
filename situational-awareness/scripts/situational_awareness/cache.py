"""Provider-neutral prompt-cache analysis and `cache-check` CLI.

All conclusions are derived from on-disk provider counters. A cache-bust event is
measured; its cause is inferred unless the transcript records a model change or
compaction event.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass, field

from situational_awareness import core, registry


@dataclass
class CacheEvent:
    turn: int
    previous_hit_ratio: float
    hit_ratio: float
    read_drop_tokens: int
    write_tokens: int
    cause: str
    confidence: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class CacheReading:
    provider: str
    session: str
    samples: int
    input_tokens: int
    read_tokens: int
    write_tokens: int
    uncached_tokens: int
    hit_ratio: float
    current_hit_ratio: float
    trend: str
    status: str
    action: str
    message: str
    busts: list[CacheEvent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    transcript_path: str | None = None

    def to_dict(self) -> dict:
        result = asdict(self)
        result["transcript_path"] = core.display_path(self.transcript_path)
        if not self.busts:
            result.pop("busts")
        if not self.notes:
            result.pop("notes")
        return result


def _ratio(read: int, total: int) -> float:
    return round(read / total, 4) if total > 0 else 0.0


def _cause(previous: core.CacheSample, current: core.CacheSample) -> tuple[str, str, list[str]]:
    if current.event == "compaction":
        return (
            "conversation_compacted",
            "high",
            ["transcript records a compaction boundary before this sample"],
        )
    if previous.model and current.model and previous.model != current.model:
        return (
            "model_changed",
            "high",
            [f"model changed from {previous.model} to {current.model}"],
        )
    evidence = ["cache-read share fell sharply"]
    if current.write_tokens > 0:
        evidence.append("cache writes increased on the same turn")
        return (
            "prefix_changed_or_cache_expired",
            "medium",
            evidence,
        )
    return (
        "prefix_changed_cache_expired_or_routing_changed",
        "low",
        evidence,
    )


def analyze(
    provider: str,
    session: str,
    samples: list[core.CacheSample],
    transcript_path: str | None = None,
    lookback: int = 8,
) -> CacheReading:
    """Aggregate recent cache telemetry and flag sharp cache-read collapses."""
    if not samples:
        raise LookupError("no cache counters in transcript")
    recent = samples[-lookback:]
    total = sum(s.input_tokens for s in recent)
    reads = sum(s.read_tokens for s in recent)
    writes = sum(s.write_tokens for s in recent)
    uncached = sum(s.uncached_tokens for s in recent)
    ratios = [_ratio(s.read_tokens, s.input_tokens) for s in recent]
    current_ratio = ratios[-1]
    hit_ratio = _ratio(reads, total)

    if len(ratios) < 3:
        trend = "insufficient_data"
    else:
        midpoint = len(ratios) // 2
        before = sum(ratios[:midpoint]) / midpoint
        after = sum(ratios[midpoint:]) / (len(ratios) - midpoint)
        delta = after - before
        trend = "improving" if delta >= 0.10 else "declining" if delta <= -0.10 else "stable"

    busts: list[CacheEvent] = []
    for idx, (previous, current) in enumerate(itertools.pairwise(recent), start=1):
        prev_ratio = _ratio(previous.read_tokens, previous.input_tokens)
        curr_ratio = _ratio(current.read_tokens, current.input_tokens)
        # Require a previously useful cache and a material collapse. This avoids
        # flagging ordinary cold starts and small-token rounding noise.
        if prev_ratio < 0.50 or prev_ratio - curr_ratio < 0.35:
            continue
        cause, confidence, evidence = _cause(previous, current)
        busts.append(
            CacheEvent(
                turn=len(samples) - len(recent) + idx + 1,
                previous_hit_ratio=prev_ratio,
                hit_ratio=curr_ratio,
                read_drop_tokens=max(0, previous.read_tokens - current.read_tokens),
                write_tokens=current.write_tokens,
                cause=cause,
                confidence=confidence,
                evidence=evidence,
            )
        )

    if len(samples) < 2:
        status, action = "warming", "observe"
        message = "cache telemetry available; need another turn to assess reuse"
    elif busts and busts[-1].turn == len(samples):
        status, action = "bust_detected", "investigate"
        message = f"cache hit ratio fell to {current_ratio:.0%}; investigate the recorded bust"
    elif hit_ratio >= 0.75:
        status, action = "healthy", "continue"
        message = f"cache healthy: {hit_ratio:.0%} of recent input tokens served from cache"
    elif hit_ratio >= 0.40:
        status, action = "partial", "watch"
        message = f"cache partial: {hit_ratio:.0%} recent hit ratio; keep the prompt prefix stable"
    else:
        status, action = "cold", "optimize"
        message = f"cache cold: {hit_ratio:.0%} recent hit ratio; check prefix stability and TTL"

    notes = []
    if all(s.write_tokens == 0 for s in recent):
        notes.append(
            "provider reported no cache-write tokens; writes may be free, implicit, or absent"
        )
    return CacheReading(
        provider=provider,
        session=session,
        samples=len(samples),
        input_tokens=total,
        read_tokens=reads,
        write_tokens=writes,
        uncached_tokens=uncached,
        hit_ratio=hit_ratio,
        current_hit_ratio=current_ratio,
        trend=trend,
        status=status,
        action=action,
        message=message,
        busts=busts,
        notes=notes,
        transcript_path=transcript_path,
    )


def read_current(session: str = "current", provider_name: str | None = None) -> CacheReading:
    if provider_name:
        provider = registry.get(provider_name)
        path = provider.locate(session)
    else:
        provider, path = registry.detect(session)
    if provider is None or path is None:
        raise LookupError(f"could not locate session {session!r}")
    raw = provider.read(path)
    sid = provider.resolve_session_id(session, path)
    return analyze(provider.name, sid, raw.cache_series, str(path))


def _human(reading: CacheReading) -> str:
    lines = [
        (
            f"cache-aware · {reading.provider} · {reading.hit_ratio:.0%} recent hit · "
            f"{reading.current_hit_ratio:.0%} current · {reading.trend} → {reading.action}"
        ),
        (
            f"  read {reading.read_tokens:,} · write {reading.write_tokens:,} · "
            f"uncached {reading.uncached_tokens:,} tokens ({reading.samples} total samples)"
        ),
    ]
    for bust in reading.busts[-3:]:
        lines.append(
            f"  bust turn {bust.turn}: {bust.previous_hit_ratio:.0%} → {bust.hit_ratio:.0%} · "
            f"{bust.cause} ({bust.confidence} confidence)"
        )
    for note in reading.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cache-check",
        description="Report prompt-cache efficiency and cache-bust events from local transcripts.",
    )
    ap.add_argument("session", nargs="?", default="current")
    ap.add_argument("--provider", choices=registry.names())
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    try:
        reading = read_current(args.session, args.provider)
    except LookupError as exc:
        if not args.quiet:
            print(f"cache-check: no data ({exc})")
        return core.EXIT_NO_DATA
    except Exception as exc:  # noqa: BLE001
        if not args.quiet:
            print(f"cache-check: error: {exc}")
        return core.EXIT_ERROR
    if not args.quiet:
        print(json.dumps(reading.to_dict(), indent=2) if args.json else _human(reading))
    # Cache health is advisory: a cold cache must never block useful work.
    return core.EXIT_CONTINUE


if __name__ == "__main__":
    raise SystemExit(main())
