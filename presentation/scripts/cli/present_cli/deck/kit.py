"""The generic deck kit (task 0008): slide plumbing, builds as duplicated slides, notes, and
versioned output, lifted from the first consumer's deck library with every brand value moved to
the token file (`brand.py`, ADR 0008).

Style: display-font sentence-case titles; body-font text; one 9 pt "Source:" line per slide and
none when nothing is cited; one plot-only chart per slide at the full content width
(chart_slide), the headline in the title, one plain-typography figure, or a stats rail where a few
core numbers are the point; never shadows, outlines or left-rule cards; two-level contents slides
(contents_slide). Builds (progressive disclosure) are duplicated slides, each adding the next group
of shapes with everything before it intact; this survives PowerPoint, Google Slides and PDF alike.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from . import brand

# Every brand value comes from the active token file (ADR 0008; see brand.py).
NAVY = brand.color("ink")
MUTED = brand.color("muted")
LABEL = brand.color("label")
ORANGE = brand.color("accent")
RULE = brand.color("rule")
WHITE = brand.color("surface")
TILE_EDGE = brand.color("edge")
BODY = brand.font("body")
DISPLAY = brand.font("display")
TEAM_DISPLAY = brand.font("team_display")

TITLE_TOP = 800000  # EMU: shapes above this are the title band
FOOTER_TOP = 6300000  # EMU: shapes below this are the footer
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

ENGINE_VERSION = "1.0.0"  # the deck engine (task 0008); receipts record it

USED: set[Path] = set()  # every image placed, for the receipt


# ---------------------------------------------------------------- slide plumbing
def duplicate(prs, src):
    """Append a copy of slide `src` (shapes, background, image relationships). Shape names are
    preserved, so a copy's shapes can be addressed by the same Google Shape ids."""
    new = prs.slides.add_slide(src.slide_layout)
    tree = new.shapes._spTree
    for el in list(tree)[2:]:
        tree.remove(el)
    rid_map = {}
    for rid, rel in src.part.rels.items():
        if rel.reltype.endswith(("/notesSlide", "/slideLayout")):
            continue
        if rel.is_external:
            rid_map[rid] = new.part.relate_to(
                rel.target_ref, rel.reltype, is_external=True
            )
        else:
            rid_map[rid] = new.part.relate_to(rel._target, rel.reltype)
    for el in list(src.shapes._spTree)[2:]:
        c = copy.deepcopy(el)
        for node in c.iter():
            for attr in list(node.attrib):
                if attr.startswith("{%s}" % R_NS) and node.attrib[attr] in rid_map:
                    node.attrib[attr] = rid_map[node.attrib[attr]]
        tree.append(c)
    bg = src._element.cSld.bg
    if bg is not None:
        new._element.cSld.insert(0, copy.deepcopy(bg))
    return new


def shape(slide, key):
    """A shape by Google Shape id (int, the middle field of its name) or by exact name (str)."""
    for sh in slide.shapes:
        if (
            isinstance(key, int) and sh.name.split(";")[1:2] == [str(key)]
        ) or sh.name == key:
            return sh
    raise KeyError(key)


def remove(sh):
    sh._element.getparent().remove(sh._element)


def set_text(sh, *runs):
    """Replace text keeping the first run's formatting. runs: str or (str, RGBColor)."""
    tf = sh.text_frame
    p0 = tf.paragraphs[0]
    proto = copy.deepcopy(p0.runs[0]._r)
    for p in tf.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    for r in list(p0.runs):
        r._r.getparent().remove(r._r)
    end = p0._p.find("{%s}endParaRPr" % A_NS)
    for item in runs:
        text, color = (item, None) if isinstance(item, str) else item
        r = copy.deepcopy(proto)
        if end is not None:
            end.addprevious(r)
        else:
            p0._p.append(r)
        run = p0.runs[-1]
        run.text = text
        if color is not None:
            run.font.color.rgb = color


def add_text(
    slide,
    x,
    y,
    w,
    h,
    text,
    size,
    color=NAVY,
    anchor=MSO_ANCHOR.TOP,
    align=PP_ALIGN.LEFT,
    font=BODY,
    name=None,
):
    """Native text box. `text` is a str, or a list of paragraphs, each a list of
    (text, size, color, bold) runs. `name` makes it addressable in builds."""
    tb = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = text if isinstance(text, list) else [[(text, size, color, False)]]
    for i, segs in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        for t, sz, col, b in segs:
            r = p.add_run()
            r.text = t
            r.font.size = Pt(sz)
            r.font.color.rgb = col
            r.font.bold = b
            r.font.name = font
    return tb


