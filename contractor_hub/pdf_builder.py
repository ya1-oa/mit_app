"""
Contractor Hub — Xactimate-Format PDF Builder
==============================================
Replicates the exact layout of the Xactimate contractor invoice PDF.

Public API
----------
generate_gc_estimate_pdf(estimate)                     -> io.BytesIO
generate_subcontractor_invoice_pdf(estimate, section)  -> io.BytesIO
"""

import io
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter

# ── Page geometry ─────────────────────────────────────────────────────────────
PW, PH = letter          # 612 × 792 pts

LM  = 36                 # left margin
RM  = 576                # right margin (36 from right edge)

# Header block (company info, every page)
HDR_COMP_X  = 100        # x of company lines
HDR_Y1      = 734        # baseline of first company line
HDR_LINE_H  = 13         # line pitch inside header
HDR_RULE_Y  = 648        # y of thin rule under header

# Footer
FTR_RULE_Y  = 44
FTR_Y       = 30

# Body
BODY_TOP    = 638        # content starts just below header rule
BODY_BTM    = 58         # content ends just above footer rule
LINE_H      = 11         # body text line pitch

# Number columns (right-justified x positions)
COL_RMV_R  = 360         # REMOVE right edge
COL_REP_R  = 414         # REPLACE right edge
COL_TAX_R  = 463         # TAX right edge
COL_OP_R   = 509         # O&P right edge
COL_TOT_R  = 560         # TOTAL right edge

# First-row item cols
COL_NUM_R  = 53          # item number right edge
COL_CAT    = 57          # CAT start
COL_SEL    = 81          # SEL start
COL_SIGN   = 112         # +/- sign
COL_DESC   = 120         # description start (row 1)
COL_CALC   = 57          # calc formula start (row 2)
COL_QTY_R  = 213         # QTY+unit right edge (row 2)

# ── Fonts ─────────────────────────────────────────────────────────────────────
F_HDR   = 'Times-Bold'
F_BODY  = 'Helvetica'
F_BOLD  = 'Helvetica-Bold'
F_MONO  = 'Courier'

FS_HDR  = 12
FS_BODY = 9
FS_SM   = 8

# ── Helpers ───────────────────────────────────────────────────────────────────

def _n(v, dec=2):
    """Format a number without $ — e.g. '1,235.52' or '0.00'."""
    try:
        f = float(v)
        if dec == 2:
            return f'{f:,.2f}'
        return f'{f:,.0f}'
    except Exception:
        return '0.00'


