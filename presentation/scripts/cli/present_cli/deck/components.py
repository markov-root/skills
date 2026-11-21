"""The component library (task 0015; ADRs 0007, 0008): native PowerPoint components with one
shared look for every chart, diagram, quote and source line. Every colour, font, size and logo
comes from the active brand token file through `brand.py`; nothing here names a brand.

Import beside the kit:

    from present_cli.deck import components as cx, kit as dk

Rules the components enforce, so a deck cannot drift:

- Native and editable. Charts are python-pptx charts (line, XY scatter, bar, stacked bar) styled by
  `style_chart`; diagrams are native shapes and text. No component places a raster image except a
  logo (`quote_slide`) or a photo/screenshot the caller passes explicitly.
- One source rule. `source_footer` is the ONLY way a source is placed: 9 pt, one line, the same
  position on every slide, `Source: Publisher, Title, Day Month Year` (`src`), datasets as
  `Publisher, Dataset (data to Day Month Year)` (`dataset`), joined with ` · `.
- Density: body 11–14 pt, labels 9–11 pt, rail headline 20–24 pt, hero ≤ 40 pt;
  muted context (the grey token, ink tints), one accent; no outlines, shadows or
  left-border callouts.
- Builds are fresh slides, not animations: a component takes `upto` (how many of its reveal
  items to draw) and `steps` / `chart_slide` draw the same geometry once per build step, so
  every step has identical positions and survives PowerPoint, Google Slides and PDF.

Slide frame: every slide is a copy of a "frame" slide (`base`: logo, left hairline, title band,
footer hairline) with its content removed (`new_slide`); `present_cli.deck.frame` builds one
from the tokens.
"""

from __future__ import annotations

import copy
import math
from datetime import date, datetime
from pathlib import Path

from lxml import etree
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_MARKER_STYLE,
    XL_TICK_LABEL_POSITION,
    XL_TICK_MARK,
)
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from . import brand
from . import kit as dk

# The component library version (task 0015): receipts record it; any visible change bumps it and
# carries a gallery diff in COMPONENTS-CHANGELOG.md (task 0016).
COMPONENTS_VERSION = "1.4.0"


# ---------------------------------------------------------------- palette (from tokens)
NAVY = brand.color("ink")
NAVY2 = brand.color("ink_2")
ORANGE = brand.color("accent")
GREY = brand.color("context")  # context points, baseline bars
GREY_LINE = brand.color("context_line")  # context lines, connectors
TINT = brand.color("tint")  # ink tint fill (tracks, bands)
TINT_ORANGE = brand.color("accent_tint")  # accent tint fill (highlighted spans)
GREEN = brand.color("accent_2")  # a reserved third category
MUTED = dk.MUTED
LABEL = dk.LABEL
RULE = dk.RULE
WHITE = dk.WHITE
GRID = brand.color("grid")  # dotted grid


def _role(name, fallback):
    """A palette role that older token files may lack (added in components 1.4.0)."""
    try:
        return brand.color(name)
    except Exception:  # noqa: BLE001 - a token file without the role keeps its fallback
        return fallback


# The default palette (maintainer, round 5): black, the brand blue and the brand grey (and their
# shades) carry structure and series; orange (ACCENT) is the one highlight; `sunrise(n)` when a
# slide genuinely needs many colours; textures (hatched, dotted, backhatched) and gradations free.
BLUE = _role("brand", NAVY2)  # the brand blue: a second series ink
BRAND_GREY = _role("brand_grey", MUTED)  # the brand grey: a third series ink
BLACK = _role("black", NAVY)
# Orange marks the one thing a slide wants seen; structural accents (kickers, rules, quote marks)
# use a gradation of the ink instead (maintainer, 2026-11-12).


# ---------------------------------------------------------------- texture vocabulary
def tint(color: RGBColor, pct: float) -> RGBColor:
    """`color` mixed with white: pct 100 = full colour, 14 = a light ground."""
    r, g, b = color
    f = pct / 100
    return RGBColor(*(round(c * f + 255 * (1 - f)) for c in (r, g, b)))


TEXTURES = ("solid", "hatched", "backhatched", "dotted", "faded", "shade")
"""One texture vocabulary for every chart series, bar, segment, legend swatch and shape, so
series read by texture as well as tone (decided 9 Nov 2026):

- solid: full colour, the key series ("April: found by model A").
- hatched: 45° lines in the colour at 62% over a 14% ground of the same colour.
- backhatched: the opposite diagonal, 135°; differs from hatched by direction, not density.
- dotted: dots in the colour at 62% over the 14% ground.
- faded: a plain 18% tint (context, e.g. the 2025 baseline); the last resort.
- shade: the 14% ground alone.
Order of use when a chart needs several: solid, hatched, dotted, backhatched, then faded.
Textured fills (all but solid) take a thin 0.5 pt outline in the colour so the edge reads."""
_PATTERN = {"hatched": "ltUpDiag", "backhatched": "ltDnDiag", "dotted": "pct20"}
PATTERN_INK, TEXTURE_GROUND, FADED_TINT = (
    int(brand.size("texture_pattern_ink_pct")),
    int(brand.size("texture_ground_pct")),
    int(brand.size("texture_faded_pct")),
)


SOFT = tint(NAVY, 62)  # structural accent: a gradation of the ink, not the highlight


