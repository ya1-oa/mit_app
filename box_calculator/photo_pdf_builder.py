"""
Build a Photo Evidence PDF for a BoxCalcCPSSession (PPR box count report).

One section per room: box count summary table followed by a photo grid so
insurers can verify the estimated box quantities against the actual packout
contents.

Uses the same progressive sub-PDF / pypdf merge approach as
cps_report/photo_pdf_builder.py so only one room's images are in memory at
a time.
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

logger = logging.getLogger(__name__)

# Brand colours (mirror cps_report/photo_pdf_builder.py)
C_HEADER_BG = colors.HexColor('#1e40af')
C_HEADER_FG = colors.white
C_ROOM_BG   = colors.HexColor('#1e3a5f')
C_ROOM_FG   = colors.white
C_TOTAL_BG  = colors.HexColor('#0d6efd')
C_TOTAL_FG  = colors.white
C_ALT       = colors.HexColor('#f0f7ff')
C_TEXT      = colors.HexColor('#0f172a')
C_MUTED     = colors.HexColor('#64748b')
C_RULE      = colors.HexColor('#e2e8f0')

IMG_COLS = 3
IMG_SIZE = 2.1 * inch


def _fmt_int(v) -> str:
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return '0'


def _make_header_footer(page_offset_ref: list):
    def _hf(canvas, doc):
        canvas.saveState()
        w, h = letter
        canvas.setStrokeColor(C_RULE)
        canvas.setLineWidth(0.5)
        canvas.line(0.5 * inch, h - 0.42 * inch, w - 0.5 * inch, h - 0.42 * inch)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(0.5 * inch, 0.3 * inch, 'CPS Photo Report — Confidential')
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
        'room_hdr': ParagraphStyle('RH', fontSize=11, textColor=C_ROOM_FG, leading=14,
                                   fontName='Helvetica-Bold'),
        'tbl_hdr':  ParagraphStyle('TH', fontSize=7, textColor=colors.white, leading=9,
                                   fontName='Helvetica-Bold', alignment=1),
        'tbl_val':  ParagraphStyle('TV', fontSize=9, textColor=C_TEXT, leading=11,
                                   fontName='Helvetica-Bold', alignment=1),
    }


def _download_image(url: str) -> Optional[BytesIO]:
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        raw = BytesIO(resp.content)
        # Normalise to JPEG/PNG via Pillow so ReportLab handles GIF, WebP,
        # palette-mode images, etc. without crashing.
        try:
            from PIL import Image as PilImage
            raw.seek(0)
            pil_img = PilImage.open(raw)
            pil_img.load()
            if pil_img.mode == 'RGBA':
                out = BytesIO()
                pil_img.save(out, format='PNG')
                out.seek(0)
                return out
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            out = BytesIO()
            pil_img.save(out, format='JPEG', quality=85)
            out.seek(0)
            return out
        except Exception:
            raw.seek(0)
            return raw
    except Exception as exc:
        logger.debug(f"CPS Photo PDF: failed to download {url}: {exc}")
        return None


def _fetch_parallel(urls: list[str], max_workers: int = 8) -> list[Optional[BytesIO]]:
    results: list[Optional[BytesIO]] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_image, url): idx for idx, url in enumerate(urls)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    return results


def _image_grid(image_bufs: list[Optional[BytesIO]], cell_w: float) -> list:
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
        num = idx + 1
        if buf is None:
            return [Paragraph(f"Photo {num}\n(unavailable)", empty_style)]
        try:
            img = Image(buf, width=IMG_SIZE, height=IMG_SIZE)
            img.hAlign = 'CENTER'
            return [img]
        except Exception:
            return [Paragraph(f"Photo {num}\n(error)", empty_style)]

    img_rows, cap_rows = [], []
    for chunk_start in range(0, len(image_bufs), IMG_COLS):
        chunk = list(image_bufs[chunk_start:chunk_start + IMG_COLS])
        while len(chunk) < IMG_COLS:
            chunk.append(None)
        img_rows.append([_img_cell(buf, chunk_start + i) for i, buf in enumerate(chunk)])
        cap_rows.append([
            [Paragraph(f"Photo {chunk_start + i + 1}", cap_style)]
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


def _build_cover_pdf(session, room_data: list, styles: dict,
                     page_offset_ref: list) -> bytes:
    """Build the cover page + table of contents."""
    from .cps_analyzer import CPS_COLUMN_LABELS
    buf = BytesIO()
    doc = _make_doc(buf, page_offset_ref)
    usable_w = letter[0] - 1.0 * inch
    story = []

    now = datetime.date.today().strftime('%B %d, %Y')

    cover = Table(
        [[Paragraph('CPS Photo Report', styles['h1'])],
         [Paragraph(
             'Visual proof of packout room contents — supports CPS box count estimates',
             styles['h2'],
         )]],
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

    info = Table(
        [['Insured',       session.client.pOwner or '—',    'Report Date', now],
         ['Claim #',       session.client.claimNumber or '—', 'Total Rooms',
          str(len([rd for rd in room_data if rd['status'] == 'complete']))],
         ['Claim ID',      session.client.encircle_claim_id or '—',
          'Total Boxes',   str(session.grand_total)]],
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
        imgs = len(rd['urls'])
        photo_note = f"{imgs} photo{'s' if imgs != 1 else ''}" if imgs else 'no photos'
        story.append(Paragraph(
            f"<b>{rd['room_name']}</b> — {rd['total']} boxes ({photo_note})",
            styles['body'],
        ))
    story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


def _build_room_pdf(rd: dict, styles: dict, page_offset_ref: list) -> bytes:
    """Build one room's section as a stand-alone PDF — download only this room's images."""
    from .cps_analyzer import CPS_COLUMNS, CPS_COLUMN_LABELS
    buf = BytesIO()
    doc = _make_doc(buf, page_offset_ref)
    usable_w = letter[0] - 1.0 * inch
    cell_w = usable_w / IMG_COLS

    story = []
    room_name = rd['room_name']
    total     = rd['total']
    urls      = rd['urls']

    # Room banner
    rh = Table(
        [[Paragraph(room_name, styles['room_hdr']),
          Paragraph(f"Total: {total} boxes", styles['room_hdr'])]],
        colWidths=[usable_w * 0.7, usable_w * 0.3],
    )
    rh.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_ROOM_BG),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
    ]))
    story.append(rh)
    story.append(Spacer(1, 6))

    # Box count summary table — split 12 columns into 2 rows of 6 to fit portrait
    cols_a = CPS_COLUMNS[:6]
    cols_b = CPS_COLUMNS[6:]

    col_w = usable_w / 6

    def _count_table(cols):
        hdr = [Paragraph(CPS_COLUMN_LABELS[c], styles['tbl_hdr']) for c in cols]
        vals = [Paragraph(_fmt_int(rd['counts'].get(c, 0)), styles['tbl_val']) for c in cols]
        t = Table([hdr, vals], colWidths=[col_w] * len(cols))
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('BACKGROUND',    (0, 1), (-1, 1), C_ALT),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('FONTSIZE',      (0, 0), (-1, -1), 7.5),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('GRID',          (0, 0), (-1, -1), 0.3, C_RULE),
        ]))
        return t

    story.append(_count_table(cols_a))
    story.append(Spacer(1, 2))
    story.append(_count_table(cols_b))
    story.append(Spacer(1, 8))

    # Download and render photos
    if urls:
        logger.info(f"PPR Photo PDF: room {room_name!r} — downloading {len(urls)} images")
        bufs = _fetch_parallel(urls)
        story.extend(_image_grid(bufs, cell_w))
        # Explicitly free before returning
        bufs.clear()
    else:
        story.append(Paragraph("No Encircle photos available for this room.", styles['muted']))

    story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()


# ── Public API ─────────────────────────────────────────────────────────────────

def build_box_photo_pdf(session) -> bytes:
    """
    Build the Photo Evidence PDF for a BoxCalcCPSSession.

    Processes rooms one at a time using the same progressive sub-PDF / pypdf
    merge approach as cps_report/photo_pdf_builder.py. Peak memory = one
    room's images, not all rooms combined.

    If a room's image_urls are empty (uploaded via file, not Encircle),
    attempts to re-fetch from Encircle using the session's claim ID.
    """
    from pypdf import PdfReader, PdfWriter
    from .cps_analyzer import CPS_COLUMNS

    # Try to fetch Encircle media for fallback rooms (those without stored URLs)
    encircle_media: list[dict] = []
    if session.client.encircle_claim_id:
        try:
            from docsAppR.encircle_client import EncircleAPIClient
            api = EncircleAPIClient()
            encircle_media = api.get_all_claim_media(session.client.encircle_claim_id)
            logger.info(
                f"PPR Photo PDF: fetched {len(encircle_media)} Encircle media items "
                f"for claim {session.client.encircle_claim_id}"
            )
        except Exception as exc:
            logger.warning(f"PPR Photo PDF: could not fetch Encircle media: {exc}")

    # Pre-compute room data
    rooms = list(
        session.rooms.exclude(room_name__startswith='[OVERVIEW]')
                     .order_by('order', 'room_name')
    )
    room_data = []
    for room in rooms:
        urls = list(room.image_urls or [])
        if not urls and encircle_media:
            # Fallback: filter claim media by room number prefix
            import re
            m = re.match(r'^(\d+)', room.room_name.strip())
            if m:
                prefix = m.group(1)
                urls = []
                for item in encircle_media:
                    ct = (item.get('content_type') or '').lower().split(';')[0].strip()
                    if not ct.startswith('image/'):
                        continue
                    dl_url = item.get('download_uri')
                    if not dl_url:
                        continue
                    for label in item.get('labels', []):
                        lm = re.match(r'^(\d+)', (label or '').strip())
                        if lm and lm.group(1) == prefix:
                            urls.append(dl_url)
                            break
                pass  # no artificial cap — use all available URLs

        counts = {col: getattr(room, col, 0) or 0 for col in CPS_COLUMNS}
        room_data.append({
            'room_name': room.room_name,
            'status':    room.status,
            'total':     room.total,
            'counts':    counts,
            'urls':      urls,
        })
        logger.info(
            f"PPR Photo PDF: room {room.room_name!r} — "
            f"{room.total} boxes, {len(urls)} urls"
        )

    styles = _make_styles()
    page_offset_ref = [0]
    writer = PdfWriter()

    # Cover
    logger.info(f"PPR Photo PDF: building cover for session {session.id} ({len(rooms)} rooms)")
    cover_bytes = _build_cover_pdf(session, room_data, styles, page_offset_ref)
    cover_reader = PdfReader(BytesIO(cover_bytes))
    page_offset_ref[0] += len(cover_reader.pages)
    for page in cover_reader.pages:
        writer.add_page(page)
    del cover_bytes, cover_reader

    # One sub-PDF per room
    for i, rd in enumerate(room_data):
        logger.info(f"PPR Photo PDF: room {i + 1}/{len(room_data)}: {rd['room_name']!r}")
        room_bytes = _build_room_pdf(rd, styles, page_offset_ref)
        room_reader = PdfReader(BytesIO(room_bytes))
        page_offset_ref[0] += len(room_reader.pages)
        for page in room_reader.pages:
            writer.add_page(page)
        del room_bytes, room_reader

    logger.info(
        f"PPR Photo PDF: complete — {page_offset_ref[0]} pages for session {session.id}"
    )
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