def _per_line_op(li, estimate):
    """O&P amount for one line item."""
    if li.is_memo:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    op_pct = estimate.overhead_pct + estimate.profit_pct
    return (base * op_pct / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _per_line_tax(li, estimate):
    """Tax amount for one line item (computed on base + O&P)."""
    if li.is_memo or not li.taxable:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    op   = _per_line_op(li, estimate)
    return ((base + op) * estimate.tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _per_line_total(li, estimate):
    """Full line total (base + O&P + tax)."""
    if li.is_memo:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    return (base + _per_line_op(li, estimate) + _per_line_tax(li, estimate)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def _section_totals(section, estimate):
    """Returns (tax_sum, op_sum, total_sum) for a section."""
    tax = op = tot = Decimal('0.00')
    for li in section.line_items.all():
        tax += _per_line_tax(li, estimate)
        op  += _per_line_op(li, estimate)
        tot += _per_line_total(li, estimate)
    return tax, op, tot


def _wrap(text, max_chars):
    """Split text into lines of max_chars. Simple word-wrap."""
    if not text:
        return []
    words = text.split()
    lines, cur = [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
    if cur:
        lines.append(cur)
    return lines or ['']


# ── XactimateDoc class ────────────────────────────────────────────────────────

class XactimateDoc:
    """Canvas-based Xactimate-format document builder."""

    def __init__(self, buf, estimate, company, company_short='', is_sub=False):
        """
        company       – Contractor instance whose header appears on every page
        company_short – Short name for the 'COMPANY  EIN XX' first line
        is_sub        – True for subcontractor invoices
        """
        self.c             = rl_canvas.Canvas(buf, pagesize=letter)
        self.estimate      = estimate
        self.company       = company
        self.company_short = company_short or company.name
        self.is_sub        = is_sub
        self.page_num      = 0
        self._est_num      = estimate.estimate_number or f'EST-{str(estimate.id)[:8].upper()}'
        self._today        = date.today().strftime('%-m/%-d/%Y') if hasattr(date.today(), 'strftime') else str(date.today())
        try:
            self._today = date.today().strftime('%#m/%#d/%Y')  # Windows
        except Exception:
            try:
                self._today = date.today().strftime('%-m/%-d/%Y')  # Unix
            except Exception:
                self._today = date.today().strftime('%m/%d/%Y')
        self.y             = BODY_TOP  # current y cursor

    # ── Page management ──────────────────────────────────────────────────────

    def new_page(self):
        if self.page_num > 0:
            self._draw_footer()
            self.c.showPage()
        self.page_num += 1
        self._draw_header()
        self.y = BODY_TOP

    def check_space(self, need=LINE_H * 3):
        """Start a new page if there isn't enough room."""
        if self.y - need < BODY_BTM:
            self.new_page()

    # ── Header / footer ──────────────────────────────────────────────────────

    def _draw_header(self):
        c = self.c
        co = self.company

        # Page number (top-left)
        c.setFont(F_BODY, FS_HDR)
        c.drawString(LM, PH - 16, str(self.page_num))

        # Company block (Times-Bold 12)
        c.setFont(F_HDR, FS_HDR)
        x, y = HDR_COMP_X, HDR_Y1

        short = self.company_short.upper()
        ein   = co.ein or ''
        lines = [
            f'{short}    EIN {ein}',
            co.name.upper(),
            co.address if co.address else '',
            f'{co.city}, {co.state} {co.zip_code}' if co.city else '',
            f'EIN {ein}',
        ]
        phone_line = ''
        if co.phone:
            phone_line = co.phone
            if co.contact_person:
                phone_line += f' {co.contact_person.upper()}'
        if phone_line:
            lines.append(phone_line)
        if co.email:
            lines.append(co.email.upper())

        for line in lines:
            if line.strip():
                c.drawString(x, y, line)
            y -= HDR_LINE_H

        # Rule
        c.setLineWidth(0.5)
        c.line(LM, HDR_RULE_Y, RM, HDR_RULE_Y)

    def _draw_footer(self):
        c = self.c
        c.setLineWidth(0.5)
        c.line(LM, FTR_RULE_Y, RM, FTR_RULE_Y)
        c.setFont(F_BODY, FS_SM)
        c.drawString(LM, FTR_Y, self._est_num)
        right_text = f'{self._today}    Page: {self.page_num}'
        c.drawRightString(RM, FTR_Y, right_text)

    # ── Low-level draw helpers ────────────────────────────────────────────────

    def _text(self, x, y, text, font=F_BODY, size=FS_BODY, bold=False):
        if bold:
            font = F_BOLD
        self.c.setFont(font, size)
        self.c.drawString(x, y, str(text))

    def _text_r(self, x, y, text, font=F_MONO, size=FS_BODY):
        self.c.setFont(font, size)
        self.c.drawRightString(x, y, str(text))

    def _rule(self, y=None, full=False):
        """Draw a thin separator rule."""
        if y is None:
            y = self.y
        x1 = LM if full else LM + 4
        self.c.setLineWidth(0.3)
        self.c.line(x1, y, RM, y)

    def _separator(self, char='='):
        """Draw a separator line and advance y."""
        self.c.setFont(F_MONO, FS_SM)
        line = char * 80
        self.c.drawString(LM, self.y, line[:int((RM - LM) / 5.4)])
        self.y -= LINE_H

    def _section_heading(self, label, continued=False):
        """Draw a centered section heading (bold)."""
        self.check_space(LINE_H * 4)
        self.y -= LINE_H
        prefix = 'CONTINUED - ' if continued else ''
        full   = (prefix + label).upper()
        self.c.setFont(F_BOLD, FS_BODY)
        text_w = self.c.stringWidth(full, F_BOLD, FS_BODY)
        cx = LM + (RM - LM - text_w) / 2
        self.c.drawString(cx, self.y, full)
        self.y -= LINE_H * 2

    def _col_headers(self):
        """Draw the two-row column header."""
        c = self.c
        y = self.y
        c.setFont(F_BODY, FS_BODY)
        c.drawString(COL_CAT,  y, 'CAT')
        c.drawString(COL_SEL,  y, 'SEL')
        c.drawString(COL_SIGN + 2, y, 'ACT DESCRIPTION')
        y -= LINE_H
        c.drawString(COL_CALC, y, 'CALC')
        c.drawRightString(COL_QTY_R, y, 'QTY')
        c.drawRightString(COL_RMV_R, y, 'REMOVE')
        c.drawRightString(COL_REP_R, y, 'REPLACE')
        c.drawRightString(COL_TAX_R, y, 'TAX')
        c.drawRightString(COL_OP_R,  y, 'O&P')
        c.drawRightString(COL_TOT_R, y, 'TOTAL')
        self.y = y - LINE_H

    # ── Subcontractor info block ──────────────────────────────────────────────

    def _sub_block(self, sub):
        """Render the subcontractor info block."""
        self.check_space(LINE_H * 7)
        self._separator('.')
        self._text(LM, self.y, '.............. SUBCONTRACTOR ..................',
                   font=F_BODY, size=FS_BODY)
        self.y -= LINE_H * 2

        c = self.c
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, self.y,
                     f'{sub.name.upper()}  EIN # {sub.ein}')
        self.y -= LINE_H

        c.setFont(F_BODY, FS_BODY)
        for line in [sub.address,
                     f'{sub.city}, {sub.state} {sub.zip_code}' if sub.city else '',
                     sub.phone + (' ' + sub.contact_person if sub.contact_person else '')
                     if sub.phone else '',
                     sub.email]:
            if line and line.strip():
                c.drawString(LM + 4, self.y, line)
                self.y -= LINE_H

        if sub.certification:
            c.drawString(LM + 4, self.y, sub.certification)
            self.y -= LINE_H

        self._separator()

    # ── One line item (2-row format) ──────────────────────────────────────────

    def _line_item(self, num, li, estimate):
        """Render one line item in Xactimate two-row format."""
        need = LINE_H * 2 + (LINE_H * len(_wrap(li.notes, 90)) if li.notes else 0)
        self.check_space(need + LINE_H)

        op    = _per_line_op(li, estimate)
        tax   = _per_line_tax(li, estimate)
        total = _per_line_total(li, estimate)
        base  = li.quantity * (li.remove_rate + li.replace_rate)

        c = self.c

        # ── Row 1: number, CAT, SEL, sign, description ──────────────────────
        y = self.y
        c.setFont(F_BODY, FS_BODY)
        c.drawRightString(COL_NUM_R, y, f'{num}.')
        c.setFont(F_BOLD, FS_SM)
        c.drawString(COL_CAT, y, li.cat)
        c.drawString(COL_SEL, y, li.sel)

        # Sign
        sign = '-' if (li.remove_rate > 0 and li.replace_rate == 0) else '+'
        bid_marker = ''
        if li.is_bid_item:
            bid_marker = '[*E]' if not li.taxable else '[*]'
        c.setFont(F_BODY, FS_BODY)
        c.drawString(COL_SIGN, y, sign)
        if bid_marker:
            c.drawString(COL_SIGN + 8, y, bid_marker)

        # Description (wraps if needed)
        c.setFont(F_BODY, FS_BODY)
        desc_x = COL_DESC + (22 if bid_marker else 0)
        desc_lines = _wrap(li.description, 70)
        c.drawString(desc_x, y, desc_lines[0])
        self.y -= LINE_H

        # Overflow description lines
        for extra in desc_lines[1:]:
            self.check_space(LINE_H)
            c.drawString(COL_DESC, self.y, extra)
            self.y -= LINE_H

        # ── Row 2: calc, qty, remove, replace, tax, o&p, total ──────────────
        y2 = self.y
        c.setFont(F_MONO, FS_SM)

        # Calc formula + qty + unit
        calc_str = f'{li.calc_formula} ' if li.calc_formula else ''
        qty_str  = f'{_n(li.quantity)}{li.unit}'
        c.drawString(COL_CALC, y2, calc_str + qty_str)

        # Numbers (right-justified)
        if li.is_memo:
            # Zero-dollar memo row
            self.y -= LINE_H
        else:
            c.drawRightString(COL_RMV_R, y2, _n(li.remove_rate))
            c.drawString(COL_RMV_R + 2, y2, '+')
            c.drawRightString(COL_REP_R, y2, _n(li.replace_rate))
            c.drawString(COL_REP_R + 2, y2, '=')
            c.drawRightString(COL_TAX_R, y2, _n(tax))
            c.drawRightString(COL_OP_R,  y2, _n(op))
            c.drawRightString(COL_TOT_R, y2, _n(total))
            self.y -= LINE_H

        # Notes (if any)
        if li.notes:
            c.setFont(F_BODY, FS_SM)
            for note_line in _wrap(li.notes, 90):
                self.check_space(LINE_H)
                c.drawString(COL_DESC, self.y, note_line)
                self.y -= LINE_H

    # ── Section total line ────────────────────────────────────────────────────

    def _section_total(self, label, tax, op, total):
        self.check_space(LINE_H * 2)
        self.y -= LINE_H // 2
        c = self.c
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, self.y, f'Totals: {label}')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(COL_TAX_R, self.y, _n(tax))
        c.drawRightString(COL_OP_R,  self.y, _n(op))
        c.drawRightString(COL_TOT_R, self.y, _n(total))
        self.y -= LINE_H * 2

    # ── Cover page ────────────────────────────────────────────────────────────

    def build_cover_page(self):
        self.new_page()
        c, y = self.c, self.y
        est = self.estimate
        cli = est.client

        def kv(label, value, label2='', value2='', y=None):
            """Draw a key/value pair (optionally two columns)."""
            nonlocal self
            if y is None:
                y = self.y
            c.setFont(F_BOLD, FS_BODY)
            c.drawRightString(LM + 90, y, label + ':')
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, y, str(value))
            if label2:
                c.setFont(F_BOLD, FS_BODY)
                c.drawRightString(LM + 350, y, label2 + ':')
                c.setFont(F_BODY, FS_BODY)
                c.drawString(LM + 354, y, str(value2))
            self.y -= LINE_H

        # Client info
        phone = cli.cPhone or cli.DAPhone or ''
        kv('Client', cli.pOwner or '—', 'Home', phone)
        kv('Home', cli.pAddress or '—')
        addr2 = cli.pCityStateZip or ''
        if addr2:
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, self.y, addr2)
            self.y -= LINE_H
        kv('Property', cli.pAddress or '—')
        if addr2:
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, self.y, addr2)
            self.y -= LINE_H
        self.y -= LINE_H

        # Estimator
        estimator = est.estimator
        if estimator:
            kv('Operator', (estimator.email or '').split('@')[0].upper())
            self.y -= LINE_H
            kv('Estimator', estimator.contact_person or estimator.name,
               'Business', estimator.phone or '')
            kv('Company', estimator.name, 'E-mail', estimator.email or '')
            kv('Business', estimator.address or '')
            if estimator.city:
                c.setFont(F_BODY, FS_BODY)
                c.drawString(LM + 94, self.y,
                             f'{estimator.city}, {estimator.state} {estimator.zip_code}')
                self.y -= LINE_H
        self.y -= LINE_H

        # Insurance
        kv('Reference', '', 'Business', cli.DAPhone or cli.fieldAdjEmail or '')
        kv('Company',
           cli.insuranceCo_Name or '—',
           'E-mail', cli.DAEmail or cli.fieldAdjEmail or '')
        self.y -= LINE_H

        # Estimate details
        kv('Type of Estimate', est.type_of_estimate or 'Fire')
        date_str = est.date_entered.strftime('%m/%d/%Y') if est.date_entered else ''
        kv('Date Entered', date_str, 'Date Assigned', '')
        self.y -= LINE_H
        kv('Price List', est.price_list or '')
        kv('Labor Efficiency', 'Restoration/Service/Remodel')
        kv('Estimate', self._est_num)
        kv('File Number', f'#{cli.claimNumber}' if cli.claimNumber else '')
        self.y -= LINE_H * 3

        c.setFont(F_BOLD, FS_HDR)
        cx = LM + (RM - LM - c.stringWidth('THANK YOU', F_BOLD, FS_HDR)) / 2
        c.drawString(cx, self.y, 'THANK YOU')

    # ── Site conditions / preamble block ─────────────────────────────────────

    def _site_conditions(self):
        self.check_space(LINE_H * 4)
        self._separator()
        lbl = f'Site Conditions'
        self._text(LM, self.y, lbl, bold=True)
        self.y -= LINE_H

    # ── Section pages ─────────────────────────────────────────────────────────

    def build_section(self, section, item_counter_start=1):
        """Build pages for one section. Returns next item counter."""
        est    = self.estimate
        label  = section.section_label
        sub    = section.subcontractor

        # ── Section heading on a new page segment ────────────────────────────
        self.check_space(LINE_H * 8)
        self._section_heading(label, continued=False)

        # Estimate number centered
        c = self.c
        c.setFont(F_BODY, FS_BODY)
        num_w = c.stringWidth(self._est_num, F_BODY, FS_BODY)
        c.drawString(LM + (RM - LM - num_w) / 2, self.y, self._est_num)
        self.y -= LINE_H

        # Column headers
        self._col_headers()

        # Subcontractor info (if section has one)
        if sub:
            self._sub_block(sub)

        self._separator()

        # Line items
        item_num = item_counter_start
        line_items = list(section.line_items.order_by('order'))
        for li in line_items:
            # Page break mid-section → "CONTINUED -" heading
            if self.y - LINE_H * 4 < BODY_BTM:
                self.new_page()
                self._section_heading(label, continued=True)
                self._col_headers()

            self._line_item(item_num, li, est)
            item_num += 1

        # Section total
        tax, op, tot = _section_totals(section, est)
        self._section_total(label, tax, op, tot)

        return item_num

    # ── Line item totals page ─────────────────────────────────────────────────

    def build_line_totals(self, sections):
        """Bottom of the last section page — summary line."""
        total_tax = total_op = total_tot = Decimal('0.00')
        for s in sections:
            t, o, tt = _section_totals(s, self.estimate)
            total_tax += t
            total_op  += o
            total_tot += tt

        self.check_space(LINE_H * 3)
        self.y -= LINE_H
        self.c.setFont(F_BOLD, FS_BODY)
        self.c.drawString(LM, self.y,
                          f'Line Item Totals: {self._est_num}')
        self.c.setFont(F_MONO, FS_BODY)
        self.c.drawRightString(COL_TAX_R, self.y, _n(total_tax))
        self.c.drawRightString(COL_OP_R,  self.y, _n(total_op))
        self.c.drawRightString(COL_TOT_R, self.y, _n(total_tot))
        self.y -= LINE_H * 2
        return total_tax, total_op, total_tot

    # ── Summary page ─────────────────────────────────────────────────────────

    def build_summary_page(self):
        est = self.estimate
        self.new_page()
        c = self.c
        y = self.y

        # "Summary" heading
        c.setFont(F_BOLD, FS_HDR)
        hdr_w = c.stringWidth('Summary', F_BOLD, FS_HDR)
        c.drawString(LM + (RM - LM - hdr_w) / 2, y, 'Summary')
        y -= LINE_H * 2

        li_total = float(est.line_item_total)
        overhead = float(est.overhead_amount)
        profit   = float(est.profit_amount)
        tax      = float(est.tax_amount)
        rcv      = li_total + overhead + profit + tax

        rows = [
            ('Line Item Total', li_total, False),
            ('Overhead',        overhead, False),
            ('Profit',          profit,   False),
            ('Total Tax',       tax,      False),
            ('', None, False),
            ('Replacement Cost Value', rcv, True),
            ('Net Claim',              rcv, True),
        ]

        for label, val, bold in rows:
            if val is None:
                y -= LINE_H
                continue
            if bold:
                c.setFont(F_BOLD, FS_BODY)
                c.drawString(LM, y, label)
                c.setFont(F_MONO, FS_BODY)
                c.drawRightString(RM, y, f'${_n(val)}')
            else:
                c.setFont(F_BODY, FS_BODY)
                c.drawString(LM + 20, y, label)
                c.setFont(F_MONO, FS_BODY)
                c.drawRightString(RM - 20, y, _n(val))
            y -= LINE_H

        y -= LINE_H * 4
        # Signature
        c.setFont(F_BOLD, FS_HDR)
        gc_name = est.estimator.contact_person if est.estimator and est.estimator.contact_person else \
                  (est.gc_contractor.contact_person if est.gc_contractor.contact_person else est.gc_contractor.name)
        sw = c.stringWidth(gc_name.upper(), F_BOLD, FS_HDR)
        c.drawString(LM + (RM - LM - sw) / 2, y, gc_name.upper())
        self.y = y - LINE_H

    # ── Recap of Taxes, Overhead and Profit ──────────────────────────────────

    def build_recap_taxes_page(self):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        c.setFont(F_BOLD, FS_HDR)
        hdr = 'Recap of Taxes, Overhead and Profit'
        c.drawString(LM + (RM - LM - c.stringWidth(hdr, F_BOLD, FS_HDR)) / 2, y, hdr)
        y -= LINE_H * 3

        # Header row
        c.setFont(F_BOLD, FS_BODY)
        c.drawRightString(LM + 280, y, f'Overhead ({est.overhead_pct}%)')
        c.drawRightString(LM + 380, y, f'Profit ({est.profit_pct}%)')
        c.drawRightString(LM + 480, y, f'Total Tax ({est.tax_rate}%)')
        y -= LINE_H

        li_total = float(est.line_item_total)
        overhead = float(est.overhead_amount)
        profit   = float(est.profit_amount)
        tax      = float(est.tax_amount)

        c.setFont(F_BODY, FS_BODY)
        c.drawString(LM, y, 'Line Items')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(LM + 280, y, _n(overhead))
        c.drawRightString(LM + 380, y, _n(profit))
        c.drawRightString(LM + 480, y, _n(tax))
        y -= LINE_H

        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'Total')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(LM + 280, y, _n(overhead))
        c.drawRightString(LM + 380, y, _n(profit))
        c.drawRightString(LM + 480, y, _n(tax))
        self.y = y - LINE_H

    # ── Recap by Room (section breakdown) ────────────────────────────────────

    def build_recap_by_room_page(self, sections):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        c.setFont(F_BOLD, FS_HDR)
        hdr = 'Recap by Room'
        c.drawString(LM + (RM - LM - c.stringWidth(hdr, F_BOLD, FS_HDR)) / 2, y, hdr)
        y -= LINE_H

        c.setFont(F_BODY, FS_BODY)
        c.drawString(LM, y, f'Estimate: {self._est_num}')
        y -= LINE_H * 2

        total_base = Decimal('0.00')
        for s in sections:
            base = sum(
                li.quantity * (li.remove_rate + li.replace_rate)
                for li in s.line_items.all()
                if not li.is_memo
            )
            total_base += base
        if total_base == 0:
            total_base = Decimal('1')  # avoid div/0

        for s in sections:
            base = sum(
                li.quantity * (li.remove_rate + li.replace_rate)
                for li in s.line_items.all()
                if not li.is_memo
            )
            pct = base / total_base * 100
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 8, y, s.section_label.upper())
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - 60, y, _n(base))
            c.drawRightString(RM, y, f'{float(pct):.2f}%')
            y -= LINE_H

        # Totals
        y -= LINE_H // 2
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'Subtotal of Areas')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(RM - 60, y, _n(total_base))
        c.drawRightString(RM, y, '100.00%')
        y -= LINE_H
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'Total')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(RM - 60, y, _n(total_base))
        c.drawRightString(RM, y, '100.00%')
        self.y = y - LINE_H

    # ── Recap by Category ─────────────────────────────────────────────────────

    def build_recap_by_category_page(self, sections):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        c.setFont(F_BOLD, FS_HDR)
        hdr = 'Recap by Category'
        c.drawString(LM + (RM - LM - c.stringWidth(hdr, F_BOLD, FS_HDR)) / 2, y, hdr)
        y -= LINE_H

        c.setFont(F_BODY, FS_BODY)
        c.drawString(LM, y, 'O&P Items')
        c.drawRightString(RM - 60, y, 'Total')
        c.drawRightString(RM, y, '%')
        y -= LINE_H * 2

        # Group line items by CAT
        cat_totals = {}
        grand = Decimal('0.00')
        for s in sections:
            for li in s.line_items.all():
                if li.is_memo:
                    continue
                base = li.quantity * (li.remove_rate + li.replace_rate)
                cat = li.cat.upper()
                cat_totals[cat] = cat_totals.get(cat, Decimal('0.00')) + base
                grand += base

        if grand == 0:
            grand = Decimal('1')

        for cat, total in sorted(cat_totals.items()):
            pct = total / grand * 100
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 8, y, cat)
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - 60, y, _n(total))
            c.drawRightString(RM, y, f'{float(pct):.2f}%')
            y -= LINE_H

        y -= LINE_H // 2
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'O&P Items Subtotal')
        overhead = float(est.overhead_amount)
        profit   = float(est.profit_amount)
        tax      = float(est.tax_amount)
        total_f  = float(est.line_item_total)
        grand_f  = float(est.grand_total)

        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(RM - 60, y, _n(total_f))
        c.drawRightString(RM, y, f'{(total_f/grand_f*100 if grand_f else 0):.2f}%')
        y -= LINE_H

        for label, val in [
            (f'Overhead', overhead),
            (f'Profit', profit),
            ('Total Tax', tax),
            ('Total', grand_f),
        ]:
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 8, y, label)
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - 60, y, _n(val))
            c.drawRightString(RM, y, f'{(val/grand_f*100 if grand_f else 0):.2f}%')
            y -= LINE_H

        y -= LINE_H * 3
        c.setFont(F_BOLD, FS_HDR)
        ty = 'THANK YOU'
        c.drawString(LM + (RM - LM - c.stringWidth(ty, F_BOLD, FS_HDR)) / 2, y, ty)
        self.y = y - LINE_H

    # ── Finalize ──────────────────────────────────────────────────────────────

    def save(self):
        self._draw_footer()
        self.c.save()


