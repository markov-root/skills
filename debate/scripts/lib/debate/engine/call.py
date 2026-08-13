"""One model call for one debate round: generate -> cache raw -> parse -> validate -> persist.

Split out of the debate loop (task-0024): the loop owns round SEQUENCING; this owns a single
resumable CALL. Task-agnostic — the task supplies the prompt and schema; this caches, validates,
and records. Resumable at two levels (a completed step is skipped; a cached raw is re-parsed
without re-calling the model, unless that raw is itself unusable).
"""

from __future__ import annotations

import logging
import time

from debate.backends import CallRecord, Debater, extract_json
from debate.engine.artifacts import RunStore
from debate.engine.validate import validate_output
from debate.tasks.base import DebateTask

_log = logging.getLogger("debate.engine.call")

_ROUND_DIR = {
    "propose": "round-1-propose",
    "critique": "round-2-critique",
    "revise": "round-3-revise",
    "redteam": "round-4-redteam",
    "respond": "round-5-respond",
}


def _round_dir(round_name: str) -> str:
    """Storage dir for a round. Fixed rounds get their numbered name; dynamic escalation rounds
    ("escalate-1", "respond-2") get a stable `round-<name>` dir so resume keys them cleanly."""
    return _ROUND_DIR.get(round_name, f"round-{round_name}")


def _with_persona(system: str, debater: Debater) -> str:
    """Prepend this voice's optional persona to its system prompt (task-0008). The persona is the
    voice's expert LENS — it shapes only this voice, is NEVER shown to peers/arbitrator (blinding is
    preserved), and defaults to none so a persona-less debate's prompt is byte-identical."""
    persona = getattr(debater, "persona", None)
    return f"{persona.strip()}\n\n{system}" if persona else system


# A model occasionally returns a 200 with truncated/malformed JSON (provider-side cutoff, not a
# clean max_tokens stop). That's usually flaky, so re-call a bounded number of times before
# failing the whole run — one bad response shouldn't kill an hour-long debate.
_PARSE_ATTEMPTS = 3


def produce(
    task: DebateTask,
    debater: Debater,
    round_name: str,
    user: str,
    store: RunStore,
    metrics: list[dict] | None = None,
    *,
    stage: str | None = None,
):
    """One model call for one round: generate -> cache raw -> parse -> validate -> persist.

    Resumable at two levels: a completed (validated) step is skipped; an interrupted step whose
    raw response was cached is re-parsed without re-calling the model — UNLESS that cached raw is
    itself unparseable (e.g. a truncated/malformed response), in which case it is discarded and the
    model is re-called, so a bad response can't poison resume into crashing forever. When a live
    model call happens, its wall-clock + token/cost telemetry are appended to `metrics`.
    """
    stage = stage or round_name  # dynamic rounds ("respond-2") share a stage's prompt/schema
    rdir = _round_dir(round_name)

    def _emit_cached_record() -> None:
        # L0 (audit E-1): a cache hit is NOT lossy — its record was written on the original live
        # call and is re-read from disk. Only synthesize an explicit-null stub for a run whose calls
        # predate L0 capture, so `calls.jsonl` still has one row per call.
        if not store.has_call_record(rdir, debater.id):
            store.write_call_record(
                rdir, debater.id, CallRecord.cached_stub(debater, round_name, stage).to_dict()
            )

    if store.has(rdir, debater.id):
        _emit_cached_record()
        if metrics is not None:
            metrics.append({"round": round_name, "debater": debater.id, "cached": True})
        return store.read(rdir, debater.id)
    schema = task.output_schema(stage)
    invalid_dump = store.dir / "_invalid" / f"{rdir}-{debater.id}.json"
    # A cached raw is reusable only if it both PARSES and VALIDATES. A truncated/garbage raw (parse
    # error) or a well-formed-but-wrong-shape raw (schema error) must be re-called, never re-served
    # into a crash on every resume — both are ValueError (OutputSchemaError subclasses it).
    if store.has_raw(rdir, debater.id):
        try:
            out = extract_json(store.read_raw(rdir, debater.id))
            if schema:
                validate_output(out, schema, context=f"{debater.id} {round_name}")
        except ValueError:
            out = None  # bad cached raw → fall through to a fresh call
        if out is not None:
            _emit_cached_record()
            if metrics is not None:
                metrics.append({"round": round_name, "debater": debater.id, "cached": True})
            store.write(rdir, debater.id, out)
            return out

    # One bad response shouldn't kill an hour-long paid debate: retry parse AND schema failures a
    # bounded number of times, feeding the rejection reason back so the re-call can self-correct
    # (esp. a missing required field). Only after the last attempt do we raise.
    correction = ""
    system = _with_persona(
        task.system_prompt(stage), debater
    )  # task-0008 (constant across retries)
    for attempt in range(1, _PARSE_ATTEMPTS + 1):
        t0 = time.perf_counter()
        raw = debater.generate(system, user + correction, want_json=True)
        wall_s = round(time.perf_counter() - t0, 2)
        store.write_raw(rdir, debater.id, raw)  # persist BEFORE parse/validate can fail
        if metrics is not None:
            metrics.append(
                {
                    "round": round_name,
                    "debater": debater.id,
                    "backend": getattr(debater, "backend", None),  # split real vs notional cost
                    "wall_s": wall_s,
                    "attempt": attempt,
                    **(getattr(debater, "last_meta", {}) or {}),
                }
            )
        try:
            out = extract_json(raw)
            if schema:
                validate_output(
                    out, schema, context=f"{debater.id} {round_name}", dump_to=invalid_dump
                )
        except ValueError as e:  # JSON-parse failure OR OutputSchemaError (a ValueError subclass)
            if attempt == _PARSE_ATTEMPTS:
                raise
            _log.warning(
                "%s %s: unusable response (attempt %d/%d) — re-calling: %s",
                debater.id,
                round_name,
                attempt,
                _PARSE_ATTEMPTS,
                str(e)[:200],
            )
            correction = (
                f"\n\nYOUR PREVIOUS RESPONSE WAS REJECTED: {str(e)[:500]}\n"
                "Return a corrected single JSON object that fixes this and satisfies the "
                "required schema exactly."
            )
            continue
        # L0 (audit E-1): capture the normalized CallRecord from the just-succeeded call's telemetry
        # BEFORE returning, so every live call has a durable, re-readable row (superset, explicit
        # nulls). Written per call; the loop folds them into calls.jsonl at the end of the run.
        store.write_call_record(
            rdir,
            debater.id,
            CallRecord.from_call(
                debater, round_name, stage, latency_ms=wall_s * 1000, attempt=attempt, cached=False
            ).to_dict(),
        )
        store.write(rdir, debater.id, out)
        return out
