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


def _load_image_bytes(url: str) -> Optional[bytes]:
    """Fetch raw image bytes.

    Storage keys are read straight from default_storage (no presigned-URL
    HTTP round-trip, which fails intermittently in production). Real
    http(s) URLs are downloaded normally.
    """
    if url.startswith(('http://', 'https://')):
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.warning(f"Photo PDF: download failed for {url}: {exc}")
            return None
    try:
        from django.core.files.storage import default_storage
        with default_storage.open(url, 'rb') as fh:
            return fh.read()
    except Exception as exc:
        logger.warning(f"Photo PDF: storage read failed for {url}: {exc}")
        return None


def _download_image(url: str) -> Optional[BytesIO]:
    """Load one image (storage key or URL) and return a JPEG BytesIO, or None on failure.

    Converts through Pillow so any format Encircle serves (WEBP, HEIC, etc.)
    is normalised to JPEG before ReportLab touches it.
    """
    raw = _load_image_bytes(url)
    if raw is None:
        return None
    try:
        from PIL import Image as PilImage
        pil = PilImage.open(BytesIO(raw))
        if pil.mode not in ('RGB', 'L'):
            pil = pil.convert('RGB')
        out = BytesIO()
        pil.save(out, format='JPEG', quality=85)
        out.seek(0)
        return out
    except Exception as exc:
        logger.warning(f"Photo PDF: image conversion failed for {url}: {exc}")
        return None


def _fetch_parallel(urls: list[str], max_workers: int = 8) -> list[Optional[BytesIO]]:
    """Download all URLs in parallel, returning results in original order."""
    results: list[Optional[BytesIO]] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_image, url): idx for idx, url in enumerate(urls)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    return results


def _render_images(image_bufs: list, size: float, per_row: int) -> list:
    """Render loaded images in rows of up to `per_row`. Failed/missing images
    are skipped entirely — no captions, no placeholder boxes, no padding.
    One photo renders as one photo."""
    imgs = []
    for buf in image_bufs:
        if buf is None:
            continue
        try:
            img = Image(buf, width=size, height=size)
            imgs.append(img)
        except Exception as exc:
            logger.warning(f"Photo PDF: could not render image: {exc}")

    if not imgs:
        return []

    flow = []
    for start in range(0, len(imgs), per_row):
        chunk = imgs[start:start + per_row]
        tbl = Table([chunk], colWidths=[size + 8] * len(chunk),
                    rowHeights=[size + 6])
        tbl.setStyle(TableStyle([
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ]))
        tbl.hAlign = 'LEFT'
        flow.append(tbl)
    return flow


def _image_grid(image_bufs: list[Optional[BytesIO]],
                photo_start: int,
                cell_w: float) -> list:
    """Room-level image grid (legacy fallback for reports without attribution)."""
    return _render_images(image_bufs, IMG_SIZE, IMG_COLS)


def _item_image_strip(image_bufs: list, cell_w: float) -> list:
    """Image strip beneath a single line item — real photos only."""
    return _render_images(image_bufs, ITEM_IMG_SIZE, ITEM_IMG_COLS)


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

    # ── Header block — identical format & data source to the PPR Box Count ────
    _blue_dark = colors.HexColor('#1e3a5f')
    _border    = colors.HexColor('#aaaaaa')

    hdr_label = ParagraphStyle('HdrLabel', fontName='Helvetica-Bold', fontSize=8,
                               textColor=_blue_dark, spaceAfter=1)
    hdr_val   = ParagraphStyle('HdrVal', fontName='Helvetica', fontSize=9,
                               textColor=C_TEXT, spaceAfter=5)
    hdr_addr  = ParagraphStyle('HdrAddr', fontName='Helvetica-Bold', fontSize=10,
                               textColor=C_TEXT)

    client       = session.client
    claim_num    = (getattr(client, 'claimNumber',   '') or '') or '—'
    insured      = (getattr(client, 'pOwner',        '') or '') or '—'
    street       = getattr(client, 'pAddress',       '') or ''
    city_st_zip  = getattr(client, 'pCityStateZip',  '') or ''
    loss_date    = getattr(session, 'loss_date', None) or getattr(client, 'loss_date', None)
    loss_date_str = loss_date.strftime('%b %d, %Y') if loss_date else '—'

    left_content = [
        Paragraph('Report Date:', hdr_label),
        Paragraph(now,            hdr_val),
        Paragraph('Date of Loss:', hdr_label),
        Paragraph(loss_date_str,   hdr_val),
        Paragraph('Total Rooms:', hdr_label),
        Paragraph(str(len(room_data)), hdr_val),
    ]
    right_content = [
        Paragraph('Claim Number:', hdr_label),
        Paragraph(claim_num,       hdr_val),
        Paragraph('Insured:', hdr_label),
        Paragraph(insured,    hdr_val),
        Paragraph('Property Address:', hdr_label),
        Paragraph(street or '—',   hdr_addr),
    ]
    if city_st_zip:
        right_content.append(Paragraph(city_st_zip, hdr_addr))

    def _hdr_cell(flowables, cell_w):
        t = Table([[f] for f in flowables], colWidths=[cell_w])
        t.setStyle(TableStyle([
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ]))
        return t

    _pad = 10
    _lw  = usable_w * 0.42
    _rw  = usable_w * 0.58
    info = Table(
        [[_hdr_cell(left_content,  _lw - 2 * _pad),
          _hdr_cell(right_content, _rw - 2 * _pad)]],
        colWidths=[_lw, _rw],
    )
    info.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.8, _border),
        ('INNERGRID',     (0, 0), (-1, -1), 0.8, _border),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), _pad),
        ('RIGHTPADDING',  (0, 0), (-1, -1), _pad),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
    ]))
    story.append(info)
    story.append(Spacer(1, 10))

    # Photo disclaimer — explains why item count can exceed photo count
    note_style = ParagraphStyle(
        'PhotoNote', fontSize=8, textColor=C_TEXT, leading=11,
        backColor=colors.HexColor('#fffbeb'),
        borderColor=colors.HexColor('#fde68a'), borderWidth=0.5,
        borderPadding=6,
    )
    story.append(Paragraph(
        '<b>Photo Note:</b> Some photos may contain more than one non-salvageable '
        'item. As a result, the total item count in the PPR Schedule of Loss may '
        'exceed the total number of photos in this photo evidence report — this is '
        'expected and does not indicate a discrepancy.',
        note_style,
    ))
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
                strip = _item_image_strip(item_bufs, item_strip_cell_w)
                if strip:
                    story.extend(strip)
                else:
                    story.append(Paragraph(
                        '  Photos could not be loaded for this item.',
                        styles['muted'],
                    ))
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
