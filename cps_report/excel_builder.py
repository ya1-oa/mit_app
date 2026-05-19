"""
Build a Schedule of Loss Excel file using openpyxl.
Matches the Encircle Detailed format with image columns removed.
"""
from __future__ import annotations

import datetime

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter


# ── Column definitions (image columns removed) ────────────────────────────────
# Original had 27 cols; we drop: Item Photo (D4), Data Tag Photo (J10),
# Receipt Photo (M13) → 24 cols remain.
COLUMNS = [
    # (header_row5, header_row6, width)
    ('#',                   '',                     5),
    ('Room',                '',                     22),
    ('Box',                 '',                     8),
    ('Location',            '',                     14),
    ('Item\nDescription',   '',                     32),
    ('Brand',               '',                     18),
    ('Disposition',         '',                     14),
    ('Condition',           '',                     12),
    ('QTY',                 '',                     6),
    ('Model #',             '',                     16),
    ('Serial #',            '',                     16),
    ('Retailer',            '',                     16),
    ('Replacement\nSource', '',                     14),
    ('Purchase Price',      'Each',                 12),
    ('',                    'Total',                12),
    ('Age',                 'Y',                    6),
    ('',                    'M',                    6),
    ('Replacement Value',   'Each',                 14),
    ('',                    'Total',                14),
    ('Depreciation',        'Category',             16),
    ('',                    '%',                    8),
    ('',                    'Amount',               12),
    ('Actual Cash Value',   'Each',                 14),
    ('',                    'Total',                14),
]

# Column letter shortcuts (1-based)
COL = {name: idx + 1 for idx, (name, _, __) in enumerate(COLUMNS)}

# Friendly color palette
CLR_HEADER_BG    = 'FF1F3864'   # dark navy
CLR_HEADER_FG    = 'FFFFFFFF'
CLR_SUBHEADER_BG = 'FF2F5496'   # medium blue
CLR_SUBHEADER_FG = 'FFFFFFFF'
CLR_ROOM_BG      = 'FFD6E4BC'   # light green
CLR_ROOM_FG      = 'FF000000'
CLR_TOTAL_BG     = 'FFFFF2CC'   # light yellow
CLR_ALT_ROW      = 'FFF2F2F2'
CLR_SIG_SIGNED   = 'FFD1FAE5'   # light mint — signed
CLR_SIG_PENDING  = 'FFFAFAFA'   # near-white — awaiting
CLR_SIG_LINK     = 'FF2563EB'   # blue — hyperlink


def _font(bold=False, color='FF000000', size=10):
    return Font(name='Calibri', bold=bold, color=color, size=size)


def _fill(hex_color):
    return PatternFill(fill_type='solid', fgColor=hex_color)


def _thin_border():
    side = Side(style='thin', color='FFB8B8B8')
    return Border(left=side, right=side, top=side, bottom=side)


def _center(wrap=False):
    return Alignment(horizontal='center', vertical='center', wrap_text=wrap)


def _left(wrap=False):
    return Alignment(horizontal='left', vertical='center', wrap_text=wrap)


def _currency_fmt():
    return '$#,##0.00'


def _pct_fmt():
    return '0.00"%"'


