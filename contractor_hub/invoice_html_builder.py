"""
invoice_html_builder.py
=======================
Builds the Django template context for xactimate_invoice.html and
optionally renders the template to a PDF via WeasyPrint.

Usage — in views.py:
    from .invoice_html_builder import render_sub_invoice_pdf, render_sub_invoice_html

    # Return an HttpResponse with Content-Type: application/pdf
    return render_sub_invoice_pdf(request, estimate, section)

    # Return an HttpResponse with Content-Type: text/html  (browser print → PDF)
    return render_sub_invoice_html(request, estimate, section)

The TWO dynamic inputs per invoice
-----------------------------------
  1. Client / Claim info  — from the Client / GCEstimate models
  2. Subcontractor info   — from the Contractor model on the section

Everything else (line item descriptions, notes, separator text) is static
template content keyed by work type.  QTY values and rates come from the
BoxCountReport + Xactimate price list as they already do in pdf_builder.py.
"""

from __future__ import annotations

import io
import math
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.http import HttpResponse
from django.template.loader import render_to_string

# ── Items per body page (approximate — adjust for line density) ──────────────
ITEMS_PER_PAGE = 28

# ── Xactimate reference info (static — Allstate) ────────────────────────────
ALLSTATE_REF = {
    'company': 'Allstate Insurance Company',
    'phone':   '(888) 656-8005',
    'email':   'claims@claims.allstate.com',
}

# ── Estimator / GC info (static — All Phase Consulting) ─────────────────────
APC_ESTIMATOR = {
    'name':         'JOE JONES',
    'phone':        '(216) 450-7228',
    'email':        'WSBJOE9@GMAIL.COM',
    'company_name': 'ALL PHASE CONSULTING, LLC',
    'address':      '375 ROCKBRIDGE RD 172343  LILBURN, GA 30047',
    'operator':     'WSBJOE9',
}


# ─────────────────────────────────────────────────────────────────────────────
# Number formatter
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v, dollars: bool = False) -> str:
    """Format Decimal/float for display in the invoice."""
    try:
        f = float(v)
        s = f'{f:,.2f}'
        return f'${s}' if dollars else s
    except Exception:
        return '0.00'


# ─────────────────────────────────────────────────────────────────────────────
# Tax / total helpers  (mirrors pdf_builder.py logic)
# ─────────────────────────────────────────────────────────────────────────────