# ---------------------------------------------------------------- the many-colour ramp
def _srgb_to_oklab(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def _oklab_to_srgb(L, a, b):
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    def enc(v):
        v = min(1.0, max(0.0, v))
        return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return RGBColor(*(round(enc(v) * 255) for v in rgb))


def sunrise(n: int, role: str = "line") -> list:
    """`n` colours from the brand's many-colour ramp (the `score_0` … `score_100` tokens), evenly
    spaced end to end, for a slide that genuinely needs many categories (maintainer, round 5: one
    consistent rainbow, not ad hoc hues). role "fill": the ramp as is (tiles, areas, bars under
    navy text); "line": deepened in OKLab (lightness capped at 0.62, chroma lifted) so lines,
    markers and text read on white. Pair with textures when n > 5. Default palette stays ink /
    context / one accent highlight."""
    stops = [brand.color(f"score_{k}") for k in range(0, 101, 10)]
    out = []
    for i in range(n):
        pos = 0 if n == 1 else i * 10 / (n - 1)
        lo = min(int(pos), 9)
        f = pos - lo
        a, b_ = _srgb_to_oklab(stops[lo]), _srgb_to_oklab(stops[lo + 1])
        L, A, B = (a[j] + (b_[j] - a[j]) * f for j in range(3))
        if role == "line":
            L, A, B = min(L, 0.62), A * 1.6, B * 1.6
        out.append(_oklab_to_srgb(L, A, B))
    return out


def texture(fmt, kind: str, color: RGBColor, outline=True):
    """Apply a texture to anything with python-pptx `.fill` and `.line` (a shape, a chart
    series or point `.format`). kind: one of TEXTURES. Patterned fills are native a:pattFill
    (fg = colour at 62%, bg = 14% ground)."""
    from pptx.enum.dml import MSO_PATTERN

    fill = fmt.fill
    if kind == "solid":
        fill.solid()
        fill.fore_color.rgb = color
    elif kind in ("faded", "shade"):
        fill.solid()
        fill.fore_color.rgb = tint(
            color, FADED_TINT if kind == "faded" else TEXTURE_GROUND
        )
    else:
        fill.patterned()
        fill.pattern = {
            "hatched": MSO_PATTERN.LIGHT_UPWARD_DIAGONAL,
            "backhatched": MSO_PATTERN.LIGHT_DOWNWARD_DIAGONAL,
            "dotted": MSO_PATTERN.PERCENT_20,
        }[kind]
        fill.fore_color.rgb = tint(color, PATTERN_INK)
        fill.back_color.rgb = tint(color, TEXTURE_GROUND)
    if kind != "solid" and outline:
        fmt.line.color.rgb = color
        fmt.line.width = Pt(0.5)
    else:
        fmt.line.fill.background()


BODY, DISPLAY = dk.BODY, dk.DISPLAY

# ---------------------------------------------------------------- geometry (EMU)
IN = 914400
PT = 12700
X0, X1 = (
    int(1.19 * IN),
    int(13.06 * IN),
)  # content left/right edge (title band, footer rule)
Y0, Y1 = (
    int(1.18 * IN),
    int(6.62 * IN),
)  # content top / bottom: 0.32 in clear above the footer hairline (6.94 in), every slide
RAIL_W = int(3.05 * IN)  # rail text width
RAIL_GAP = int(0.3 * IN)  # rail divider to rail text / to main area
FOOTER = (1085850, 6451600, 10852150, 254000)  # the team footer text slot, every slide

MONTHS = "January February March April May June July August September October November December".split()


# ================================================================ sources
def _day(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _month(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{MONTHS[d.month - 1][:3]} {d.year}"


class Source(str):
    """A source line in the house format that also carries its URL (`.url`, or None), so the
    footer can hyperlink it. Behaves as a plain str everywhere else (joins, f-strings)."""

    url: str | None
    short: str

    def __new__(cls, content: str, url: str | None = None, short: str | None = None):
        o = super().__new__(cls, content)
        o.url = url
        o.short = short or content
        return o


def link(content: str, url: str | None, short: str | None = None) -> Source:
    """A free-form source text with its URL (`cx.link("example.org (checked 8 November 2026)",
    "https://example.org")`)."""
    return Source(content, url, short=short)


def src(
    publisher: str, title: str, when, url: str | None = None, short: str | None = None
) -> Source:
    """One source in the house format: `Publisher, Title, Day Month Year` (when: date or ISO str;
    a plain str that is not ISO, e.g. "September 2026", is used as written). url: the page the
    footer links to (record it for every source: notes / data provenance)."""
    try:
        mon = _month(when)
        when = _day(when)
    except (TypeError, ValueError):
        mon = when
    return Source(f"{publisher}, {title}, {when}", url, short=short or f"{publisher}, {mon}")


def dataset(
    publisher: str, name: str, data_to, url: str | None = None, short: str | None = None
) -> Source:
    """One dataset in the house format: `Publisher, Dataset (data to Day Month Year)`; url: the
    dataset's landing page or data URL."""
    return Source(
        f"{publisher}, {name} (data to {_day(data_to)})",
        url,
        short=short or f"{publisher} data to {_month(data_to)}",
    )


_HLINK_CLR_EXT = "{A12FA001-AC4F-418D-AE19-62706E023703}"
_AHYP = "http://schemas.microsoft.com/office/drawing/2018/hyperlinkcolor"


def hyperlink(run, url: str):
    """Hyperlink a text run to url, keeping the run's own colour (PowerPoint 2019+ `ahyp:hlinkClr
    val="tx"`; older viewers fall back to the theme hyperlink colour)."""
    run.hyperlink.address = url
    hl = run._r.find(qn("a:rPr")).find(qn("a:hlinkClick"))
    ext_lst = etree.SubElement(hl, qn("a:extLst"))
    ext = etree.SubElement(ext_lst, qn("a:ext"))
    ext.set("uri", _HLINK_CLR_EXT)
    clr = etree.SubElement(ext, f"{{{_AHYP}}}hlinkClr", nsmap={"ahyp": _AHYP})
    clr.set("val", "tx")
    return run


SOURCES_LABEL = "Sources"
SOURCE_CELLS = 4  # the footer grid: at least four equidistant cells, so positions repeat slide to slide


def cell_row(slide, x, y, w, h, cells, label=None, min_cells=1, size=9, color=None,
             italic=False, name="cells", label_w=None):
    """One row of equidistant cells (components 1.4.0): the table system shared by the `SOURCES`
    footer and figure legends. cells: [{"t", "url"?, "swatch"?: (kind, color)}]; a caps `label`
    (letter-spaced, bold) heads the row; every cell gets the same width, (w - label) /
    max(len(cells), min_cells), a hairline tick between cells. Text that would not fit a cell
    on one line steps the whole row down (size - 1, - 1.5, - 2), so a row keeps one size. Returns the shapes."""
    color = MUTED if color is None else color
    out = []
    lw = 0
    if label:
        lw = label_w or int((len(label) * size * 0.78 + 14) * PT)
        out.append(text(slide, x, y, lw, h, label, size - 1, color, bold=True, spacing=1.2,
                        caps=True, name=f"{name}-label"))
    n = max(len(cells), min_cells)
    if not cells:
        return out
    cw = (w - lw) // n
    sw_w = int(0.36 * IN) if any(c.get("swatch") for c in cells) else 0

    def fits(f):
        return all(len(c["t"]) * f * 0.56 * PT <= cw - int(0.18 * IN) - sw_w for c in cells)

    fs = next((f for f in (size, size - 1, size - 1.5) if fits(f)), size - 2)  # one size per row
    for i, c in enumerate(cells):
        cx0 = x + lw + i * cw
        if i:
            out.append(line(slide, cx0 - int(0.09 * IN), y + int(0.02 * IN), cx0 - int(0.09 * IN),
                            y + int(size * 1.05 * PT), GREY_LINE, 0.5, name=f"{name}-tick-{i}"))
        tx = cx0
        if c.get("swatch"):
            kind, col = c["swatch"]
            tx = cx0 + _swatch(slide, cx0, y + int(size * 0.65 * PT), kind, col, f"{name}-{i}-m")
        avail = cx0 + cw - int(0.18 * IN) - tx
        out.append(text(slide, tx, y, avail, h, [[{"t": c["t"], "url": c.get("url"),
                                                   "italic": italic}]], fs, color,
                        name=f"{name}-{i}", anchor=MSO_ANCHOR.TOP))
    return out


def source_footer(slide, *sources):
    """THE way a source is placed (one rule, every deck; a table since components 1.4.0): under
    the footer hairline, a `SOURCES` label then one equidistant cell per source (at least
    SOURCE_CELLS, so cells line up from slide to slide), each short label ("Hendrycks et al.,
    Jan 2023") italic and hyperlinked to its exact URL. The full references (publisher, title,
    date, URL) go to the slide's speaker notes. A source is cited once: in the footer, never
    again inline. No sources: no footer. Returns the label shape or None."""
    for sh in list(slide.shapes):
        if sh.top >= dk.FOOTER_TOP and sh.height < int(0.5 * IN) and (
            sh.has_text_frame or sh.name.startswith("source-footer")):
            dk.remove(sh)
    items = []
    for s_ in sources:
        if not s_:
            continue
        if isinstance(s_, tuple):
            s_ = Source(*s_)
        if not isinstance(s_, Source):
            s_ = Source(str(s_))
        items.append(s_)
    dk.set_sources(slide, [(str(s_), getattr(s_, "url", None)) for s_ in items])
    if not items:
        return None
    x, y, w, h = FOOTER
    seen, cells = set(), []
    for s_ in items:  # two pages of one publisher in one month read as one label
        if s_.short in seen:
            continue
        seen.add(s_.short)
        cells.append({"t": s_.short, "url": getattr(s_, "url", None)})
    shapes = cell_row(slide, x, y, w, h, cells, label=SOURCES_LABEL, min_cells=SOURCE_CELLS,
                      size=9, italic=True, name="source-footer")
    return shapes[0]


# ================================================================ primitives
def text(
    slide,
    x,
    y,
    w,
    h,
    content,
    size=12,
    color=NAVY,
    bold=False,
    font=BODY,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    name=None,
    spacing=None,
    line=None,
    caps=False,
):
    """Native text box (no margins, wrapped). content: str, or paragraphs = list of lists of runs,
    a run being str or dict(t=, size=, color=, bold=, font=, italic=, url=). spacing: letter spacing in
    pt (caps labels use 1.2). line: line spacing multiple."""
    tb = slide.shapes.add_textbox(Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [[content]]
    for i, runs in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line:
            p.line_spacing = line
        for run in runs if isinstance(runs, list) else [runs]:
            spec = {"t": run} if isinstance(run, str) else run
            r = p.add_run()
            r.text = spec["t"].upper() if caps else spec["t"]
            f = r.font
            f.size = Pt(spec.get("size", size))
            f.color.rgb = spec.get("color", color)
            f.bold = spec.get("bold", bold)
            f.italic = spec.get("italic", False)
            f.name = spec.get("font", font)
            sp = spec.get("spacing", spacing)
            if sp:
                r._r.get_or_add_rPr().set("spc", str(int(sp * 100)))
            if spec.get("url"):
                hyperlink(r, spec["url"])
    return tb


def label(
    slide, x, y, w, content, color=LABEL, size=9.5, name=None, align=PP_ALIGN.LEFT
):
    """Small bold caps label with letter spacing ("APRIL 2026", "TASK LENGTH, 50% SUCCESS")."""
    return text(
        slide,
        x,
        y,
        w,
        int(size * 1.6 * PT),
        content,
        size,
        color,
        bold=True,
        spacing=1.2,
        caps=True,
        name=name,
        align=align,
    )


def box(slide, x, y, w, h, fill=TINT, name=None, shape=MSO_SHAPE.RECTANGLE, tex=None):
    """Filled shape, never a shadow; no outline unless textured (`tex`, see TEXTURES: the
    thin same-colour edge of a hatched/dotted/faded mark)."""
    s = slide.shapes.add_shape(
        shape, Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h))
    )
    texture(s, tex or "solid", fill, outline=False)
    s.shadow.inherit = False
    dk._drop_style(s)
    if name:
        s.name = name
    return s


def rule(slide, x, y, w, color=RULE, weight=0.75, name=None):
    """Horizontal hairline."""
    return line(slide, x, y, x + w, y, color, weight, name=name)


def vrule(slide, x, y, h, color=RULE, weight=0.75, name=None):
    """Vertical hairline (rail divider)."""
    return line(slide, x, y, x, y + h, color, weight, name=name)


def line(
    slide,
    x1,
    y1,
    x2,
    y2,
    color=GREY_LINE,
    weight=1.0,
    dash=False,
    arrow=False,
    name=None,
):
    """Straight connector; arrow=True puts an arrowhead at (x2, y2)."""
    c = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Emu(int(x1)), Emu(int(y1)), Emu(int(x2)), Emu(int(y2))
    )
    c.line.color.rgb = color
    c.line.width = Pt(weight)
    if dash:
        c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    if arrow:
        ln = c.line._get_or_add_ln()
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")
    dk._drop_style(c)
    if name:
        c.name = name
    return c


def dot(slide, cx, cy, d, fill=NAVY, name=None):
    """Filled circle centred on (cx, cy), diameter d."""
    return box(
        slide, cx - d / 2, cy - d / 2, d, d, fill, name=name, shape=MSO_SHAPE.OVAL
    )


LOGO_NAVY = brand.rgb("ink")


def navy_logo(png) -> Path:
    """The monochrome ink (`navy` token) version of a logo PNG (every logo, every deck): ink pixels become navy, white and near-white pixels become transparent (so white
    detail inside a filled mark knocks out to the slide), alpha is kept. Cached once in
    `brand.cache_dir()` as <name>-<hash8>-t.png; a file already named *-navy.png is returned as is."""
    import hashlib

    png = Path(png)
    if png.stem.endswith("-navy"):
        return png
    digest = hashlib.sha256(png.read_bytes()).hexdigest()[:8]
    out = (
        brand.cache_dir() / f"{png.stem}-{digest}-t.png"
    )  # -t: trimmed to ink (logo sizing v2)
    if out.exists():
        return out
    from PIL import Image

    im = Image.open(png).convert("RGBA")
    px = im.load()
    for yy in range(im.height):
        for xx in range(im.width):
            r, g, b, a_ = px[xx, yy]
            if not a_:
                continue
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
            sat = (max(r, g, b) - min(r, g, b)) / 255
            k = min(1.0, max((1 - lum) / 0.25, sat / 0.3))
            px[xx, yy] = (*LOGO_NAVY, int(a_ * k))
    box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if box:  # trim empty margins so every logo's box is its ink (equal sizing needs it)
        im = im.crop(box)
    out.parent.mkdir(parents=True, exist_ok=True)
    import os

    tmp = out.with_suffix(f".{os.getpid()}.tmp.png")
    im.save(tmp)
    os.replace(tmp, out)  # atomic: parallel deck builds never read a half-written file
    return out


# One size per placement type, identical in every deck ("all logos the same size"). Logos are sized by AREA (optical sizing), so a long wordmark and a square mark read as the
# same size; then clamped to the role's height and width. (area in², h_max in, w_max in)
LOGO_ROLES = {
    "quote": (0.6, 0.95, 3.4),  # quote slides, top left, above the quote glyph
    "row": (
        0.22,
        0.47,
        1.5,
    ),  # a logo beside or above text: partner rows, signers, doers, headers
    "label": (0.036, 0.19, 0.21),  # provider mark beside a model label on a chart
}


def logo_size(png, role):
    """(w, h) in EMU for a trimmed logo in a LOGO_ROLES placement: equal area, clamped."""
    from PIL import Image

    area, h_max, w_max = LOGO_ROLES[role]
    with Image.open(png) as im:
        a = im.width / im.height
    # optical sizing: between equal area (a**-0.5) and equal height (a**0), so wide multi-line
    # wordmarks stay readable next to square marks (same size, but legible)
    h = area**0.5 * a**-0.35
    h = min(h, h_max, w_max / a)
    return int(a * h * IN), int(h * IN)


def logo(slide, png, x, y, h=None, name="logo", max_w=None, navy=True, role=None):
    """A logo PNG in monochrome navy (`navy_logo`, trimmed to its ink; navy=False only for a brand
    that must keep its colours, by explicit decision). role ("quote", "row", "label"): the one size
    for that placement type in every deck, area-normalised and centred vertically in the role's
    height band starting at y; h/max_w are then ignored. Without a role (title lockups only): height
    h, width capped at max_w. Logos are the only raster a component places; PNGs live in the
    consumer's logo folder (`brand.logo_dir()`)."""
    if navy:
        png = navy_logo(png)
    if role:
        w_, h_ = logo_size(png, role)
        y = int(y) + (int(LOGO_ROLES[role][1] * IN) - h_) // 2
        pic = slide.shapes.add_picture(
            str(png), Emu(int(x)), Emu(int(y)), Emu(w_), Emu(h_)
        )
    else:
        pic = slide.shapes.add_picture(
            str(png), Emu(int(x)), Emu(int(y)), height=Emu(int(h))
        )
        if max_w and pic.width > max_w:
            ratio = max_w / pic.width
            pic.width, pic.height = int(max_w), int(pic.height * ratio)
    pic.name = name
    dk.USED.add(Path(png))
    return pic


LOGOS = brand.logo_dir()  # the consumer's logo folder (beside its `mark` logo), or None


def logo_path(slug: str) -> Path:
    """<logo folder>/<slug>.png (e.g. "anthropic", "openai")."""
    if LOGOS is None:
        raise FileNotFoundError(f"{slug}: the active tokens name no logo folder")
    for p in (LOGOS / f"{slug}.png", LOGOS / "partners" / f"{slug}.png"):
        if p.exists():
            return p
    raise FileNotFoundError(slug)


# ================================================================ slides and builds
def new_slide(prs, base, title, sources=()):
    """A fresh slide on the deck frame: copy of `base` (team frame slide) with every content and
    footer shape removed, the title set (display-font, sentence case) and the source footer written."""
    s = dk.duplicate(prs, base)
    for sh in dk.content_shapes(s):
        dk.remove(sh)
    dk.style(s, title=title, footer=None)
    source_footer(s, *sources)
    return s


def steps(prs, base, title, sources, n, draw, notes=None, takeaway_text=None):
    """Progressive disclosure: n slides; slide k (1..n) is a fresh frame on which draw(slide, k)
    draws everything revealed up to step k. Same geometry on every step by construction."""
    out = []
    for k in range(1, n + 1):
        s = new_slide(prs, base, title, sources)
        if takeaway_text:
            takeaway(s, takeaway_text)
        draw(s, k)
        if notes is not None:
            dk.set_notes(s, notes)
        out.append(s)
    return out


def takeaway(slide, content, x=X0, y=Y0, w=None, size=14, name="takeaway"):
    """The slide's core point in one line above the visual: 14 pt navy, an optional bold lead.
    content: str, or (lead, rest) to set the lead in bold."""
    w = w or (X1 - x)
    runs = (
        [{"t": content[0], "bold": True}, {"t": " " + content[1]}]
        if isinstance(content, tuple)
        else [content]
    )
    return text(slide, x, y, w, int(0.5 * IN), [runs], size, NAVY, name=name)


PANEL_LEAD_SIZE = brand.size("panel_lead_pt")

_FONTS = {}


def _font(bold):
    """body-font at 100 px for measuring (None when PIL or the font files are missing)."""
    if bold not in _FONTS:
        try:
            from PIL import ImageFont

            f = brand.font_file("body_bold" if bold else "body")
            _FONTS[bold] = ImageFont.truetype(str(f), 100) if f else None
        except Exception:  # noqa: BLE001  (fallback: average glyph width)
            _FONTS[bold] = None
    return _FONTS[bold]


def text_lines(runs, size, w):
    """Lines a body-font paragraph wraps to in width w (EMU) at `size` pt: greedy word wrap with the
    real glyph advances (PIL + the body font file from the tokens), so panels and rails reserve the height
    the text really takes. runs: str or [(text, bold)]. Falls back to 0.55 em per character."""
    runs = [(runs, False)] if isinstance(runs, str) else runs
    words = []
    for t, b in runs:
        for i, wd in enumerate(t.split(" ")):
            if wd:
                words.append((wd, b))
    limit = w / PT  # points

    def width(wd, b):
        f = _font(b)
        if f is None:
            return len(wd) * size * 0.55
        return f.getlength(wd) / 100 * size

    space = width(" ", False) if _font(False) else size * 0.28
    n, cur = 1, 0.0
    for wd, b in words:
        ww = width(wd, b)
        if cur and cur + space + ww > limit:
            n, cur = n + 1, ww
        else:
            cur = cur + space + ww if cur else ww
    return n


def panel_lead(slide, x, y, w, content, size=PANEL_LEAD_SIZE, name="takeaway"):
    """The takeaway as the side panel's lead sentence (library v2): body-font 15 pt navy, the
    lead in bold, wrapped to the panel width, an orange 1.5 pt rule under it. Returns the y
    below it (where the rail starts)."""
    lead, rest = content if isinstance(content, tuple) else ("", content)
    n = text_lines([(lead, True), (rest, False)], size, w)
    h = int(n * size * 1.3 * PT)
    runs = ([{"t": lead, "bold": True}] if lead else []) + [
        {"t": (" " if lead else "") + rest}
    ]
    text(slide, x, y, w, h, [runs], size, NAVY, name=name, line=1.05)
    y += h + int(0.12 * IN)
    rule(slide, x, y, int(0.45 * IN), SOFT, 1.5, name=f"{name}-rule")
    return y + int(0.26 * IN)


def rail(
    slide,
    x,
    y,
    w,
    head,
    hero=None,
    unit=None,
    context=None,
    facts=(),
    upto=None,
    hero_color=NAVY,
    bottom=Y1,
    note=None,
    blocks=(),
):
    """The rail: a small caps label, one hero value with its context, then 2–4 small ordered facts.

    head: label ("PUBLISHED FRONTIER RATE"). hero: display-font figure (str, ≤ 40 pt; a list of
    (text, size) runs for "6 → 14"); unit: smaller text after it; context: 12 pt line under it.
    facts: [(value, text)] or [(value, text, color)] in reading order; value is set bold 15 pt
    beside a 11 pt explanation. blocks: alternative to hero+facts for a rail of 2–3 equal stats
    (the ECI rail: frontier rate, then open-weight lag, then consumer hardware): [(label, figure,
    note)] each a caps label, a display-font 30 pt figure (str, or (number, unit)) and an 11 pt note,
    hairlines between. upto: how many facts/blocks to draw (builds; None = all). note: method or
    scope line at the bottom (9.5 pt grey). Returns the y below the last element."""
    if blocks:
        for i, (lab, fig, nt) in enumerate(blocks if upto is None else blocks[:upto]):
            if i:
                rule(slide, x, y - int(0.14 * IN), w, name=f"rail-block-{i}-r")
            label(slide, x, y, w, lab, name=f"rail-block-{i}-l")
            big, unit = (fig, "") if isinstance(fig, str) else fig
            runs = [{"t": big, "size": 30}] + (
                [{"t": " " + unit, "size": 13, "font": BODY, "bold": True}]
                if unit
                else []
            )
            text(
                slide,
                x,
                y + int(0.24 * IN),
                w,
                int(0.55 * IN),
                [runs],
                30,
                hero_color,
                font=DISPLAY,
                name=f"rail-block-{i}-f",
                anchor=MSO_ANCHOR.BOTTOM,
            )
            n = text_lines(nt, 11, w)
            h = int(n * 11 * 1.32 * PT)
            text(
                slide,
                x,
                y + int(0.84 * IN),
                w,
                h,
                nt,
                11,
                LABEL,
                name=f"rail-block-{i}-n",
            )
            y += int(0.84 * IN) + h + int(0.32 * IN)
        if note:
            text(
                slide,
                x,
                bottom - int(0.42 * IN),
                w,
                int(0.42 * IN),
                note,
                9.5,
                MUTED,
                name="rail-note",
                anchor=MSO_ANCHOR.BOTTOM,
            )
        return y
    label(slide, x, y, w, head, name="rail-head")
    y += int(0.32 * IN)
    if hero is not None:
        runs = (
            [{"t": t, "size": s} for t, s in hero]
            if isinstance(hero, list)
            else [{"t": hero, "size": 40}]
        )
        if unit:
            runs.append({"t": "  " + unit, "size": 15, "font": BODY, "bold": True})
        text(
            slide,
            x,
            y,
            w,
            int(0.7 * IN),
            [runs],
            40,
            hero_color,
            font=DISPLAY,
            name="rail-hero",
            anchor=MSO_ANCHOR.BOTTOM,
        )
        y += int(0.78 * IN)
    if context:
        n = text_lines(context, 12, w)
        h = int(n * 12 * 1.3 * PT)
        text(slide, x, y, w, h, context, 12, LABEL, name="rail-context")
        y += h + int(0.14 * IN)
    shown = facts if upto is None else facts[:upto]
    if shown:
        rule(slide, x, y, w, name="rail-rule")
        y += int(0.16 * IN)
    vw = int(1.12 * IN)
    for i, f in enumerate(shown):
        value, expl = f[0], f[1]
        col = f[2] if len(f) > 2 else NAVY
        n = text_lines(expl, 11, w - vw)
        h = max(int(0.3 * IN), int(n * 11 * 1.32 * PT))
        text(
            slide,
            x,
            y - int(0.02 * IN),
            vw - int(0.08 * IN),
            int(0.3 * IN),
            value,
            15,
            col,
            bold=True,
            name=f"rail-fact-{i}-v",
        )
        text(
            slide,
            x + vw,
            y + int(0.02 * IN),
            w - vw,
            h,
            expl,
            11,
            LABEL,
            name=f"rail-fact-{i}-t",
        )
        y += h + int(0.16 * IN)
    if note:
        text(
            slide,
            x,
            bottom - int(0.42 * IN),
            w,
            int(0.42 * IN),
            note,
            9.5,
            MUTED,
            name="rail-note",
            anchor=MSO_ANCHOR.BOTTOM,
        )
    return y


def rail_area(side="right"):
    """(main_box, rail_x, divider_x) for a slide with a rail on `side` ("right" or "left")."""
    if side == "right":
        rx = X1 - RAIL_W
        div = rx - RAIL_GAP
        return (X0, Y0, div - RAIL_GAP - X0, Y1 - Y0), rx, div
    div = X0 + RAIL_W + RAIL_GAP
    return (div + RAIL_GAP, Y0, X1 - div - RAIL_GAP, Y1 - Y0), X0, div


def chart_slide(
    prs,
    base,
    title,
    sources,
    draw,
    rail_spec=None,
    takeaway_text=None,
    stages=1,
    rail_side="right",
    rail_sync=False,
    notes=None,
    rail_from=1,
    legend=None,
):
    """One chart (or native visual) per slide with ALL its text in the side panel (library v2,
    9 Nov 2026): no takeaway line above the plot; the panel (right or left) leads with the
    takeaway sentence, then the rail. The visual gets the full plot area.

    Slides are the presenter's memory triggers: takeaway_text (required) is the key point as a
    short sentence (the panel's lead, from stage 1); rail facts are phrased as the sentences he
    will say, in order. Without rail_spec the panel holds the takeaway alone.

    legend: [(kind, color, text)] drawn by `legend_line` at the same place on every chart (the
    BOTTOM of the visual, boxless); the box passed to draw ends above it.
    draw(slide, box, stage): draws the visual into box (x, y, w, h) for build stage 1..stages
    (a native chart from chart_xy / chart_line / chart_bar, plus overlays). rail_spec: kwargs for
    `rail` (head, hero, unit, context, facts, note, hero_color). rail_side: "right" (default) or
    "left". rail_sync: rail items (facts or blocks) appear with the builds — True: stage k shows
    k items (the ECI pattern: rate, then lag, then consumer hardware); a list: stage k shows
    rail_sync[k-1] items; False: all items from stage 1. rail_from: first stage that shows the
    rail (its space is reserved from stage 1, so the chart never moves). takeaway_text: str or (lead, rest).
    Returns the build slides."""

    if not takeaway_text:
        raise ValueError(
            f"chart_slide {title!r}: a takeaway line is required (the presenter's memory trigger)"
        )

    def one(s, k):
        main, rx, div = rail_area(
            rail_side
        )  # the side panel always exists (takeaway lives there)
        x, y, w, h = main
        if legend:  # legends at the bottom of the visual, every chart (library v2)
            nr = legend_rows(legend, 10, w)
            lh = int(0.3 * IN) + (nr - 1) * int(10 * LEGEND_ROW * PT)
            legend_line(s, x, y + h - lh + int(0.04 * IN), legend, max_w=w)
            h -= lh + int(0.08 * IN)
        draw(s, (x, y, w, h), k)
        vrule(s, div, Y0, Y1 - Y0, name="rail-divider")
        ry = panel_lead(s, rx, Y0 + int(0.02 * IN), RAIL_W, takeaway_text)
        if rail_spec and k >= rail_from:
            spec = dict(rail_spec)
            if rail_sync is True:
                spec["upto"] = k
            elif rail_sync:
                spec["upto"] = rail_sync[k - 1]
            rail(s, rx, ry, RAIL_W, **spec)

    return steps(prs, base, title, sources, stages, one, notes)


# ================================================================ charts
def serial(d) -> float:
    """Excel date serial for a date / ISO string (date axes on XY charts)."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        d = d.date()
    return float((d - date(1899, 12, 30)).days)


def _el(tag, **attrs):
    e = etree.Element(qn(tag))
    for k, v in attrs.items():
        e.set(k, str(v))
    return e


def _sppr_noline_nofill():
    sp = _el("c:spPr")
    sp.append(_el("a:noFill"))
    ln = _el("a:ln")
    ln.append(_el("a:noFill"))
    sp.append(ln)
    return sp


def _set_line(sppr_owner, color, width_pt, dash=None):
    ln = sppr_owner.format.line
    ln.color.rgb = color
    ln.width = Pt(width_pt)
    if dash:
        ln.dash_style = dash


class Plot:
    """Data → slide coordinates for a chart whose inner plot area is placed manually, so native
    overlays (bands, annotations, limit labels) sit exactly on the data. Returned by chart_*."""

    def __init__(self, chart_frame, layout, xr, yr, xlog=False, ylog=False):
        self.gf, self.layout, self.xr, self.yr, self.xlog, self.ylog = (
            chart_frame,
            layout,
            xr,
            yr,
            xlog,
            ylog,
        )
        bx, by, bw, bh = (
            chart_frame.left,
            chart_frame.top,
            chart_frame.width,
            chart_frame.height,
        )
        lx, ly, lw, lh = layout
        self.left, self.top = bx + lx * bw, by + ly * bh
        self.width, self.height = lw * bw, lh * bh
        self.chart = chart_frame.chart

    @staticmethod
    def _f(v, r, log):
        lo, hi = r
        if log:
            return (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo))
        return (v - lo) / (hi - lo)

    def x(self, v):
        return int(self.left + self._f(v, self.xr, self.xlog) * self.width)

    def y(self, v):
        return int(self.top + (1 - self._f(v, self.yr, self.ylog)) * self.height)

    def pt(self, xv, yv):
        return self.x(xv), self.y(yv)


def style_chart(chart, layout=(0.07, 0.04, 0.9, 0.84), font_size=10):
    """The one chart style: body-font, transparent background without border, no title, no legend
    (`legend_line` draws it natively), light grid, grey axis text, square corners, and the inner
    plot area at a fixed manual layout (fractions x, y, w, h of the chart frame) so overlays can
    be placed with `Plot`."""
    cs = chart._chartSpace
    rc = cs.find(qn("c:roundedCorners"))
    if rc is None:
        rc = _el("c:roundedCorners", val=0)
        cs.insert(0, rc)
    rc.set("val", "0")
    chart.has_title = False
    chart.has_legend = False
    chart.font.name = BODY
    chart.font.size = Pt(font_size)
    chart.font.color.rgb = LABEL
    c_chart = cs.find(qn("c:chart"))
    atd = c_chart.find(qn("c:autoTitleDeleted"))
    if atd is None:
        atd = _el("c:autoTitleDeleted", val=1)
        c_chart.insert(0, atd)
    atd.set("val", "1")
    old = cs.find(qn("c:spPr"))
    if old is not None:
        cs.remove(old)
    c_chart.addnext(_sppr_noline_nofill())
    pa = c_chart.find(qn("c:plotArea"))
    lay = pa.find(qn("c:layout"))
    if lay is not None:
        pa.remove(lay)
    lay = _el("c:layout")
    ml = _el("c:manualLayout")
    ml.append(_el("c:layoutTarget", val="inner"))
    ml.append(_el("c:xMode", val="edge"))
    ml.append(_el("c:yMode", val="edge"))
    for k, v in zip("xywh", layout):
        ml.append(_el(f"c:{k}", val=f"{v:.4f}"))
    lay.append(ml)
    pa.insert(0, lay)
    ps = pa.find(qn("c:spPr"))
    if ps is not None:
        pa.remove(ps)
    pa.append(_sppr_noline_nofill())


def _axis(
    ax,
    lo=None,
    hi=None,
    major=None,
    fmt=None,
    grid=True,
    log=None,
    line=True,
    labels=True,
    size=10,
    color=LABEL,
):
    if lo is not None:
        ax.minimum_scale = lo
    if hi is not None:
        ax.maximum_scale = hi
    if major is not None:
        ax.major_unit = major
    ax.has_major_gridlines = grid
    ax.has_minor_gridlines = False
    if grid:  # light dotted grid
        _set_line(ax.major_gridlines, GRID, 0.75, MSO_LINE_DASH_STYLE.ROUND_DOT)
    ax.major_tick_mark = XL_TICK_MARK.NONE
    ax.minor_tick_mark = XL_TICK_MARK.NONE
    if line:
        _set_line(ax, GREY_LINE, 0.75)
    else:
        ax.format.line.fill.background()
    if fmt:
        ax.tick_labels.number_format = fmt
        ax.tick_labels.number_format_is_linked = False
    ax.tick_labels.font.size = Pt(size)
    ax.tick_labels.font.color.rgb = color
    ax.tick_labels.font.name = BODY
    if not labels:
        ax.tick_label_position = XL_TICK_LABEL_POSITION.NONE
    if log:
        sc = ax._element.find(qn("c:scaling"))
        lb = sc.find(qn("c:logBase"))
        if lb is None:
            lb = _el("c:logBase")
            sc.insert(0, lb)
        lb.set("val", str(log))


def _label_point(point, content, pos, size=10, color=NAVY):
    """Per-point data label with rich text: content str or list of (text, size, color, bold)."""
    dl = point.data_label
    tf = dl.text_frame
    runs = content if isinstance(content, list) else [(content, size, color, True)]
    p = tf.paragraphs[0]
    first = True
    for t, sz, col, b in runs:
        if t.startswith("\n"):
            p = tf.add_paragraph()
            t = t[1:]
        r = p.add_run()
        r.text = t
        r.font.size = Pt(sz)
        r.font.color.rgb = col
        r.font.bold = b
        r.font.name = BODY
        first = False
    dl.position = pos
    return dl


def chart_xy(
    slide, bx, series, x_axis, y_axis, layout=(0.075, 0.03, 0.905, 0.86), name="chart"
):
    """XY scatter (date or numeric x), any mix of point clouds and lines, with per-point labels.

    series: list of dicts, drawn back to front:
      name, points [(x, y)], color, line (bool, default False), width (pt), dash (bool),
      marker ("circle", "diamond", "square", None), size (marker pt), marker_fill (default color),
      labels {index: str | [(text, size, color, bold)]} and label_pos {index: "above"|"below"|
      "left"|"right"} (per-point data labels; text with a leading "\\n" starts a new line).
      band: [(x, lo, hi)] instead of points draws a filled uncertainty band (no line, no markers)
      behind the chart's lines: `color` at `opacity` (default 0.18). Stack ±2σ under ±1σ by
      listing the wider band first.
    x_axis / y_axis: dicts lo, hi, major, fmt (number format, e.g. "yyyy" for dates given as
      `serial`), log (base, e.g. 10 or 60: native logarithmic axis via c:logBase), grid, labels.
    Returns a Plot for native overlays."""
    bands = [s for s in series if "band" in s]
    series = [s for s in series if "band" not in s]
    cd = XyChartData()
    longest = max(len(s["points"]) for s in series)
    for s in series:
        ser = cd.add_series(s["name"])
        pts = list(s["points"])
        # LibreOffice (24.2) drops an XY series that has fewer points than a later one; pad
        # every series to the same length by repeating its last point (drawn on top of itself)
        pts += [pts[-1]] * (longest - len(pts))
        for xv, yv in pts:
            ser.add_data_point(xv, yv)
    x, y, w, h = bx
    gf = slide.shapes.add_chart(
        XL_CHART_TYPE.XY_SCATTER, Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)), cd
    )
    gf.name = name
    ch = gf.chart
    style_chart(ch, layout)
    _axis(ch.category_axis, **{"grid": False, **x_axis})
    _axis(ch.value_axis, **{"grid": True, "line": False, **y_axis})
    markers = {
        "circle": XL_MARKER_STYLE.CIRCLE,
        "diamond": XL_MARKER_STYLE.DIAMOND,
        "square": XL_MARKER_STYLE.SQUARE,
        None: XL_MARKER_STYLE.NONE,
    }
    pos = {
        "above": XL_LABEL_POSITION.ABOVE,
        "below": XL_LABEL_POSITION.BELOW,
        "left": XL_LABEL_POSITION.LEFT,
        "right": XL_LABEL_POSITION.RIGHT,
        "center": XL_LABEL_POSITION.CENTER,
    }
    for s, ser in zip(series, ch.plots[0].series):
        col = s.get("color", NAVY)
        ser.smooth = False
        if s.get("line"):
            _set_line(
                ser,
                col,
                s.get("width", 2.0),
                MSO_LINE_DASH_STYLE.DASH if s.get("dash") else None,
            )
        else:
            ser.format.line.fill.background()
        m = s.get("marker", "circle" if not s.get("line") else None)
        ser.marker.style = markers[m]
        if m:
            ser.marker.size = int(s.get("size", 6))
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = s.get("marker_fill", col)
            mline = s.get("marker_line")
            if mline:
                _set_line(ser.marker, mline, 1.5)
            else:
                ser.marker.format.line.fill.background()
        for i, content in (s.get("labels") or {}).items():
            _label_point(
                ser.points[i], content, pos[(s.get("label_pos") or {}).get(i, "above")]
            )
    xr = (x_axis.get("lo"), x_axis.get("hi"))
    yr = (y_axis.get("lo"), y_axis.get("hi"))
    plot = Plot(gf, layout, xr, yr, bool(x_axis.get("log")), bool(y_axis.get("log")))
    for j, b in enumerate(bands):
        band_shape(slide, plot, b["band"], b.get("color", NAVY), b.get("opacity", 0.18),
                   name=f"{name}-band-{j}")
    return plot


def band_shape(slide, plot, band, color, opacity=0.18, name="band"):
    """A filled polygon between the lo and hi edges of [(x, lo, hi)] in data units, placed
    behind the chart frame so the chart's lines draw over it."""
    upper = [plot.pt(x_, hi) for x_, _, hi in band]
    lower = [plot.pt(x_, lo) for x_, lo, _ in reversed(band)]
    pts = upper + lower
    fb = slide.shapes.build_freeform(pts[0][0], pts[0][1], scale=1.0)
    fb.add_line_segments(pts[1:], close=True)
    sh = fb.convert_to_shape()
    sh.fill.solid()
    sh.fill.fore_color.rgb = color
    clr = sh.fill._xPr.find(qn("a:solidFill"))[0]
    a = etree.SubElement(clr, qn("a:alpha"))
    a.set("val", str(int(opacity * 100000)))
    sh.line.fill.background()
    sh.shadow.inherit = False
    dk._drop_style(sh)
    sh.name = name
    el = sh._element
    el.getparent().remove(el)
    plot.gf._element.addprevious(el)
    return sh


def chart_line(
    slide,
    bx,
    categories,
    series,
    y_axis,
    layout=(0.075, 0.03, 0.905, 0.86),
    name="chart",
):
    """Category line chart (evenly spaced periods). series: dicts name, values (None = gap),
    color, width, dash, marker, labels {index: str}, label_pos. y_axis as in chart_xy."""
    cd = CategoryChartData()
    cd.categories = categories
    for s in series:
        cd.add_series(s["name"], s["values"])
    x, y, w, h = bx
    gf = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        Emu(int(x)),
        Emu(int(y)),
        Emu(int(w)),
        Emu(int(h)),
        cd,
    )
    gf.name = name
    ch = gf.chart
    style_chart(ch, layout)
    _axis(ch.category_axis, grid=False)
    _axis(ch.value_axis, **{"line": False, **y_axis})
    for s, ser in zip(series, ch.plots[0].series):
        col = s.get("color", NAVY)
        ser.smooth = False
        _set_line(
            ser,
            col,
            s.get("width", 2.0),
            MSO_LINE_DASH_STYLE.DASH if s.get("dash") else None,
        )
        ser.marker.style = (
            XL_MARKER_STYLE.CIRCLE if s.get("marker", True) else XL_MARKER_STYLE.NONE
        )
        ser.marker.size = 6
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = col
        ser.marker.format.line.fill.background()
        for i, content in (s.get("labels") or {}).items():
            _label_point(ser.points[i], content, XL_LABEL_POSITION.ABOVE)
    return Plot(gf, layout, (0, len(categories)), (y_axis.get("lo"), y_axis.get("hi")))


