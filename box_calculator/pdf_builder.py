"""
CPS Box Count Report PDF builder.

Layout follows the standard CPS Box Summary invoice format:
  2-column bordered header (title + dates | claim info + insured + address)
  Room × 12 box-type table with per-room totals and grand totals row
  Optional estimator note
  Insured initials line + "Page X of Y" footer
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .cps_analyzer import CPS_COLUMNS

# ── Colours ──────────────────────────────────────────────────────────────────
_BLUE_DARK    = colors.HexColor("#1e3a5f")
_BLUE_MID     = colors.HexColor("#2e6da4")
_BLUE_LIGHT   = colors.HexColor("#d9eaf7")
_YELLOW_LIGHT = colors.HexColor("#fff9e6")
_RED_LIGHT    = colors.HexColor("#ffe0e0")
_GREY_LIGHT   = colors.HexColor("#f5f5f5")
_GREY_MID     = colors.HexColor("#d0d0d0")
_WHITE        = colors.white
_BLACK        = colors.black

_PAGE_W, _PAGE_H = landscape(letter)
_MARGIN    = 0.55 * inch
_CONTENT_W = _PAGE_W - 2 * _MARGIN

_COMPANY_NAME = "All Phase Consulting, LLC"

# Column labels that match the reference invoice format
_COL_LABELS = {
    "small":          "Small\nBox",
    "medium":         "Medium\nBox",
    "large":          "Large\nBox",
    "box_wrapped":    "XL Box /\nUnboxed",
    "picture_mirror": "Picture /\nMirror",
    "plant_vase":     "Lamp /\nPlant /\nVase",
    "tv":             "TV\nBox",
    "wardrobe":       "Wardrobe\nBox",
    "mattress":       "Mattress\nBox",
    "dish_pack":      "Dish\nPack\nBox",
    "glass_pack":     "Glass\nPack\nBox",
    "boots_pans":     "Pots &\nPans\nBox",
}


def _styles():
    return {
        "title": ParagraphStyle(
            "cps_title", fontName="Helvetica-Bold", fontSize=13,
            textColor=_BLUE_DARK, alignment=TA_LEFT, spaceAfter=4,
        ),
        "hdr_label": ParagraphStyle(
            "cps_hdr_label", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, spaceAfter=1,
        ),
        "hdr_val": ParagraphStyle(
            "cps_hdr_val", fontName="Helvetica", fontSize=9,
            textColor=_BLACK, spaceAfter=5,
        ),
        "hdr_addr": ParagraphStyle(
            "cps_hdr_addr", fontName="Helvetica-Bold", fontSize=10,
            textColor=_BLACK, alignment=TA_LEFT,
        ),
        "cell_hdr": ParagraphStyle(
            "cps_cell_hdr", fontName="Helvetica-Bold", fontSize=6.5,
            textColor=_WHITE, alignment=TA_CENTER,
        ),
        "cell_room": ParagraphStyle(
            "cps_cell_room", fontName="Helvetica", fontSize=7.5,
            textColor=_BLACK, leading=10,
        ),
        "cell_num": ParagraphStyle(
            "cps_cell_num", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, alignment=TA_CENTER,
        ),
        "cell_total": ParagraphStyle(
            "cps_cell_total", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, alignment=TA_CENTER,
        ),
        "grand_lbl": ParagraphStyle(
            "cps_grand_lbl", fontName="Helvetica-Bold", fontSize=8.5,
            textColor=_BLUE_DARK, alignment=TA_LEFT,
        ),
        "grand_num": ParagraphStyle(
            "cps_grand_num", fontName="Helvetica-Bold", fontSize=8.5,
            textColor=_BLUE_DARK, alignment=TA_CENTER,
        ),
        "note_text": ParagraphStyle(
            "cps_note_text", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, leading=11,
        ),
        "co_name": ParagraphStyle(
            "cps_co_name", fontName="Helvetica-Bold", fontSize=10,
            textColor=_BLUE_DARK, alignment=TA_LEFT, spaceAfter=4,
        ),
    }


# Track total page count for "Page X of Y" footer
class _PageCountDoc(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._total_pages = 0

    def handle_pageEnd(self):
        self._total_pages = self.page
        super().handle_pageEnd()


def _make_footer(total_pages_ref: list):
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(
            _MARGIN, 0.3 * inch,
            "Insured Initials _________",
        )
        page_label = f"Page {doc.page}"
        if total_pages_ref[0]:
            page_label += f" of {total_pages_ref[0]}"
        canvas.drawRightString(_PAGE_W - _MARGIN, 0.3 * inch, page_label)
        canvas.restoreState()
    return _footer


def build_cps_pdf(session) -> bytes:
    """Build and return raw PDF bytes for a BoxCalcCPSSession."""
    buf = io.BytesIO()

    total_pages_ref = [0]

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=0.5 * inch, bottomMargin=0.65 * inch,
    )

    S = _styles()
    client = session.client
    rooms  = list(session.rooms.order_by("order", "room_name"))
    grand  = {col: 0 for col in CPS_COLUMNS}
    for r in rooms:
        for col in CPS_COLUMNS:
            grand[col] += getattr(r, col, 0) or 0
    grand_total = sum(grand.values())

    today_str    = date.today().strftime("%b %d, %Y").replace(" 0", " ")
    claim_date   = getattr(session, 'created_at', None)
    claim_date_str = claim_date.strftime("%b %d, %Y").replace(" 0", " ") if claim_date else "—"

    # Prefer an explicit loss_date if the session has one
    loss_date = getattr(session, 'loss_date', None) or getattr(client, 'loss_date', None)
    loss_date_str = (
        loss_date.strftime("%b %d, %Y").replace(" 0", " ")
        if loss_date else claim_date_str
    )

    claim_num = getattr(client, 'claimNumber', '') or '—'
    insured   = getattr(client, 'pOwner',       '') or '—'
    address   = getattr(client, 'pAddress',     '') or '—'

    story = []

    # ── Header: 2-column bordered grid ───────────────────────────────────────
    # Left column: company name + title + report date + date of loss
    left_content = [
        Paragraph(_COMPANY_NAME,  S["co_name"]),
        Paragraph("Box Summary",  S["title"]),
        Paragraph("Report Date:", S["hdr_label"]),
        Paragraph(today_str,      S["hdr_val"]),
        Paragraph("Date of Loss:", S["hdr_label"]),
        Paragraph(loss_date_str,   S["hdr_val"]),
    ]

    # Right column: claim id, insured, property address
    right_content = [
        Paragraph("Claim Id:", S["hdr_label"]),
        Paragraph(claim_num,   S["hdr_val"]),
        Paragraph("Insured:", S["hdr_label"]),
        Paragraph(insured,    S["hdr_val"]),
        Paragraph("Property Address:", S["hdr_label"]),
        Paragraph(address,            S["hdr_addr"]),
    ]

    def _cell(flowables, usable_w):
        t = Table([[f] for f in flowables], colWidths=[usable_w])
        t.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    _hdr_pad = 10
    lw = _CONTENT_W * 0.42
    rw = _CONTENT_W * 0.58

    header_tbl = Table(
        [[_cell(left_content, lw - 2 * _hdr_pad),
          _cell(right_content, rw - 2 * _hdr_pad)]],
        colWidths=[lw, rw],
    )
    _border = colors.HexColor("#aaaaaa")
    header_tbl.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.8, _border),
        ("INNERGRID",     (0, 0), (-1, -1), 0.8, _border),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), _hdr_pad),
        ("RIGHTPADDING",  (0, 0), (-1, -1), _hdr_pad),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 10))

    # ── Box count table ───────────────────────────────────────────────────────
    box_col_w   = 0.57 * inch
    total_col_w = 0.52 * inch
    room_col_w  = _CONTENT_W - (len(CPS_COLUMNS) * box_col_w) - total_col_w
    col_widths  = [room_col_w] + [box_col_w] * len(CPS_COLUMNS) + [total_col_w]

    header_row = (
        [Paragraph("Room", S["cell_hdr"])]
        + [Paragraph(_COL_LABELS[c], S["cell_hdr"]) for c in CPS_COLUMNS]
        + [Paragraph("Total", S["cell_hdr"])]
    )
    table_data = [header_row]

    ts_commands = [
        ("BACKGROUND",    (0, 0), (-1, 0),  _BLUE_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  _WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  6.5),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (0, -1),  6),
    ]

    error_rows = []
    for row_idx, room in enumerate(rooms, start=1):
        counts    = [getattr(room, col, 0) or 0 for col in CPS_COLUMNS]
        row_total = sum(counts)

        row = (
            [Paragraph(room.room_name, S["cell_room"])]
            + [Paragraph(str(c), S["cell_num"]) for c in counts]
            + [Paragraph(str(row_total), S["cell_total"])]
        )
        table_data.append(row)
        if room.status == "error":
            error_rows.append(row_idx)

    grand_row = (
        [Paragraph("Total", S["grand_lbl"])]
        + [Paragraph(str(grand[c]), S["grand_num"]) for c in CPS_COLUMNS]
        + [Paragraph(str(grand_total), S["grand_num"])]
    )
    table_data.append(grand_row)
    grand_idx = len(table_data) - 1

    ts_commands += [
        ("BACKGROUND",  (0, grand_idx), (-1, grand_idx), _YELLOW_LIGHT),
        ("FONTNAME",    (0, grand_idx), (-1, grand_idx), "Helvetica-Bold"),
        ("LINEABOVE",   (0, grand_idx), (-1, grand_idx), 1.5, _BLUE_MID),
        ("LINEBELOW",   (0, grand_idx), (-1, grand_idx), 1.5, _BLUE_MID),
    ]
    for er in error_rows:
        ts_commands.append(("BACKGROUND", (0, er), (-1, er), _RED_LIGHT))

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(ts_commands))
    story.append(tbl)

    # ── Optional estimator note ───────────────────────────────────────────────
    note_text = (session.notes or "").strip()
    if note_text:
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"<b>Estimator Note:</b> {note_text}", S["note_text"]
        ))

    # ── Two-pass build to get total page count for footer ────────────────────
    footer_fn = _make_footer(total_pages_ref)

    # First pass — count pages
    from reportlab.platypus import BaseDocTemplate
    buf_probe = io.BytesIO()
    doc_probe = SimpleDocTemplate(
        buf_probe,
        pagesize=landscape(letter),
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=0.5 * inch, bottomMargin=0.65 * inch,
    )

    import copy
    story_copy = copy.deepcopy(story)
    page_count = [0]

    class _CountingCanvas:
        def __init__(self, *a, **kw): pass
    def _count_footer(canvas, doc):
        page_count[0] = doc.page

    doc_probe.build(story_copy, onFirstPage=_count_footer, onLaterPages=_count_footer)
    total_pages_ref[0] = page_count[0]

    # Second pass — real build with correct total
    doc.build(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
    return buf.getvalue()