def _build_header_rows(ws, session):
    """Rows 1–4: claim metadata banner."""
    num_cols = len(COLUMNS)
    last_col = get_column_letter(num_cols)

    # Row 1 — Title + Claim Id + Type of Loss
    ws.row_dimensions[1].height = 30
    ws.merge_cells(f'A1:{last_col}1')
    c = ws['A1']
    c.value = f"Schedule of Loss — Detailed Report\nReport Date: {datetime.date.today().strftime('%b %d, %Y')}"
    c.font = _font(bold=True, color=CLR_HEADER_FG, size=13)
    c.fill = _fill(CLR_HEADER_BG)
    c.alignment = _center(wrap=True)

    # Row 2 — Claim Id / Date / CAT Code
    ws.row_dimensions[2].height = 18
    ws.merge_cells('A2:H2')
    ws['A2'].value = f"Claim Id: {session.encircle_claim_id}"
    ws['A2'].font = _font(color=CLR_HEADER_FG)
    ws['A2'].fill = _fill(CLR_SUBHEADER_BG)
    ws['A2'].alignment = _left()

    mid = get_column_letter(9)
    end = get_column_letter(num_cols)
    ws.merge_cells(f'{mid}2:{end}2')
    loss_date = session.loss_date.strftime('%b %d, %Y') if session.loss_date else ''
    ws[f'{mid}2'].value = f"Claim Date: {loss_date}   |   Type of Loss: {session.loss_type}"
    ws[f'{mid}2'].font = _font(color=CLR_HEADER_FG)
    ws[f'{mid}2'].fill = _fill(CLR_SUBHEADER_BG)
    ws[f'{mid}2'].alignment = _left()

    # Row 3 — Insured
    ws.row_dimensions[3].height = 18
    ws.merge_cells(f'A3:{last_col}3')
    ws['A3'].value = f"Insured: {session.insured_name}   |   Claim #: {session.claim_number}"
    ws['A3'].font = _font(color=CLR_HEADER_FG)
    ws['A3'].fill = _fill(CLR_SUBHEADER_BG)
    ws['A3'].alignment = _left()

    # Row 4 — blank spacer
    ws.row_dimensions[4].height = 6


def _build_column_headers(ws, start_row=5):
    """Rows 5–6: two-row column headers."""
    ws.row_dimensions[start_row].height = 30
    ws.row_dimensions[start_row + 1].height = 16

    col_groups = {}  # track which row-5 headers span multiple columns
    for col_idx, (h5, h6, _) in enumerate(COLUMNS, start=1):
        if h5:
            col_groups.setdefault(h5, []).append(col_idx)

    # Write row 5 headers — merge siblings that share the same text
    written = set()
    for col_idx, (h5, h6, _) in enumerate(COLUMNS, start=1):
        cell5 = ws.cell(row=start_row, column=col_idx)
        cell6 = ws.cell(row=start_row + 1, column=col_idx)

        cell5.fill = _fill(CLR_HEADER_BG)
        cell5.font = _font(bold=True, color=CLR_HEADER_FG, size=9)
        cell5.alignment = _center(wrap=True)
        cell5.border = _thin_border()

        cell6.fill = _fill(CLR_SUBHEADER_BG)
        cell6.font = _font(bold=True, color=CLR_HEADER_FG, size=9)
        cell6.alignment = _center()
        cell6.border = _thin_border()

        if h5 and h5 not in written:
            siblings = col_groups.get(h5, [col_idx])
            if len(siblings) > 1:
                start_c = get_column_letter(siblings[0])
                end_c = get_column_letter(siblings[-1])
                try:
                    ws.merge_cells(f'{start_c}{start_row}:{end_c}{start_row}')
                except Exception:
                    pass
            ws.cell(row=start_row, column=col_idx).value = h5
            written.add(h5)

        if h6:
            cell6.value = h6
        elif not h5:
            pass  # continuation column, leave blank
        else:
            # No sub-header: merge rows 5+6 in this column
            try:
                ws.merge_cells(f'{get_column_letter(col_idx)}{start_row}:{get_column_letter(col_idx)}{start_row+1}')
            except Exception:
                pass


def _write_room_header(ws, row, room):
    """A full-width row that labels the room."""
    num_cols = len(COLUMNS)
    ws.row_dimensions[row].height = 20
    ws.merge_cells(f'A{row}:{get_column_letter(num_cols)}{row}')
    c = ws[f'A{row}']
    label = f"{room.room_number}  —  {room.room_name}"
    if room.ai_confidence:
        label += f"   (AI confidence: {room.ai_confidence})"
    c.value = label
    c.font = _font(bold=True, size=10)
    c.fill = _fill(CLR_ROOM_BG)
    c.alignment = _left()
    c.border = _thin_border()