def chart_bar(
    slide,
    bx,
    categories,
    series,
    horizontal=True,
    stacked=False,
    value_axis=None,
    colors=None,
    labels=True,
    label_fmt="0",
    label_text=None,
    gap=60,
    overlap=None,
    layout=(0.2, 0.02, 0.72, 0.94),
    name="chart",
    cat_size=11,
    label_size=11,
    show_cat=True,
):
    """Clustered or stacked bar/column chart with value labels.

    series: [(name, values, color)] or [(name, values, color, texture)] (TEXTURES; default
    solid); colors: optional per-point overrides for the first series ({index: RGBColor or
    (RGBColor, texture)}, e.g. the one solid orange bar among faded ones). label_fmt: number format of value labels;
    label_text: {(series_index, point_index): str or (str, RGBColor)} custom label text
    ("~1,200", "3–6", ("0", ORANGE)).
    overlap 100 with a grey first series draws a "track" behind the values (0–100% rows).
    value_axis: dict lo, hi, major, fmt, grid, labels. Horizontal charts list categories top-down.
    Returns a Plot (category index 0..n along the category axis)."""
    cd = CategoryChartData()
    cd.categories = categories
    series = [tuple(sr) + ("solid",) * (4 - len(sr)) for sr in series]
    for nm, vals, _, _t in series:
        cd.add_series(nm, vals)
    kind = {
        (True, False): XL_CHART_TYPE.BAR_CLUSTERED,
        (True, True): XL_CHART_TYPE.BAR_STACKED,
        (False, False): XL_CHART_TYPE.COLUMN_CLUSTERED,
        (False, True): XL_CHART_TYPE.COLUMN_STACKED,
    }[(horizontal, stacked)]
    x, y, w, h = bx
    gf = slide.shapes.add_chart(
        kind, Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)), cd
    )
    gf.name = name
    ch = gf.chart
    style_chart(ch, layout)
    plot = ch.plots[0]
    plot.gap_width = gap
    if overlap is not None:
        plot.overlap = overlap
    elif stacked:
        plot.overlap = 100
    va = {"grid": False, "labels": False, "line": False, **(value_axis or {})}
    _axis(ch.value_axis, **va)
    _axis(
        ch.category_axis,
        grid=False,
        line=not horizontal,
        size=cat_size,
        color=NAVY,
        labels=show_cat,
    )
    if horizontal:
        ch.category_axis.reverse_order = True
        # with reversed categories the value axis must cross at the maximum to stay at the bottom
        crosses = ch.value_axis._element  # noqa: F841  (labels are hidden by default)
    for si, ((nm, vals, col, tex), ser) in enumerate(zip(series, plot.series)):
        texture(ser.format, tex, col)
        ser.invert_if_negative = False
        if si == 0 and colors:
            for i, c in colors.items():
                # RGBColor is itself a tuple subclass: test for it first (library v2 fix)
                c, t = (c, "solid") if isinstance(c, RGBColor) else c
                texture(ser.points[i].format, t, c)
        on_dark = stacked and tex == "solid"
        if labels and (labels is True or si in labels):
            dls = ser.data_labels
            dls.show_value = True
            dls.number_format = label_fmt
            dls.number_format_is_linked = False
            dls.font.size = Pt(label_size)
            dls.font.bold = True
            dls.font.name = BODY
            dls.font.color.rgb = WHITE if on_dark else NAVY
            dls.position = (
                XL_LABEL_POSITION.OUTSIDE_END
                if not stacked
                else XL_LABEL_POSITION.CENTER
            )
        for (s_i, p_i), t in (label_text or {}).items():
            if s_i == si:
                t, tcol = t if isinstance(t, tuple) else (t, WHITE if on_dark else NAVY)
                _label_point(
                    ser.points[p_i],
                    [(t, label_size, tcol, True)],
                    XL_LABEL_POSITION.OUTSIDE_END
                    if not stacked
                    else XL_LABEL_POSITION.CENTER,
                )
    vr = (va.get("lo", 0), va.get("hi", 1))
    return Plot(
        gf,
        layout,
        vr if horizontal else (0, len(categories)),
        (0, len(categories)) if horizontal else vr,
    )


