"""The slide frame every component slide is copied from, built from the tokens (task 0015).

A frame slide holds: a title band text box (above `kit.TITLE_TOP`, so `kit.style` sets the
title), a left hairline, a footer hairline at 6.94 in, and the `mark_png` logo when the tokens
name one. The frame is the deck's first slide; `finish()` drops it from the final order.
"""

from __future__ import annotations

from pptx import Presentation
from pptx.util import Emu

from . import brand
from . import components as cx
from . import kit as dk

SLIDE_W, SLIDE_H = 12192000, 6858000  # 13.333 in × 7.5 in, 16:9


def new_deck():
    """(prs, base): an empty 16:9 deck whose only slide is the frame."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(SLIDE_W), Emu(SLIDE_H)
    base = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    cx.text(
        base,
        cx.X0,
        int(0.32 * cx.IN),
        cx.X1 - cx.X0,
        int(0.5 * cx.IN),
        "Title",
        24,
        cx.NAVY,
        font=dk.DISPLAY,
        name="frame-title",
    )
    cx.vrule(
        base, int(0.95 * cx.IN), int(0.35 * cx.IN), int(6.59 * cx.IN), name="frame-left"
    )
    cx.rule(base, cx.X0, int(6.94 * cx.IN), cx.X1 - cx.X0, name="frame-footer")
    mark = brand.logo("mark_png")
    if mark is not None:
        cx.logo(  # the left column: the mark on top, the slide counter at its foot
            base,
            mark,
            int(0.255 * cx.IN),
            int(0.3 * cx.IN),
            int(0.44 * cx.IN),
            name="frame-logo",
            navy=False,
        )
    return prs, base


def finish(prs, slides):
    """Make `slides` the deck, in order; the frame and any unused slide are dropped. Every
    framed slide gets its position, "n / N", at the foot of the left column."""
    dk.reorder(prs, slides)
    n = len(slides)
    for i, s in enumerate(slides, 1):
        if any(sh.name == "frame-left" for sh in s.shapes):
            cx.text(
                s,
                int(0.1 * cx.IN),
                int(6.98 * cx.IN),
                int(0.75 * cx.IN),
                int(0.25 * cx.IN),
                f"{i} / {n}",
                9,
                cx.LABEL,
                align=cx.PP_ALIGN.CENTER,
                name="frame-counter",
            )
    return prs


def section_kicker(slide, number: int, name: str) -> None:
    """The section a slide belongs to, as a small caps line (soft ink) above its title; the title
    moves down to make room (components 1.2.0)."""
    title = next((sh for sh in slide.shapes if sh.name == "frame-title"), None)
    if title is None:
        return
    title.top = int(0.52 * cx.IN)
    cx.label(
        slide,
        cx.X0,
        int(0.26 * cx.IN),
        int(6 * cx.IN),
        f"{number:02d} · {name}",
        cx.SOFT,
        size=9.5,
        name="frame-kicker",
    )
