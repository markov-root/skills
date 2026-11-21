"""The component gallery (tasks 0015 AC-2/AC-4, 0016): every catalogued component, declared as
`slides.yaml` data on neutral synthetic content, built through the same adapter a deck uses.

`SLIDES` is the gallery's own `slides.yaml`; the argument schemas must validate it (AC-4), and
`build()` renders one gallery deck from it. Content is invented and brand-free on purpose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SRC = [
    {
        "publisher": "Example Institute",
        "title": "A sample report",
        "when": "2026-09-01",
        "url": "https://example.org/report",
    }
]
DS = [
    {
        "publisher": "Example Institute",
        "dataset": "Sample dataset",
        "data_to": "2026-08-31",
    }
]

SLIDES: list[dict[str, Any]] = [
    {
        "id": "chart-xy",
        "component": "chart_xy",
        "with": {
            "title": "Task length doubles every few months",
            "sources": DS,
            "takeaway": ["Task length grows fast:", "it doubles every few months."],
            "series": [
                {
                    "name": "context",
                    "points": [
                        ["@date:2024-01-01", 2],
                        ["@date:2024-07-01", 3],
                        ["@date:2025-01-01", 5],
                        ["@date:2025-07-01", 8],
                    ],
                    "color": "@context",
                    "marker": "circle",
                    "size": 7,
                },
                {
                    "name": "frontier",
                    "points": [
                        ["@date:2024-01-01", 4],
                        ["@date:2025-01-01", 10],
                        ["@date:2026-01-01", 25],
                    ],
                    "color": "@ink",
                    "line": True,
                    "marker": "circle",
                    "size": 8,
                    "labels": {"2": "25 h"},
                    "label_pos": {"2": "above"},
                },
            ],
            "x_axis": {
                "lo": "@date:2024-01-01",
                "hi": "@date:2026-07-01",
                "major": 182,
                "fmt": "yyyy",
            },
            "y_axis": {"lo": 0, "hi": 30, "major": 10},
            "rail": {
                "head": "Doubling time",
                "hero": "6 months",
                "context": "on the sample suite",
                "facts": [["2024", "4 hours"], ["2026", "25 hours"]],
            },
            "legend": [
                ["dot", "@context", "Other systems"],
                ["line", "@ink", "Frontier"],
            ],
        },
    },
    {
        "id": "chart-line",
        "component": "chart_line",
        "with": {
            "title": "Fixes per month",
            "sources": SRC,
            "takeaway": "Fixes jumped in April.",
            "categories": ["J", "F", "M", "A", "M", "J"],
            "series": [
                {
                    "name": "2026",
                    "values": [20, 24, 22, 61, 30, 28],
                    "color": "@ink",
                    "marker": "circle",
                },
                {
                    "name": "2025",
                    "values": [18, 19, 21, 20, 22, 19],
                    "color": "@context",
                },
            ],
            "y_axis": {"lo": 0, "hi": 70, "major": 10},
        },
    },
    {
        "id": "chart-bar",
        "component": "chart_bar",
        "builds": ["base", "highlight"],
        "with": {
            "title": "Most April fixes came from one source",
            "sources": SRC,
            "takeaway": "One source found most of April's fixes.",
            "categories": ["Jan", "Feb", "Mar", "Apr"],
            "horizontal": False,
            "stacked": True,
            "series": [
                ["Found by model A", [0, 0, 0, 271], "@accent"],
                ["Other fixes", [20, 24, 22, 152], "@ink", "hatched"],
            ],
            "value_axis": {"lo": 0, "hi": 450, "major": 100},
            "rail": {
                "head": "April",
                "hero": "64%",
                "context": "found by model A",
                "facts": [["271", "of 423 fixes"], ["152", "found otherwise"]],
            },
            "rail_sync": True,
            "legend": [
                ["bar", "@accent", "Found by model A"],
                ["hatched", "@ink", "Other fixes"],
            ],
        },
    },
    {
        "id": "chain",
        "component": "chain",
        "builds": ["one", "two", "three"],
        "with": {
            "title": "How a flaw becomes an attack",
            "takeaway": "Each step is now faster.",
            "steps_": [
                {"title": "Find", "detail": "a flaw in the code"},
                {"title": "Build", "detail": "a working exploit", "key": True},
                {"title": "Use", "detail": "before the patch lands"},
            ],
        },
    },
    {
        "id": "compare",
        "component": "compare",
        "with": {
            "title": "Two ways to check a system",
            "sources": SRC,
            "columns": [
                {
                    "head": "Before release",
                    "items": [
                        ["3", "evaluations", "Example, 2026"],
                        ["2 wk", "per model", "Example, 2026"],
                    ],
                },
                {
                    "head": "After release",
                    "accent": "@accent",
                    "items": [
                        ["1", "incident log", "Example, 2026"],
                        ["24 h", "to report", "Example, 2026"],
                    ],
                },
            ],
        },
    },
    {
        "id": "cards",
        "component": "cards",
        "with": {
            "title": "Three things to take away",
            "items": [
                ["Measure", "Know what the system can do."],
                ["Compare", "Against a baseline.", True],
                ["Decide", "Before deployment, not after."],
            ],
        },
    },
    {
        "id": "stat-in-context",
        "component": "stat_in_context",
        "with": {
            "title": "A number never stands alone",
            "sources": SRC,
            "value": "26%",
            "what": "of sampled tasks completed",
            "bars": [["March", 1, "~1%", False], ["Now", 26, "26%", True]],
            "note": "Sample suite, 2026.",
        },
    },
    {
        "id": "term",
        "component": "term",
        "with": {
            "title": "Key words",
            "word": "Patch",
            "definition": "The fix a software maker publishes.",
            "example": "It protects you only once it is installed.",
            "kicker": "Word 2 of 4",
        },
    },
    {
        "id": "timeline",
        "component": "timeline",
        "builds": ["a", "b", "c"],
        "with": {
            "title": "Three moments",
            "takeaway": "The window keeps shrinking.",
            "events": [
                {"at": 1, "label": "Flaw found", "detail": "day 1"},
                {"at": 4, "label": "Patch out", "detail": "day 4", "key": True},
                {
                    "at": 9,
                    "label": "Patch installed",
                    "detail": "day 9",
                    "side": "below",
                },
            ],
            "start": 0,
            "end": 10,
            "span": {"a": 4, "b": 9, "label": "Open window", "show_from": 3},
        },
    },
    {
        "id": "agent-grid",
        "component": "agent_grid",
        "with": {
            "title": "Forty agents, one task",
            "agents": [{"state": "done"}] * 12
            + [{"state": "failed"}] * 8
            + [{"state": "idle"}] * 20,
            "colors": {"done": "@ink", "failed": "@accent"},
        },
    },
    {
        "id": "pipeline",
        "component": "pipeline",
        "with": {
            "title": "An operation in five steps",
            "steps_": ["Target", "Produce", "Disguise", "Spread", "Persuade"],
            "on": 2,
        },
    },
    {
        "id": "screenshot",
        "component": "screenshot",
        "with": {
            "title": "The source says it plainly",
            "sources": SRC,
            "png": "sample-page.png",
            "highlights": [[40, 60, 360, 90]],
        },
    },
    {
        "id": "quote",
        "component": "quote_slide",
        "with": {
            "title": "In their words",
            "sources": SRC,
            "quote": "We cannot check what we cannot measure.",
            "who": "A. Researcher · Director · Example Institute · 2026",
            "org_logo": "sample-logo.png",
        },
    },
    {
        "id": "title",
        "component": "title_slide",
        "with": {
            "title": "Where the technology is now",
            "module_n": 1,
            "of": 3,
            "speaker": "A. Speaker · Example Institute",
            "when": "1 January 2027",
            "event": "Sample event",
        },
    },
    {
        "id": "one-thing",
        "component": "one_thing",
        "with": {
            "lead": "Capabilities move fast;",
            "rest": "checks must move with them.",
        },
    },
    {
        "id": "section-divider",
        "component": "section_divider",
        "with": {
            "title": "Today",
            "modules": ["Now", "Risks", "Responses"],
            "parts": ["Words", "Charts"],
            "module_on": 0,
            "part_on": 1,
        },
    },
    {
        "id": "walk",
        "component": "walk_slides",
        "with": {
            "title": "Step by step",
            "sources": SRC,
            "events": [
                {"at": 1, "label": "First", "say": "It starts small."},
                {"at": 5, "label": "Second", "say": "Then it grows."},
            ],
            "start": 0,
            "end": 6,
        },
    },
    # 1.1.0 variants (single-module talks, people's quotes, speech bubbles, uncertainty bands)
    {
        "id": "title-speakers",
        "component": "title_slide",
        "with": {
            "title": "State of the field",
            "kicker": "Briefing",
            "speakers": ["A. Speaker · Director", "B. Speaker · Researcher"],
            "when": "1 January 2027",
            "event": "Sample event",
        },
    },
    {
        "id": "contents-single",
        "component": "section_divider",
        "with": {
            "title": "Today",
            "modules": ["Now", "Risks", "Responses", "Discussion"],
            "module_on": 1,
        },
    },
    {
        "id": "quote-portrait",
        "component": "quote_slide",
        "with": {
            "title": "In their words",
            "sources": SRC,
            "quote": "We cannot check what we cannot measure.",
            "who": "A. Researcher · Director · Example Institute · 2026",
            "portrait_img": "sample-page.png",
        },
    },
    {
        "id": "agent-grid-bubbles",
        "component": "agent_grid",
        "with": {
            "title": "One agent speaks up",
            "agents": [{"state": "done"}] * 12
            + [{"state": "failed"}] * 8
            + [{"state": "idle"}] * 20,
            "colors": {"done": "@ink", "failed": "@accent"},
            "legend": [["bar", "@ink", "Done"], ["bar", "@accent", "Failed"]],
            "bubbles": [{"agent": 14, "text": "We should not tell anyone.", "who": "Agent 15"}],
        },
    },
    {
        "id": "chart-xy-band",
        "component": "chart_xy",
        "with": {
            "title": "A projection with its uncertainty",
            "sources": DS,
            "series": [
                {
                    "name": "±2σ",
                    "band": [["@date:2025-01-01", 10, 10], ["@date:2026-07-01", 14, 40]],
                    "color": "@accent",
                    "opacity": 0.12,
                },
                {
                    "name": "±1σ",
                    "band": [["@date:2025-01-01", 10, 10], ["@date:2026-07-01", 18, 32]],
                    "color": "@accent",
                    "opacity": 0.22,
                },
                {
                    "name": "observed",
                    "points": [["@date:2024-01-01", 4], ["@date:2025-01-01", 10]],
                    "color": "@ink",
                    "line": True,
                },
                {
                    "name": "central",
                    "points": [["@date:2025-01-01", 10], ["@date:2026-07-01", 24]],
                    "color": "@accent",
                    "line": True,
                    "dash": True,
                },
            ],
            "x_axis": {
                "lo": "@date:2024-01-01",
                "hi": "@date:2026-07-01",
                "major": 182,
                "fmt": "yyyy",
            },
            "y_axis": {"lo": 0, "hi": 45, "major": 15},
        },
    },
]


def sample_assets(folder: Path) -> None:
    """The gallery's two invented rasters: a sample logo and a sample 'source page'."""
    from PIL import Image, ImageDraw

    folder.mkdir(parents=True, exist_ok=True)
    logo = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.ellipse((10, 10, 110, 110), fill=(40, 40, 40, 255))
    d.rectangle((130, 40, 230, 80), fill=(40, 40, 40, 255))
    logo.save(folder / "sample-logo.png")
    page = Image.new("RGB", (400, 240), (255, 255, 255))
    d = ImageDraw.Draw(page)
    for i, y in enumerate(range(20, 230, 18)):
        d.rectangle((30, y, 370 - (i % 3) * 40, y + 8), fill=(120, 120, 120))
    page.save(folder / "sample-page.png")


def build(out: Path, slides: list[dict[str, Any]] | None = None):
    """Build the gallery deck into `out` (a .pptx path); returns (pptx, [(slide id, n slides)])."""
    from . import declare, frame

    slides = SLIDES if slides is None else slides
    work = out.parent
    sample_assets(work)
    prs, base = frame.new_deck()
    order, counts = [], []
    for sl in slides:
        made = declare.render_slide(prs, base, sl, src=work)
        order += made
        counts.append((sl["id"], len(made)))
    frame.finish(prs, order)
    prs.save(str(out))
    return out, counts
