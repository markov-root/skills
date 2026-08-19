"""Handoff generator (task 0004).

`context-check --handoff` emits a ready-to-complete handoff doc: mechanical facts
(session, context %, changed files, open tasks) are pre-filled from disk; the
judgment sections are left for the agent to write. The instruction header encodes
the standard: nothing important should stay trapped in the chat.

The tool cannot summarize the conversation — only the agent can. What this
automates is the trigger, the scaffolding, and the quality bar, every time.
"""

from __future__ import annotations

import datetime
import shutil
import subprocess
from pathlib import Path

from situational_awareness.core import Reading

INSTRUCTION = """\
<!-- INSTRUCTION TO THE AGENT — delete this block before saving -->
Complete every TODO below, then SAVE this file to `{handoff_path}` and post the
"Message to the next agent" section as your final chat message. The standard:

- Nothing important may remain only in this chat. Move durable knowledge to where
  it belongs: decisions -> docs/adrs/, lessons learned -> docs/lessons/, planned
  work -> docs/tasks/ — then reference them here. This handoff is the index, not
  the sole record.
- Give the next agent enough to hit the ground running WITHOUT re-reading the whole
  chat: what's done, what's next, and file:line POINTERS to read for full context.
- Be concrete. "Fixed the parser" is useless; "core.py:88 forecast() skips negative
  deltas (compaction) — see lesson 0002" is a handoff.
- Assume a compaction is coming right after this. Write as if the current context
  window is about to disappear (it is).
"""


def _git(cwd: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        out = subprocess.run(
            [git, "-C", str(cwd), *args], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _open_tasks(cwd: Path) -> list[str]:
    tasks: list[str] = []
    for f in sorted((cwd / "docs" / "tasks").glob("[0-9]*.md")):
        status = title = ""
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines()[:12]:
            low = line.lower()
            if low.startswith("status:"):
                status = line.split(":", 1)[1].strip()
            elif low.startswith("title:"):
                title = line.split(":", 1)[1].strip()
        if status and not status.lower().startswith(("done", "deferred")):
            tasks.append(f"- [{f.stem}] {title} — _{status}_")
    return tasks


def _next_id(cwd: Path) -> str:
    nums = [
        int(f.stem[:4])
        for f in (cwd / "docs" / "handoffs").glob("[0-9]*.md")
        if f.stem[:4].isdigit()
    ]
    return f"{(max(nums) + 1) if nums else 1:04d}"


def render(reading: Reading, cwd: Path | None = None) -> str:
    cwd = cwd or Path.cwd()
    hid = _next_id(cwd)
    handoff_path = f"docs/handoffs/{hid}-<short-title>.md"
    today = datetime.date.today().isoformat()

    changed = _git(cwd, "status", "--porcelain") or "(clean / not a git repo)"
    commits = _git(cwd, "log", "--oneline", "-6") or "(none)"
    tasks = _open_tasks(cwd)
    tasks_block = "\n".join(tasks) if tasks else "- (none open — check docs/tasks/)"
    ctx = f"{reading.remaining_pct:.0f}% remaining ({reading.used_tokens:,}/{reading.window:,}, {reading.action})"

    return f"""{INSTRUCTION.format(handoff_path=handoff_path)}
---
id: {hid}
title: <short session summary>
date: {today}
author: {reading.model or "agent"} ({reading.provider})
context_at_handoff: {ctx}
status: paused
---

## TL;DR
TODO — 2-3 sentences: where things stand and the single most important thing next.

## Done this session
TODO — what changed and why. Recent commits for reference:
```
{commits}
```

## Current state
TODO — what works, what's half-done, what's untested. Uncommitted changes:
```
{changed}
```

## Next steps (in order)
TODO — ordered, concrete. Open tasks on disk:
{tasks_block}

## Key files & entry points
TODO — `path:line` pointers the next agent should READ to get 100% back up to speed.

## Decisions & rationale
TODO — link docs/adrs/ for anything decided; don't leave reasoning only in chat.

## Lessons learned
TODO — record durable gotchas in docs/lessons/ and link them here.

## Gotchas / landmines
TODO — what will bite the next agent.

## Open questions
TODO.

---

## Message to the next agent
TODO — a self-contained paste: who you are picking up from, the goal, exactly where
to start, and which files to read first. The reader should finish this message
already oriented.
"""