def _legend_item_w(kind, t, size):
    mw = {"dot": 0.16, "line": 0.36, "dash": 0.36}.get(kind, 0.28)
    return int(mw * IN), int(len(t) * size * 0.52 * PT) + int(0.1 * IN)


def legend_rows(items, size=10, max_w=None):
    """How many rows `legend_line` needs for items within max_w (1 when max_w is None)."""
    if not max_w or not items:
        return 1
    per = max(1, max_w // _legend_cell(items, size))
    return -(-len(items) // per)


def _legend_cell(items, size):
    """The one cell width every item of a legend gets (components 1.4.0: legends are a table of
    equidistant cells, the same system as the `SOURCES` footer): the widest item plus a gap."""
    return max(sum(_legend_item_w(k, t, size)) for k, _, t in items) + int(0.22 * IN)


LEGEND_ROW = brand.size(
    "legend_row_pitch"
)  # legend row pitch, in multiples of the legend type size


def _swatch(slide, x, cy, kind, col, name):
    """A legend swatch at x, centred on cy; returns its advance (swatch + gap), in EMU."""
    if kind == "dot":
        dot(slide, x + int(0.05 * IN), cy, int(0.09 * IN), col, name=name)
        return int(0.16 * IN)
    if kind == "bar" or kind in TEXTURES:
        box(slide, x, cy - int(0.05 * IN), int(0.2 * IN), int(0.14 * IN), col, name=name,
            tex=None if kind == "bar" else kind)
        if kind in TEXTURES and kind != "solid":
            texture(slide.shapes[-1], kind, col, outline=True)
        return int(0.28 * IN)
    line(slide, x, cy, x + int(0.28 * IN), cy, col, 2.0, dash=kind == "dash", name=name)
    return int(0.36 * IN)


def legend_line(slide, x, y, items, size=10, name="legend", max_w=None):
    """Native boxless legend, at the bottom of a chart (chart_slide places it): [(kind, color, text)] with kind "dot", "region" (swatch of a `region`),
    "line", "dash", "bar" (solid swatch) or a texture name ("hatched", "faded"…) for a textured
    swatch matching the bars. Items sit in equidistant cells (one width, the widest item's), left
    to right, wrapping to a new row past max_w (EMU), so a legend reads as a table."""
    cell = _legend_cell(items, size) if items else 0
    per = max(1, max_w // cell) if max_w and cell else len(items) or 1
    x0, cx = x, x
    for i, (kind, col, t) in enumerate(items):
        if i and i % per == 0:
            cx, y = x0, y + int(size * LEGEND_ROW * PT)
        cell_x = cx
        cy = y + int(size * 0.65 * PT)
        if kind == "dot":
            dot(
                slide,
                cx + int(0.05 * IN),
                cy,
                int(0.09 * IN),
                col,
                name=f"{name}-{i}-m",
            )
            mw = int(0.16 * IN)
        elif kind == "region":  # swatch of a `region` (tint + fine 45° hatch, no edge)
            from pptx.enum.dml import MSO_PATTERN

            sw = box(
                slide,
                cx,
                cy - int(0.05 * IN),
                int(0.2 * IN),
                int(0.14 * IN),
                col,
                name=f"{name}-{i}-m",
            )
            sw.fill.patterned()
            sw.fill.pattern = MSO_PATTERN.LIGHT_UPWARD_DIAGONAL
            sw.fill.fore_color.rgb = tint(col, REGION_INK)
            sw.fill.back_color.rgb = tint(col, REGION_GROUND)
            mw = int(0.28 * IN)
        elif kind == "bar" or kind in TEXTURES:
            box(
                slide,
                cx,
                cy - int(0.05 * IN),
                int(0.2 * IN),
                int(0.14 * IN),
                col,
                name=f"{name}-{i}-m",
                tex=None if kind == "bar" else kind,
            )
            if (
                kind in TEXTURES and kind != "solid"
            ):  # swatch keyed like its bars: textured, thin edge
                sw = slide.shapes[-1]
                texture(sw, kind, col, outline=True)
            mw = int(0.28 * IN)
        else:
            line(
                slide,
                cx,
                cy,
                cx + int(0.28 * IN),
                cy,
                col,
                2.0,
                dash=kind == "dash",
                name=f"{name}-{i}-m",
            )
            mw = int(0.36 * IN)
        tw = int(len(t) * size * 0.52 * PT) + int(0.1 * IN)
        text(
            slide,
            cx + mw,
            y,
            tw,
            int(size * 1.5 * PT),
            t,
            size,
            LABEL,
            name=f"{name}-{i}-t",
        )
        cx = cell_x + cell
    return cx


def annotate(
    slide,
    x,
    y,
    head,
    sub=None,
    w=int(1.8 * IN),
    align=PP_ALIGN.LEFT,
    color=NAVY,
    size=10.5,
    name=None,
    anchor=MSO_ANCHOR.TOP,
):
    """A chart annotation: bold head (10.5 pt) and an optional grey second line, placed with its
    top-left at (x, y) (align right: top-right; center: top-centre)."""
    if align == PP_ALIGN.RIGHT:
        x -= w
    elif align == PP_ALIGN.CENTER:
        x -= w // 2
    paras = [[{"t": head, "bold": True, "color": color}]]
    if sub:
        paras.append([{"t": sub, "size": size - 1, "color": LABEL}])
    return text(
        slide,
        x,
        y,
        w,
        int((2.6 if sub else 1.4) * size * PT),
        paras,
        size,
        color,
        align=align,
        name=name,
        anchor=anchor,
    )


BG = brand.color("surface")  # label grounds: the slide's own colour, so a ground never shows


def halo(shape, color=WHITE, radius_pt=3):
    """A halo behind every run of a text shape (a:glow), so a number drawn over a hatched or
    dotted fill stays readable without a pill box."""
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            rpr = r._r.get_or_add_rPr()
            eff = rpr.find(qn("a:effectLst"))
            if eff is None:
                eff = etree.SubElement(rpr, qn("a:effectLst"))
                # schema order: ln, fill, effectLst, … latin — move before latin/ea/cs if present
                for tag in ("a:latin", "a:ea", "a:cs", "a:sym"):
                    el = rpr.find(qn(tag))
                    if el is not None:
                        el.addprevious(eff)
                        break
            glow = etree.SubElement(eff, qn("a:glow"))
            glow.set("rad", str(int(radius_pt * PT)))
            clr = etree.SubElement(glow, qn("a:srgbClr"))
            clr.set("val", str(color))
            a = etree.SubElement(clr, qn("a:alpha"))
            a.set("val", "90000")
    return shape


REGION_INK, REGION_GROUND = 45, 7


def region(
    slide,
    x,
    y,
    w,
    h,
    color=None,
    label_text=None,
    sub=None,
    at="top-left",
    size=10.5,
    edge=None,
    name="region",
):
    """A shaded region of a chart (e.g. "beyond METR's reliable range", a forecast window), in the
    EU-report language: a light tint of `color` with a fine 45° hatch over it, never an opaque
    box, no outline. label_text/sub: set INSIDE the region with a halo (no box behind the
    letters); at: "top-left", "top-right", "bottom-left" or "bottom-right". edge: optional
    side ("top", "bottom", "left", "right") that takes a dashed hairline in the colour, marking
    the boundary the region starts from (e.g. the 16-hour limit). Returns the region shape."""
    from pptx.enum.dml import MSO_PATTERN

    color = color or GREY_LINE
    s = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h))
    )
    s.fill.patterned()
    s.fill.pattern = MSO_PATTERN.LIGHT_UPWARD_DIAGONAL
    s.fill.fore_color.rgb = tint(color, REGION_INK)
    s.fill.back_color.rgb = tint(color, REGION_GROUND)
    s.line.fill.background()
    s.shadow.inherit = False
    dk._drop_style(s)
    s.name = name
    if edge:
        x1, y1, x2, y2 = {
            "top": (x, y, x + w, y),
            "bottom": (x, y + h, x + w, y + h),
            "left": (x, y, x, y + h),
            "right": (x + w, y, x + w, y + h),
        }[edge]
        line(slide, x1, y1, x2, y2, color, 1.0, dash=True, name=f"{name}-edge")
    if label_text:
        pad = int(0.1 * IN)
        lw = min(
            w - 2 * pad, int(max(len(label_text), len(sub or "")) * size * 0.56 * PT)
        )
        lh = int((2.6 if sub else 1.4) * size * PT)
        right, bottom = at.endswith("right"), at.startswith("bottom")
        lx = x + w - pad - lw if right else x + pad
        ly = y + h - pad - lh if bottom else y + pad
        paras = [[{"t": label_text, "bold": True}]]
        if sub:
            paras.append([{"t": sub, "size": size - 1, "color": LABEL, "bold": False}])
        tb = text(
            slide,
            lx,
            ly,
            lw,
            lh,
            paras,
            size,
            NAVY,
            align=PP_ALIGN.RIGHT if right else PP_ALIGN.LEFT,
            name=f"{name}-label",
        )
        halo(tb, BG)
    return s


