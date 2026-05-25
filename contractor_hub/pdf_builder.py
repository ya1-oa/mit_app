"""
Contractor Hub — GC Estimate PDF Builder
=========================================
Generates a professional Xactimate-format PDF estimate using ReportLab.

Public API:
    generate_gc_estimate_pdf(estimate) -> io.BytesIO
"""

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Table, TableStyle, Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

# ── Colour palette ────────────────────────────────────────────────────────────
PURPLE      = colors.HexColor('#7c3aed')
PURPLE_LIGHT= colors.HexColor('#f3e8ff')
DARK        = colors.HexColor('#0f172a')
MID         = colors.HexColor('#475569')
LIGHT       = colors.HexColor('#94a3b8')
WHITE       = colors.white
ROW_ALT     = colors.HexColor('#f8fafc')
GREEN       = colors.HexColor('#065f46')
GREEN_BG    = colors.HexColor('#d1fae5')


# ── Styles ────────────────────────────────────────────────────────────────────
_SS = getSampleStyleSheet()

def _style(name, base='Normal', **kw):
    s = ParagraphStyle(name, parent=_SS[base], **kw)
    return s

H1       = _style('H1', fontSize=16, fontName='Helvetica-Bold', textColor=WHITE, spaceAfter=4)
H2       = _style('H2', fontSize=11, fontName='Helvetica-Bold', textColor=DARK, spaceAfter=6)
LABEL    = _style('LBL', fontSize=7, fontName='Helvetica-Bold', textColor=LIGHT,
                  spaceBefore=6, spaceAfter=2, leading=9)
BODY     = _style('BODY', fontSize=8, fontName='Helvetica', textColor=DARK, leading=11)
BODY_SM  = _style('BODY_SM', fontSize=7, fontName='Helvetica', textColor=MID, leading=9)
MONO     = _style('MONO', fontSize=8, fontName='Courier', textColor=DARK, leading=10)
MONO_CAT = _style('MONO_CAT', fontSize=8, fontName='Courier-Bold', textColor=PURPLE, leading=10)
TOTAL    = _style('TOTAL', fontSize=9, fontName='Helvetica-Bold', textColor=DARK, leading=12)
GRAND    = _style('GRAND', fontSize=11, fontName='Helvetica-Bold', textColor=PURPLE, leading=14)
FOOTER   = _style('FOOTER', fontSize=7, fontName='Helvetica', textColor=LIGHT,
                  alignment=TA_CENTER, leading=9)


def _fmt(val):
    """Format a Decimal or float as $X,XXX.XX"""
    try:
        return f'${float(val):,.2f}'
    except Exception:
        return '$0.00'


def _header_footer(canvas, doc):
    """Draw page header and footer on every page."""
    canvas.saveState()
    w, h = letter

    # ── Top purple bar ────────────────────────────────────────────────────────
    canvas.setFillColor(PURPLE)
    canvas.rect(0.5 * inch, h - 0.9 * inch, w - inch, 0.55 * inch, fill=1, stroke=0)

    canvas.setFont('Helvetica-Bold', 12)
    canvas.setFillColor(WHITE)
    canvas.drawString(0.65 * inch, h - 0.65 * inch, 'GC ESTIMATE')

    # Page number (right)
    canvas.setFont('Helvetica', 8)
    canvas.drawRightString(w - 0.55 * inch, h - 0.65 * inch, f'Page {doc.page}')

    # ── Footer rule ───────────────────────────────────────────────────────────
    canvas.setStrokeColor(LIGHT)
    canvas.setLineWidth(0.5)
    canvas.line(0.5 * inch, 0.55 * inch, w - 0.5 * inch, 0.55 * inch)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(LIGHT)
    canvas.drawCentredString(w / 2, 0.35 * inch, 'Confidential — Claimet App · Generated for internal use only')

    canvas.restoreState()


