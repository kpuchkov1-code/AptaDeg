"""AptaDeg — co-founder overview PDF.
What the model does, why it's useful, current limitations, and next steps.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether, Image,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.graphics.shapes import (
    Drawing, Rect, String, Line, Polygon, Circle,
)
RoundRect = lambda x, y, w, h, r, **kw: Rect(x, y, w, h, rx=r, ry=r, **kw)
from reportlab.lib.colors import HexColor

OUT = "AptaDeg_Overview.pdf"

W, H = A4
LEFT = RIGHT = 2.2 * cm
TEXT_W = W - LEFT - RIGHT          # ~454 pt

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BLACK   = colors.black
WHITE   = colors.white
DARK    = HexColor("#111111")
MID     = HexColor("#444444")
GREY    = HexColor("#777777")
LGREY   = HexColor("#cccccc")
XLGREY  = HexColor("#f0f0f0")
RULE    = HexColor("#bbbbbb")

# Phase colours for pipeline diagram
C_PREP  = HexColor("#ddeeff")   # blue-grey  — structure preparation
C_GEN   = HexColor("#ddf0dd")   # green      — aptamer generation
C_VAL   = HexColor("#fdf5dc")   # amber      — validation
C_RANK  = HexColor("#f0e8f8")   # purple     — scoring/ranking

C_TEXT_PREP  = HexColor("#224466")
C_TEXT_GEN   = HexColor("#225522")
C_TEXT_VAL   = HexColor("#665500")
C_TEXT_RANK  = HexColor("#442266")

STROKE_PREP  = HexColor("#7aabdd")
STROKE_GEN   = HexColor("#66bb66")
STROKE_VAL   = HexColor("#ddbb44")
STROKE_RANK  = HexColor("#9966cc")

PHASE_COLORS = {
    "prep":  (C_PREP,  STROKE_PREP,  C_TEXT_PREP),
    "gen":   (C_GEN,   STROKE_GEN,   C_TEXT_GEN),
    "val":   (C_VAL,   STROKE_VAL,   C_TEXT_VAL),
    "rank":  (C_RANK,  STROKE_RANK,  C_TEXT_RANK),
}

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
def S(name, **kw):
    d = dict(fontName="Helvetica", fontSize=10, textColor=DARK,
             leading=15, spaceAfter=6, alignment=TA_JUSTIFY)
    d.update(kw)
    return ParagraphStyle(name, **d)

TITLE_S = S("TITLE", fontName="Helvetica-Bold", fontSize=24, textColor=BLACK,
             leading=30, spaceAfter=4, alignment=TA_LEFT)
SUB_S   = S("SUB",   fontName="Helvetica", fontSize=11, textColor=MID,
             leading=16, spaceAfter=2, alignment=TA_LEFT)
META_S  = S("META",  fontName="Helvetica", fontSize=8.5, textColor=GREY,
             leading=11, spaceAfter=2, alignment=TA_LEFT)
H1_S    = S("H1",    fontName="Helvetica-Bold", fontSize=14, textColor=BLACK,
             leading=19, spaceBefore=18, spaceAfter=5, alignment=TA_LEFT)
H2_S    = S("H2",    fontName="Helvetica-Bold", fontSize=11, textColor=BLACK,
             leading=15, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT)
BODY_S  = S("BODY")
LEFT_S  = S("LEFT",  alignment=TA_LEFT)
BULL_S  = S("BULL",  leftIndent=14, firstLineIndent=0, spaceAfter=3, alignment=TA_LEFT)
CAP_S   = S("CAP",   fontSize=8.5, textColor=GREY, leading=12,
             alignment=TA_CENTER, fontName="Helvetica-Oblique")
TH_S    = S("TH",    fontName="Helvetica-Bold", fontSize=8.5, textColor=BLACK,
             leading=12, alignment=TA_LEFT)
TD_S    = S("TD",    fontName="Helvetica", fontSize=8.5, textColor=DARK,
             leading=12, alignment=TA_LEFT)
NOTE_S  = S("NOTE",  fontName="Helvetica-Oblique", fontSize=9, textColor=MID,
             leading=14, alignment=TA_LEFT)

def p(text, sty=BODY_S):  return Paragraph(text, sty)
def h1(text):             return Paragraph(text, H1_S)
def h2(text):             return Paragraph(text, H2_S)
def sp(n=8):              return Spacer(1, n)
def hr():                 return HRFlowable(width="100%", thickness=0.6,
                                            color=RULE, spaceAfter=8, spaceBefore=4)
def bull(text):           return Paragraph("<bullet>\u2022</bullet> " + text, BULL_S)
def b(t):                 return f"<b>{t}</b>"
def i(t):                 return f"<i>{t}</i>"
def th(text):             return Paragraph(f"<b>{text}</b>", TH_S)
def td(text):             return Paragraph(text, TD_S)


def note_box(text):
    """Light grey shaded note box."""
    inner = Paragraph(text, NOTE_S)
    t = Table([[inner]], colWidths=[TEXT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), XLGREY),
        ("BOX",           (0,0), (-1,-1), 0.5, LGREY),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    return t


def tbl(headers, rows, widths):
    data = [[th(c) for c in headers]]
    for row in rows:
        data.append([td(str(c)) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), HexColor("#e0e0e0")),
        ("LINEBELOW",     (0,0), (-1,0), 1.0, BLACK),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, XLGREY]),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, LGREY),
        ("BOX",           (0,0), (-1,-1), 0.6, HexColor("#999999")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("RIGHTPADDING",  (0,0), (-1,-1), 7),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    return t


def screenshot(path, width_frac=1.0, aspect=None):
    """Embed a screenshot at given fraction of text width."""
    from PIL import Image as PILImage
    img = PILImage.open(path)
    w_px, h_px = img.size
    ar = h_px / w_px
    w_pt = TEXT_W * width_frac
    h_pt = w_pt * ar
    return Image(path, width=w_pt, height=h_pt)


# ---------------------------------------------------------------------------
# Pipeline diagram — horizontal, two rows, colour-coded by phase
# ---------------------------------------------------------------------------
def _draw_box(d, x, y, bw, bh, label_top, label_bot, phase, step_num):
    fill, stroke, txt_clr = PHASE_COLORS[phase]
    # Box
    d.add(RoundRect(x, y, bw, bh, 3,
                    fillColor=fill, strokeColor=stroke, strokeWidth=1.0))
    # Step badge (small circle top-left)
    badge_r = 7
    d.add(Circle(x + badge_r + 2, y + bh - badge_r - 2, badge_r,
                 fillColor=stroke, strokeColor=stroke, strokeWidth=0))
    d.add(String(x + badge_r + 2, y + bh - badge_r - 2 - 3.5,
                 step_num, fontSize=6, fontName="Helvetica-Bold",
                 fillColor=WHITE, textAnchor="middle"))
    # Top label (bold)
    d.add(String(x + bw / 2, y + bh / 2 + 1,
                 label_top, fontSize=7.5, fontName="Helvetica-Bold",
                 fillColor=txt_clr, textAnchor="middle"))
    # Bottom label (regular)
    if label_bot:
        d.add(String(x + bw / 2, y + bh / 2 - 9,
                     label_bot, fontSize=6.5, fontName="Helvetica",
                     fillColor=txt_clr, textAnchor="middle"))


def _arrow_right(d, x0, y, x1, clr=GREY):
    d.add(Line(x0, y, x1 - 5, y, strokeColor=clr, strokeWidth=0.8))
    d.add(Polygon([x1 - 5, y + 4, x1 - 5, y - 4, x1, y],
                  fillColor=clr, strokeColor=clr, strokeWidth=0))


def _arrow_turn(d, x_end, y_top, x_start, y_bot, clr=GREY):
    """Right-angle connector: end of row1 → start of row2."""
    turn_x = x_end + 14
    mid_y  = (y_top + y_bot) / 2
    d.add(Line(x_end, y_top, turn_x, y_top,
               strokeColor=clr, strokeWidth=0.8))
    d.add(Line(turn_x, y_top, turn_x, y_bot,
               strokeColor=clr, strokeWidth=0.8))
    d.add(Line(turn_x, y_bot, x_start + 5, y_bot,
               strokeColor=clr, strokeWidth=0.8))
    d.add(Polygon([x_start + 5, y_bot + 4, x_start + 5, y_bot - 4, x_start, y_bot],
                  fillColor=clr, strokeColor=clr, strokeWidth=0))


def pipeline_flow_diagram():
    """Horizontal two-row pipeline diagram, colour-coded by phase."""
    # (step_num, label_top, label_bot, phase)
    row1 = [
        ("0",    "CRBN",       "reference",    "prep"),
        ("1",    "Fetch",      "structure",    "prep"),
        ("2",    "Clean",      "PDB",          "prep"),
        ("3",    "Detect",     "pockets",      "prep"),
        ("4+5",  "Generate",   "candidates*",  "gen"),
        ("6",    "Filter",     "fold stability","val"),
    ]
    row2 = [
        ("7",    "Build",      "3D structures","val"),
        ("8",    "Dock",       "to pocket",    "val"),
        ("9",    "Score",      "degradability","rank"),
        ("10",   "Refine",     "round 1",      "rank"),
        ("11",   "Refine",     "round 2",      "rank"),
        ("12",   "Refine",     "round 3",      "rank"),
    ]

    N1     = len(row1)
    N2     = len(row2)
    BOX_W  = 63
    BOX_H  = 40
    GAP    = 8       # horizontal gap between boxes
    ROW_V  = 28      # vertical gap between rows (for connector)
    PAD_L  = 8       # left padding
    PAD_T  = 12      # top padding

    # Row y coordinates (top row is higher in reportlab's y-up space)
    total_h = PAD_T + BOX_H + ROW_V + BOX_H + PAD_T + 18
    y_row1  = total_h - PAD_T - BOX_H    # bottom of row1 boxes
    y_row2  = y_row1 - ROW_V - BOX_H     # bottom of row2 boxes

    total_w = PAD_L + N1 * BOX_W + (N1 - 1) * GAP + 20  # +20 for turn connector
    total_w = max(total_w, TEXT_W)

    # Centre each row
    row1_w  = N1 * BOX_W + (N1 - 1) * GAP
    row2_w  = N2 * BOX_W + (N2 - 1) * GAP
    x0_r1   = (total_w - row1_w) / 2
    x0_r2   = (total_w - row2_w) / 2

    d = Drawing(total_w, total_h)

    # Phase legend bar (above row 1)
    legend_items = [
        ("Structure prep", C_PREP, STROKE_PREP),
        ("Generation",     C_GEN,  STROKE_GEN),
        ("Validation",     C_VAL,  STROKE_VAL),
        ("Scoring",        C_RANK, STROKE_RANK),
    ]
    lx = x0_r1
    ly = y_row1 + BOX_H + 6
    for lbl, fill, stroke in legend_items:
        d.add(RoundRect(lx, ly, 12, 9, 2, fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
        d.add(String(lx + 15, ly + 1, lbl, fontSize=6.5, fontName="Helvetica",
                     fillColor=GREY, textAnchor="start"))
        lx += 86

    # Row 1
    for idx, (num, top, bot, phase) in enumerate(row1):
        x = x0_r1 + idx * (BOX_W + GAP)
        _draw_box(d, x, y_row1, BOX_W, BOX_H, top, bot, phase, num)
        if idx < N1 - 1:
            _arrow_right(d,
                         x + BOX_W, y_row1 + BOX_H / 2,
                         x + BOX_W + GAP, GREY)

    # Right-angle connector from row1 last box to row2 first box
    x_r1_end   = x0_r1 + N1 * BOX_W + (N1 - 1) * GAP
    _arrow_turn(d,
                x_r1_end,          y_row1 + BOX_H / 2,
                x0_r2,             y_row2 + BOX_H / 2,
                GREY)

    # Row 2
    for idx, (num, top, bot, phase) in enumerate(row2):
        x = x0_r2 + idx * (BOX_W + GAP)
        _draw_box(d, x, y_row2, BOX_W, BOX_H, top, bot, phase, num)
        if idx < N2 - 1:
            _arrow_right(d,
                         x + BOX_W, y_row2 + BOX_H / 2,
                         x + BOX_W + GAP, GREY)

    # Footnote
    d.add(String(x0_r2, y_row2 - 14,
                 "* steps 4 and 5 (literature scraping and sequence generation) run in parallel",
                 fontSize=6.5, fontName="Helvetica-Oblique", fillColor=GREY))

    return d


# ---------------------------------------------------------------------------
# Ternary complex diagram — cleaner version
# ---------------------------------------------------------------------------
def ternary_diagram():
    W2, H2 = TEXT_W, 170.0
    d = Drawing(W2, H2)

    TP_W, TP_H = 115, 70
    tp_x, tp_y = 24, 60

    CR_W, CR_H = 105, 55
    cr_x = W2 - 24 - CR_W
    cr_y = 65

    apt_cx, apt_cy = W2 / 2, H2 / 2

    # Target protein
    d.add(RoundRect(tp_x, tp_y, TP_W, TP_H, 4,
                    fillColor=C_PREP, strokeColor=STROKE_PREP, strokeWidth=1.2))
    d.add(String(tp_x + TP_W / 2, tp_y + TP_H - 14,
                 "Target Protein", fontSize=8, fontName="Helvetica-Bold",
                 fillColor=C_TEXT_PREP, textAnchor="middle"))
    d.add(String(tp_x + TP_W / 2, tp_y + TP_H - 26,
                 "(any protein of interest)", fontSize=6.5, fontName="Helvetica",
                 fillColor=GREY, textAnchor="middle"))

    # Binding pocket indentation
    pocket_cx = tp_x + TP_W
    pocket_cy = tp_y + TP_H / 2
    d.add(Circle(pocket_cx, pocket_cy, 13,
                 fillColor=WHITE, strokeColor=STROKE_PREP, strokeWidth=0.8))
    d.add(String(pocket_cx, pocket_cy + 2, "pocket", fontSize=6,
                 fontName="Helvetica-Oblique", fillColor=GREY, textAnchor="middle"))

    # RNA aptamer (central oval — drawn with a thin rect for simplicity)
    from reportlab.graphics.shapes import Ellipse
    d.add(Ellipse(apt_cx, apt_cy, 58, 28,
                  fillColor=C_GEN, strokeColor=STROKE_GEN, strokeWidth=1.2))
    d.add(String(apt_cx, apt_cy + 6, "RNA Aptamer", fontSize=8.5,
                 fontName="Helvetica-Bold", fillColor=C_TEXT_GEN, textAnchor="middle"))
    d.add(String(apt_cx, apt_cy - 6, "(warhead)", fontSize=7,
                 fontName="Helvetica", fillColor=C_TEXT_GEN, textAnchor="middle"))

    # CRBN
    d.add(RoundRect(cr_x, cr_y, CR_W, CR_H, 4,
                    fillColor=C_RANK, strokeColor=STROKE_RANK, strokeWidth=1.2))
    d.add(String(cr_x + CR_W / 2, cr_y + CR_H - 13,
                 "CRBN (E3 ligase)", fontSize=8, fontName="Helvetica-Bold",
                 fillColor=C_TEXT_RANK, textAnchor="middle"))
    d.add(String(cr_x + CR_W / 2, cr_y + CR_H - 26,
                 "pomalidomide site", fontSize=6.5, fontName="Helvetica",
                 fillColor=GREY, textAnchor="middle"))

    # Aptamer ↔ pocket (binding)
    d.add(Line(pocket_cx + 13, pocket_cy, apt_cx - 58, apt_cy,
               strokeColor=STROKE_PREP, strokeWidth=1.0,
               strokeDashArray=[4, 3]))
    d.add(String((pocket_cx + 13 + apt_cx - 58) / 2, pocket_cy + 7,
                 "binds", fontSize=6.5, fontName="Helvetica-Oblique",
                 fillColor=GREY, textAnchor="middle"))

    # Aptamer ↔ CRBN (linker)
    d.add(Line(apt_cx + 58, apt_cy, cr_x, cr_y + CR_H / 2,
               strokeColor=STROKE_RANK, strokeWidth=1.2,
               strokeDashArray=[6, 3]))
    mid_x = (apt_cx + 58 + cr_x) / 2
    mid_y = (apt_cy + cr_y + CR_H / 2) / 2
    d.add(String(mid_x, mid_y + 7, "PEG linker", fontSize=7,
                 fontName="Helvetica-Bold", fillColor=C_TEXT_RANK, textAnchor="middle"))
    d.add(String(mid_x, mid_y - 3, "(length estimated by model)", fontSize=6,
                 fontName="Helvetica-Oblique", fillColor=GREY, textAnchor="middle"))

    # CRBN → ubiquitin arrow
    ub_x = cr_x + CR_W / 2
    d.add(Line(ub_x, cr_y, ub_x, 12,
               strokeColor=GREY, strokeWidth=0.8, strokeDashArray=[3, 3]))
    d.add(Polygon([ub_x - 4, 17, ub_x + 4, 17, ub_x, 12],
                  fillColor=GREY, strokeColor=GREY, strokeWidth=0))
    d.add(String(ub_x + 6, 14, "ubiquitylates target → degradation",
                 fontSize=6.5, fontName="Helvetica-Oblique", fillColor=GREY))

    # Distance bracket
    bracket_y = tp_y - 16
    x_left  = apt_cx + 58
    x_right = cr_x
    d.add(Line(x_left, bracket_y, x_right, bracket_y,
               strokeColor=LGREY, strokeWidth=0.6))
    d.add(Line(x_left,  bracket_y - 4, x_left,  bracket_y + 4,
               strokeColor=LGREY, strokeWidth=0.6))
    d.add(Line(x_right, bracket_y - 4, x_right, bracket_y + 4,
               strokeColor=LGREY, strokeWidth=0.6))
    d.add(String((x_left + x_right) / 2, bracket_y - 12,
                 "distance measured by model  \u2192  linker length",
                 fontSize=6.5, fontName="Helvetica", fillColor=GREY, textAnchor="middle"))

    return d


# ---------------------------------------------------------------------------
# Score radar schematic
# ---------------------------------------------------------------------------
def score_radar_diagram():
    """Simple pentagon showing the five scoring axes."""
    import math
    W3, H3 = 200.0, 180.0
    cx, cy, r = 100.0, 90.0, 60.0
    d = Drawing(W3, H3)

    axes = ["Epitope", "Lysine", "Ternary", "Hook", "Fold"]
    n = len(axes)
    angles = [math.pi / 2 + 2 * math.pi * k / n for k in range(n)]

    # Background pentagon (max extent)
    pts_outer = []
    for a in angles:
        pts_outer += [cx + r * math.cos(a), cy + r * math.sin(a)]
    d.add(Polygon(pts_outer, fillColor=XLGREY, strokeColor=LGREY, strokeWidth=0.6))

    # Grid rings
    for frac in [0.33, 0.66]:
        pts = []
        for a in angles:
            pts += [cx + r * frac * math.cos(a), cy + r * frac * math.sin(a)]
        d.add(Polygon(pts, fillColor=None, strokeColor=LGREY, strokeWidth=0.4))

    # Axis lines
    for a in angles:
        d.add(Line(cx, cy, cx + r * math.cos(a), cy + r * math.sin(a),
                   strokeColor=LGREY, strokeWidth=0.5))

    # Example scores (illustrative, not real data)
    scores = [0.74, 0.72, 0.64, 0.44, 0.40]
    pts_score = []
    for a, s in zip(angles, scores):
        pts_score += [cx + r * s * math.cos(a), cy + r * s * math.sin(a)]
    d.add(Polygon(pts_score, fillColor=HexColor("#aaddee"),
                  strokeColor=STROKE_PREP, strokeWidth=1.2))

    # Axis labels
    for a, lbl in zip(angles, axes):
        lx = cx + (r + 14) * math.cos(a)
        ly = cy + (r + 14) * math.sin(a) - 4
        d.add(String(lx, ly, lbl, fontSize=7, fontName="Helvetica-Bold",
                     fillColor=DARK, textAnchor="middle"))

    return d


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------
doc = SimpleDocTemplate(
    OUT, pagesize=A4,
    leftMargin=LEFT, rightMargin=RIGHT,
    topMargin=2.2*cm, bottomMargin=2.2*cm,
)

story = []

IMG1 = "C:/Users/Kirill/OneDrive/Pictures/Screenshots/AptaDeg Frontend1.png"
IMG2 = "C:/Users/Kirill/OneDrive/Pictures/Screenshots/AptaDeg Frontend2.png"
IMG3 = "C:/Users/Kirill/OneDrive/Pictures/Screenshots/AptaGen Frontend3.png"

# ===========================================================================
# COVER
# ===========================================================================
story += [
    sp(30),
    p("AptaDeg", TITLE_S),
    sp(2),
    HRFlowable(width="100%", thickness=2.0, color=BLACK, spaceAfter=10, spaceBefore=4),
    p("Computational RNA aptamer design for targeted protein degradation", SUB_S),
    sp(4),
    p("Internal overview \u2014 March 2026", META_S),
    sp(24),
    p(
        "This document describes " + b("AptaDeg") + " \u2014 a computational pipeline that "
        "automatically generates and ranks RNA aptamer candidates for use in targeted "
        "protein degradation. It explains what each step of the pipeline does, why the "
        "approach is novel, and where the current limitations and improvement opportunities lie. "
        "It is written for a technical co-founder audience without assumed wet-lab biology background.",
        S("intro", fontSize=10.5, textColor=MID, leading=17, alignment=TA_JUSTIFY)
    ),
    sp(24),
    screenshot(IMG1),
    sp(4),
    p("Figure 1. AptaDeg input screen \u2014 a user enters any protein PDB code and the pipeline runs automatically.", CAP_S),
    PageBreak(),
]

# ===========================================================================
# 1. THE PROBLEM
# ===========================================================================
story += [
    h1("1.  The Problem"),
    hr(),
    p(
        "Targeted protein degradation (PROTAC technology) works by recruiting an E3 ubiquitin ligase "
        "(most commonly CRBN) to sit physically adjacent to a target protein, triggering its destruction "
        "by the cell\u2019s own proteasome. This requires a bifunctional molecule \u2014 one end binds the "
        "target, the other binds CRBN, and a flexible linker connects them."
    ),
    p(
        "The challenge: " + b("a molecule that binds a target is not the same as a molecule that degrades it.") + " "
        "Binding affinity \u2014 the property traditional aptamer selection (SELEX) optimises for \u2014 "
        "is necessary but not sufficient. The geometry of the ternary complex (target + aptamer + CRBN) "
        "determines whether ubiquitin transfer can actually occur. A perfectly binding aptamer that "
        "positions CRBN on the wrong face of the target, or too far away, will not degrade it."
    ),
    sp(8),
    ternary_diagram(),
    sp(4),
    p("Figure 2. The ternary complex. The aptamer (centre) must simultaneously engage the target protein\u2019s binding site "
      "and hold CRBN close enough for ubiquitin transfer. The linker length and geometry are critical.", CAP_S),
    sp(12),
    p(
        "AptaDeg addresses this by scoring aptamer candidates not just on predicted binding affinity, "
        "but on four factors that together determine whether degradation is likely to succeed. "
        "This is a fundamentally different question from what SELEX answers, and it is where "
        "a computational model adds unique value."
    ),
    PageBreak(),
]

# ===========================================================================
# 2. THE PIPELINE
# ===========================================================================
story += [
    h1("2.  The Pipeline"),
    hr(),
    p(
        "The pipeline takes a four-character PDB accession code as input (the unique identifier "
        "for any protein structure in the international database) and outputs a ranked list of RNA "
        "aptamer candidates. It runs fully automatically. No manual steps are required between "
        "input and results."
    ),
    sp(10),
    pipeline_flow_diagram(),
    sp(4),
    p("Figure 3. The AptaDeg pipeline \u2014 13 steps from a PDB code to ranked candidates. "
      "Steps 4 and 5 run in parallel. Colour indicates phase: "
      "blue = structure preparation, green = generation, amber = validation, purple = scoring.", CAP_S),
    sp(14),
]

story += [
    h2("Step 0 \u2014 Load CRBN reference"),
    p(
        "The pipeline begins by loading the crystal structure of CRBN (Cereblon, the E3 ubiquitin "
        "ligase responsible for tagging proteins for destruction) bound to pomalidomide \u2014 a "
        "clinically approved immunomodulatory drug that sits inside the CRBN binding pocket. "
        "This structure (PDB: 4CI1) is held locally and never re-downloaded. The 3D centroid "
        "of the pomalidomide binding site is computed and stored as a fixed anchor coordinate: "
        "every aptamer candidate\u2019s 3\u2032 terminus is later measured against this point to "
        "determine whether a linker of reasonable length could bridge the two proteins."
    ),
    sp(8),

    h2("Step 1 \u2014 Fetch target structure"),
    p(
        "The target protein\u2019s structure is downloaded from the RCSB Protein Data Bank using "
        "the four-character PDB accession code entered by the user. PDB codes identify unique "
        "experimentally determined structures \u2014 typically from X-ray crystallography or "
        "cryo-electron microscopy \u2014 that include all-atom 3D coordinates. If no PDB entry "
        "is available (for example, if the user enters a UniProt ID), the pipeline can fall "
        "back to ESMFold, a sequence-based structure predictor, to generate a plausible fold "
        "computationally. The raw file is saved to a local cache; repeat runs of the same "
        "target skip the network step entirely."
    ),
    sp(8),

    h2("Step 2 \u2014 Clean structure"),
    p(
        "PDB files downloaded from public databases contain far more than just the protein chain: "
        "water molecules, co-crystallised small-molecule ligands, metal ions, and other "
        "heteroatoms are present and would confuse downstream tools. BioPython\u2019s structure "
        "parser is used to strip all HETATM records (non-protein atoms) while retaining the "
        "protein backbone and sidechains. The result is saved as a fresh PDB file used for all "
        "subsequent steps. This cleaning step is necessary because fpocket, ViennaRNA, and rDock "
        "all have specific expectations about what a valid input looks like."
    ),
    sp(8),

    h2("Step 3 \u2014 Detect binding pockets"),
    p(
        "fpocket, a geometric cavity detection algorithm, is run on the cleaned protein structure. "
        "It works by rolling a small probe sphere across the protein surface and identifying "
        "concave regions enclosed by multiple surface-facing residues \u2014 these cavities are "
        "candidate binding sites. Each identified pocket is scored by volume, hydrophobicity, "
        "and a druggability estimate. The highest-scoring pocket is selected as the docking "
        "target: the physical cavity that every aptamer candidate will be evaluated against."
    ),
    p(
        "fpocket runs inside WSL2 (Windows Subsystem for Linux 2), where it is natively compiled "
        "as a Linux binary. Its output is parsed back into Python as a ranked list of pocket "
        "coordinates and residue annotations. If fpocket is not installed in WSL, the pipeline "
        "raises immediately rather than silently continuing \u2014 pocket detection is a hard "
        "dependency; every subsequent step depends on knowing where to dock."
    ),
    sp(8),

    h2("Steps 4\u20135 \u2014 Generate candidates (parallel)"),
    p(
        "Two generation strategies run simultaneously as concurrent threads and their outputs "
        "are merged at the end of this step:"
    ),
    bull(
        b("Step 4 \u2014 Literature-seeded SELEX simulation. ") +
        "PubMed, Aptagen, and AptaBase are queried in parallel for published aptamers against "
        "the target protein and structurally similar targets. Known validated sequences from the "
        "literature are then mutated using transition-biased substitution: A\u2194G and U\u2194C "
        "changes (transitions) are weighted 3\u00d7 more than transversions, mimicking the "
        "mutation patterns of natural RNA evolution. Fifteen mutants are generated per known "
        "seed sequence, each passing a ViennaRNA fold-stability gate (MFE \u2264 \u22125 kcal/mol) "
        "before being accepted into the pool. This strategy grounds the search in validated "
        "biology rather than pure de novo generation."
    ),
    sp(4),
    bull(
        b("Step 5 \u2014 Sequence generation with RNAFlow. ") +
        "RNAFlow is a graph neural network trained to generate RNA sequences conditioned on "
        "the 3D geometry of a protein surface. Given the pocket coordinates from step 3, it "
        "samples novel sequences whose predicted shape complements that specific surface. "
        "RNAFlow runs on GPU (the local RTX 3070, accessed via WSL2 where the DGL CUDA "
        "libraries are installed) and generates approximately 30 sequences per run in around "
        "50 seconds. Because the GPU time budget is finite, the gap between 30 RNAFlow samples "
        "and the 200-candidate target is padded with additional transition-biased SELEX "
        "sequences. The two pools are merged and deduplicated before proceeding."
    ),
    sp(10),
    screenshot(IMG2),
    sp(4),
    p("Figure 4. The pipeline running for protein 1NKP (c-Myc/Max complex). Steps 0\u20139 are complete; "
      "refinement rounds are in progress. Real-time log output is shown below the progress bar.", CAP_S),
    sp(10),

    h2("Step 6 \u2014 Filter by fold stability"),
    p(
        "Each of the ~200 candidate sequences is folded computationally using ViennaRNA, which "
        "calculates the minimum free energy (MFE) secondary structure: the most thermodynamically "
        "stable base-pairing arrangement the sequence can adopt given standard physiological "
        "conditions. Sequences with MFE above \u22125 kcal/mol are discarded as insufficiently "
        "structured \u2014 they are likely to be disordered in solution rather than adopting a "
        "defined 3D shape capable of making specific protein contacts. This filter also doubles "
        "as a sanity check on sequence quality, removing very short or degenerate sequences "
        "before the more expensive 3D modelling step."
    ),
    sp(8),

    h2("Step 7 \u2014 Build 3D structures"),
    p(
        "The top candidates by fold stability are converted from 1D sequences to full 3D PDB "
        "atomic coordinates using rna-tools\u2019 template-based backbone modelling. Three "
        "canonical RNA topology families are tried for each sequence: stem-loop (template 2AP6), "
        "G-quadruplex (2GKU), and multi-stem junction (3Q3Z). The template producing the best "
        "structural coverage for that sequence is selected. The result is a PDB file containing "
        "all-atom coordinates for each aptamer \u2014 the 3D starting geometry rDock requires "
        "as input. Structure building runs across a thread pool to process multiple candidates "
        "in parallel."
    ),
    p(
        "The quality of these template-based models is lower than experimental structures, but "
        "sufficient for the docking step: rDock evaluates relative binding scores, so what "
        "matters is that each model is internally consistent, not that it is perfectly accurate "
        "in absolute terms."
    ),
    sp(8),

    h2("Step 8 \u2014 Dock to pocket"),
    p(
        "Each 3D aptamer structure is docked to the binding pocket from step 3 using rDock. "
        "rDock evaluates the placed pose for steric fit (no overlapping atoms), electrostatic "
        "complementarity (charge matching between aptamer functional groups and pocket residues), "
        "and van der Waals contacts. The pipeline uses rDock\u2019s single-pose scoring mode "
        "(\u2018score.prm\u2019) rather than a full conformational search, which would be "
        "prohibitively slow when applied to 200 candidates. This is a deliberate speed "
        "trade-off: conformational docking (\u2018dock.prm\u2019) would find the lowest-energy "
        "binding pose but takes orders of magnitude longer per candidate."
    ),
    p(
        "Four docking jobs run in parallel inside WSL2. The docking score (lower = better "
        "binding) is stored alongside each candidate and used as one input to the degradability "
        "scoring step. Importantly, docking score alone is not the final ranking criterion \u2014 "
        "it is one component of a broader model."
    ),
    sp(8),

    h2("Step 9 \u2014 Score degradability"),
    p(
        "The docked candidates are evaluated on four properties that together determine whether "
        "the aptamer is likely to trigger protein degradation \u2014 not just whether it binds. "
        "This is the core scientific contribution of AptaDeg: no existing public tool scores "
        "RNA aptamers specifically for PROTAC-relevant geometry."
    ),
    sp(4),
    tbl(
        ["Component", "What it measures", "Weight"],
        [
            ["Epitope quality",
             "Whether the aptamer contacts an accessible surface region. Deeply buried binding "
             "may sterically block the CRBN-E2 ubiquitin transfer complex from approaching the "
             "target. Measured using solvent-accessible surface area (SASA) on the bound residues.",
             "30%"],
            ["Lysine accessibility",
             "How many surface-exposed lysines sit near the binding site. Ubiquitin is covalently "
             "attached to lysine \u03b5-amino groups \u2014 if none are accessible in the right "
             "geometry, degradation cannot proceed regardless of binding affinity.",
             "20%"],
            ["Ternary geometry",
             "Straight-line distance from the aptamer\u2019s 3\u2032 end to the CRBN pomalidomide "
             "pocket centroid. Optimal range 15\u201350 \u00c5 (peaks at 30 \u00c5, parabolic "
             "falloff). Too close causes steric clash between the two proteins; too far makes "
             "the linker too floppy to hold both proteins in contact simultaneously.",
             "30%"],
            ["Hook effect",
             "If the aptamer itself binds CRBN directly, it competes with pomalidomide for the "
             "same pocket and prevents ternary complex formation. Candidates with predicted "
             "CRBN affinity receive a penalty proportional to their estimated CRBN binding score.",
             "20%"],
        ],
        [3.8*cm, 9.6*cm, 1.8*cm]
    ),
    sp(6),
    p(
        "The composite score (0\u20131, higher = better) reflects predicted degradability. "
        "A candidate that binds the target with high affinity but scores poorly on ternary "
        "geometry or lysine accessibility will rank lower than one with modest binding but "
        "excellent geometric positioning. This is the fundamental reframing the tool offers."
    ),
    sp(8),

    h2("Steps 10\u201312 \u2014 Iterative refinement (three rounds)"),
    p(
        "The top-5 candidates by composite score seed three rounds of mutational refinement. "
        "In each round, 15 transition-biased mutants are generated from each of the five seeds "
        "(75 new sequences total). Each mutant is docked to the same pocket and re-scored. "
        "The best performers across all 75 carry forward as the next round\u2019s seeds. "
        "This progressively narrows the search toward candidates that score well across "
        "all four degradability components simultaneously rather than optimising a single axis."
    ),
    p(
        "Each refinement round takes approximately 70 minutes (75 docking jobs, four parallel "
        "WSL2 workers). Three rounds add roughly 3.5 hours to total run time. For rapid "
        "exploration, refinement can be skipped entirely or limited to a single round, "
        "cutting total time to under 30 minutes. Any partial results can be loaded instantly "
        "via the \u201cLoad Cached Results\u201d button without re-running earlier steps."
    ),
    sp(20),
]

# ===========================================================================
# 3. RESULTS
# ===========================================================================
story += [
    h1("3.  Output"),
    hr(),
    p(
        "When the pipeline finishes, it returns the top 5 candidates ranked by degradability score. "
        "These are not simply the aptamers that bind best \u2014 they are the ones that score best "
        "across all four degradability criteria combined. A candidate that binds tightly but sits "
        "in the wrong geometry for CRBN recruitment will rank below one with moderate binding "
        "but excellent positioning."
    ),
    p(
        "For each candidate the interface shows:"
    ),
    bull(
        b("RNA sequence. ") +
        "The full nucleotide sequence, colour-coded by base (A/U/G/C), written in standard "
        "5\u2032\u21923\u2032 notation. This is the sequence that would be synthesised for experimental "
        "validation. Length typically 30\u201360 nucleotides."
    ),
    bull(
        b("Component score breakdown. ") +
        "A bar chart showing each of the four degradability components individually, plus the "
        "composite score. This makes it immediately clear whether a candidate scores well "
        "across the board or is being lifted by a single dominant component."
    ),
    bull(
        b("3D structure viewer. ") +
        "An interactive molecular viewer (3Dmol.js) showing the predicted 3D conformation of "
        "the aptamer. The structure can be rotated and zoomed. Colour indicates secondary structure "
        "element (stem, loop, junction)."
    ),
    bull(
        b("Linker length estimate. ") +
        "The estimated number of PEG (polyethylene glycol) repeat units needed to bridge the "
        "aptamer\u2019s 3\u2032 end to the CRBN pomalidomide site, based on the measured distance. "
        "PEG-n linkers are a standard choice in PROTAC chemistry; each repeat contributes "
        "approximately 3.5 \u00c5 of reach."
    ),
    bull(
        b("Experimental recommendation. ") +
        "A one-line read on whether the candidate is worth taking forward to synthesis "
        "(e.g. \u201cprioritise for surface plasmon resonance (SPR) binding validation\u201d)."
    ),
    sp(10),
    screenshot(IMG3),
    sp(4),
    p("Figure 5. Results view showing the top candidates after running the pipeline on protein 1NKP "
      "(c-Myc/Max complex). Candidate 01 scores 0.53 degradability. The predicted 3D structure is "
      "shown top-right; the radar chart (bottom-right) breaks down all four component scores. "
      "12 initial candidates were generated; 87 were docked after one refinement round.", CAP_S),
    sp(12),
    note_box(
        i("Example run \u2014 1NKP (c-Myc/Max bHLH-LZ domain): ") +
        "200 sequence candidates generated; top 12 docked initially; 75 mutant docking jobs "
        "in refinement round 1. Best degradability score: 0.53. Top candidate: G-quadruplex "
        "scaffold, PEG-30 linker recommendation (86 \u00c5 bridging distance). "
        "The pipeline is target-agnostic \u2014 this target was selected as a test case only."
    ),
    PageBreak(),
]

# ===========================================================================
# 4. WHY IT'S USEFUL
# ===========================================================================
story += [
    h1("4.  Why This Is Useful"),
    hr(),
    p(
        "The standard wet-lab approach to finding an aptamer for a protein involves running "
        "SELEX (Systematic Evolution of Ligands by EXponential enrichment): cycling RNA pools "
        "through rounds of binding selection and amplification until high-affinity binders "
        "emerge. This process takes weeks, costs significant reagent budget, and by design "
        "optimises only for binding affinity \u2014 not for the geometry that PROTAC-mediated "
        "degradation requires."
    ),
    p(
        "AptaDeg reframes the question from \u201cwhat binds?\u201d to \u201cwhat degrades?\u201d "
        "It does this computationally, in under 30 minutes, before any synthesis is needed. "
        "The key differentiators:"
    ),
    sp(4),
    tbl(
        ["Capability", "Why it matters"],
        [
            ["Target-agnostic",
             "Any protein with a PDB entry can be run. The pipeline is not specialised to any "
             "one disease area or protein family \u2014 you enter a PDB code and it handles the rest."],
            ["Degradability-first scoring",
             "No existing publicly available tool scores RNA aptamers specifically for PROTAC-relevant "
             "geometry. Traditional aptamer tools (SELEX simulators, binding predictors) optimise "
             "binding affinity. That is a necessary but insufficient condition for degradation. "
             "AptaDeg scores what those tools ignore."],
            ["Literature integration",
             "Known validated aptamers from PubMed and aptamer databases seed the candidate pool. "
             "Where experimentally confirmed sequences exist, the model starts from them rather "
             "than generating purely from scratch. This anchors the search in proven biology."],
            ["End-to-end automation",
             "From a four-letter PDB code to ranked candidates complete with 3D structures, "
             "docking scores, linker length estimates, and interactive visualisation \u2014 "
             "with zero manual steps. The core pipeline runs in under 30 minutes."],
            ["Interpretable output",
             "Each of the four scoring components is shown separately alongside the composite score. "
             "A researcher can immediately see whether a candidate ranks highly because of good "
             "geometry, good lysine accessibility, or both \u2014 and design the next experiment accordingly."],
        ],
        [4.0*cm, 11.5*cm]
    ),
    sp(12),
    KeepTogether([
        h2("Why RNAFlow rather than an alternative sequence generator?"),
        sp(4),
        tbl(
            ["Alternative", "What it does", "Why not used here"],
            [
                ["gRNAde",
                 "Designs RNA sequences given an RNA backbone as input.",
                 "Requires a known RNA structure as input, not a protein surface. Cannot generate aptamers against a new protein target without an existing RNA structure."],
                ["antaRNA / MCTS-RNA",
                 "Generates RNA sequences that fold into a specified 2D structure.",
                 "Optimises RNA shape, not protein-surface complementarity. No protein conditioning."],
                ["RNA-X",
                 "Assembles RNA aptamers by grafting known binding motifs onto a scaffold.",
                 "Not conditioned on a specific protein surface. Good for structural design; not for protein-targeted aptamer generation."],
                ["AlphaFold 3",
                 "Predicts the 3D structure of protein-RNA complexes given both sequences.",
                 "A structure predictor, not a sequence designer. Best used downstream to validate top candidates."],
                ["RhoDesign",
                 "An RNA inverse folding model: given an RNA backbone structure as input, it designs RNA sequences that fold into that backbone.",
                 "Requires an existing RNA backbone structure as input \u2014 it cannot generate aptamers from scratch. "
                 "A backbone generator such as RFDpoly or RNA-FrameFlow would be needed first, making RhoDesign "
                 "a refinement step rather than a starting point. Useful in a more complete pipeline but cannot "
                 "replace a de novo generator."],
            ],
            [2.8*cm, 5.6*cm, 6.5*cm]
        ),
    ]),
    PageBreak(),
]

# ===========================================================================
# 5. LIMITATIONS AND IMPROVEMENTS
# ===========================================================================
story += [
    h1("5.  Current Limitations"),
    hr(),
    p(
        "AptaDeg is an early-stage research tool. Its scores are best interpreted as a relative "
        "ranking to prioritise which candidates are " + i("most worth testing") + ", not as absolute "
        "predictions of experimental outcome. The following gaps represent the largest distance "
        "between what the model computes and what would happen in a real cell:"
    ),
    sp(4),
    tbl(
        ["Limitation", "What this means in practice", "Severity"],
        [
            ["Ternary cooperativity not modelled",
             "The model measures the straight-line distance between the aptamer and CRBN as a "
             "stand-in for geometric compatibility. In reality, when all three components "
             "(target + aptamer + CRBN) come together, they can either stabilise or actively "
             "destabilise each other \u2014 a phenomenon called cooperativity. A molecule can "
             "look geometrically fine by distance alone but still fail because the combined "
             "complex is unfavourable. This is probably the single largest gap between the "
             "model score and real experimental outcome.",
             "High"],
            ["Linker modelled as a rigid rod",
             "The model calculates how long a linker is needed by measuring the straight-line "
             "distance between the aptamer\u2019s end and CRBN. But PEG linkers are long, "
             "flexible chains that wiggle and loop in solution \u2014 they do not behave like "
             "a rigid rod. The real probability that the linker simultaneously holds both "
             "proteins in contact is much lower than the distance calculation implies, "
             "especially for longer linkers.",
             "High"],
            ["Docking uses scoring, not conformational search",
             "When rDock evaluates an aptamer against the pocket, it scores a single pre-placed "
             "pose rather than searching for the best-fitting orientation. Think of it as "
             "checking whether a key fits a lock in one fixed position, rather than rotating "
             "the key to find the best fit. The scored position may not be the natural binding "
             "mode, so the docking scores are informative but not definitive.",
             "Medium"],
            ["No nuclease stability model",
             "Unmodified RNA is destroyed within minutes in blood or inside cells by enzymes "
             "called RNases. The pipeline does not evaluate or penalise sequences based on "
             "how quickly they would be degraded biologically. In practice, any candidate "
             "taken to synthesis would need chemical modifications (e.g. 2\u2032-O-methyl, "
             "phosphorothioate) to survive long enough to act.",
             "Medium"],
            ["No cell delivery model",
             "All scoring assumes the aptamer successfully reaches its target protein inside "
             "the cell. In reality, getting a large RNA molecule across the cell membrane, "
             "out of the endosome, and to the right cellular compartment is a substantial "
             "challenge. The pipeline currently has no model for this.",
             "Medium"],
            ["Lysine geometry not validated",
             "The model counts surface-exposed lysines near the binding site as a proxy for "
             "ubiquitylation potential. However, not all accessible lysines are in the right "
             "orientation for the E2 enzyme to reach them when CRBN is in position. The count "
             "is a rough approximation, not a validated geometric model.",
             "Low\u2013Medium"],
        ],
        [3.8*cm, 9.2*cm, 1.8*cm]
    ),
    sp(16),
    h1("6.  How the Model Can Be Improved"),
    hr(),
    p(
        "The limitations above are not fundamental \u2014 each has a known technical solution. "
        "The following improvements are listed in rough order of expected impact on the gap "
        "between model score and real experimental outcome:"
    ),
    sp(4),
    tbl(
        ["Improvement", "What it would add and how"],
        [
            ["AlphaFold 3 ternary complex prediction",
             "AlphaFold 3 can predict the 3D structure of a full protein-RNA complex given "
             "both sequences as input. For the top 3\u20135 ranked candidates, this would "
             "replace the current distance-based geometry estimate with a true structural "
             "model of all three components (target + aptamer + CRBN) in contact. It would "
             "capture cooperativity effects and reveal steric clashes invisible to the "
             "current approach. This is the highest-value single upgrade available."],
            ["Conformational docking (dock.prm)",
             "Switching rDock from single-pose scoring to a full conformational search "
             "(\u2018dock.prm\u2019 mode) would find the lowest-energy binding orientation "
             "for each aptamer rather than evaluating one pre-placed pose. The trade-off "
             "is time: conformational search is roughly 50\u2013100\u00d7 slower per "
             "candidate, so it would be applied only to the top candidates after the "
             "initial scoring filter."],
            ["Chemical modification scoring",
             "Any aptamer going to synthesis would need chemical modifications to survive "
             "in biological fluids. Adding a rule-based model for common stabilising "
             "modifications (2\u2032-O-methyl groups, phosphorothioate backbone linkages, "
             "locked nucleic acid residues) would let the pipeline predict modification "
             "compatibility and flag sequences likely to be incompatible with standard "
             "modification chemistry."],
            ["Experimental feedback loop",
             "The four scoring weights (30/20/30/20) are currently heuristic estimates "
             "based on biological reasoning, not data. Once candidates are synthesised "
             "and tested (e.g. SPR for binding, TR-FRET for ternary complex formation), "
             "the experimental results can be used to retrain the weights. Even a small "
             "set of 10\u201320 measured data points would substantially improve the "
             "predictive accuracy of the composite score."],
            ["Larger RNAFlow sample budget",
             "RNAFlow is currently capped at 30 GPU-generated sequences per run because "
             "of time constraints (~50 seconds total). Increasing this to 200\u2013500 "
             "samples would meaningfully expand coverage of the sequence space that is "
             "geometrically compatible with the target pocket. This requires either "
             "more GPU time or running RNAFlow overnight as a background job."],
            ["Backbone-conditioned refinement (RhoDesign, RNA-FrameFlow)",
             "Once a top candidate backbone structure is available, RNA inverse folding "
             "models such as RhoDesign can re-design the sequence to better fit that "
             "specific backbone conformation. Paired with a backbone diffusion model "
             "like RNA-FrameFlow (which generates backbone structures de novo), this "
             "creates a more complete generate\u2192refine loop than RNAFlow alone provides."],
        ],
        [4.2*cm, 11.3*cm]
    ),
    sp(14),
    note_box(
        i("Current pipeline run time: ") +
        "Core steps (structure prep through initial scoring): 20\u201330 minutes. "
        "Refinement rounds (3\u00d7 75 mutant docking jobs): 3\u20134 hours. "
        "For rapid iteration the refinement can be skipped entirely or limited to one round, "
        "cutting total time to under 30 minutes. Results can be loaded from cache at any point "
        "via the \u201cLoad Cached Results\u201d button without re-running completed steps."
    ),
]

# ===========================================================================
# BUILD
# ===========================================================================
doc.build(story)
print(f"Written: {OUT}")
