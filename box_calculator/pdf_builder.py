"""
CPS Box Count Report PDF builder.

Produces a landscape A4 report matching the standard CPS pack-out format:
  Cover block (client, claim, date, address)
  Room × 11 box-type table with per-room totals
  Grand totals row
  Estimator notes section

Uses ReportLab Platypus for layout.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .cps_analyzer import CPS_COLUMNS, CPS_COLUMN_LABELS

# ── Colours ──────────────────────────────────────────────────────────────────
_BLUE_DARK   = colors.HexColor("#1e3a5f")
_BLUE_MID    = colors.HexColor("#2e6da4")
_BLUE_LIGHT  = colors.HexColor("#d9eaf7")
_YELLOW_LIGHT = colors.HexColor("#fff2cc")
_RED_LIGHT   = colors.HexColor("#ffe0e0")
_GREY_LIGHT  = colors.HexColor("#f5f5f5")
_GREY_MID    = colors.HexColor("#e0e0e0")
_WHITE       = colors.white
_BLACK       = colors.black

_PAGE_W, _PAGE_H = landscape(letter)
_MARGIN = 0.55 * inch
_CONTENT_W = _PAGE_W - 2 * _MARGIN


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", fontName="Helvetica-Bold", fontSize=16,
            textColor=_BLUE_DARK, alignment=TA_CENTER, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=10,
            textColor=_BLUE_MID, alignment=TA_CENTER, spaceAfter=2,
        ),
        "meta_label": ParagraphStyle(
            "meta_label", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK,
        ),
        "meta_val": ParagraphStyle(
            "meta_val", fontName="Helvetica", fontSize=8,
            textColor=_BLACK,
        ),
        "section_hdr": ParagraphStyle(
            "section_hdr", fontName="Helvetica-Bold", fontSize=9,
            textColor=_BLUE_DARK, alignment=TA_LEFT,
        ),
        "notes_body": ParagraphStyle(
            "notes_body", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, leading=12,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=7,
            textColor=colors.grey, alignment=TA_CENTER,
        ),
        "cell_hdr": ParagraphStyle(
            "cell_hdr", fontName="Helvetica-Bold", fontSize=7,
            textColor=_WHITE, alignment=TA_CENTER,
        ),
        "cell_room": ParagraphStyle(
            "cell_room", fontName="Helvetica", fontSize=7.5,
            textColor=_BLACK, leading=10,
        ),
        "cell_num": ParagraphStyle(
            "cell_num", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, alignment=TA_CENTER,
        ),
        "cell_total": ParagraphStyle(
            "cell_total", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, alignment=TA_CENTER,
        ),
        "grand_lbl": ParagraphStyle(
            "grand_lbl", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, alignment=TA_LEFT,
        ),
        "grand_num": ParagraphStyle(
            "grand_num", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, alignment=TA_CENTER,
        ),
    }


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(
        _PAGE_W / 2, 0.3 * inch,
        f"CPS Box Count Report  ·  Generated {date.today().strftime('%B %d, %Y')}  ·  AI estimates — verify before finalizing",
    )
    canvas.drawRightString(
        _PAGE_W - _MARGIN, 0.3 * inch,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def build_cps_pdf(session) -> bytes:
    """
    Build and return raw PDF bytes for a BoxCalcCPSSession.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=0.6 * inch, bottomMargin=0.65 * inch,
    )

    S = _styles()
    client = session.client
    rooms = list(session.rooms.order_by("order", "room_name"))
    grand = {col: 0 for col in CPS_COLUMNS}
    for r in rooms:
        for col in CPS_COLUMNS:
            grand[col] += getattr(r, col, 0) or 0
    grand_total = sum(grand.values())

    story = []

    # ── Header block ─────────────────────────────────────────────────────────
    story.append(Paragraph("CPS Box Count Report", S["title"]))
    story.append(Paragraph(
        "Contents Processing Sheet — Pre-Packout Box Count Estimate",
        S["subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=_BLUE_MID, spaceAfter=6))

    # Meta info row (client | claim | date | address)
    meta_rows = []
    meta_rows.append((
        Paragraph("Insured:", S["meta_label"]),
        Paragraph(client.pOwner or "—", S["meta_val"]),
        Paragraph("Claim #:", S["meta_label"]),
        Paragraph(client.claimNumber or "—", S["meta_val"]),
        Paragraph("Date:", S["meta_label"]),
        Paragraph(date.today().strftime("%B %d, %Y"), S["meta_val"]),
    ))
    if client.pAddress:
        meta_rows.append((
            Paragraph("Property:", S["meta_label"]),
            Paragraph(client.pAddress, S["meta_val"]),
            "", "", "", "",
        ))

    meta_col_w = [0.7 * inch, 2.2 * inch, 0.65 * inch, 1.6 * inch, 0.5 * inch, 1.4 * inch]
    meta_tbl = Table(meta_rows, colWidths=meta_col_w)
    meta_tbl.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8))

    # ── Box count table ───────────────────────────────────────────────────────
    col_labels = [CPS_COLUMN_LABELS[c] for c in CPS_COLUMNS]

    # Column widths — room name gets the slack, box columns fixed
    box_col_w = 0.62 * inch
    total_col_w = 0.5 * inch
    room_col_w = _CONTENT_W - (len(CPS_COLUMNS) * box_col_w) - total_col_w
    col_widths = [room_col_w] + [box_col_w] * len(CPS_COLUMNS) + [total_col_w]

    # Header row
    header = (
        [Paragraph("Room / Area", S["cell_hdr"])]
        + [Paragraph(lbl, S["cell_hdr"]) for lbl in col_labels]
        + [Paragraph("Total", S["cell_hdr"])]
    )
    table_data = [header]

    # Data rows
    ts_commands = [
        ("BACKGROUND",    (0, 0), (-1, 0),  _BLUE_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  _WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  7),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (0, -1),  5),
    ]

    error_rows = []
    for row_idx, room in enumerate(rooms, start=1):
        counts = [getattr(room, col, 0) or 0 for col in CPS_COLUMNS]
        row_total = sum(counts)

        def _num(v, style):
            return Paragraph(str(v) if v else "—", style)

        row = (
            [Paragraph(room.room_name, S["cell_room"])]
            + [_num(c, S["cell_num"]) for c in counts]
            + [_num(row_total, S["cell_total"])]
        )
        table_data.append(row)

        if room.status == "error":
            error_rows.append(row_idx)

    # Grand totals row
    grand_counts_list = [grand[col] for col in CPS_COLUMNS]
    grand_row = (
        [Paragraph("GRAND TOTALS", S["grand_lbl"])]
        + [Paragraph(str(v) if v else "—", S["grand_num"]) for v in grand_counts_list]
        + [Paragraph(str(grand_total), S["grand_num"])]
    )
    table_data.append(grand_row)
    grand_row_idx = len(table_data) - 1

    ts_commands += [
        ("BACKGROUND",   (0, grand_row_idx), (-1, grand_row_idx), _YELLOW_LIGHT),
        ("FONTNAME",     (0, grand_row_idx), (-1, grand_row_idx), "Helvetica-Bold"),
        ("LINEABOVE",    (0, grand_row_idx), (-1, grand_row_idx), 1.5, _BLUE_MID),
        ("LINEBELOW",    (0, grand_row_idx), (-1, grand_row_idx), 1.5, _BLUE_MID),
    ]
    for er in error_rows:
        ts_commands.append(("BACKGROUND", (0, er), (-1, er), _RED_LIGHT))

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(ts_commands))
    story.append(tbl)

    # ── Summary stats ─────────────────────────────────────────────────────────
    complete = sum(1 for r in rooms if r.status == "complete")
    errors   = sum(1 for r in rooms if r.status == "error")
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"{len(rooms)} room(s) analyzed  ·  {complete} complete  ·  {errors} with errors  ·  "
        f"Grand total: <b>{grand_total}</b> boxes",
        S["footer"],
    ))

    # ── Estimator notes ───────────────────────────────────────────────────────
    notes_text = session.notes.strip() if session.notes else ""
    room_notes = [(r.room_name, r.ai_notes.strip()) for r in rooms if r.ai_notes and r.ai_notes.strip()]

    if notes_text or room_notes:
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY_MID, spaceAfter=6))
        story.append(Paragraph("Estimator Notes", S["section_hdr"]))
        story.append(Spacer(1, 4))

        if notes_text:
            story.append(Paragraph(notes_text, S["notes_body"]))
            story.append(Spacer(1, 6))

        for room_name, note in room_notes:
            story.append(Paragraph(
                f"<b>{room_name}:</b> {note}",
                S["notes_body"],
            ))
            story.append(Spacer(1, 3))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()