def _tax(li, tax_rate: Decimal) -> Decimal:
    if getattr(li, 'is_memo', False) or not getattr(li, 'taxable', True):
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    return (base * tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _total(li, tax_rate: Decimal) -> Decimal:
    if getattr(li, 'is_memo', False):
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    return (base + _tax(li, tax_rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────────────────────────
# Convert a DB section / temp section into flat line-item dicts for the template
# ─────────────────────────────────────────────────────────────────────────────

def _build_line_item_dicts(section, tax_rate: Decimal) -> list[dict]:
    """
    Return a flat list of row dicts.  Each dict has a 'kind' key:
      'item'       — normal line item row
      'sep_eq'     — ===... separator
      'sep_dash'   — ---... separator
      'note'       — indented note text
      'sub_block'  — subcontractor info block
    """
    rows: list[dict] = []
    num = 0

    for li in section.line_items.order_by('order'):
        if getattr(li, 'is_memo', False):
            # Memo rows render as separator/note rows
            rows.append({'kind': 'sep_eq',  'text': '=' * 78})
            if li.description:
                rows.append({'kind': 'note', 'text': li.description})
            rows.append({'kind': 'sep_eq',  'text': '=' * 78})
            continue

        num += 1
        tax_val   = _tax(li, tax_rate)
        total_val = _total(li, tax_rate)

        # Build notes list from li.notes string (newline-delimited)
        notes_raw = getattr(li, 'notes', '') or ''
        note_lines = [n.strip() for n in notes_raw.split('\n') if n.strip()]

        rows.append({
            'kind':        'item',
            'num':         num,
            'cat':         getattr(li, 'cat', '') or '',
            'sel':         getattr(li, 'sel', '') or '',
            'act':         '+',
            'description': li.description or '',
            'calc':        getattr(li, 'calc_formula', '') or '',
            'qty':         _fmt(li.quantity),
            'unit':        getattr(li, 'unit', 'EA') or 'EA',
            'remove':      _fmt(li.remove_rate),
            'replace':     _fmt(li.replace_rate),
            'tax':         _fmt(tax_val),
            'total':       _fmt(total_val),
            'notes':       note_lines,
            'is_bid_item': getattr(li, 'is_bid_item', False),
            'is_memo':     False,
        })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Paginate flat rows into page buckets
# ─────────────────────────────────────────────────────────────────────────────

def _paginate(rows: list[dict], items_per_page: int = ITEMS_PER_PAGE) -> list[dict]:
    """
    Split rows into page dicts.  Each page dict has:
      room_label   : str | None
      items        : list of row dicts
      show_totals  : bool  (True on last page only)
      totals_rows  : list of totals row dicts (empty unless show_totals)
    """
    pages = []
    chunk: list[dict] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= items_per_page:
            pages.append({'room_label': None, 'items': chunk,
                          'show_totals': False, 'totals_rows': []})
            chunk = []
    if chunk or not pages:
        pages.append({'room_label': None, 'items': chunk,
                      'show_totals': True, 'totals_rows': []})
    else:
        pages[-1]['show_totals'] = True
    return pages


# ─────────────────────────────────────────────────────────────────────────────
# Recap helpers
# ─────────────────────────────────────────────────────────────────────────────

def _recap_by_room(section) -> list[dict]:
    label = getattr(section, 'section_label', section.section_type.upper())
    # The sub invoice has a single room section equal to the full subtotal
    # Room-level breakdown would come from section.rooms if that relationship
    # exists; here we return a single "Main Level" row.
    return [
        {'label': f'Area: Main Level', 'value': '', 'pct': '', 'indent': False},
        {'label': label, 'value': '——', 'pct': '100.00', 'indent': True},
        {'label': f'Area Subtotal: Main Level', 'value': '——', 'pct': '100.00', 'indent': False},
        {'label': 'Subtotal of Areas', 'value': '——', 'pct': '100.00', 'indent': False},
    ]


def _recap_by_cat(section, tax_rate: Decimal) -> list[dict]:
    """
    Build the Recap by Category table.
    Category codes come from existing line items.
    Returns list of {label, value, pct}.
    """
    cat_totals: dict[str, Decimal] = {}
    grand = Decimal('0.00')
    for li in section.line_items.all():
        if getattr(li, 'is_memo', False):
            continue
        t = _total(li, tax_rate)
        cat_totals[li.cat] = cat_totals.get(li.cat, Decimal('0.00')) + t
        grand += t

    rows = []
    for cat, val in sorted(cat_totals.items()):
        pct = (val / grand * 100).quantize(Decimal('0.01')) if grand else Decimal('0.00')
        rows.append({'label': cat, 'value': _fmt(val), 'pct': _fmt(pct)})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Main context builder
# ─────────────────────────────────────────────────────────────────────────────

def build_invoice_context(estimate, section) -> dict[str, Any]:
    """
    Build the full template context dict for xactimate_invoice.html.

    estimate : GCEstimate (or _ClientEstimate shim from views.py)
    section  : GCSection  (or _TempSection from pdf_builder.py)
    """
    sub      = section.subcontractor
    client   = estimate.client
    tax_rate = Decimal(str(estimate.tax_rate)) if estimate.tax_rate else Decimal('8.00')

    # ── Line item total / tax / RCV ──────────────────────────────────────────
    line_item_total = Decimal('0.00')
    tax_total       = Decimal('0.00')
    for li in section.line_items.all():
        if not getattr(li, 'is_memo', False):
            line_item_total += _total(li, tax_rate)
            tax_total       += _tax(li, tax_rate)
    # line_item_total already includes tax; separate out pre-tax base
    pre_tax_total = line_item_total - tax_total
    rcv           = line_item_total

    section_totals = {
        'tax':             _fmt(tax_total),
        'line_item_total': _fmt(pre_tax_total),
        'rcv':             _fmt(rcv),
    }

    # ── Summary page rows ────────────────────────────────────────────────────
    summary_rows = [
        {'label': 'Line Item Total',       'value': _fmt(pre_tax_total), 'bold': False},
        {'label': 'Total Tax',             'value': _fmt(tax_total),     'bold': False},
        {'label': 'Replacement Cost Value','value': _fmt(rcv),           'bold': True},
        {'label': 'Net Claim',             'value': _fmt(rcv),           'bold': True},
    ]

    # ── Recaps ───────────────────────────────────────────────────────────────
    cat_rows   = _recap_by_cat(section, tax_rate)
    cat_subtotal = sum(
        Decimal(r['value'].replace(',', '')) for r in cat_rows
    )
    cat_sub_pct  = (cat_subtotal / rcv * 100).quantize(Decimal('0.01')) if rcv else Decimal('0.00')
    cat_tax_pct  = (tax_total    / rcv * 100).quantize(Decimal('0.01')) if rcv else Decimal('0.00')

    # ── Line item rows → paginate ────────────────────────────────────────────
    flat_rows  = _build_line_item_dicts(section, tax_rate)
    li_pages   = _paginate(flat_rows)

    # Inject totals into the last page
    if li_pages:
        li_pages[-1]['show_totals'] = True
        li_pages[-1]['totals_rows'] = [
            {
                'label':   f'Total: {getattr(section, "section_label", "Main Level")}',
                'remove':  '0.00',
                'replace': '0.00',
                'tax':     _fmt(tax_total),
                'total':   _fmt(rcv),
                'bold':    True,
            },
            {
                'label':   f'Line Item Totals: {estimate.estimate_number}-CON',
                'remove':  '0.00',
                'replace': '0.00',
                'tax':     _fmt(tax_total),
                'total':   _fmt(rcv),
                'bold':    False,
            },
        ]

    # ── Page numbers ─────────────────────────────────────────────────────────
    body_page_count  = len(li_pages)
    summary_page_num = body_page_count + 2   # cover=1, body pages, summary
    recap_tax_page_num  = summary_page_num + 1
    recap_room_page_num = recap_tax_page_num + 1
    recap_cat_page_num  = recap_room_page_num + 1

    # ── Date string ──────────────────────────────────────────────────────────
    try:
        today = date.today()
        today_str = today.strftime('%-m/%-d/%Y')
    except Exception:
        today_str = date.today().strftime('%m/%d/%Y')

    # ── Client address fields ────────────────────────────────────────────────
    # Handle flexible Client model field names gracefully
    def _cf(client, *attrs, default=''):
        for a in attrs:
            v = getattr(client, a, None)
            if v:
                return v
        return default

    billing_address = _cf(client, 'billingAddress', 'address', 'homeAddress')
    billing_city    = _cf(client, 'billingCity', 'city', 'homeCity')
    billing_state   = _cf(client, 'billingState', 'state', 'homeState')
    billing_zip     = _cf(client, 'billingZip', 'zip_code', 'homeZip')
    home_address    = _cf(client, 'homeAddress', 'address')
    home_city       = _cf(client, 'homeCity', 'city')
    home_state      = _cf(client, 'homeState', 'state')
    home_zip        = _cf(client, 'homeZip', 'zip_code')
    client_phone    = _cf(client, 'phone', 'cell_phone', 'homePhone')
    claim_number    = _cf(client, 'claimNumber', 'claim_number', 'file_number')
    file_number     = _cf(estimate, 'file_number', 'claimNumber')

    # ── Build a simple namespace for client (avoids template attr errors) ────
    class _C:
        pass
    c = _C()
    c.pOwner          = _cf(client, 'pOwner', 'name', 'full_name')
    c.phone           = f'Home: {client_phone}' if client_phone else ''
    c.billingAddress  = billing_address
    c.billingCity     = billing_city
    c.billingState    = billing_state
    c.billingZip      = billing_zip
    c.homeAddress     = home_address
    c.homeCity        = home_city
    c.homeState       = home_state
    c.homeZip         = home_zip

    # ── Estimate fields ──────────────────────────────────────────────────────
    class _E:
        pass
    e = _E()
    e.estimate_number  = estimate.estimate_number or f'EST-{str(estimate.id)[:8].upper()}'
    e.file_number      = file_number or claim_number or ''
    e.date_entered     = (
        estimate.date_entered.strftime('%-m/%-d/%Y')
        if hasattr(estimate, 'date_entered') and estimate.date_entered
        else ''
    )
    e.price_list       = getattr(estimate, 'price_list', 'OHCL8X_02MAY26') or 'OHCL8X_02MAY26'
    e.type_of_estimate = getattr(estimate, 'type_of_estimate', 'Fire') or 'Fire'
    e.tax_rate         = tax_rate

    # ── Section label / bid confirmed label ──────────────────────────────────
    section_label = getattr(section, 'section_label', section.section_type.upper())
    bid_labels = {
        'admin':     'CPS ADMINISTRATION SERVICES BID ACCEPTED & CONFIRMED',
        'packing':   'CPS PACKOUT & Evaluation BID ACCEPTED & CONFIRMED',
        'cleaning':  'CPS CLN BID ACCEPTED & CONFIRMED CPS',
        'demo':      'CPS DMO BID ACCEPTED & CONFIRMED',
        'transport': 'CPS TRANSPORTING CONTENTS BID ACCEPTED & CONFIRMED',
        'storage':   'CPS STORAGE BID ACCEPTED & CONFIRMED',
    }
    bid_confirmed_label = bid_labels.get(
        section.section_type,
        f'{section_label.upper()} BID ACCEPTED & CONFIRMED'
    )

    # ── Recap by room (fill actual values now that we have totals) ───────────
    recap_room = [
        {'label': 'Area: Main Level',            'value': '',              'pct': '',       'indent': False},
        {'label': section_label,                 'value': _fmt(pre_tax_total), 'pct': '100.00', 'indent': True},
        {'label': 'Area Subtotal: Main Level',   'value': _fmt(pre_tax_total), 'pct': '100.00', 'indent': False},
        {'label': 'Subtotal of Areas',           'value': _fmt(pre_tax_total), 'pct': '100.00', 'indent': False},
        {'label': 'Total',                       'value': _fmt(pre_tax_total), 'pct': '100.00', 'indent': False},
    ]

    return {
        'sub':                   sub,
        'client':                c,
        'estimate':              e,
        'reference':             ALLSTATE_REF,
        'operator':              APC_ESTIMATOR['operator'],
        'estimator_name':        APC_ESTIMATOR['name'],
        'estimator_phone':       APC_ESTIMATOR['phone'],
        'estimator_email':       APC_ESTIMATOR['email'],
        'estimator_company_name': APC_ESTIMATOR['company_name'],
        'estimator_address':     APC_ESTIMATOR['address'],
        'section_label':         section_label,
        'bid_confirmed_label':   bid_confirmed_label,
        'line_item_pages':       li_pages,
        'section_totals':        section_totals,
        'summary_rows':          summary_rows,
        'recap_by_room':         recap_room,
        'recap_by_cat':          cat_rows,
        'recap_subtotal_pct':    _fmt(cat_sub_pct),
        'recap_tax_pct':         _fmt(cat_tax_pct),
        'today_str':             today_str,
        'summary_page_num':      summary_page_num,
        'recap_tax_page_num':    recap_tax_page_num,
        'recap_room_page_num':   recap_room_page_num,
        'recap_cat_page_num':    recap_cat_page_num,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public render helpers
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATE_NAME = 'contractor_hub/xactimate_invoice.html'


def render_sub_invoice_html(request, estimate, section) -> HttpResponse:
    """
    Return the invoice as an HTML page — user prints via browser → Save as PDF.
    This is the zero-dependency path (no WeasyPrint needed).
    """
    ctx  = build_invoice_context(estimate, section)
    html = render_to_string(TEMPLATE_NAME, ctx, request=request)
    return HttpResponse(html, content_type='text/html; charset=utf-8')


def render_sub_invoice_pdf_weasyprint(request, estimate, section) -> HttpResponse:
    """
    Return the invoice as a real PDF using WeasyPrint.
    Requires:  pip install weasyprint
    """
    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise RuntimeError(
            'WeasyPrint is not installed.  Run: pip install weasyprint'
        ) from exc

    ctx    = build_invoice_context(estimate, section)
    html   = render_to_string(TEMPLATE_NAME, ctx, request=request)
    pdf_io = io.BytesIO()
    WP_HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(pdf_io)
    pdf_io.seek(0)

    est_num  = ctx['estimate'].estimate_number.replace(' ', '_').replace('/', '-')
    sec_type = getattr(section, 'section_type', 'invoice').upper()
    fname    = f'{est_num}_{sec_type}_SUB_INVOICE.pdf'

    response = HttpResponse(pdf_io.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{fname}"'
    return response
