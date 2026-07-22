"""
Build a Schedule of Loss PDF using reportlab.
Sections per room, per-room subtotals, grand total page.
"""
from __future__ import annotations

import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
C_HEADER_BG  = colors.HexColor('#1e40af')   # dark blue — cover / section headers
C_HEADER_FG  = colors.white
C_ROOM_BG    = colors.HexColor('#059669')   # green — room header rows
C_ROOM_FG    = colors.white
C_ALT        = colors.HexColor('#f0fdf4')   # very light green — alternating item rows
C_TOTAL_BG   = colors.HexColor('#1e3a5f')   # navy — subtotal / grand total rows
C_TOTAL_FG   = colors.white
C_RULE       = colors.HexColor('#e2e8f0')
C_TEXT       = colors.HexColor('#0f172a')
C_MUTED      = colors.HexColor('#64748b')


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    # Top rule
    canvas.setStrokeColor(C_RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.6 * inch, h - 0.45 * inch, w - 0.6 * inch, h - 0.45 * inch)
    # Footer
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(C_MUTED)
    canvas.drawString(0.6 * inch, 0.35 * inch, 'PPR Schedule of Loss  |  All Phase Consulting, LLC')
    canvas.drawRightString(w - 0.6 * inch, 0.35 * inch, f'Page {doc.page}')
    canvas.restoreState()