# ── Public API ────────────────────────────────────────────────────────────────

def generate_gc_estimate_pdf(estimate) -> io.BytesIO:
    """
    Full GC estimate PDF matching the Xactimate invoice format.
    """
    buf = io.BytesIO()
    gc  = estimate.gc_contractor
    # Use email prefix as "short name" for the one-liner header
    short = gc.email.split('@')[0].upper() if gc.email else gc.name[:20].upper()

    doc = XactimateDoc(buf, estimate, gc, company_short=short)

    # Cover page
    doc.build_cover_page()

    # Section pages
    sections = list(
        estimate.sections.prefetch_related('line_items', 'subcontractor').order_by('order')
    )
    item_counter = 1
    for section in sections:
        doc.new_page()
        item_counter = doc.build_section(section, item_counter)

    # Line item totals
    doc.build_line_totals(sections)

    # Summary pages
    doc.build_summary_page()
    doc.build_recap_taxes_page()
    doc.build_recap_by_room_page(sections)
    doc.build_recap_by_category_page(sections)

    doc.save()
    buf.seek(0)
    return buf


def generate_subcontractor_invoice_pdf(estimate, section) -> io.BytesIO:
    """
    Invoice for a single subcontractor section.
    Header shows the sub's company info. Billed-To shows the GC.
    """
    buf = io.BytesIO()
    sub = section.subcontractor
    gc  = estimate.gc_contractor

    if not sub:
        # Fall back to GC header if section is GC-direct
        sub = gc

    short = sub.email.split('@')[0].upper() if sub.email else sub.name[:20].upper()
    doc   = XactimateDoc(buf, estimate, sub, company_short=short, is_sub=True)

    # Cover page (simplified)
    doc.new_page()
    c, y = doc.c, doc.y

    c.setFont(F_BOLD, FS_HDR)
    c.drawString(LM, y, 'SUBCONTRACTOR INVOICE')
    y -= LINE_H * 2

    cli = estimate.client
    rows = [
        ('Bill To',    gc.name),
        ('GC Address', gc.address or '—'),
        ('',           f'{gc.city}, {gc.state} {gc.zip_code}' if gc.city else ''),
        ('Re: Client', cli.pOwner or '—'),
        ('Property',   cli.pAddress or '—'),
        ('Claim #',    cli.claimNumber or '—'),
        ('Estimate #', doc._est_num),
        ('Section',    section.section_label),
    ]
    for label, val in rows:
        if val:
            if label:
                c.setFont(F_BOLD, FS_BODY)
                c.drawRightString(LM + 80, y, label + ':')
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 84, y, val)
            y -= LINE_H

    doc.y = y - LINE_H

    # Section
    doc.new_page()
    doc.build_section(section, item_counter_start=1)

    # Section summary
    tax, op, tot = _section_totals(section, estimate)
    doc.check_space(LINE_H * 6)
    doc.y -= LINE_H

    c = doc.c
    for label, val in [
        ('Section Subtotal',  float(section.section_subtotal)),
        (f'Overhead ({estimate.overhead_pct}%)',  float(estimate.overhead_amount * section.section_subtotal / estimate.line_item_total if estimate.line_item_total else 0)),
        (f'Profit ({estimate.profit_pct}%)',      float(estimate.profit_amount   * section.section_subtotal / estimate.line_item_total if estimate.line_item_total else 0)),
        (f'Tax ({estimate.tax_rate}%)',            float(tax)),
        ('TOTAL DUE', float(tot)),
    ]:
        c.setFont(F_BOLD if 'TOTAL' in label else F_BODY, FS_BODY)
        c.drawString(LM + 200, doc.y, label)
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(RM, doc.y, f'${_n(val)}')
        doc.y -= LINE_H

    doc.y -= LINE_H * 3
    c.setFont(F_BODY, FS_BODY)
    c.drawString(LM, doc.y, 'Authorized Signature: ________________________')
    c.drawString(LM, doc.y - LINE_H * 2, 'Print Name:           ________________________')
    c.drawString(LM, doc.y - LINE_H * 4, 'Date:                 ________________________')

    doc.save()
    buf.seek(0)
    return buf
