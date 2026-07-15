"""
Build a Photo Evidence PDF alongside the Schedule of Loss.
One section per room: compact item list (with matching item numbers)
followed by an image grid so insurers can verify each replacement claim.

Images are re-fetched from Encircle at render time using the same
matching logic as the PPR AI analyzer.
"""
from __future__ import annotations

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Optional

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

from .ai_analyzer import fetch_all_claim_media, filter_room_images

logger = logging.getLogger(__name__)

# ── Brand colours (mirror pdf_builder.py) ─────────────────────────────────────
C_HEADER_BG = colors.HexColor('#1e40af')
C_HEADER_FG = colors.white
C_ROOM_BG   = colors.HexColor('#059669')
C_ROOM_FG   = colors.white
C_TOTAL_BG  = colors.HexColor('#1e3a5f')
C_TOTAL_FG  = colors.white
C_ALT       = colors.HexColor('#f0fdf4')
C_TEXT      = colors.HexColor('#0f172a')
C_MUTED     = colors.HexColor('#64748b')
C_RULE      = colors.HexColor('#e2e8f0')

# Grid layout
IMG_COLS = 3
IMG_SIZE = 2.1 * inch   # square cell size (image fills this)


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _header_footer(canvas, doc):
    canvas.saveState()
    w, h = letter
    canvas.setStrokeColor(C_RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.5 * inch, h - 0.42 * inch, w - 0.5 * inch, h - 0.42 * inch)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(C_MUTED)
    canvas.drawString(0.5 * inch, 0.3 * inch, 'CPS Photo Evidence Report — Confidential')
    canvas.drawRightString(w - 0.5 * inch, 0.3 * inch, f'Page {doc.page}')
    canvas.restoreState()


def _download_image(url: str) -> Optional[BytesIO]:
    """Download one image URL and return a seekable BytesIO, or None on failure."""
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        buf = BytesIO(resp.content)
        buf.seek(0)
        return buf
    except Exception as exc:
        logger.debug(f"Photo PDF: failed to download {url}: {exc}")
        return None


def _fetch_parallel(urls: list[str], max_workers: int = 8) -> list[Optional[BytesIO]]:
    """Download all URLs in parallel, returning results in original order."""
    results: list[Optional[BytesIO]] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_image, url): idx for idx, url in enumerate(urls)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    return results


def _image_grid(image_bufs: list[Optional[BytesIO]],
                photo_start: int,
                cell_w: float) -> list:
    """
    Return a list of flowables containing images in a 3-column grid.
    Each image occupies one cell; a caption row follows each image row.
    """
    styles = getSampleStyleSheet()
    cap_style = ParagraphStyle(
        'PhotoCap', parent=styles['Normal'],
        fontSize=6.5, textColor=C_MUTED, leading=8, alignment=1,
    )
    empty_style = ParagraphStyle(
        'Empty', parent=styles['Normal'],
        fontSize=6.5, textColor=C_RULE, leading=8, alignment=1,
    )

    def _img_cell(buf, idx):
        num = photo_start + idx
        if buf is None:
            return [Paragraph(f"Photo {num}\n(unavailable)", empty_style)]
        try:
            img = Image(buf, width=IMG_SIZE, height=IMG_SIZE)
            img.hAlign = 'CENTER'
            return [img]
        except Exception:
            return [Paragraph(f"Photo {num}\n(error)", empty_style)]

    def _cap_cell(idx):
        return [Paragraph(f"Photo {photo_start + idx}", cap_style)]

    img_rows = []    # alternating: image row, caption row
    cap_rows = []

    for chunk_start in range(0, len(image_bufs), IMG_COLS):
        chunk = image_bufs[chunk_start:chunk_start + IMG_COLS]
        # Pad to full width
        while len(chunk) < IMG_COLS:
            chunk.append(None)

        img_row = [_img_cell(buf, chunk_start + i) for i, buf in enumerate(chunk)]
        cap_row = [_cap_cell(chunk_start + i) for i in range(IMG_COLS)]
        img_rows.append(img_row)
        cap_rows.append(cap_row)

    if not img_rows:
        return []

    # Interleave image rows and caption rows
    all_rows = []
    row_heights = []
    for img_row, cap_row in zip(img_rows, cap_rows):
        all_rows.append(img_row)
        all_rows.append(cap_row)
        row_heights.append(IMG_SIZE + 4)   # image row
        row_heights.append(10)             # caption row

    tbl = Table(all_rows, colWidths=[cell_w] * IMG_COLS, rowHeights=row_heights)
    tbl.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        # Light grid on image rows only (even rows = images)
        ('BOX',           (0, 0), (-1, -1), 0.3, C_RULE),
    ]))
    return [tbl]