def add_box(slide, x, y, w, h, fill=WHITE, line=TILE_EDGE, name=None):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(x), Emu(y), Emu(w), Emu(h))
    if name:
        s.name = name
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Emu(9525)
    s.shadow.inherit = False
    _drop_style(s)
    return s


def _drop_style(sh):
    """Remove the shape's theme style reference (<p:style>): its effectRef draws a drop shadow
    in LibreOffice/PDF even when spPr carries an empty effectLst (seen in v7.0.0)."""
    st = sh._element.find(
        "{http://schemas.openxmlformats.org/presentationml/2006/main}style"
    )
    if st is not None:
        sh._element.remove(st)


def replace_picture(slide, key, png):
    """Swap a picture for `png`, fitted inside the same box, centred, sent behind other shapes
    (the PNGs are opaque; the team's thin rules must stay visible). Keeps the old name."""
    old = shape(slide, key)
    x, y, w, h, name = old.left, old.top, old.width, old.height, old.name
    remove(old)
    pic = add_picture(slide, png, x, y, w, h)
    pic.name = name
    return pic


def add_picture(slide, png, x, y, w, h, name=None, crop=None, align="center"):
    """Picture fitted inside (x, y, w, h), sent to the back. crop: optional (left, right)
    fractions of the image width to cut away (one panel of a two-panel frame). align:
    "center" or "left" (horizontal)."""
    pic = slide.shapes.add_picture(str(png), Emu(x), Emu(y), width=Emu(w))
    iw, ih = pic.image.size
    aspect = iw / ih
    if crop:
        pic.crop_left, pic.crop_right = crop
        aspect *= 1 - crop[0] - crop[1]
    pw, ph = w, int(w / aspect)
    if ph > h:
        pw, ph = int(h * aspect), h
    pic.width, pic.height = pw, ph
    pic.left = x if align == "left" else x + (w - pw) // 2
    pic.top = y + (h - ph) // 2
    tree = slide.shapes._spTree
    tree.remove(pic._element)
    tree.insert(2, pic._element)
    if name:
        pic.name = name
    USED.add(Path(png))
    return pic


# ---------------------------------------------------------------- style
def _text_shapes(shapes, in_group=False):
    """(shape, in_group) for every shape, recursing into group shapes."""
    for sh in list(shapes):
        if sh.shape_type == 6:  # MSO_SHAPE_TYPE.GROUP
            yield from _text_shapes(sh.shapes, True)
        else:
            yield sh, in_group


def _pt(run):
    return run.font.size.pt if run.font.size is not None else None