def value_label(
    slide,
    at,
    value,
    label_at=None,
    size=11,
    color=NAVY,
    with_halo=True,
    align="left",
    name=None,
):
    """A number on a chart mark. at: (x, y) EMU of the mark (from Plot). When the number fits in
    its bar/segment, label_at is None and it is centred on `at` with a halo; when it does not, it
    sits outside at label_at with a thin CURVED leader back to the mark (the EU-report stacked-
    bar convention)."""
    w = int(len(value) * size * 0.6 * PT) + int(0.06 * IN)
    h = int(size * 1.4 * PT)
    if label_at is None:
        x, y = at[0] - w // 2, at[1] - h // 2
        tb = text(
            slide,
            x,
            y,
            w,
            h,
            value,
            size,
            color,
            bold=True,
            align=PP_ALIGN.CENTER,
            name=name,
            anchor=MSO_ANCHOR.MIDDLE,
        )
    else:
        x, y = label_at
        if align == "right":
            x -= w
        ex = x if at[0] < x else x + w
        c = slide.shapes.add_connector(
            MSO_CONNECTOR.CURVE,
            Emu(int(at[0])),
            Emu(int(at[1])),
            Emu(int(ex)),
            Emu(int(y + h // 2)),
        )
        c.line.color.rgb = GREY_LINE
        c.line.width = Pt(0.75)
        dk._drop_style(c)
        tb = text(
            slide,
            x,
            y,
            w,
            h,
            value,
            size,
            color,
            bold=True,
            name=name,
            anchor=MSO_ANCHOR.MIDDLE,
            align=PP_ALIGN.RIGHT if align == "right" else PP_ALIGN.LEFT,
        )
    if with_halo:
        halo(tb)
    return tb


PROVIDERS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google-gemini",
    "deepmind": "deepmind",
    "meta": "meta",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "alibaba": "qwen",
    "moonshot": "kimi",
    "kimi": "kimi",
    "z.ai": "z-ai",
    "zhipu": "z-ai",
    "glm": "glm",
    "xai": "xai",
    "mistral": "mistral",
}
"""Model provider → logo slug in the consumer's logo folder."""


def provider_logo(provider: str):
    """Logo path for a model provider name ("OpenAI", "Google DeepMind"…), or None."""
    key = provider.lower()
    for k, slug in PROVIDERS.items():
        if k in key:
            try:
                return logo_path(slug)
            except FileNotFoundError:
                return None
    return None


def callout(
    slide,
    at,
    label_at,
    head,
    sub=None,
    color=NAVY,
    align="left",
    size=10.5,
    name=None,
    leader=True,
    provider=None,
    ground="fill",
):
    """A labelled point (a milestone label): a bold head and optional grey second line
    at label_at (EMU; top-left corner, or top-right when align="right"), on a ground of the slide
    background so it reads over context points, with a thin leader from the data point `at`
    (EMU, from Plot.pt) to the nearest edge of the label. Use instead of a data label when the
    label must sit away from crowded data. provider: the model's developer ("OpenAI",
    "Anthropic"…): its logo sits left of the label (charts that label models always pass it).
    ground: "fill" (slide-background ground, over context points) or "halo" (no box: a glow
    behind the letters, for a label set inside a hatched `region`)."""
    w = int(
        max(len(head) * size * 0.58, len(sub or "") * (size - 1) * 0.53) * PT
    ) + int(0.08 * IN)
    h = int((2.5 if sub else 1.3) * size * PT)
    x, y = label_at
    lg = provider_logo(provider) if provider else None
    lw = int(0.24 * IN) if lg else 0
    if align == "right":
        x -= w
    if lg:
        logo(
            slide,
            lg,
            x - lw,
            y + int(0.02 * IN),
            name=f"{name or 'callout'}-logo",
            role="label",
        )
    if leader and at:
        px, py = at
        ex = min(max(px, x - lw), x + w)
        ey = min(max(py, y), y + h)
        line(slide, px, py, ex, ey, GREY_LINE, 0.75, name=f"{name or 'callout'}-leader")
    paras = [[{"t": head, "bold": True, "color": color}]]
    if sub:
        paras.append([{"t": sub, "size": size - 1, "color": LABEL}])
    tb = text(
        slide, x, y, w, h, paras, size, color, name=name
    )  # text always reads from the logo
    if ground == "halo":
        halo(tb, BG)
    else:
        tb.fill.solid()
        tb.fill.fore_color.rgb = BG
    return tb


# ================================================================ quote
def portrait(slide, img, x, y, d=int(0.95 * IN), name="portrait"):
    """A person's photograph as a circle of diameter d (centre-cropped to a square), full
    colour. The only raster besides logos and screenshots a component places."""
    from PIL import Image

    with Image.open(img) as im:
        w_, h_ = im.size
    pic = slide.shapes.add_picture(str(img), Emu(int(x)), Emu(int(y)), Emu(d), Emu(d))
    if w_ > h_:
        c = (w_ - h_) / w_ / 2
        pic.crop_left = pic.crop_right = c
    elif h_ > w_:
        c = (h_ - w_) / h_  # keep the top: faces sit high in a portrait
        pic.crop_top, pic.crop_bottom = c * 0.15, c * 0.85
    pic.auto_shape_type = MSO_SHAPE.OVAL
    pic.name = name
    dk.USED.add(Path(img))
    return pic


def quote_slide(
    prs,
    base,
    title,
    quote,
    who,
    sources,
    org_logo=None,
    portrait_img=None,
    original=None,
    context=None,
    notes=None,
    logo_h=int(0.55 * IN),
):
    """Quote page, identical everywhere: the quoter's logo (monochrome navy), a large orange
    quote-mark glyph, the quote (display-font 26 pt, navy, italic), the attribution (name · role ·
    organisation · date, 11 pt). No context cards (v2): `context` is ignored. A person's quote
    passes `portrait_img` (their photograph, drawn as a circle) instead of `org_logo`.

    original: the quote in its original language when it is not English; the English translation
    is then the main text and the original sits underneath, smaller and grey, both in quotation
    marks. org_logo: slug in the logo folder or a Path. context: optional [(head, sub)] row
    of 2–4 small numbered facts under the quote (what happened before/after). Returns [slide]."""
    s = new_slide(prs, base, title, sources)
    x, w = X0 + int(0.35 * IN), int(9.6 * IN)
    if portrait_img is not None:  # a person: their photograph; an organisation: its logo
        portrait(s, portrait_img, x, Y0 + int(0.05 * IN), int(1.45 * IN))
        top = Y0 + int(1.75 * IN)
    else:
        if org_logo is None:
            raise ValueError("quote_slide needs org_logo or portrait_img")
        png = org_logo if isinstance(org_logo, Path) else logo_path(org_logo)
        logo(
            s, png, x, Y0 + int(0.1 * IN), role="quote"
        )  # logo_h is ignored: one size everywhere
        top = Y0 + int(1.35 * IN)
    text(
        s,
        x - int(0.08 * IN),
        top - int(0.2 * IN),
        int(1.0 * IN),
        int(1.3 * IN),
        "“",
        110,
        SOFT,
        font=DISPLAY,
        name="quote-glyph",
    )
    qx = x + int(0.95 * IN)
    qn_ = len(quote)
    qsize = 26 if qn_ < 170 else 22 if qn_ < 300 else 18
    lines = math.ceil(qn_ * qsize * 0.5 * PT / (w - int(0.95 * IN)))
    qh = int(lines * qsize * 1.35 * PT)
    text(
        s,
        qx,
        top,
        w - int(0.95 * IN),
        qh,
        [[{"t": f"“{quote}”", "italic": True}]],
        qsize,
        NAVY,
        font=DISPLAY,
        line=1.12,
        name="quote",
    )
    y = top + qh + int(0.18 * IN)
    if original:
        on = math.ceil(len(original) * 13 * 0.5 * PT / (w - int(0.95 * IN)))
        oh = int(on * 13 * 1.35 * PT)
        text(
            s,
            qx,
            y,
            w - int(0.95 * IN),
            oh,
            [[{"t": f"“{original}”", "italic": True}]],
            13,
            MUTED,
            name="quote-original",
            line=1.1,
        )
        y += oh + int(0.14 * IN)
    rule(s, qx, y, int(0.6 * IN), SOFT, 1.5, name="quote-rule")
    text(
        s,
        qx,
        y + int(0.12 * IN),
        w - int(0.95 * IN),
        int(0.3 * IN),
        who,
        11.5,
        LABEL,
        name="quote-who",
    )
    # context: accepted for compatibility, no longer drawn (decided 9 Nov 2026: no numbered
    # 01/02/03 cards on quote slides; what happened before/after goes in the notes)
    if notes is not None:
        dk.set_notes(s, notes)
    return [s]


# ================================================================ diagrams
def chain(
    slide,
    bx,
    steps_,
    upto=None,
    key_color=ORANGE,
    box_h=int(0.62 * IN),
    name="chain",
    numbered=True,
):
    """Step boxes left to right, joined by arrows: navy filled boxes with white text, the key
    step(s) orange; each box carries a one-line description (and optional date) beneath it.

    steps_: [dict(title, detail=None, date=None, key=False, muted=False)]; upto: steps drawn
    (builds). muted: a context step (navy 14% ground, navy text), e.g. "how it used to work".
    bx: (x, y, w, h) — boxes at the top of the box, descriptions under them."""
    x, y, w, h = bx
    n = len(steps_)
    gap = int(0.38 * IN)
    bw = (w - (n - 1) * gap) // n
    for i, st in enumerate(steps_[: upto or n]):
        muted = st.get("muted") and not st.get("key")
        sx = x + i * (bw + gap)
        yy = y
        if st.get("date"):
            label(
                slide,
                sx,
                yy,
                bw,
                st["date"],
                ORANGE if st.get("key") else LABEL,
                name=f"{name}-{i}-date",
            )
            yy += int(0.28 * IN)
        fill = key_color if st.get("key") else NAVY
        box(
            slide,
            sx,
            yy,
            bw,
            box_h,
            fill,
            name=f"{name}-{i}-box",
            tex="shade" if muted else None,
        )
        head = (f"{i + 1:02d}  " if numbered else "") + st["title"]
        text(
            slide,
            sx + int(0.12 * IN),
            yy,
            bw - int(0.2 * IN),
            box_h,
            head,
            12,
            NAVY if muted else WHITE,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
            name=f"{name}-{i}-title",
            line=0.95,
        )
        if st.get("detail"):
            text(
                slide,
                sx,
                yy + box_h + int(0.12 * IN),
                bw,
                h - (yy - y) - box_h - int(0.12 * IN),
                st["detail"],
                11,
                LABEL,
                name=f"{name}-{i}-detail",
            )
        if i < n - 1 and (upto is None or i + 1 < upto):
            ay = yy + box_h // 2
            line(
                slide,
                sx + bw + int(0.05 * IN),
                ay,
                sx + bw + gap - int(0.05 * IN),
                ay,
                GREY_LINE,
                1.25,
                arrow=True,
                name=f"{name}-{i}-arrow",
            )


def compare(
    slide, bx, columns, upto=None, name="compare", value_w=int(1.35 * IN), value_size=20
):
    """Two or three columns side by side. columns: [dict(head, sub=None, accent=NAVY, items=
    [(value, text, source_label)])]; each column: a coloured caps head with a 2 pt rule, then
    rows of a bold value (display-font 20 pt) and its explanation, separated by hairlines. source_label
    is a short grey tag ("Publisher, Sep 2026"); the full source still goes in the footer.
    upto: columns drawn (builds). value_w / value_size: width and size of the value column."""
    x, y, w, h = bx
    n = len(columns)
    gap = int(0.45 * IN)
    cw = (w - (n - 1) * gap) // n
    for c, col in enumerate(columns[: upto or n]):
        cx = x + c * (cw + gap)
        acc = col.get("accent", NAVY)
        label(slide, cx, y, cw, col["head"], acc, size=10.5, name=f"{name}-{c}-head")
        rule(slide, cx, y + int(0.3 * IN), cw, acc, 2.0, name=f"{name}-{c}-rule")
        yy = y + int(0.42 * IN)
        if col.get("sub"):
            text(
                slide,
                cx,
                yy,
                cw,
                int(0.3 * IN),
                col["sub"],
                11,
                LABEL,
                name=f"{name}-{c}-sub",
            )
            yy += int(0.36 * IN)
        items = col["items"]
        rh = (y + h - yy) // max(1, len(items))
        vw = value_w
        for i, it in enumerate(items):
            value, expl = it[0], it[1]
            tag = it[2] if len(it) > 2 else None
            text(
                slide,
                cx,
                yy + int(0.06 * IN),
                vw,
                int(0.45 * IN),
                value,
                value_size,
                acc,
                font=DISPLAY,
                name=f"{name}-{c}-{i}-v",
            )
            text(
                slide,
                cx + vw,
                yy + int(0.06 * IN),
                cw - vw,
                rh - int(0.36 * IN),
                expl,
                12,
                NAVY,
                name=f"{name}-{c}-{i}-t",
            )
            if tag:
                tl = math.ceil(len(expl) * 12 * 0.5 * PT / (cw - vw))
                text(
                    slide,
                    cx + vw,
                    yy + int(0.1 * IN) + int(tl * 12 * 1.3 * PT),
                    cw - vw,
                    int(0.24 * IN),
                    tag,
                    9.5,
                    MUTED,
                    name=f"{name}-{c}-{i}-s",
                )
            if i < len(items) - 1:
                rule(slide, cx, yy + rh - int(0.04 * IN), cw, name=f"{name}-{c}-{i}-r")
            yy += rh


def cards(slide, bx, items, upto=None, name="cards", accent=None):
    """Numbered cards in a row: 01, 02… in display-font, a hairline, a bold head (12 pt) and a short
    text (11 pt). items: [(head, text)] or [(head, text, key)] — key cards take the orange number
    and rule. accent: index of the card to highlight (alternative to key). upto: cards drawn."""
    x, y, w, h = bx
    n = len(items)
    gap = int(0.3 * IN)
    cw = (w - (n - 1) * gap) // n
    for i, it in enumerate(items[: upto or n]):
        head, body = it[0], it[1]
        key = (len(it) > 2 and it[2]) or accent == i
        cx = x + i * (cw + gap)
        col = ORANGE if key else NAVY
        text(
            slide,
            cx,
            y,
            cw,
            int(0.32 * IN),
            f"{i + 1:02d}",
            15,
            col,
            font=DISPLAY,
            name=f"{name}-{i}-n",
        )
        rule(
            slide,
            cx,
            y + int(0.36 * IN),
            cw,
            col if key else RULE,
            1.5 if key else 0.75,
            name=f"{name}-{i}-r",
        )
        text(
            slide,
            cx,
            y + int(0.46 * IN),
            cw,
            h - int(0.46 * IN),
            [
                [{"t": head, "bold": True, "size": 12}],
                [{"t": body, "size": 11, "color": LABEL}],
            ],
            12,
            NAVY,
            name=f"{name}-{i}-t",
        )


def stat_in_context(
    slide, bx, value, what, bars, note=None, name="stat", value_color=ORANGE
):
    """A number never stands alone: the value (display-font 40 pt) and what it measures, then the
    comparison it lives in as proportional native bars — e.g. 26% now against ~1% in March.
    bars: [(label, number, display, highlight)] drawn top-down on a common scale (max = largest
    number); the highlighted bar is orange, the rest grey. note: scope line beneath."""
    x, y, w, h = bx
    text(
        slide,
        x,
        y,
        w,
        int(0.7 * IN),
        value,
        40,
        value_color,
        font=DISPLAY,
        name=f"{name}-v",
        anchor=MSO_ANCHOR.BOTTOM,
    )
    text(
        slide,
        x,
        y + int(0.75 * IN),
        w,
        int(0.5 * IN),
        what,
        12,
        NAVY,
        name=f"{name}-what",
    )
    top = y + int(1.35 * IN)
    mx = max(b[1] for b in bars) or 1
    lw = int(1.4 * IN)
    bw = w - lw - int(0.75 * IN)
    for i, (lab, num, disp, hi) in enumerate(bars):
        by = top + i * int(0.42 * IN)
        text(
            slide,
            x,
            by,
            lw - int(0.1 * IN),
            int(0.3 * IN),
            lab,
            11,
            NAVY if hi else LABEL,
            anchor=MSO_ANCHOR.MIDDLE,
            name=f"{name}-{i}-l",
        )
        ww = max(int(0.03 * IN), int(bw * num / mx))
        box(
            slide,
            x + lw,
            by + int(0.04 * IN),
            ww,
            int(0.22 * IN),
            ORANGE if hi else GREY,
            name=f"{name}-{i}-b",
        )
        text(
            slide,
            x + lw + ww + int(0.08 * IN),
            by,
            int(0.8 * IN),
            int(0.3 * IN),
            disp,
            11,
            NAVY,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
            name=f"{name}-{i}-d",
        )
    if note:
        text(
            slide,
            x,
            top + len(bars) * int(0.42 * IN) + int(0.1 * IN),
            w,
            int(0.4 * IN),
            note,
            9.5,
            MUTED,
            name=f"{name}-note",
        )


def term(slide, bx, word, definition, example=None, kicker=None, name="term"):
    """A defined word: small caps kicker ("WORD 1 OF 4"), the word (display-font 30 pt), the definition
    (14 pt) and an example line (11 pt grey). Returns the y below it."""
    x, y, w, h = bx
    if kicker:
        label(slide, x, y, w, kicker, SOFT, name=f"{name}-k")
        y += int(0.3 * IN)
    text(slide, x, y, w, int(0.6 * IN), word, 30, NAVY, font=DISPLAY, name=f"{name}-w")
    y += int(0.62 * IN)
    n = math.ceil(len(definition) * 14 * 0.5 * PT / w)
    dh = int(n * 14 * 1.35 * PT)
    text(slide, x, y, w, dh, definition, 14, NAVY, name=f"{name}-d")
    y += dh + int(0.12 * IN)
    if example:
        text(slide, x, y, w, int(0.5 * IN), example, 11, LABEL, name=f"{name}-e")
        y += int(0.5 * IN)
    return y


# ================================================================ timeline
def timeline(
    slide,
    bx,
    events,
    start=None,
    end=None,
    scale="linear",
    ticks=None,
    span=None,
    upto=None,
    axis_y=None,
    name="tl",
    tick_fmt=None,
    desc_w=int(2.1 * IN),
    walk=None,
):
    """Events on one horizontal axis, revealed in order (fixed geometry across builds).

    events: [dict(at, label, detail=None, date=None, key=False, side="above"|"below", dx=0)]
      at: a position on the scale — date / ISO string (scale "linear" over dates), a number
      (hours, days, years… with scale "linear" or "log"), or ignored with scale "ordinal"
      (events evenly spaced in list order). side: text above or below the axis. dx: horizontal
      nudge of the text (EMU) when two events crowd. key: orange marker and head.
    start, end: axis range (same unit as `at`; dates allowed). ticks: [(at, text)] axis labels.
    span: optional highlighted window dict(a, b, label, sub=None, color=ORANGE, show_from=1) — an
      orange band on the axis between two positions with its own label (e.g. the N-day window);
      shown from build step show_from (1-based event count) onwards.
    upto: events drawn (builds). Each event's text is a detail callout (date, label, 1–2 line
      description) joined to its marker by a leader; lift (EMU, per event) lengthens the leader to
      stagger crowded callouts. walk: index of the current event for walk mode — earlier events
      stay small and grey (marker + label only), the current one is orange with its full callout,
      later ones are not drawn; `walk_slides` makes one slide per event this way.
    Returns the position function at → x (EMU)."""
    x, y, w, h = bx
    ay = axis_y if axis_y is not None else y + h // 2
    n = len(events)

    def num(v):
        if isinstance(v, (str, date)):
            return serial(v)
        return float(v)

    if scale == "ordinal":

        def pos(
            v,
        ):  # markers near the left of equal slots, so each callout fits its slot
            return int(x + w * (v + 0.08) / n)

        ats = list(range(n))
    else:
        lo, hi = num(start), num(end)
        if scale == "log":

            def pos(v):
                return int(
                    x
                    + w
                    * (math.log(num(v)) - math.log(lo))
                    / (math.log(hi) - math.log(lo))
                )
        else:

            def pos(v):
                return int(x + w * (num(v) - lo) / (hi - lo))

        ats = [e["at"] for e in events]
    line(slide, x, ay, x + w, ay, NAVY, 2.0, name=f"{name}-axis")
    for i, (tv, tt) in enumerate(ticks or []):
        tx = pos(tv)
        line(
            slide,
            tx,
            ay - int(0.06 * IN),
            tx,
            ay + int(0.06 * IN),
            NAVY,
            1.25,
            name=f"{name}-tick-{i}",
        )
        text(
            slide,
            tx - int(0.6 * IN),
            ay + int(0.1 * IN),
            int(1.2 * IN),
            int(0.25 * IN),
            tt,
            10,
            LABEL,
            align=PP_ALIGN.CENTER,
            name=f"{name}-tickl-{i}",
        )
    shown = n if upto is None else upto
    if walk is not None:
        shown = walk + 1
    if span and shown >= span.get("show_from", 1):
        a, b = pos(span["a"]), pos(span["b"])
        col = span.get("color", ORANGE)
        box(
            slide,
            a,
            ay - int(0.07 * IN),
            b - a,
            int(0.14 * IN),
            col,
            name=f"{name}-span",
        )
        sy = (
            ay + int(0.42 * IN)
            if span.get("side", "below") == "below"
            else ay - int(0.95 * IN)
        )
        text(
            slide,
            a,
            sy,
            max(b - a - int(0.15 * IN), int(1.6 * IN)),
            int(0.5 * IN),
            [[{"t": span["label"], "bold": True, "color": col}]]
            + (
                [[{"t": span["sub"], "size": 10.5, "color": LABEL}]]
                if span.get("sub")
                else []
            ),
            12,
            col,
            name=f"{name}-span-l",
        )
    for i, ev in enumerate(events[:shown]):
        ex = pos(ats[i])
        past = walk is not None and i < walk
        if walk is not None:
            col = GREY_LINE if past else ORANGE
        else:
            col = ORANGE if ev.get("key") else NAVY
        above = ev.get("side", "above") == "above"
        dot(
            slide,
            ex,
            ay,
            int((0.12 if past else 0.16) * IN),
            col,
            name=f"{name}-{i}-dot",
        )
        lift = ev.get("lift", 0)
        stem = int(0.32 * IN) + lift
        tx = ex - int(0.05 * IN) + ev.get("dx", 0)
        tw = ev.get("w", desc_w)
        paras = []
        if past:
            ev = {"label": ev["label"], "date": ev.get("date")}
        if ev.get("date"):
            paras.append(
                [
                    {
                        "t": ev["date"].upper(),
                        "size": 9.5,
                        "bold": True,
                        "spacing": 1.0,
                        "color": col if col != NAVY else LABEL,
                    }
                ]
            )
        paras.append(
            [
                {
                    "t": ev["label"],
                    "size": 10.5 if past else 12.5,
                    "bold": True,
                    "color": col,
                }
            ]
        )
        if ev.get("detail"):
            paras.append([{"t": ev["detail"], "size": 11, "color": LABEL}])
        th = int(1.25 * IN)
        if above:
            line(
                slide,
                ex,
                ay - stem,
                ex,
                ay - int(0.1 * IN),
                GREY_LINE,
                0.75,
                name=f"{name}-{i}-stem",
            )
            text(
                slide,
                tx,
                ay - stem - th - int(0.04 * IN),
                tw,
                th,
                paras,
                12,
                col,
                anchor=MSO_ANCHOR.BOTTOM,
                name=f"{name}-{i}-t",
            )
        else:
            line(
                slide,
                ex,
                ay + int(0.1 * IN),
                ex,
                ay + stem,
                GREY_LINE,
                0.75,
                name=f"{name}-{i}-stem",
            )
            text(
                slide,
                tx,
                ay + stem + int(0.04 * IN),
                tw,
                th,
                paras,
                12,
                col,
                name=f"{name}-{i}-t",
            )
    return pos


def walk_slides(prs, base, title, sources, events, bx=None, notes=None, **timeline_kw):
    """Walk mode: one slide per event on the same axis — the current event orange with its
    callout, the earlier ones small and grey — so the presenter walks event by event. Each
    event may carry `say`: the short sentence shown as that slide's takeaway (the presenter's
    memory trigger). bx defaults to the content area under the takeaway. Returns the slides."""
    box_ = bx or (X0, Y0 + int(0.6 * IN), X1 - X0, Y1 - Y0 - int(0.6 * IN))

    def draw(s, k):
        ev = events[k - 1]
        if ev.get("say"):
            takeaway(s, ev["say"])
        timeline(s, box_, events, walk=k - 1, **timeline_kw)

    return steps(prs, base, title, sources, len(events), draw, notes)


LIFECYCLE = [
    dict(
        label="Vulnerability exists",
        detail="A flaw in the code. Nobody may know about it yet.",
        side="above",
    ),
    dict(
        label="Exploit built",
        detail="Code that uses the flaw to break in.",
        side="below",
        key=True,
    ),
    dict(
        label="Patch published",
        detail="The vendor releases a fix. The flaw is now public.",
        side="above",
    ),
    dict(
        label="Patch installed",
        detail="The fix reaches your systems. Until then you are exposed.",
        side="below",
    ),
]


# ================================================================ source screenshot
def screenshot(
    slide,
    png,
    bx,
    crop=None,
    highlights=(),
    mat=True,
    name="screenshot",
    align="center",
):
    """A real captured source page (the only non-logo raster a deck may show), cropped to the
    relevant passage and fitted in bx (x, y, w, h), on a light tint mat (no outline), with the
    key phrase(s) marked by translucent orange highlight boxes. No caption and no source text:
    the source goes in the footer like on every slide.

    crop: (left, top, right, bottom) in image pixels (None = whole image). highlights: [(left,
    top, right, bottom)] in image pixels of the ORIGINAL image. align: "center" or "left".
    Returns (picture, to_slide) where to_slide(px, py) maps image pixels to slide EMU."""
    import struct

    with open(png, "rb") as f:
        iw, ih = struct.unpack(">II", f.read(24)[16:24])
    l, t, r, b = crop or (0, 0, iw, ih)
    x, y, w, h = bx
    pad = int(0.1 * IN) if mat else 0
    aw, ah = w - 2 * pad, h - 2 * pad
    scale = min(aw / (r - l), ah / (b - t))
    pw, ph = int((r - l) * scale), int((b - t) * scale)
    px = x + pad + (0 if align == "left" else (aw - pw) // 2)
    py = y + pad + (ah - ph) // 2
    if mat:
        box(
            slide,
            px - pad,
            py - pad,
            pw + 2 * pad,
            ph + 2 * pad,
            TINT,
            name=f"{name}-mat",
        )
    pic = slide.shapes.add_picture(str(png), Emu(px), Emu(py), Emu(pw), Emu(ph))
    pic.crop_left, pic.crop_right = l / iw, 1 - r / iw
    pic.crop_top, pic.crop_bottom = t / ih, 1 - b / ih
    pic.name = name
    dk.USED.add(Path(png))

    def to_slide(qx, qy):
        return int(px + (qx - l) * scale), int(py + (qy - t) * scale)

    for i, (hl, ht, hr, hb) in enumerate(highlights):
        x1, y1 = to_slide(hl, ht)
        x2, y2 = to_slide(hr, hb)
        s = box(slide, x1, y1, x2 - x1, y2 - y1, ORANGE, name=f"{name}-hl-{i}")
        clr = s.fill._xPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
        a = etree.SubElement(clr, qn("a:alpha"))
        a.set("val", "32000")
    return pic, to_slide


# ================================================================ section transitions
def section_divider(
    prs,
    base,
    modules,
    module_on,
    parts=None,
    part_on=None,
    descriptions=None,
    notes="",
    title="Today",
):
    """The two-level contents slide re-inserted before every sub-section (decided 9 Nov 2026): the
    day's modules big, this module's parts small, the CURRENT module and part navy with white
    text, everything else grey; a callback to where we are. Built on `dk.contents_slide` (no
    "Module NN, in N parts" caption). notes: at most a one-line signpost from the script.
    Returns the slide (caller adds it to the deck order).

    A single-level talk (one module, one agenda) passes its agenda as `modules` and omits
    `parts`: one row of large items, the current one lit. descriptions: one very short line per
    item (what the section covers), set under its name inside the box.

    In a deck, every slide after a contents slide carries that section as a small kicker above
    its title ("02 · Cybersecurity"; added by the deck build)."""
    s = dk.contents_slide(
        prs, base, modules, parts, module_on, part_on, title=title, descriptions=descriptions
    )
    dk.set_notes(s, notes or "")
    return s


# ================================================================ agent grid
def agent_grid(
    slide,
    bx,
    agents,
    colors,
    t=None,
    default="idle",
    cols=None,
    gap=0.2,
    min_size=0.45,
    legend=None,
    bubbles=None,
    name="grid",
):
    """Many small native squares, one per agent (the huggingface.wtf grid): each square sized by
    activity, coloured by its state at time step `t`, all in a fixed grid so every build step
    has identical geometry.

    agents: [dict(state=str) or dict(timeline=[(time, state), …] sorted by time), optional
      size (0..1: activity; the square's side scales from min_size to 1 of the cell)]. With
      timeline, the state at t is the last entry with time ≤ t (`default` before the first; t
      None = the final state).
    colors: {state: RGBColor or (RGBColor, texture)}; a state not in colors (e.g. default
      "idle") is drawn GREY. gap: fraction of the cell left empty. cols: fixed column count
      (None = the count that makes the largest square in bx).
    legend: [(kind, colour, text)] drawn under the grid (as `legend_line`; kind "bar" for a
      square swatch); the grid shrinks to leave it room.
    bubbles: [dict(agent=index, text=…, who=optional caption, side="auto"|"left"|"right")]: a
      speech bubble whose tail points at that agent's square, which is ringed in the accent. The
      bubble sits on the side with more room, clamped inside the slide.
    Returns dict(cols, rows, cell, x0, y0, counts={state: n}, center=f(i) → (x, y) EMU)."""
    x, y, w, h = bx
    if legend:
        h = h - int(0.4 * IN)
    n = len(agents)
    if cols is None:
        best = (0, 1)
        for c in range(1, n + 1):
            cell_ = min(w / c, h / math.ceil(n / c))
            if cell_ > best[0]:
                best = (cell_, c)
        cols = best[1]
    rows = math.ceil(n / cols)
    cell = min(w / cols, h / rows)
    x0 = x + (w - cols * cell) / 2
    y0 = y + (h - rows * cell) / 2
    counts = {}

    def state_of(a):
        if "timeline" not in a:
            return a.get("state", default)
        st = default
        for tt, s_ in a["timeline"]:
            if t is None or tt <= t:
                st = s_
            else:
                break
        return st

    def center(i):
        r, c = divmod(i, cols)
        return int(x0 + (c + 0.5) * cell), int(y0 + (r + 0.5) * cell)

    full = cell * (1 - gap)
    for i, a in enumerate(agents):
        st = state_of(a)
        counts[st] = counts.get(st, 0) + 1
        spec = colors.get(st, GREY)
        col, tex = (spec, None) if isinstance(spec, RGBColor) else spec
        side = full * (
            min_size + (1 - min_size) * max(0.0, min(1.0, a.get("size", 1.0)))
        )
        cx_, cy_ = center(i)
        box(
            slide,
            cx_ - side / 2,
            cy_ - side / 2,
            side,
            side,
            col,
            name=f"{name}-{i}",
            tex=tex,
        )
    if legend:
        legend_line(
            slide,
            x,
            y + h + int(0.15 * IN),
            [tuple(it) for it in legend],
            size=10,
            name=f"{name}-legend",
            max_w=w,
        )
    for j, b in enumerate(bubbles or []):
        speech_bubble(
            slide,
            center(int(b["agent"])),
            b["text"],
            who=b.get("who"),
            ring=cell * (1 - gap),
            side=b.get("side", "auto"),
            name=f"{name}-bubble-{j}",
        )
    return dict(
        cols=cols, rows=rows, cell=cell, x0=x0, y0=y0, counts=counts, center=center
    )


def speech_bubble(
    slide, at, content, who=None, ring=None, side="auto", w=int(3.3 * IN), name="bubble"
):
    """A speech bubble (white, ink outline, rounded) whose tail points at `at` (x, y EMU): what
    one agent or person said, quoted. who: a small caps caption above the words. ring: draw an
    accent ring of this side around the speaker's mark. side: "auto" picks the side of `at` with
    more room."""
    ax, ay = at
    size = 13 if len(content) < 90 else 11.5
    n = text_lines(content, size, w - int(0.36 * IN))
    n = text_lines(content, size, w - int(0.5 * IN))
    h = int((n * size * 1.3 + (14 if who else 0)) * PT) + int(0.42 * IN)
    if side == "auto":
        side = "left" if ax > (X0 + X1) / 2 else "right"
    off = int(0.45 * IN)
    bx_ = ax - off - w if side == "left" else ax + off
    bx_ = max(X0, min(bx_, X1 - w))
    by_ = max(Y0, min(ay - h - int(0.35 * IN), Y1 - h))
    if by_ + h > ay - int(0.1 * IN) and ay - h - int(0.35 * IN) < Y0:
        by_ = min(ay + int(0.35 * IN), Y1 - h)
    sh = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGULAR_CALLOUT,
        Emu(int(bx_)),
        Emu(int(by_)),
        Emu(int(w)),
        Emu(int(h)),
    )
    sh.adjustments[0] = (ax - (bx_ + w / 2)) / w
    sh.adjustments[1] = (ay - (by_ + h / 2)) / h
    sh.fill.solid()
    sh.fill.fore_color.rgb = WHITE
    sh.line.color.rgb = NAVY
    sh.line.width = Pt(1)
    sh.shadow.inherit = False
    dk._drop_style(sh)
    sh.name = name
    pad = int(0.24 * IN)
    ty = by_ + pad
    if who:
        label(slide, bx_ + pad, ty, w - 2 * pad, who, SOFT, size=8.5, name=f"{name}-who")
        ty += int(14 * PT)
    text(
        slide,
        bx_ + pad,
        ty,
        w - 2 * pad,
        h - (ty - by_) - pad // 2,
        [[{"t": f"“{content}”", "italic": True}]],
        size,
        NAVY,
        line=1.12,
        name=f"{name}-text",
    )
    if ring:
        r = int(ring * 1.9)
        o = slide.shapes.add_shape(
            MSO_SHAPE.OVAL, Emu(int(ax - r / 2)), Emu(int(ay - r / 2)), Emu(r), Emu(r)
        )
        o.fill.background()
        o.line.color.rgb = ORANGE
        o.line.width = Pt(2)
        o.shadow.inherit = False
        dk._drop_style(o)
        o.name = f"{name}-ring"
    return sh


# ================================================================ title page
BRAND_DARK = brand.color("dark_ground")  # dark full-bleed grounds
# Speaker, date and event are talk content (talk.yaml), never library defaults.


def _on_dark(pct):
    """White at pct% opacity over the brand Dark (brand: white text at varying opacities)."""
    return RGBColor(*(round(255 * pct / 100 + c * (1 - pct / 100)) for c in BRAND_DARK))


def title_slide(
    prs,
    base,
    title,
    module_n=None,
    of=5,
    subtitle=None,
    speaker="",
    when="",
    event="",
    speakers=None,
    kicker=None,
    name="title",
):
    """The module's title page, identical in every deck and styled by the tokens: the
    `brand_dark` full bleed, the official white lockup (unaltered), "MODULE N OF 5", the title
    (display-font), an optional subtitle (body-font), and under a hairline the speaker line and the date
    and event line in white at brand opacities. Sharp corners, no shadows. base: any deck slide
    (its shapes are removed). Returns the slide; the caller sets its notes.

    A single-module talk omits `module_n`; `kicker` then replaces the "Module N of M" label (or
    nothing is drawn). speakers: ["Name · Role", …] for several presenters, set side by side
    under the hairline (name white, role dimmed); it replaces `speaker`."""
    s = dk.duplicate(prs, base)
    for sh in list(s.shapes):
        dk.remove(sh)
    W, H = prs.slide_width, prs.slide_height
    box(s, 0, 0, W, H, BRAND_DARK, name=f"{name}-ground")
    mx = int(0.95 * IN)
    lockup = brand.logo("lockup_white")
    if lockup is not None:
        logo(
            s,
            lockup,
            mx,
            int(0.7 * IN),
            int(0.8 * IN),
            name=f"{name}-lockup",
            navy=False,
        )
    tw = W - 2 * mx
    y = int(2.45 * IN)
    head = f"Module {module_n} of {of}" if module_n is not None else kicker
    if head:
        label(s, mx, y, tw, head, _on_dark(70), size=11, name=f"{name}-module")
    y += int(0.42 * IN)
    n = (
        text_lines(title, 54, tw) + 0
    )  # body-font metrics approximate display-font closely enough
    th = int(n * 54 * 1.18 * PT)
    text(
        s,
        mx,
        y,
        tw,
        th,
        title,
        54,
        WHITE,
        font=DISPLAY,
        line=1.05,
        name=f"{name}-title",
    )
    y += th + int(0.18 * IN)
    # No subtitle on title pages (decided 9 Nov 2026): `subtitle` is accepted and ignored.
    by = int(5.55 * IN)
    rule(s, mx, by, tw, _on_dark(30), 0.75, name=f"{name}-rule")
    occasion = " · ".join(p for p in (when, event) if p)
    if speakers:
        cw = min(int(4.2 * IN), tw // len(speakers))
        for i, sp in enumerate(speakers):
            photo = sp.get("photo") if isinstance(sp, dict) else None
            label_ = (
                f"{sp['name']} · {sp.get('role', '')}" if isinstance(sp, dict) else str(sp)
            )
            who, _, role = label_.partition(" · ")
            lines = [[{"t": who, "size": 14, "color": WHITE}]]
            if role:
                lines.append([{"t": role, "size": 12, "color": _on_dark(70)}])
            tx = mx + i * cw
            if photo:
                portrait(s, photo, tx, by + int(0.16 * IN), int(0.62 * IN), name=f"{name}-face-{i}")
                tx += int(0.78 * IN)
            text(
                s,
                tx,
                by + int(0.2 * IN),
                cw - int(0.2 * IN) - (int(0.78 * IN) if photo else 0),
                int(0.6 * IN),
                lines,
                14,
                WHITE,
                line=1.3,
                name=f"{name}-speaker-{i}",
            )
        if occasion:
            text(
                s,
                mx,
                by + int(0.9 * IN),
                tw,
                int(0.3 * IN),
                occasion,
                12,
                _on_dark(70),
                name=f"{name}-occasion",
            )
        return s
    text(
        s,
        mx,
        by + int(0.2 * IN),
        tw,
        int(0.9 * IN),
        [
            [{"t": speaker, "size": 14, "color": WHITE}],
            [{"t": occasion, "size": 12, "color": _on_dark(70)}],
        ],
        14,
        WHITE,
        line=1.3,
        name=f"{name}-byline",
    )
    return s


def one_thing(
    prs,
    base,
    lead,
    rest,
    kicker="The one thing to remember from this module",
    name="one-thing",
):
    """The module's one-thing statement (and, with another kicker, its closing payoff), identical
    in every deck: brand Dark full bleed, a small kicker, the statement in display-font, white lead +
    orange rest. Returns the slide; the caller sets its notes."""
    s = dk.duplicate(prs, base)
    for sh in list(s.shapes):
        dk.remove(sh)
    W, H = prs.slide_width, prs.slide_height
    box(s, 0, 0, W, H, BRAND_DARK, name=f"{name}-ground")
    mx = int(1.2 * IN)
    tw = W - 2 * mx
    label(
        s, mx, int(2.0 * IN), tw, kicker, _on_dark(70), size=11, name=f"{name}-kicker"
    )
    text(
        s,
        mx,
        int(2.45 * IN),
        tw,
        int(3.0 * IN),
        [[{"t": lead + " ", "color": WHITE}, {"t": rest, "color": ORANGE}]],
        30,
        WHITE,
        font=DISPLAY,
        line=1.12,
        name=f"{name}-statement",
    )
    return s


# ---------------------------------------------------------------- the operation pipeline (9 Nov 2026)
def pipeline(
    slide, box_, steps_, on=None, upto=None, mini=False, tag=None, name="pipeline"
):
    """An operation's steps left to right (e.g. Target, Produce, Disguise, Spread, Persuade) as
    native boxes joined by arrows; the one diagram reused across a module. Muting as `ladder`: with
    `on` set, that step is orange and the others are a pale navy ground with grey text; without
    `on`, every step is navy. mini=True: a thin strip (for the top of a step slide), smaller type.
    steps_: [str] or [dict(title, tag=None)]. tag: optional [str] per step (overrides a dict's tag),
    a small line under each box. upto: steps drawn (builds; None = all). Returns the list of
    (x, w) column positions so a caller can align a grid under the steps."""
    x, y, w, h = (int(v) for v in box_)
    n = len(steps_)
    shown = n if upto is None else upto
    gap = int((0.26 if mini else 0.42) * IN)
    bw = (w - (n - 1) * gap) // n
    bh = int((0.36 if mini else 0.72) * IN)
    size = 10.5 if mini else 14
    cols = []
    for i, st in enumerate(steps_):
        st = st if isinstance(st, dict) else {"title": st}
        sx = x + i * (bw + gap)
        cols.append((sx, bw))
        if i >= shown:
            continue
        lit = on is None or on == i
        if on == i:
            fill, ink, tex = ORANGE, WHITE, None
        elif lit:
            fill, ink, tex = NAVY, WHITE, None
        else:
            fill, ink, tex = NAVY, LABEL, "shade"
        box(slide, sx, y, bw, bh, fill, name=f"{name}-{i}-box", tex=tex)
        runs = [
            {
                "t": f"{i + 1}  ",
                "size": size - 2,
                "color": ink if on == i or on is None else GREY_LINE,
            },
            {"t": st["title"], "bold": True},
        ]
        text(
            slide,
            sx,
            y,
            bw,
            bh,
            [runs],
            size,
            ink,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
            name=f"{name}-{i}-title",
        )
        t = (tag[i] if tag and i < len(tag) else None) or st.get("tag")
        if t:
            th = max(0, h - bh - int(0.08 * IN))
            text(
                slide,
                sx,
                y + bh + int(0.08 * IN),
                bw,
                th,
                t,
                9.5 if mini else 12,
                (ORANGE if on == i else NAVY) if lit else GREY_LINE,
                align=PP_ALIGN.CENTER,
                name=f"{name}-{i}-tag",
                line=1.05,
            )
        if i < n - 1 and i + 1 < shown:
            ay = y + bh // 2
            line(
                slide,
                sx + bw + int(0.04 * IN),
                ay,
                sx + bw + gap - int(0.04 * IN),
                ay,
                GREY_LINE,
                1.0 if mini else 1.25,
                arrow=True,
                name=f"{name}-{i}-arrow",
            )
    return cols