def build_pdf(session) -> bytes:
    buf = BytesIO()
    styles = getSampleStyleSheet()

    h1 = ParagraphStyle('H1', parent=styles['Normal'],
                         fontSize=22, textColor=C_HEADER_FG, leading=26,
                         fontName='Helvetica-Bold')
    h2 = ParagraphStyle('H2', parent=styles['Normal'],
                         fontSize=13, textColor=C_HEADER_FG, leading=16,
                         fontName='Helvetica-Bold')
    body = ParagraphStyle('Body', parent=styles['Normal'],
                           fontSize=9, textColor=C_TEXT, leading=13)
    muted = ParagraphStyle('Muted', parent=styles['Normal'],
                            fontSize=8, textColor=C_MUTED, leading=11)
    room_hdr = ParagraphStyle('RoomHdr', parent=styles['Normal'],
                               fontSize=11, textColor=C_ROOM_FG, leading=14,
                               fontName='Helvetica-Bold')

    doc = BaseDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.6 * inch,
    )
    w = letter[0] - 1.2 * inch  # usable width

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='normal',
    )
    doc.addPageTemplates([
        PageTemplate(id='main', frames=[frame], onPage=_header_footer),
    ])

    story = []

    # ── Pre-compute totals ─────────────────────────────────────────────────────
    rooms = list(session.rooms.prefetch_related('items').order_by('order', 'room_number'))
    grand_rcv = grand_qty = 0

    room_stats = []
    for room in rooms:
        items = list(room.items.filter(structural=False).order_by('order'))
        rcv = sum((float(i.replacement_value_each or 0) * (i.qty or 1)) for i in items)
        qty = sum(i.qty or 1 for i in items)
        room_stats.append({'room': room, 'items': items, 'rcv': rcv, 'qty': qty})
        grand_rcv += rcv
        grand_qty += qty

    # ── Cover page ────────────────────────────────────────────────────────────
    cover_data = [
        [Paragraph('NON SALVAGEABLE / PPR Schedule of Loss', h1)],
        [Paragraph('All Phase Consulting, LLC', h2)],
        [Paragraph('Personal Property Replacement — Replacement Value Report', h2)],
    ]
    cover_tbl = Table(cover_data, colWidths=[w])
    cover_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), C_HEADER_BG),
        ('TOPPADDING',  (0, 0), (-1, 0), 20),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING',  (0, 1), (-1, 1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
        ('TOPPADDING',  (0, 2), (-1, 2), 2),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 20),
        ('LEFTPADDING',  (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('ROUNDEDCORNERS', [6]),
    ]))
    story.append(cover_tbl)
    story.append(Spacer(1, 16))

    # Claim info block — pull from the Client record (same source as the box
    # count header) so values populate even when session fields are blank.
    now = datetime.date.today().strftime('%B %d, %Y')
    _client      = session.client
    _insured     = (getattr(_client, 'pOwner',      '') or '').strip() or '—'
    _claim_num   = (getattr(_client, 'claimNumber', '') or '').strip() or '—'
    _street      = (getattr(_client, 'pAddress',      '') or '').strip().strip(',').strip()
    _city_st_zip = (getattr(_client, 'pCityStateZip', '') or '').strip().strip(',').strip()
    _loss_val    = getattr(session, 'loss_date', None) or getattr(_client, 'loss_date', None)
    _loss_date   = _loss_val.strftime('%B %d, %Y') if _loss_val else '—'
    info_rows = [
        ['Insured',        _insured,             'Report Date',   now],
        ['Address',        _street or '—',       '',              _city_st_zip],
        ['Claim Number',   _claim_num,           'Date of Loss',  _loss_date],
        ['Total Rooms',    str(len(rooms)),      'Total Items',   str(grand_qty)],
        ['Replacement Value', _fmt_usd(grand_rcv), '',            ''],
    ]
    info_col_w = [w * 0.18, w * 0.32, w * 0.18, w * 0.32]
    info_tbl = Table(info_rows, colWidths=info_col_w)
    info_tbl.setStyle(TableStyle([
        ('FONTNAME',  (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',  (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), C_MUTED),
        ('TEXTCOLOR', (2, 0), (2, -1), C_MUTED),
        ('TEXTCOLOR', (1, 0), (1, -1), C_TEXT),
        ('TEXTCOLOR', (3, 0), (3, -1), C_TEXT),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, C_ALT]),
        ('TOPPADDING',  (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('BOX',       (0, 0), (-1, -1), 0.5, C_RULE),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, C_RULE),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=0.5, color=C_RULE))
    story.append(Spacer(1, 4))
    story.append(Paragraph('Rooms included in this report:', muted))
    story.append(Spacer(1, 6))

    # Room summary list on cover
    for rs in room_stats:
        r = rs['room']
        story.append(Paragraph(
            f"<b>{r.room_number} {r.room_name}</b> — "
            f"{len(rs['items'])} items &nbsp;|&nbsp; RCV: {_fmt_usd(rs['rcv'])}",
            body,
        ))
    story.append(PageBreak())

    # ── Item columns ─────────────────────────────────────────────────────────
    # # | Description | Brand | Qty | Age | RCV Each | RCV Total | Cond
    col_w = [w*0.04, w*0.32, w*0.14, w*0.06, w*0.07, w*0.12, w*0.12, w*0.13]
    col_headers = ['#', 'Description', 'Brand', 'Qty', 'Age', 'RCV Each', 'RCV Total', 'Cond']

    global_item_num = 1

    # ── Room sections ─────────────────────────────────────────────────────────
    for rs in room_stats:
        room  = rs['room']
        items = rs['items']

        # Room header banner
        rh_data = [[Paragraph(f"{room.room_number}  {room.room_name}", room_hdr),
                    Paragraph(f"<b>{len(items)} items</b>", room_hdr),
                    Paragraph(f"RCV: <b>{_fmt_usd(rs['rcv'])}</b>", room_hdr)]]
        rh_tbl = Table(rh_data, colWidths=[w * 0.5, w * 0.2, w * 0.3])
        rh_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), C_ROOM_BG),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
        ]))
        story.append(rh_tbl)

        # Column header row
        tbl_data = [col_headers]
        for i, item in enumerate(items):
            age_str = f"{item.age_years or 0}y"
            if item.age_months:
                age_str += f" {item.age_months}m"
            tbl_data.append([
                str(global_item_num),
                item.description or '',
                item.brand or '',
                str(item.qty or 1),
                age_str,
                _fmt_usd(item.replacement_value_each),
                _fmt_usd(float(item.replacement_value_each or 0) * (item.qty or 1)),
                item.condition or '',
            ])
            global_item_num += 1

        # Subtotal row
        tbl_data.append([
            '', 'ROOM SUBTOTAL', '', str(rs['qty']), '',
            '', _fmt_usd(rs['rcv']), '',
        ])

        item_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
        n = len(tbl_data)
        item_tbl.setStyle(TableStyle([
            # Header row
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, 0), (-1, 0), 7.5),
            ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
            # Item rows
            ('FONTSIZE',      (0, 1), (-1, -2), 7.5),
            ('TEXTCOLOR',     (0, 1), (-1, -2), C_TEXT),
            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, C_ALT]),
            # Numeric right-align
            ('ALIGN',         (2, 0), (-1, -1), 'RIGHT'),
            # Subtotal row
            ('BACKGROUND',    (0, n-1), (-1, n-1), C_TOTAL_BG),
            ('TEXTCOLOR',     (0, n-1), (-1, n-1), C_TOTAL_FG),
            ('FONTNAME',      (0, n-1), (-1, n-1), 'Helvetica-Bold'),
            ('FONTSIZE',      (0, n-1), (-1, n-1), 7.5),
            # Grid
            ('GRID',          (0, 0), (-1, -1), 0.3, C_RULE),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ]))
        story.append(item_tbl)
        story.append(Spacer(1, 10))

        # ── Per-room signature block ───────────────────────────────────────────
        if room.signature_name and room.signed_at:
            sig_date = room.signed_at.strftime('%B %d, %Y at %I:%M %p')
            sig_data = [
                [Paragraph('<b>Client Signature — Room Confirmation</b>', body),
                 Paragraph(f'<font color="#64748b">Signed {sig_date}</font>', muted)],
                [Paragraph(
                    f'<font size="13"><b>{room.signature_name}</b></font>', body),
                 Paragraph('Electronically signed by typed name', muted)],
            ]
            sig_tbl = Table(sig_data, colWidths=[w * 0.65, w * 0.35])
            sig_tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('TOPPADDING',    (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LEFTPADDING',   (0, 0), (-1, -1), 10),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
                ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('LINEBELOW',     (0, 0), (-1, 0), 0.3, colors.HexColor('#e2e8f0')),
                ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(KeepTogether([sig_tbl]))
        else:
            sig_placeholder = Table(
                [[Paragraph('Awaiting client signature', muted)]],
                colWidths=[w],
            )
            sig_placeholder.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#fafafa')),
                ('TOPPADDING',    (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LEFTPADDING',   (0, 0), (-1, -1), 10),
                ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ]))
            story.append(KeepTogether([sig_placeholder]))

        story.append(Spacer(1, 14))

    # ── Grand total page ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph('Grand Total Summary', ParagraphStyle(
        'GT', parent=styles['Normal'],
        fontSize=16, fontName='Helvetica-Bold', textColor=C_HEADER_BG, leading=20,
    )))
    story.append(Spacer(1, 12))

    gt_data = [['', 'Rooms', 'Items', 'Replacement Value']]
    for rs in room_stats:
        r = rs['room']
        gt_data.append([
            f"{r.room_number} {r.room_name}",
            '1',
            str(len(rs['items'])),
            _fmt_usd(rs['rcv']),
        ])
    gt_data.append(['GRAND TOTAL', str(len(rooms)), str(grand_qty),
                    _fmt_usd(grand_rcv)])

    gt_col_w = [w * 0.50, w * 0.14, w * 0.14, w * 0.22]
    gt_tbl = Table(gt_data, colWidths=gt_col_w)
    n = len(gt_data)
    gt_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 8.5),
        ('FONTSIZE',      (0, 1), (-1, -2), 8.5),
        ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, C_ALT]),
        ('BACKGROUND',    (0, n-1), (-1, n-1), C_TOTAL_BG),
        ('TEXTCOLOR',     (0, n-1), (-1, n-1), C_TOTAL_FG),
        ('FONTNAME',      (0, n-1), (-1, n-1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, n-1), (-1, n-1), 9),
        ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
        ('GRID',          (0, 0), (-1, -1), 0.3, C_RULE),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    story.append(gt_tbl)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Report generated {datetime.datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        muted,
    ))

    doc.build(story)
    return buf.getvalue()
