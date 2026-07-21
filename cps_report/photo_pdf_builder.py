"""
Build a Photo Evidence PDF alongside the Schedule of Loss.
One section per room: compact item list (with matching item numbers)
followed by an image grid so insurers can verify each replacement claim.

Images are downloaded room-by-room to avoid memory exhaustion on large claims.
Each room is rendered as a separate sub-PDF then merged with pypdf so no more
than one room's image data is in Python memory at any time.
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

# Room-level image grid (legacy / fallback for reports without per-item attribution)
IMG_COLS = 3
IMG_SIZE = 2.1 * inch

# Per-item image strip
ITEM_IMG_COLS = 3
ITEM_IMG_SIZE = 1.9 * inch


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _make_header_footer(page_offset_ref: list):
    """Return an onPage callback that uses a shared offset for global page numbers."""
    def _hf(canvas, doc):
        canvas.saveState()
        w, h = letter
        canvas.setStrokeColor(C_RULE)
        canvas.setLineWidth(0.5)
        canvas.line(0.5 * inch, h - 0.42 * inch, w - 0.5 * inch, h - 0.42 * inch)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(0.5 * inch, 0.3 * inch, 'PPR Photo Evidence Report  |  All Phase Consulting, LLC')
        canvas.drawRightString(
            w - 0.5 * inch, 0.3 * inch,
            f'Page {page_offset_ref[0] + doc.page}',
        )
        canvas.restoreState()
    return _hf


def _make_doc(buf, page_offset_ref: list):
    doc = BaseDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.65 * inch, bottomMargin=0.5 * inch,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    doc.addPageTemplates([
        PageTemplate(id='main', frames=[frame],
                     onPage=_make_header_footer(page_offset_ref)),
    ])
    return doc


def _make_styles() -> dict:
    styles = getSampleStyleSheet()
    return {
        'h1':       ParagraphStyle('H1', fontSize=20, textColor=C_HEADER_FG, leading=24,
                                   fontName='Helvetica-Bold'),
        'h2':       ParagraphStyle('H2', fontSize=10, textColor=C_HEADER_FG, leading=13,
                                   fontName='Helvetica-Bold'),
        'body':     ParagraphStyle('Body', fontSize=8.5, textColor=C_TEXT, leading=12),
        'muted':    ParagraphStyle('Muted', fontSize=7.5, textColor=C_MUTED, leading=10),
        'room_hdr': ParagraphStyle('RH', fontSize=10, textColor=C_ROOM_FG, leading=13,
                                   fontName='Helvetica-Bold'),
    }


def _resolve_storage_url(key: str) -> str:
    """Convert a storage key to a downloadable URL; pass http(s) URLs through unchanged."""
    if key.startswith(('http://', 'https://')):
        return key
    try:
        from django.core.files.storage import default_storage
        return default_storage.url(key)
    except Exception:
        return key


def _download_image(url: str) -> Optional[BytesIO]:
    """Download one image URL (or storage key) and return a JPEG BytesIO, or None on failure.

    Converts through Pillow so any format Encircle serves (WEBP, HEIC, etc.)
    is normalised to JPEG before ReportLab touches it.
    """
    resolved = _resolve_storage_url(url)
    try:
        resp = requests.get(resolved, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Photo PDF: download failed for {resolved}: {exc}")
        return None

    try:
        from PIL import Image as PilImage
        pil = PilImage.open(BytesIO(resp.content))
        if pil.mode not in ('RGB', 'L'):
            pil = pil.convert('RGB')
        out = BytesIO()
        pil.save(out, format='JPEG', quality=85)
        out.seek(0)
        return out
    except Exception as exc:
        logger.warning(f"Photo PDF: image conversion failed for {resolved}: {exc}")
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
    """Return flowables for a 3-column image grid (legacy fallback)."""
    styles = getSampleStyleSheet()
    cap_style = ParagraphStyle(
        'PhotoCap', parent=styles['Normal'],
        fontSize=6.5, textColor=C_MUTED, leading=8, alignment=1,
    )
    def _img_cell(buf, idx):
        if buf is None:
            ph = Table([['']], colWidths=[IMG_SIZE], rowHeights=[IMG_SIZE])
            ph.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
                ('BOX',        (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ]))
            return [ph]
        try:
            img = Image(buf, width=IMG_SIZE, height=IMG_SIZE)
            img.hAlign = 'CENTER'
            return [img]
        except Exception as _exc:
            logger.warning(f"Photo PDF: could not render image: {_exc}")
            ph = Table([['']], colWidths=[IMG_SIZE], rowHeights=[IMG_SIZE])
            ph.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
                ('BOX',        (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ]))
            return [ph]

    img_rows, cap_rows = [], []
    for chunk_start in range(0, len(image_bufs), IMG_COLS):
        chunk = list(image_bufs[chunk_start:chunk_start + IMG_COLS])
        while len(chunk) < IMG_COLS:
            chunk.append(None)
        img_rows.append([_img_cell(buf, chunk_start + i) for i, buf in enumerate(chunk)])
        cap_rows.append([
            [Paragraph(f"Photo {photo_start + chunk_start + i}", cap_style)]
            for i in range(IMG_COLS)
        ])

    if not img_rows:
        return []

    all_rows, row_heights = [], []
    for img_row, cap_row in zip(img_rows, cap_rows):
        all_rows.append(img_row)
        all_rows.append(cap_row)
        row_heights.append(IMG_SIZE + 4)
        row_heights.append(10)

    tbl = Table(all_rows, colWidths=[cell_w] * IMG_COLS, rowHeights=row_heights)
    tbl.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('BOX',           (0, 0), (-1, -1), 0.3, C_RULE),
    ]))
    return [tbl]


def _item_image_strip(image_bufs: list, cell_w: float) -> list:
    """Return flowables for the image strip shown beneath a single line item."""
    styles = getSampleStyleSheet()
    cap_style = ParagraphStyle(
        'ItemCap', parent=styles['Normal'],
        fontSize=6, textColor=C_MUTED, leading=7, alignment=1,
    )

    def _img_cell(buf, num):
        if buf is None:
            ph = Table([['']], colWidths=[ITEM_IMG_SIZE], rowHeights=[ITEM_IMG_SIZE])
            ph.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
                ('BOX',        (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ]))
            return [ph]
        try:
            img = Image(buf, width=ITEM_IMG_SIZE, height=ITEM_IMG_SIZE)
            img.hAlign = 'CENTER'
            return [img]
        except Exception as _exc:
            logger.warning(f"Photo PDF: could not render image: {_exc}")
            ph = Table([['']], colWidths=[ITEM_IMG_SIZE], rowHeights=[ITEM_IMG_SIZE])
            ph.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
                ('BOX',        (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ]))
            return [ph]

    padded = list(image_bufs)
    while len(padded) % ITEM_IMG_COLS != 0:
        padded.append(None)

    all_rows, row_heights = [], []
    for row_start in range(0, len(padded), ITEM_IMG_COLS):
        chunk   = padded[row_start:row_start + ITEM_IMG_COLS]
        img_row = [_img_cell(buf, row_start + j + 1) for j, buf in enumerate(chunk)]
        cap_row = [[Paragraph(f"Photo {row_start + j + 1}", cap_style)] for j in range(ITEM_IMG_COLS)]
        all_rows.append(img_row)
        all_rows.append(cap_row)
        row_heights.append(ITEM_IMG_SIZE + 4)
        row_heights.append(9)

    if not all_rows:
        return []

    tbl = Table(all_rows, colWidths=[cell_w] * ITEM_IMG_COLS, rowHeights=row_heights)
    tbl.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 3),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
        ('BOX',           (0, 0), (-1, -1), 0.3, C_RULE),
    ]))
    return [tbl]


# ── Sub-PDF builders ───────────────────────────────────────────────────────────

def _build_cover_pdf(session, room_data: list, styles: dict,
                     page_offset_ref: list) -> bytes:
    """Build the cover page + table of contents as a stand-alone PDF."""
    buf = BytesIO()
    doc = _make_doc(buf, page_offset_ref)
    usable_w = letter[0] - 1.0 * inch
    story = []

    now = datetime.date.today().strftime('%B %d, %Y')

    cover = Table(
        [[Paragraph('NON SALVAGEABLE / PPR Photo Evidence Report', styles['h1'])],
         [Paragraph('All Phase Consulting, LLC', styles['h2'])],
         [Paragraph(
             'Personal property replacement items with supporting photo documentation',
             styles['h2'],
         )]],
        colWidths=[usable_w],
    )
    cover.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_HEADER_BG),
        ('TOPPADDING',    (0, 0), (-1, 0), 20),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING',    (0, 1), (-1, 1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 2),
        ('TOPPADDING',    (0, 2), (-1, 2), 2),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 20),
        ('LEFTPADDING',   (0, 0), (-1, -1), 16),
    ]))
    story.append(cover)
    story.append(Spacer(1, 12))

    _addr = ', '.join(filter(None, [
        getattr(session.client, 'pAddress', '') or '',
        getattr(session.client, 'pCityStateZip', '') or '',
    ]))
    info = Table(
        [['Insured',   session.insured_name or '—',  'Report Date', now],
         ['Claim #',   session.claim_number or '—',  'Address',     _addr or '—'],
         ['Loss Type', session.loss_type or '—',     'Total Rooms', str(len(room_data))]],
        colWidths=[usable_w*0.14, usable_w*0.36, usable_w*0.14, usable_w*0.36],
    )
    info.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',      (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR',     (0, 0), (0, -1), C_MUTED),
        ('TEXTCOLOR',     (2, 0), (2, -1), C_MUTED),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.3, C_RULE),
    ]))
    story.append(info)
    story.append(Spacer(1, 10))

    story.append(Paragraph('Contents:', styles['muted']))
    story.append(Spacer(1, 3))
    for rd in room_data:
        r = rd['room']
        rng = (f"#{rd['first_n']}–#{rd['last_n']}"
               if len(rd['items']) > 1 else f"#{rd['first_n']}")
        story.append(Paragraph(
            f"<b>{r.room_number} {r.room_name}</b> — "
            f"{len(rd['items'])} items ({rng})",
            styles['body'],
        ))
    story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


def _build_room_pdf(rd: dict, styles: dict, page_offset_ref: list) -> bytes:
    """
    Build one room's section as a stand-alone PDF.
    Downloads only this room's images; frees them before returning.
    """
    buf = BytesIO()
    doc = _make_doc(buf, page_offset_ref)
    usable_w = letter[0] - 1.0 * inch
    cell_w = usable_w / IMG_COLS
    item_strip_cell_w = usable_w / ITEM_IMG_COLS

    col_widths = [
        usable_w*0.05, usable_w*0.42, usable_w*0.18,
        usable_w*0.05, usable_w*0.15, usable_w*0.15,
    ]
    hdr_style = TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 7),
        ('ALIGN',         (3, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('GRID',          (0, 0), (-1, -1), 0.3, C_RULE),
    ])

    story = []
    room    = rd['room']
    items   = rd['items']
    first_n = rd['first_n']
    last_n  = rd['last_n']

    has_attribution = any(item.source_image_urls for item in items)

    # Room banner
    rng = f"Items #{first_n}–#{last_n}" if len(items) > 1 else f"Item #{first_n}"
    rh = Table(
        [[Paragraph(f"{room.room_number}  {room.room_name}", styles['room_hdr']),
          Paragraph(
              f"{len(items)} item{'s' if len(items) != 1 else ''}  |  {rng}",
              styles['room_hdr'],
          )]],
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

    hdr_tbl = Table(
        [['#', 'Description', 'Brand', 'Qty', 'RCV Each', 'RCV Total']],
        colWidths=col_widths,
    )
    hdr_tbl.setStyle(hdr_style)
    story.append(hdr_tbl)

    # Collect ordered URLs for this room only
    url_set: set[str] = set()
    ordered_urls: list[str] = []
    if has_attribution:
        for item in items:
            for u in (item.source_image_urls or []):
                if u not in url_set:
                    ordered_urls.append(u)
                    url_set.add(u)
    else:
        for u in rd['urls']:
            if u not in url_set:
                ordered_urls.append(u)
                url_set.add(u)

    # Download this room's images (only these, not all rooms)
    url_to_buf: dict = {}
    if ordered_urls:
        logger.info(
            f"Photo PDF: room {room.room_number} — downloading {len(ordered_urls)} images"
        )
        bufs = _fetch_parallel(ordered_urls)
        url_to_buf = dict(zip(ordered_urls, bufs))

    # Per-item rows
    room_rcv_total = 0.0
    for offset, item in enumerate(items):
        rcv_each  = float(item.replacement_value_each or 0)
        rcv_total = rcv_each * (item.qty or 1)
        room_rcv_total += rcv_total
        item_num = first_n + offset

        row_fill = C_ALT if offset % 2 == 1 else colors.white
        item_row_tbl = Table(
            [[str(item_num),
              Paragraph((item.description or '')[:80], styles['body']),
              Paragraph((item.brand or '—')[:25], styles['muted']),
              str(item.qty or 1),
              _fmt_usd(rcv_each),
              _fmt_usd(rcv_total)]],
            colWidths=col_widths,
        )
        item_row_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), row_fill),
            ('FONTSIZE',      (0, 0), (-1, -1), 7.5),
            ('ALIGN',         (3, 0), (-1, -1), 'RIGHT'),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
            ('GRID',          (0, 0), (-1, -1), 0.3, C_RULE),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(item_row_tbl)

        if has_attribution:
            item_urls = list(item.source_image_urls or [])
            if item_urls:
                item_bufs = [url_to_buf.get(u) for u in item_urls]
                story.extend(_item_image_strip(item_bufs, item_strip_cell_w))
            else:
                story.append(Paragraph(
                    '  No photos attributed for this item.',
                    styles['muted'],
                ))
        story.append(Spacer(1, 3))

    # Room total row
    total_tbl = Table(
        [['', '', '', '', 'ROOM TOTAL', _fmt_usd(room_rcv_total)]],
        colWidths=col_widths,
    )
    total_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_TOTAL_BG),
        ('TEXTCOLOR',     (0, 0), (-1, -1), C_TOTAL_FG),
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 7.5),
        ('ALIGN',         (4, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    story.append(total_tbl)

    # Fallback for old reports without per-item attribution: show room image grid
    if not has_attribution:
        if ordered_urls:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Note: This report pre-dates per-item attribution. "
                f"Showing all {len(ordered_urls)} room images below.",
                styles['muted'],
            ))
            story.append(Spacer(1, 4))
            all_bufs = [url_to_buf.get(u) for u in ordered_urls]
            story.extend(_image_grid(all_bufs, 1, cell_w))
        else:
            story.append(
                Paragraph("No Encircle images available for this room.", styles['muted'])
            )

    story.append(PageBreak())
    doc.build(story)

    # Explicitly free image buffers before returning
    url_to_buf.clear()
    return buf.getvalue()


# ── Public API ─────────────────────────────────────────────────────────────────

def build_photo_pdf(session, prefetched_media: list[dict] | None = None) -> bytes:
    """
    Build the Photo Evidence PDF for a CPSReportSession.

    Processes rooms one at a time: each room's images are downloaded,
    rendered into a small sub-PDF, then the BytesIO buffers are freed
    before the next room starts.  Peak memory = one room's images, not
    all rooms combined.

    Pass prefetched_media to skip the Encircle API call (only needed for
    rooms that pre-date the analyzed_image_urls migration).
    """
    from pypdf import PdfReader, PdfWriter

    # Resolve Encircle media (only used as fallback for un-analyzed rooms)
    if prefetched_media is not None:
        all_media = prefetched_media
    else:
        all_media = []
        if session.encircle_claim_id:
            try:
                all_media = fetch_all_claim_media(session.encircle_claim_id)
            except Exception as exc:
                logger.warning(f"Photo PDF: could not fetch Encircle media: {exc}")

    # Pre-compute room metadata — no image downloads yet
    rooms = list(
        session.rooms.prefetch_related('items').order_by('order', 'room_number')
    )
    global_item_num = 1
    room_data = []
    for room in rooms:
        items = list(room.items.filter(structural=False).order_by('order'))
        first_n = global_item_num
        global_item_num += len(items)
        last_n = global_item_num - 1

        if room.analyzed_image_urls:
            room_urls = room.analyzed_image_urls
            url_source = 'stored'
        elif getattr(room, 'status', None) == 'complete':
            # Analyzed but Encircle had no images for this room — skip fallback
            room_urls = []
            url_source = 'none_found'
        else:
            room_urls = filter_room_images(all_media, room.room_number) if all_media else []
            url_source = 'filtered'

        logger.info(
            f"Photo PDF: room {room.room_number} {room.room_name} — "
            f"{len(items)} items, {len(room_urls)} urls ({url_source})"
        )
        room_data.append({
            'room':    room,
            'items':   items,
            'first_n': first_n,
            'last_n':  last_n,
            'urls':    room_urls,
            'url_source': url_source,
        })

    styles = _make_styles()
    page_offset_ref = [0]   # mutable so closures can read the running total
    writer = PdfWriter()

    # Cover page (no images — builds instantly)
    logger.info(f"Photo PDF: building cover for session {session.id} ({len(rooms)} rooms)")
    cover_bytes = _build_cover_pdf(session, room_data, styles, page_offset_ref)
    cover_reader = PdfReader(BytesIO(cover_bytes))
    page_offset_ref[0] += len(cover_reader.pages)
    for page in cover_reader.pages:
        writer.add_page(page)
    del cover_bytes, cover_reader

    # Process each room independently — at most one room's images in memory at a time
    for i, rd in enumerate(room_data):
        room = rd['room']
        logger.info(
            f"Photo PDF: room {i + 1}/{len(room_data)}: "
            f"{room.room_number} {room.room_name}"
        )
        room_bytes = _build_room_pdf(rd, styles, page_offset_ref)
        room_reader = PdfReader(BytesIO(room_bytes))
        page_offset_ref[0] += len(room_reader.pages)
        for page in room_reader.pages:
            writer.add_page(page)
        del room_bytes, room_reader   # free before next room

    total_pages = page_offset_ref[0]
    logger.info(
        f"Photo PDF: merging complete — {total_pages} pages for session {session.id}"
    )
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