def _write_item_row(ws, row, item, item_num, alt=False):
    """One data row per item."""
    ws.row_dimensions[row].height = 15
    fill = _fill(CLR_ALT_ROW) if alt else None

    rv_each = float(item.replacement_value_each or 0)
    qty = item.qty or 1
    dep_pct = float(item.depreciation_pct or 0)
    rv_total = rv_each * qty
    dep_amount = rv_total * dep_pct / 100
    acv_each = rv_each * (1 - dep_pct / 100)
    acv_total = acv_each * qty

    row_data = [
        item_num,                               # #
        None,                                   # Room (filled by room header merge)
        None,                                   # Box
        None,                                   # Location
        item.description,                       # Item Description
        item.brand or '',                       # Brand
        item.disposition or 'Replacement',      # Disposition
        item.condition or '',                   # Condition
        item.qty,                               # QTY
        item.model_number or '',                # Model #
        item.serial_number or '',               # Serial #
        item.retailer or '',                    # Retailer
        item.replacement_source or 'Retail',    # Replacement Source
        float(item.purchase_price_each or 0),  # Purchase Price Each
        float(item.purchase_price_each or 0) * qty,  # Purchase Price Total
        item.age_years if item.age_years is not None else '',  # Age Y
        item.age_months if item.age_months is not None else '',  # Age M
        rv_each,                               # RV Each
        rv_total,                              # RV Total
        item.depreciation_category or '',      # Dep Category
        dep_pct,                               # Dep %
        dep_amount,                            # Dep Amount
        acv_each,                              # ACV Each
        acv_total,                             # ACV Total
    ]

    currency_cols = {14, 15, 18, 19, 22, 23, 24}
    pct_cols = {21}
    num_cols = {9, 16, 17}

    for col_idx, value in enumerate(row_data, start=1):
        c = ws.cell(row=row, column=col_idx, value=value)
        c.border = _thin_border()
        c.alignment = _left(wrap=(col_idx == 5))
        if fill:
            c.fill = fill
        if col_idx in currency_cols and isinstance(value, (int, float)):
            c.number_format = _currency_fmt()
            c.alignment = Alignment(horizontal='right', vertical='center')
        elif col_idx in pct_cols and isinstance(value, (int, float)):
            c.number_format = '0.0"%"'
            c.alignment = _center()
        elif col_idx in num_cols:
            c.alignment = _center()


def _write_room_total_row(ws, row, room):
    """Subtotal row at the end of each room's items."""
    num_cols = len(COLUMNS)
    ws.row_dimensions[row].height = 16
    ws.merge_cells(f'A{row}:Q{row}')
    ws[f'A{row}'].value = f"Room Total — {room.room_name}"
    ws[f'A{row}'].font = _font(bold=True, size=9)
    ws[f'A{row}'].fill = _fill(CLR_TOTAL_BG)
    ws[f'A{row}'].alignment = _right()

    for col_idx in range(1, num_cols + 1):
        c = ws.cell(row=row, column=col_idx)
        c.fill = _fill(CLR_TOTAL_BG)
        c.border = _thin_border()

    # Sum columns: RV Total (col 19), Dep Amount (22), ACV Total (24)
    items = list(room.items.all())
    if items:
        rv_sum = sum(float(i.replacement_value_each or 0) * (i.qty or 1) for i in items)
        dep_sum = sum(
            float(i.replacement_value_each or 0) * (i.qty or 1) * float(i.depreciation_pct or 0) / 100
            for i in items
        )
        acv_sum = rv_sum - dep_sum

        for col_idx, value in [(19, rv_sum), (22, dep_sum), (24, acv_sum)]:
            c = ws.cell(row=row, column=col_idx, value=value)
            c.number_format = _currency_fmt()
            c.font = _font(bold=True)
            c.fill = _fill(CLR_TOTAL_BG)
            c.alignment = Alignment(horizontal='right', vertical='center')
            c.border = _thin_border()


def _right():
    return Alignment(horizontal='right', vertical='center')