def generate_gc_estimate_pdf(estimate) -> io.BytesIO:
    """
    Build a complete GC Estimate PDF and return as BytesIO.

    Args:
        estimate: GCEstimate instance (with prefetched sections + line_items)
    """
    buf = io.BytesIO()

    doc = BaseDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=1.0 * inch,
        bottomMargin=0.75 * inch,
        title=f'GC Estimate — {estimate.estimate_number or str(estimate.id)[:8]}',
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='normal',
    )
    doc.addPageTemplates([PageTemplate(id='main', frames=frame, onPage=_header_footer)])

    story = []
    W = doc.width  # usable width

    # ── Claim info block ─────────────────────────────────────────────────────
    client = estimate.client
    gc     = estimate.gc_contractor

    info_data = [
        [
            Paragraph('INSURED', LABEL),      Paragraph('ADDRESS', LABEL),
            Paragraph('CLAIM #', LABEL),       Paragraph('DATE', LABEL),
        ],
        [
            Paragraph(client.pOwner or '—', BODY),
            Paragraph(
                (client.pAddress or '') + (f', {client.pCityStateZip}' if client.pCityStateZip else ''),
                BODY,
            ),
            Paragraph(client.claimNumber or '—', MONO),
            Paragraph(
                estimate.date_entered.strftime('%b %d, %Y') if estimate.date_entered else '—',
                BODY,
            ),
        ],
        [
            Paragraph('GC CONTRACTOR', LABEL), Paragraph('ESTIMATOR', LABEL),
            Paragraph('PRICE LIST', LABEL),     Paragraph('TYPE', LABEL),
        ],
        [
            Paragraph(gc.name, BODY),
            Paragraph(estimate.estimator.name if estimate.estimator else '—', BODY),
            Paragraph(estimate.price_list or '—', MONO),
            Paragraph(estimate.type_of_estimate or '—', BODY),
        ],
    ]

    info_table = Table(info_data, colWidths=[W * 0.27, W * 0.30, W * 0.22, W * 0.21])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ROW_ALT),
        ('BACKGROUND', (0, 2), (-1, 2), ROW_ALT),
        ('ROWPADDING',  (0, 0), (-1, -1), (6, 4, 6, 4)),
        ('BOX',         (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID',   (0, 0), (-1, -1), 0.3, colors.HexColor('#f1f5f9')),
        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    # ── Estimate number / status banner ──────────────────────────────────────
    est_num = estimate.estimate_number or f'EST-{str(estimate.id)[:8].upper()}'
    banner_data = [[
        Paragraph(f'Estimate: {est_num}', H2),
        Paragraph(estimate.get_status_display().upper(), _style(
            'STATUS', fontSize=8, fontName='Helvetica-Bold',
            textColor=GREEN, alignment=TA_RIGHT,
        )),
    ]]
    banner = Table(banner_data, colWidths=[W * 0.7, W * 0.3])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_LIGHT),
        ('ROWPADDING',  (0, 0), (-1, -1), (10, 8, 10, 8)),
        ('BOX',         (0, 0), (-1, -1), 0.5, PURPLE),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(banner)
    story.append(Spacer(1, 14))

    # ── Column widths for line-item table ────────────────────────────────────
    #   CAT  SEL  Description          Qty   Unit   Remove   Replace  Tax   Total
    COL_W = [
        0.50*inch, 0.80*inch, W - 5.35*inch,
        0.55*inch, 0.45*inch, 0.75*inch, 0.80*inch, 0.30*inch, 0.80*inch
    ]

    # ── Sections ─────────────────────────────────────────────────────────────
    sections = estimate.sections.prefetch_related('line_items', 'subcontractor').order_by('order')

    for section in sections:
        # Section heading row
        sec_label = section.section_label
        sub_name  = section.subcontractor.name if section.subcontractor else f'GC Direct — {gc.name}'
        sec_hdr_data = [[
            Paragraph(f'{section.order}. {sec_label}', _style(
                f'SH{section.pk}', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE,
            )),
            Paragraph(sub_name, _style(
                f'SHR{section.pk}', fontSize=7, fontName='Helvetica', textColor=WHITE,
                alignment=TA_RIGHT,
            )),
        ]]
        sec_hdr = Table(sec_hdr_data, colWidths=[W * 0.65, W * 0.35])
        sec_hdr.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), PURPLE),
            ('ROWPADDING',  (0, 0), (-1, -1), (8, 6, 8, 6)),
            ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(sec_hdr)

        line_items = list(section.line_items.order_by('order'))

        if not line_items:
            no_items = Table(
                [[Paragraph('No line items.', BODY_SM)]],
                colWidths=[W],
            )
            no_items.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), ROW_ALT),
                ('ROWPADDING',  (0, 0), (-1, -1), (8, 8, 8, 8)),
                ('BOX',         (0, 0), (-1, -1), 0.3, colors.HexColor('#e2e8f0')),
            ]))
            story.append(no_items)
        else:
            # Column header row
            th = [
                Paragraph('CAT',     BODY_SM),
                Paragraph('SEL',     BODY_SM),
                Paragraph('Description', BODY_SM),
                Paragraph('Qty',     _style('QTY', fontSize=7, fontName='Helvetica', alignment=TA_RIGHT)),
                Paragraph('Unit',    BODY_SM),
                Paragraph('Remove',  _style('RMV', fontSize=7, fontName='Helvetica', alignment=TA_RIGHT)),
                Paragraph('Replace', _style('RPL', fontSize=7, fontName='Helvetica', alignment=TA_RIGHT)),
                Paragraph('T',       _style('TAX', fontSize=7, fontName='Helvetica', alignment=TA_CENTER)),
                Paragraph('Total',   _style('TOT', fontSize=7, fontName='Helvetica', alignment=TA_RIGHT)),
            ]
            rows = [th]
            ts_cmds = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0, 0), (-1, 0), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ('TOPPADDING',    (0, 0), (-1, 0), 5),
                ('GRID',          (0, 0), (-1, -1), 0.25, colors.HexColor('#f1f5f9')),
                ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ]

            for i, li in enumerate(line_items):
                row_bg = WHITE if i % 2 == 0 else ROW_ALT
                r = [
                    Paragraph(li.cat,         MONO_CAT),
                    Paragraph(li.sel + (' [*]' if li.is_bid_item else ''), MONO),
                    Paragraph(li.description, BODY_SM if li.is_memo else BODY),
                    Paragraph(f'{float(li.quantity):.2f}',   _style(f'Q{i}', fontSize=7, fontName='Courier', alignment=TA_RIGHT)),
                    Paragraph(li.unit,                        BODY_SM),
                    Paragraph(_fmt(li.remove_rate),           _style(f'RM{i}', fontSize=7, fontName='Courier', alignment=TA_RIGHT, textColor=MID)),
                    Paragraph(_fmt(li.replace_rate),          _style(f'RP{i}', fontSize=7, fontName='Courier', alignment=TA_RIGHT)),
                    Paragraph('T' if li.taxable else '',      _style(f'TX{i}', fontSize=7, fontName='Helvetica', alignment=TA_CENTER, textColor=LIGHT)),
                    Paragraph(_fmt(li.line_total),            _style(f'LT{i}', fontSize=7, fontName='Courier-Bold', alignment=TA_RIGHT, textColor=DARK)),
                ]
                rows.append(r)
                data_i = i + 1
                ts_cmds.append(('BACKGROUND', (0, data_i), (-1, data_i), row_bg))
                ts_cmds.append(('TOPPADDING',    (0, data_i), (-1, data_i), 4))
                ts_cmds.append(('BOTTOMPADDING', (0, data_i), (-1, data_i), 4))

            li_table = Table(rows, colWidths=COL_W, repeatRows=1)
            li_table.setStyle(TableStyle(ts_cmds))
            story.append(li_table)

        # Section subtotal row
        sub_total_data = [[
            Paragraph('', BODY),
            Paragraph('', BODY),
            Paragraph('', BODY),
            Paragraph('', BODY),
            Paragraph('', BODY),
            Paragraph('', BODY),
            Paragraph('Section Subtotal:', _style('ST_LBL', fontSize=8, fontName='Helvetica-Bold',
                                                   textColor=MID, alignment=TA_RIGHT)),
            Paragraph('', BODY),
            Paragraph(_fmt(section.section_subtotal),
                      _style('ST_VAL', fontSize=8, fontName='Courier-Bold',
                             textColor=PURPLE, alignment=TA_RIGHT)),
        ]]
        st = Table(sub_total_data, colWidths=COL_W)
        st.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), PURPLE_LIGHT),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        story.append(st)
        story.append(Spacer(1, 10))

    # ── Grand Totals block ────────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width=W, thickness=1.5, color=PURPLE, spaceAfter=8))

    totals = [
        ['Line Item Total',              _fmt(estimate.line_item_total)],
        [f'Overhead ({estimate.overhead_pct}%)', _fmt(estimate.overhead_amount)],
        [f'Profit ({estimate.profit_pct}%)',   _fmt(estimate.profit_amount)],
        [f'Tax ({estimate.tax_rate}%)',          _fmt(estimate.tax_amount)],
        ['GRAND TOTAL',                  _fmt(estimate.grand_total)],
    ]

    tot_rows = []
    for i, (label, val) in enumerate(totals):
        is_grand = (i == len(totals) - 1)
        st = GRAND if is_grand else TOTAL
        sv = _style(f'TV{i}', fontSize=11 if is_grand else 9,
                    fontName='Courier-Bold' if is_grand else 'Courier',
                    alignment=TA_RIGHT,
                    textColor=PURPLE if is_grand else DARK)
        tot_rows.append([
            Paragraph(label, _style(f'TL{i}', fontSize=11 if is_grand else 9,
                                    fontName='Helvetica-Bold' if is_grand else 'Helvetica',
                                    textColor=PURPLE if is_grand else MID)),
            Paragraph(val, sv),
        ])

    tot_table = Table(tot_rows, colWidths=[W * 0.75, W * 0.25])
    tot_cmds = [
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW',     (0, -2), (-1, -2), 1.5, PURPLE),
        ('BACKGROUND',    (0, -1), (-1, -1), PURPLE_LIGHT),
        ('BOX',           (0, -1), (-1, -1), 1, PURPLE),
    ]
    tot_table.setStyle(TableStyle(tot_cmds))
    story.append(tot_table)
    story.append(Spacer(1, 16))

    # ── Notes ─────────────────────────────────────────────────────────────────
    if estimate.notes:
        story.append(Paragraph('Notes', LABEL))
        story.append(Paragraph(estimate.notes, BODY))
        story.append(Spacer(1, 8))

    doc.build(story)
    buf.seek(0)
    return buf
