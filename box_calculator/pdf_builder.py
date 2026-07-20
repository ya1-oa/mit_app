"""
CPS Box Count Report PDF builder.

Matches the standard CPS pack-out report format:
  3-column bordered header grid (title/purpose | claim info | loss/address)
  Room × 12 box-type table with per-room totals and grand totals row
  Estimator notes + Step 1/2/3 methodology table
  Per-room AI notes as Step 3 item descriptions
  Insured initials line + page footer
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
_BLUE_DARK    = colors.HexColor("#1e3a5f")
_BLUE_MID     = colors.HexColor("#2e6da4")
_BLUE_LIGHT   = colors.HexColor("#d9eaf7")
_YELLOW_LIGHT = colors.HexColor("#fff2cc")
_RED_LIGHT    = colors.HexColor("#ffe0e0")
_GREY_LIGHT   = colors.HexColor("#f5f5f5")
_GREY_MID     = colors.HexColor("#e0e0e0")
_WHITE        = colors.white
_BLACK        = colors.black

_PAGE_W, _PAGE_H = landscape(letter)
_MARGIN    = 0.55 * inch
_CONTENT_W = _PAGE_W - 2 * _MARGIN


def _styles():
    return {
        "title": ParagraphStyle(
            "cps_title", fontName="Helvetica-Bold", fontSize=11,
            textColor=_BLUE_DARK, alignment=TA_LEFT, spaceAfter=2,
        ),
        "purpose": ParagraphStyle(
            "cps_purpose", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, alignment=TA_LEFT,
        ),
        "hdr_label": ParagraphStyle(
            "cps_hdr_label", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK,
        ),
        "hdr_val": ParagraphStyle(
            "cps_hdr_val", fontName="Helvetica", fontSize=8,
            textColor=_BLACK,
        ),
        "hdr_loss": ParagraphStyle(
            "cps_hdr_loss", fontName="Helvetica-Bold", fontSize=10,
            textColor=_BLACK, alignment=TA_LEFT,
        ),
        "hdr_addr": ParagraphStyle(
            "cps_hdr_addr", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, alignment=TA_LEFT,
        ),
        "cell_hdr": ParagraphStyle(
            "cps_cell_hdr", fontName="Helvetica-Bold", fontSize=7,
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
            "cps_grand_lbl", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, alignment=TA_LEFT,
        ),
        "grand_num": ParagraphStyle(
            "cps_grand_num", fontName="Helvetica-Bold", fontSize=8,
            textColor=_BLUE_DARK, alignment=TA_CENTER,
        ),
        "section_hdr": ParagraphStyle(
            "cps_section_hdr", fontName="Helvetica-Bold", fontSize=9,
            textColor=_BLUE_DARK,
        ),
        "note_text": ParagraphStyle(
            "cps_note_text", fontName="Helvetica", fontSize=8,
            textColor=_BLACK, leading=11,
        ),
        "step_hdr": ParagraphStyle(
            "cps_step_hdr", fontName="Helvetica-Bold", fontSize=7.5,
            textColor=_WHITE, alignment=TA_LEFT,
        ),
        "step_body": ParagraphStyle(
            "cps_step_body", fontName="Helvetica", fontSize=7.5,
            textColor=_BLACK, leading=10,
        ),
        "step3_room": ParagraphStyle(
            "cps_step3_room", fontName="Helvetica-Bold", fontSize=7.5,
            textColor=_BLACK,
        ),
        "step3_note": ParagraphStyle(
            "cps_step3_note", fontName="Helvetica", fontSize=7.5,
            textColor=_BLACK, leading=10,
        ),
        "initials": ParagraphStyle(
            "cps_initials", fontName="Helvetica", fontSize=8,
            textColor=colors.grey, alignment=TA_LEFT,
        ),
    }


def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(
        _MARGIN, 0.3 * inch,
        f"Powered by Encircle     Insured Initials _________",
    )
    canvas.drawRightString(
        _PAGE_W - _MARGIN, 0.3 * inch,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def build_cps_pdf(session) -> bytes:
    """Build and return raw PDF bytes for a BoxCalcCPSSession."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=0.5 * inch, bottomMargin=0.65 * inch,
    )

    S = _styles()
    client  = session.client
    rooms   = list(session.rooms.order_by("order", "room_name"))
    grand   = {col: 0 for col in CPS_COLUMNS}
    for r in rooms:
        for col in CPS_COLUMNS:
            grand[col] += getattr(r, col, 0) or 0
    grand_total = sum(grand.values())

    # Claim Date = session creation date (matches report origin, not today)
    session_date_str = session.created_at.strftime("%b %d, %Y").replace(" 0", " ")

    story = []

    # ── 3-column header grid ─────────────────────────────────────────────────
    # Left cell: title + purpose + date
    left_content = [
        Paragraph("CPS Box Count Report", S["title"]),
        Paragraph("SALVAGEABLE CONTENTS", S["purpose"]),
        Paragraph("PACKOUT, TRANSPORT, STORE, CLEAN, RESET", S["purpose"]),
        Spacer(1, 14),
        Paragraph("Claim Date:", S["hdr_label"]),
        Paragraph(session_date_str, S["hdr_val"]),
    ]

    # Center cell: claim id + insured
    claim_id = getattr(client, 'claimNumber', '') or '—'
    insured  = getattr(client, 'pOwner', '') or '—'
    center_content = [
        Paragraph("Claim Id:", S["hdr_label"]),
        Paragraph(claim_id, S["hdr_val"]),
        Spacer(1, 16),
        Paragraph("Insured:", S["hdr_label"]),
        Paragraph(insured, S["hdr_val"]),
    ]

    # Right cell: property address (Bold-10 value matches reference)
    address = getattr(client, 'pAddress', '') or '—'
    right_content = [
        Paragraph("Property Address:", S["hdr_label"]),
        Paragraph(address, S["hdr_loss"]),
    ]

    # Build header as a 3-column Table.
    # Each cell holds a nested sub-table so flowables stack vertically.
    def _cell(flowables, usable_w):
        t = Table([[f] for f in flowables], colWidths=[usable_w])
        t.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    _hdr_pad = 8  # left/right padding inside each header column
    lw = _CONTENT_W * 0.30
    cw = _CONTENT_W * 0.32
    rw = _CONTENT_W * 0.38

    header_tbl = Table(
        [[_cell(left_content, lw - 2 * _hdr_pad),
          _cell(center_content, cw - 2 * _hdr_pad),
          _cell(right_content, rw - 2 * _hdr_pad)]],
        colWidths=[lw, cw, rw],
    )
    _border = colors.HexColor("#aaaaaa")
    header_tbl.setStyle(TableStyle([
        ("BOX",          (0, 0), (-1, -1), 0.8, _border),
        ("INNERGRID",    (0, 0), (-1, -1), 0.8, _border),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), _hdr_pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), _hdr_pad),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 8))

    # ── Box count table ───────────────────────────────────────────────────────
    col_labels = [CPS_COLUMN_LABELS[c] for c in CPS_COLUMNS]

    box_col_w  = 0.57 * inch
    total_col_w = 0.48 * inch
    room_col_w = _CONTENT_W - (len(CPS_COLUMNS) * box_col_w) - total_col_w
    col_widths = [room_col_w] + [box_col_w] * len(CPS_COLUMNS) + [total_col_w]

    header_row = (
        [Paragraph("Room", S["cell_hdr"])]
        + [Paragraph(lbl, S["cell_hdr"]) for lbl in col_labels]
        + [Paragraph("Total", S["cell_hdr"])]
    )
    table_data = [header_row]

    ts_commands = [
        ("BACKGROUND",    (0, 0), (-1, 0),  _BLUE_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  _WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  7),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (0, -1),  5),
    ]

    error_rows = []
    for row_idx, room in enumerate(rooms, start=1):
        counts = [getattr(room, col, 0) or 0 for col in CPS_COLUMNS]
        row_total = sum(counts)

        def _num(v, style, _zero="—"):
            return Paragraph(str(v) if v else _zero, style)

        row = (
            [Paragraph(room.room_name, S["cell_room"])]
            + [_num(c, S["cell_num"]) for c in counts]
            + [_num(row_total, S["cell_total"])]
        )
        table_data.append(row)
        if room.status == "error":
            error_rows.append(row_idx)

    grand_row = (
        [Paragraph("Total", S["grand_lbl"])]
        + [Paragraph(str(v) if v else "—", S["grand_num"]) for v in [grand[c] for c in CPS_COLUMNS]]
        + [Paragraph(str(grand_total), S["grand_num"])]
    )
    table_data.append(grand_row)
    grand_idx = len(table_data) - 1

    ts_commands += [
        ("BACKGROUND",   (0, grand_idx), (-1, grand_idx), _YELLOW_LIGHT),
        ("FONTNAME",     (0, grand_idx), (-1, grand_idx), "Helvetica-Bold"),
        ("LINEABOVE",    (0, grand_idx), (-1, grand_idx), 1.5, _BLUE_MID),
        ("LINEBELOW",    (0, grand_idx), (-1, grand_idx), 1.5, _BLUE_MID),
    ]
    for er in error_rows:
        ts_commands.append(("BACKGROUND", (0, er), (-1, er), _RED_LIGHT))

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(ts_commands))
    story.append(tbl)
    story.append(Spacer(1, 10))

    # ── Estimator note ────────────────────────────────────────────────────────
    note_text = (session.notes or "").strip()
    room_notes = [(r.room_name, r.ai_notes.strip()) for r in rooms if r.ai_notes and r.ai_notes.strip()]

    if note_text:
        story.append(Paragraph(f"<b>Estimator Note:</b> {note_text}", S["note_text"]))
        story.append(Spacer(1, 6))

    # ── Step 1/2/3 methodology table ──────────────────────────────────────────
    step_rows = [
        [Paragraph("Step", S["step_hdr"]), Paragraph("Current report use", S["step_hdr"])],
        [Paragraph("Step 1", S["step_body"]),
         Paragraph("Individual content photos: room-by-room item description and first-pass carton category.", S["step_body"])],
        [Paragraph("Step 2", S["step_body"]),
         Paragraph("100-series overview photos: check room-wide density, missed contents, and oversized handling.", S["step_body"])],
        [Paragraph("Step 3", S["step_body"]),
         Paragraph("Item description entered per individual picture.", S["step_body"])],
    ]
    step_tbl = Table(step_rows, colWidths=[0.65 * inch, _CONTENT_W - 0.65 * inch])
    step_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _BLUE_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY_LIGHT]),
    ]))
    story.append(step_tbl)

    # ── Step 3 item descriptions (per-room AI notes) ──────────────────────────
    if room_notes:
        story.append(Spacer(1, 14))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GREY_MID))
        story.append(Spacer(1, 4))
        story.append(Paragraph("STEP 3 - ITEM DESCRIPTION PER INDIVIDUAL PICTURE", S["section_hdr"]))
        story.append(Spacer(1, 4))

        desc_rows = [
            [Paragraph("Room", S["step_hdr"]), Paragraph("Description / Estimating Team Notes", S["step_hdr"])],
        ]
        for room_name, note in room_notes:
            desc_rows.append([
                Paragraph(room_name, S["step3_room"]),
                Paragraph(note, S["step3_note"]),
            ])

        desc_tbl = Table(
            desc_rows,
            colWidths=[1.8 * inch, _CONTENT_W - 1.8 * inch],
        )
        desc_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), _BLUE_DARK),
            ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
            ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY_LIGHT]),
        ]))
        story.append(desc_tbl)

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buf.getvalue()