def build_photo_pdf(session, prefetched_media: list[dict] | None = None) -> bytes:
    """
    Build the Photo Evidence PDF for a CPSReportSession.
    Pass prefetched_media (from fetch_all_claim_media) to skip the Encircle
    API call — the Celery task already has it in memory.
    Returns raw PDF bytes.
    """
    buf = BytesIO()
    styles = getSampleStyleSheet()

    h1 = ParagraphStyle('H1', fontSize=20, textColor=C_HEADER_FG, leading=24,
                         fontName='Helvetica-Bold')
    h2 = ParagraphStyle('H2', fontSize=10, textColor=C_HEADER_FG, leading=13,
                         fontName='Helvetica-Bold')
    body = ParagraphStyle('Body', fontSize=8.5, textColor=C_TEXT, leading=12)
    muted_s = ParagraphStyle('Muted', fontSize=7.5, textColor=C_MUTED, leading=10)
    room_hdr_s = ParagraphStyle('RH', fontSize=10, textColor=C_ROOM_FG, leading=13,
                                 fontName='Helvetica-Bold')

    doc = BaseDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.65 * inch, bottomMargin=0.5 * inch,
    )
    usable_w = letter[0] - 1.0 * inch
    cell_w   = usable_w / IMG_COLS

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=_header_footer)])

    story = []

    # ── Resolve Encircle media (reuse prefetched list if provided) ────────────
    if prefetched_media is not None:
        all_media = prefetched_media
    else:
        all_media = []
        if session.encircle_claim_id:
            try:
                all_media = fetch_all_claim_media(session.encircle_claim_id)
            except Exception as exc:
                logger.warning(f"Photo PDF: could not fetch Encircle media: {exc}")

    # ── Pre-compute rooms + global item numbers (same logic as pdf_builder.py) ─
    rooms = list(session.rooms.prefetch_related('items').order_by('order', 'room_number'))
    global_item_num = 1
    room_data = []
    for room in rooms:
        items = list(room.items.order_by('order'))
        first_n = global_item_num
        global_item_num += len(items)
        last_n  = global_item_num - 1
        room_data.append({'room': room, 'items': items, 'first_n': first_n, 'last_n': last_n})

    # ── Cover page ─────────────────────────────────────────────────────────────
    cover = Table(
        [[Paragraph('CPS Photo Evidence Report', h1)],
         [Paragraph('Visual proof of replacement items — matches Schedule of Loss numbering', h2)]],
        colWidths=[usable_w],
    )
    cover.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_HEADER_BG),
        ('TOPPADDING',    (0, 0), (-1, 0), 22),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING',    (0, 1), (-1, 1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 22),
        ('LEFTPADDING',   (0, 0), (-1, -1), 16),
    ]))
    story.append(cover)
    story.append(Spacer(1, 12))

    now = datetime.date.today().strftime('%B %d, %Y')
    claim_id_display = getattr(session.client, 'claimID', '') or session.encircle_claim_id or '—'
    info = Table(
        [['Insured',      session.insured_name or '—',  'Report Date',  now],
         ['Claim #',      session.claim_number or '—',  'Claim ID',     claim_id_display],
         ['Loss Type',    session.loss_type or '—',     'Total Rooms',  str(len(rooms))]],
        colWidths=[usable_w*0.14, usable_w*0.36, usable_w*0.14, usable_w*0.36],
    )
    info.setStyle(TableStyle([
        ('FONTNAME',  (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',  (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), C_MUTED),
        ('TEXTCOLOR', (2, 0), (2, -1), C_MUTED),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.3, C_RULE),
    ]))
    story.append(info)
    story.append(Spacer(1, 10))

    story.append(Paragraph('Contents:', muted_s))
    story.append(Spacer(1, 3))
    for rd in room_data:
        r = rd['room']
        rng = f"#{rd['first_n']}–#{rd['last_n']}" if len(rd['items']) > 1 else f"#{rd['first_n']}"
        story.append(Paragraph(
            f"<b>{r.room_number} {r.room_name}</b> — "
            f"{len(rd['items'])} items ({rng})",
            body,
        ))
    story.append(PageBreak())

    # ── Room sections ──────────────────────────────────────────────────────────
    photo_counter = 1

    for rd in room_data:
        room  = rd['room']
        items = rd['items']
        first_n, last_n = rd['first_n'], rd['last_n']

        # Room banner
        rng = f"Items #{first_n}–#{last_n}" if len(items) > 1 else f"Item #{first_n}"
        rh = Table(
            [[Paragraph(f"{room.room_number}  {room.room_name}", room_hdr_s),
              Paragraph(f"{len(items)} item{'s' if len(items)!=1 else ''}  |  {rng}", room_hdr_s)]],
            colWidths=[usable_w * 0.6, usable_w * 0.4],
        )
        rh.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), C_ROOM_BG),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
        ]))
        story.append(rh)
        story.append(Spacer(1, 5))

        # Compact item table — same item numbers as Schedule of Loss
        item_rows = [['#', 'Description', 'Brand', 'Qty', 'RCV Each', 'RCV Total']]
        for offset, item in enumerate(items):
            rcv_each  = float(item.replacement_value_each or 0)
            rcv_total = rcv_each * (item.qty or 1)
            item_rows.append([
                str(first_n + offset),
                (item.description or '')[:70],
                (item.brand or '')[:22],
                str(item.qty or 1),
                _fmt_usd(rcv_each),
                _fmt_usd(rcv_total),
            ])
        iw = usable_w
        it = Table(item_rows,
                   colWidths=[iw*0.05, iw*0.42, iw*0.18, iw*0.05, iw*0.15, iw*0.15],
                   repeatRows=1)
        it.setStyle(TableStyle([
            ('BACKGROUND',     (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('TEXTCOLOR',      (0, 0), (-1, 0), colors.white),
            ('FONTNAME',       (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',       (0, 0), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, C_ALT]),
            ('ALIGN',          (3, 0), (-1, -1), 'RIGHT'),
            ('TOPPADDING',     (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING',  (0, 0), (-1, -1), 3),
            ('LEFTPADDING',    (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',   (0, 0), (-1, -1), 4),
            ('GRID',           (0, 0), (-1, -1), 0.3, C_RULE),
        ]))
        story.append(it)
        story.append(Spacer(1, 8))

        # Fetch + lay out room images
        urls = filter_room_images(all_media, room.room_number) if all_media else []

        if urls:
            story.append(Paragraph(
                f"Photos: {len(urls)} images used for AI analysis above", muted_s
            ))
            story.append(Spacer(1, 4))
            image_bufs = _fetch_parallel(urls)
            story.extend(_image_grid(image_bufs, photo_counter, cell_w))
            photo_counter += len(urls)
        else:
            story.append(Paragraph(
                "No Encircle images available for this room.", muted_s
            ))

        story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()