def style(slide, title=None, footer=None, statement=None, title_size=24):
    """Apply the deck style to one slide.

    title: sentence-case text for the title-band shape (team display font -> display font). On a navy title
    slide (no text in the title band) the single largest >= 60 pt non-digit team-display-font shape is the
    title; no other shape is ever overwritten with it. statement: (white, orange) for navy
    statement/discussion slides. footer: source text without the "Source: " prefix, or None to
    remove the footer line. Any other team-display-font text (agenda digits, display numerals) becomes
    display-font run by run, in every paragraph and inside groups, each run scaled by 0.72.
    """
    shapes = list(_text_shapes(slide.shapes))
    has_band = any(
        not g
        and sh.has_text_frame
        and sh.text_frame.text.strip()
        and sh.top < TITLE_TOP
        for sh, g in shapes
    )
    navy_title = None
    if title is not None and not has_band:
        cands = [
            sh
            for sh, g in shapes
            if not g
            and sh.has_text_frame
            and sh.text_frame.text.strip()
            and not sh.text_frame.text.strip()[:2].isdigit()
            and any(
                r.font.name == TEAM_DISPLAY and (_pt(r) or 0) >= 60
                for p in sh.text_frame.paragraphs
                for r in p.runs
            )
        ]
        if cands:
            navy_title = max(
                cands,
                key=lambda sh: max(
                    _pt(r) or 0 for p in sh.text_frame.paragraphs for r in p.runs
                ),
            )
    for sh, grouped in shapes:
        if not sh.has_text_frame or not sh.text_frame.text.strip():
            continue
        runs = [r for p in sh.text_frame.paragraphs for r in p.runs]
        if not grouped and sh.top >= FOOTER_TOP:
            if footer is None:
                remove(sh)
                continue
            set_text(sh, "Source: " + footer)
            sh.width = Emu(10850000)
            for r in sh.text_frame.paragraphs[0].runs:
                r.font.size = Pt(9)
            continue
        if not grouped and title is not None and sh.top < TITLE_TOP:  # the title band
            set_text(sh, title)
            for r in sh.text_frame.paragraphs[0].runs:
                r.font.name = DISPLAY
                r.font.size = Pt(title_size)
            continue
        if not any(r.font.name == TEAM_DISPLAY for r in runs):
            continue
        whole = None
        if (
            statement is not None
            and not grouped
            and sh.top >= TITLE_TOP
            and (_pt(runs[0]) or 0) >= 30
        ):
            set_text(sh, statement[0], (statement[1], ORANGE))
            whole = 32
        elif sh is navy_title:
            set_text(sh, title)
            whole = 48
        if whole:
            for r in sh.text_frame.paragraphs[0].runs:
                r.font.name = DISPLAY
                r.font.size = Pt(whole)
            continue
        for (
            r
        ) in runs:  # display numerals and other team-display-font text keep their text, run by run
            if r.font.name != TEAM_DISPLAY:
                continue
            r.font.name = DISPLAY
            if _pt(r):
                r.font.size = Pt(max(9, round(_pt(r) * 0.72)))










# ---------------------------------------------------------------- builds
def builds(prs, slide, groups):
    """Progressive disclosure. groups: list of lists of shape keys (Google Shape id or name).
    Returns slides s1..sn where s_k shows the shapes in no group plus groups[0..k-1].
    The original slide is the last (complete) step; earlier steps are copies with later
    groups removed. Notes are copied by the caller (see notes())."""
    steps = []
    for k in range(1, len(groups)):
        s = duplicate(prs, slide)
        for g in groups[k:]:
            for key in g:
                remove(shape(s, key))
        steps.append(s)
    return steps + [slide]


def content_shapes(slide):
    """Shapes between the title band and the footer (not the logo, title, rail or footer)."""
    return [sh for sh in slide.shapes if TITLE_TOP <= sh.top < FOOTER_TOP]


def groups_by_x(slide, splits_in):
    """Reveal groups by column: content shapes binned by left edge at `splits_in` (inches).
    E.g. [6.5] -> [shapes left of 6.5 in], [shapes right of it]."""
    edges = [-1e9] + [x * 914400 for x in splits_in] + [1e12]
    return [
        [sh.name for sh in content_shapes(slide) if lo <= sh.left < hi]
        for lo, hi in zip(edges, edges[1:])
    ]


def groups_by_y(slide, splits_in):
    """As groups_by_x, binned by top edge."""
    edges = [-1e9] + [y * 914400 for y in splits_in] + [1e12]
    return [
        [sh.name for sh in content_shapes(slide) if lo <= sh.top < hi]
        for lo, hi in zip(edges, edges[1:])
    ]


# ---------------------------------------------------------------- full-width charts
INCH = 914400
CHART_BOX = (int(1.19 * INCH), int(1.0 * INCH), int(11.87 * INCH), int(5.65 * INCH))
"""x, y, w, h of the chart slot: the full content width, above the footer hairline (6.94 in).
Chart PNGs are rendered at 1920x906 (~2.12:1) for it."""


OFF_NUM = brand.color("off_number")  # greyed-out contents numerals
OFF_TEXT = brand.color("off_text")  # greyed-out contents labels