def _write_grand_total(ws, row, session):
    """Grand total row at the bottom."""
    num_cols = len(COLUMNS)
    ws.row_dimensions[row].height = 20

    ws.merge_cells(f'A{row}:Q{row}')
    ws[f'A{row}'].value = 'GRAND TOTAL'
    ws[f'A{row}'].font = _font(bold=True, color=CLR_HEADER_FG, size=11)
    ws[f'A{row}'].fill = _fill(CLR_HEADER_BG)
    ws[f'A{row}'].alignment = _right()

    all_items = []
    for room in session.rooms.prefetch_related('items').all():
        all_items.extend(room.items.all())

    rv_grand = sum(float(i.replacement_value_each or 0) * (i.qty or 1) for i in all_items)
    dep_grand = sum(
        float(i.replacement_value_each or 0) * (i.qty or 1) * float(i.depreciation_pct or 0) / 100
        for i in all_items
    )
    acv_grand = rv_grand - dep_grand

    for col_idx in range(1, num_cols + 1):
        c = ws.cell(row=row, column=col_idx)
        c.fill = _fill(CLR_HEADER_BG)
        c.border = _thin_border()

    for col_idx, value in [(19, rv_grand), (22, dep_grand), (24, acv_grand)]:
        c = ws.cell(row=row, column=col_idx, value=value)
        c.number_format = _currency_fmt()
        c.font = _font(bold=True, color=CLR_HEADER_FG, size=11)
        c.fill = _fill(CLR_HEADER_BG)
        c.alignment = _right()
        c.border = _thin_border()


def _write_room_signature_row(ws, row, room, share_url=None):
    """Signature status row immediately after each room total."""
    num_cols = len(COLUMNS)
    last_col = get_column_letter(num_cols)
    ws.row_dimensions[row].height = 18

    ws.merge_cells(f'A{row}:{last_col}{row}')
    c = ws[f'A{row}']

    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=row, column=col_idx)
        cell.border = _thin_border()

    if room.signature_name and room.signed_at:
        signed_str = room.signed_at.strftime('%B %d, %Y at %I:%M %p')
        c.value = f"✔  Signed by: {room.signature_name}   |   {signed_str}   |   Electronically signed by typed name"
        c.font = Font(name='Calibri', bold=True, color='FF065F46', size=9)
        c.fill = _fill(CLR_SIG_SIGNED)
    else:
        if share_url:
            c.value = f"⬜  Awaiting client signature — Share link: {share_url}"
            c.hyperlink = share_url
            c.font = Font(name='Calibri', color=CLR_SIG_LINK, size=9, underline='single')
        else:
            c.value = "⬜  Awaiting client signature"
            c.font = Font(name='Calibri', color='FF64748B', size=9, italic=True)
        c.fill = _fill(CLR_SIG_PENDING)

    c.alignment = _left()


def build_excel(session, share_url=None) -> bytes:
    """
    Generate the Schedule of Loss Excel file for a CPSReportSession.
    Returns raw bytes of the .xlsx file.
    """
    import io

    wb = Workbook()
    ws = wb.active
    ws.title = 'Schedule of Loss'

    # Freeze panes below header rows
    ws.freeze_panes = 'A7'

    # Column widths
    for col_idx, (_, _, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Build header
    _build_header_rows(ws, session)
    _build_column_headers(ws, start_row=5)

    current_row = 7
    global_item_num = 1
    rooms = list(session.rooms.prefetch_related('items').order_by('order', 'room_number').all())

    for room in rooms:
        items = list(room.items.order_by('order').all())
        if not items:
            continue

        # Room header row
        _write_room_header(ws, current_row, room)
        current_row += 1

        # Item rows
        for i, item in enumerate(items):
            _write_item_row(ws, current_row, item, global_item_num, alt=(i % 2 == 1))
            global_item_num += 1
            current_row += 1

        # Room subtotal
        _write_room_total_row(ws, current_row, room)
        current_row += 1

        # Signature row
        _write_room_signature_row(ws, current_row, room, share_url=share_url)
        current_row += 2  # blank spacer between rooms

    # Grand total
    _write_grand_total(ws, current_row, session)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