def add_figure(
    slide, x, y, w, figure, line, color=NAVY, size=40, line_size=13, name="figure"
):
    """A headline number as plain typography on the slide background (the deck standard,
    visual language): a large display-font figure and one small body-font line beneath it. No card,
    outline, rule or shadow. figure None: the line alone, at 18 pt navy. Returns shape names."""
    out = []
    if figure:
        fh = int(size * 1.25 * 12700)
        out.append(
            add_text(
                slide,
                x,
                y,
                w,
                fh,
                figure,
                size,
                color,
                font=DISPLAY,
                name=f"{name}-fig",
            ).name
        )
        y += fh + int(0.04 * INCH)
    ls = line_size if figure else 18
    per_line = max(1, int(w / (ls * 0.5 * 12700)))
    lines = max(1, -(-len(line) // per_line))
    out.append(
        add_text(
            slide,
            x,
            y,
            w,
            int(lines * ls * 1.3 * 12700),
            line,
            ls,
            LABEL if figure else NAVY,
            name=name,
        ).name
    )
    return out


RAIL_X = int(10.2 * INCH)
RAIL_W = int(13.06 * INCH) - RAIL_X
CHART_BOX_RAIL = (int(1.19 * INCH), int(1.0 * INCH), int(8.75 * INCH), int(5.65 * INCH))
"""Chart slot when a stats rail is used: the chart keeps the full height, the rail takes the
right 2.86 in."""


def add_rail(slide, items, top, x=None):
    """Right-hand stats rail, the team sidebar's typography without boxes or divider: per item
    a 9 pt bold caps label, a display-font figure (str; (number, unit) with a smaller unit; or a list
    of (text, size) runs) and a one-line body-font note. items: [(label, figure, note)]; x: left
    edge (default RAIL_X), width capped at 3.6 in. Returns one list of shape names per item."""
    groups, y = [], top
    RX = RAIL_X if x is None else x
    RW = min(int(13.06 * INCH) - RX, int(3.6 * INCH))
    step = min(int(1.75 * INCH), (int(6.75 * INCH) - top) // max(1, len(items)))
    for i, (label, figure, note) in enumerate(items):
        lab = add_text(
            slide,
            RX,
            y,
            RW,
            int(0.25 * INCH),
            label.upper(),
            9,
            LABEL,
            name=f"rail-{i}-label",
        )
        for r in lab.text_frame.paragraphs[0].runs:
            r.font.bold = True
        if isinstance(figure, list):  # [(text, size)], e.g. "3 sec → 16+ hr"
            runs = [[(t, sz, NAVY, False) for t, sz in figure]]
        else:
            big, unit = (figure, "") if isinstance(figure, str) else figure
            runs = [
                [(big, 40, NAVY, False)]
                + ([(" " + unit, 16, NAVY, False)] if unit else [])
            ]
        fig = add_text(
            slide,
            RX,
            y + int(0.27 * INCH),
            RW,
            int(0.7 * INCH),
            runs,
            40,
            font=DISPLAY,
            name=f"rail-{i}-fig",
        )
        top_size = max(sz for _, sz, _, _ in runs[0])
        nt = add_text(
            slide,
            RX,
            y + int(0.3 * INCH) + int(top_size * 1.32 * 12700),
            RW,
            int(0.5 * INCH),
            note,
            11,
            MUTED,
            name=f"rail-{i}-note",
        )
        groups.append([lab.name, fig.name, nt.name])
        y += step
    return groups


def chart_slide(
    prs,
    base,
    frames,
    title,
    footer,
    callout=None,
    step_titles=None,
    rail=None,
    rail_shown=0,
    rail_sync=False,
):
    """One chart, its stages as click builds; full content width (CHART_BOX) unless a rail is
    given.

    base: a team slide to copy the frame from (logo, rail, title band, footer); every content
    shape on the copy (old picture, sidebar) is removed. frames: PNG paths, one per stage, each
    later stage drawn over the previous; a frame may be (path, (crop_left, crop_right)) to show
    one panel of a two-panel render (one graph per slide). callout: optional (figure, line, fx, fy, fw), position
    and width as fractions of the placed picture, set as plain typography (add_figure); revealed
    as the last click. rail: optional [(label, figure, note)] stating the core point the chart
    proves, on the right (add_rail: "make the core point on the right like
    we used to"); the chart then sits left. The first `rail_shown` items appear with the chart,
    each later one is its own click; rail_sync: item i appears with stage i instead. step_titles: optional per-step
    titles (None keeps `title`). Returns the build slides."""
    s = duplicate(prs, base)
    for sh in content_shapes(s):
        remove(sh)
    box = CHART_BOX_RAIL if rail else CHART_BOX
    names = [f"stage-{i}" for i in range(len(frames))]
    pics = {}
    for i in reversed(
        range(len(frames))
    ):  # inserted at the back: later stages in front
        f, crop = frames[i] if isinstance(frames[i], tuple) else (frames[i], None)
        pics[i] = add_picture(
            s, f, *box, name=names[i], crop=crop, align="left" if rail else "center"
        )
    groups = [[n] for n in names]
    if rail:
        right = max(p.left + p.width for p in pics.values())
        rg = add_rail(
            s,
            rail,
            max(pics[0].top, int(1.15 * INCH)),
            x=min(RAIL_X, right + int(0.45 * INCH)),
        )
        if rail_sync:
            for i, g in enumerate(rg[: len(groups)]):
                groups[i] += g
            groups += rg[len(groups) :]
        else:
            groups[0] += [n for g in rg[:rail_shown] for n in g]
            groups += rg[rail_shown:]
    if callout:
        figure, line, fx, fy, fw = callout
        p = pics[0]
        groups.append(
            add_figure(
                s,
                p.left + int(fx * p.width),
                p.top + int(fy * p.height),
                int(fw * p.width),
                figure,
                line,
                color=ORANGE,
                name="callout",
            )
        )
    style(s, title=title, footer=footer)
    steps = builds(prs, s, groups)
    for sl, t in zip(steps, step_titles or []):
        if t:
            style(sl, title=t, footer=footer)
    return steps




# ---------------------------------------------------------------- definitions
def definition_slide(
    prs, base, word, definition, example, illustration=None, title=None, footer=None
):
    """One concept per slide : the word (display-font, large), its definition
    (body-font) and a one-line example on the left half; an illustration of the concept on the
    right half. illustration: a PNG/JPG path, or None / missing file = right half left empty
    (the next build picks it up). Returns the slide."""
    s = duplicate(prs, base)
    for sh in content_shapes(s):
        remove(sh)
    x, w = int(1.19 * INCH), int(5.35 * INCH)
    add_text(
        s,
        x,
        int(1.75 * INCH),
        w,
        int(1.0 * INCH),
        word,
        48,
        NAVY,
        font=DISPLAY,
        name="def-word",
    )
    add_text(
        s,
        x,
        int(2.95 * INCH),
        w,
        int(2.0 * INCH),
        definition,
        20,
        NAVY,
        name="def-text",
    )
    add_text(
        s,
        x,
        int(5.15 * INCH),
        w,
        int(0.9 * INCH),
        example,
        14,
        LABEL,
        name="def-example",
    )
    if illustration and Path(illustration).exists():
        add_picture(
            s,
            illustration,
            int(6.95 * INCH),
            int(1.0 * INCH),
            int(6.11 * INCH),
            int(5.65 * INCH),
            name="def-illustration",
        )
    style(s, title=title, footer=footer)
    return s


# ---------------------------------------------------------------- two-level contents
def contents_slide(
    prs,
    base,
    modules,
    parts=None,
    module_on=None,
    part_on=None,
    parts_caption=None,
    title="Today",
    descriptions=None,
):
    """The day's agenda (big row) with this module's parts (small row) beneath it
    (the deck standard, "Contents: two levels"). The current module and current part are
    navy fills with white text; every other item is light grey text with no box.

    base: a team slide to copy the frame from (logo, title band); its content and footer are
    removed. modules / parts: labels (numbered 01..); module_on / part_on: 0-based or None.
    parts None: one row only (a module without parts, e.g. the close). Returns the slide."""
    s = duplicate(prs, base)
    for sh in content_shapes(s):
        remove(sh)
    x0, x1, gap = int(1.19 * INCH), int(13.06 * INCH), int(0.2 * INCH)

    def row(labels, on, y, h, num_size, lab_size, lab_dy, tag, descs=None):
        n = len(labels)
        w = (x1 - x0 - (n - 1) * gap) // n
        pad = int(0.22 * INCH)
        # never break a word: shrink the label size until the longest word fits the column
        longest = max((len(wd) for lb in labels for wd in str(lb).split()), default=1)
        lab_size = min(lab_size, (w - 2 * pad) / (longest * 0.56 * 12700))
        for i, label in enumerate(labels):
            x = x0 + i * (w + gap)
            lit = i == on
            if lit:
                add_box(s, x, y, w, h, fill=NAVY, line=None, name=f"{tag}-{i}-fill")
            add_text(
                s,
                x + pad,
                y + pad,
                w - 2 * pad,
                int(num_size * 1.3 * 12700),
                f"{i + 1:02d}",
                num_size,
                WHITE if lit else OFF_NUM,
                font=DISPLAY,
                name=f"{tag}-{i}-n",
            )
            add_text(
                s,
                x + pad,
                y + lab_dy,
                w - 2 * pad,
                h - lab_dy - pad // 2,
                label,
                lab_size,
                WHITE if lit else OFF_TEXT,
                name=f"{tag}-{i}-l",
            )
            if descs and i < len(descs) and descs[i]:
                add_text(
                    s,
                    x + pad,
                    y + lab_dy + int(lab_size * 2.9 * 12700),
                    w - 2 * pad,
                    h - lab_dy - int(lab_size * 2.9 * 12700) - pad,
                    descs[i],
                    min(11.5, lab_size * 0.8),
                    WHITE if lit else OFF_TEXT,
                    name=f"{tag}-{i}-d",
                )

    big_h = int((2.75 if parts else 3.9) * INCH)
    row(
        modules,
        module_on,
        int(1.15 * INCH),
        big_h,
        54,
        15,
        int(1.55 * INCH),
        "module",
        None if parts else descriptions,
    )
    if parts:
        y = int(4.25 * INCH)
        if False and parts_caption:  # decided 2026-11-09: no "Module NN, in N parts" line on any contents slide
            add_text(
                s,
                x0,
                y,
                x1 - x0,
                int(0.3 * INCH),
                parts_caption,
                11,
                OFF_TEXT,
                name="parts-caption",
            )
        row(
            parts,
            part_on,
            y + int(0.4 * INCH),
            int(1.55 * INCH),
            28,
            14,
            int(0.85 * INCH),
            "part",
        )
    style(s, title=title, footer=None)
    return s


# ---------------------------------------------------------------- script -> notes
NOTE_TAGS = re.compile(
    r"\s*\[(CLAIM [^\]]+|NEW-\d+[a-z]?|SRC [^\]]+|SPK-[^\]]+|OPTION[^\]]*|TO SOURCE|TO VERIFY[^\]]*)\]"
)


def clean_notes(text):
    """Speaker notes as spoken: drops `[ON SCREEN …]` lines and every citation/work tag (CLAIM,
    NEW-, SRC, SPK-, OPTION, TO SOURCE, TO VERIFY); collapses the blank lines left behind."""
    lines = [
        NOTE_TAGS.sub("", ln)
        for ln in text.splitlines()
        if not ln.lstrip().startswith("[ON SCREEN")
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def script_by_slide(script_path):
    """{"N": spoken text} from `[Slide N …]` markers (N may carry a letter: "8b"); ON SCREEN lines
    and citation tags stripped (`clean_notes`); headings skipped."""
    out, cur = {}, None
    for line in Path(script_path).read_text().splitlines():
        m = re.match(r"\[Slide (\d+[a-z]?)", line)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        if line.startswith("#") or cur is None:
            continue
        out[cur].append(line)
    return {k: clean_notes("\n".join(v)) for k, v in out.items()}


_SOURCES: dict[int, list] = {}


def set_sources(slide, refs):
    """Record a slide's full references [(text, url)] and (re)write its notes with them."""
    _SOURCES[id(slide.part)] = list(refs)
    set_notes(slide, _NOTES.get(id(slide.part), ""))


_NOTES: dict[int, str] = {}


def set_notes(slide, text):
    """The speaker notes: `text`, then the slide's full references (the footer shows short
    labels only; components 1.2.0)."""
    _NOTES[id(slide.part)] = text or ""
    refs = _SOURCES.get(id(slide.part)) or []
    block = ""
    if refs:
        block = "Sources:\n" + "\n".join(
            f"- {t}" + (f" — {u}" if u else "") for t, u in refs
        )
    slide.notes_slide.notes_text_frame.text = "\n\n".join(p for p in (text, block) if p)


def reorder(prs, order):
    """Make `order` the deck; drop every slide not in it."""
    lst = prs.slides._sldIdLst
    by_part = {prs.part.related_part(e.rId): e for e in list(lst)}
    keep = {s.part for s in order}
    for e in list(lst):
        lst.remove(e)
    for s in order:
        lst.append(by_part[s.part])
    for part, e in by_part.items():
        if part not in keep:
            prs.part.drop_rel(e.rId)






