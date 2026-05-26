"""
Contractor Hub — Xactimate-Format PDF Builder
==============================================
Replicates the exact layout of the Xactimate contractor invoice PDF.

GC Invoice    : All sections, O&P column, GC header. Sub info blocks inside.
Sub Invoice   : One section, NO O&P column, sub's own header. Full standalone doc.

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

# ── GC column positions (right-justified x) — includes O&P ───────────────────
COL_RMV_R  = 360
COL_REP_R  = 414
COL_TAX_R  = 463
COL_OP_R   = 509
COL_TOT_R  = 560

# ── Sub column positions (right-justified x) — NO O&P ────────────────────────
# Spread REPLACE and TAX into the space freed by removing O&P column
SUB_COL_RMV_R = 360
SUB_COL_REP_R = 432
SUB_COL_TAX_R = 492
SUB_COL_TOT_R = 560

# First-row item cols (shared)
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
        return f'{f:,.2f}' if dec == 2 else f'{f:,.0f}'
    except Exception:
        return '0.00'


def _per_line_op(li, estimate):
    """O&P amount for one line item (GC invoice only)."""
    if li.is_memo:
        return Decimal('0.00')
    base   = li.quantity * (li.remove_rate + li.replace_rate)
    op_pct = estimate.overhead_pct + estimate.profit_pct
    return (base * op_pct / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _per_line_tax(li, estimate):
    """Tax for one line item.
    GC invoice:  tax = (base + O&P) × tax_rate
    Sub invoice: tax = base × tax_rate   (sub has no O&P)
    """
    if li.is_memo or not li.taxable:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    op   = _per_line_op(li, estimate)
    return ((base + op) * estimate.tax_rate / 100).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def _per_line_tax_sub(li, estimate):
    """Tax for sub invoice — base only, no O&P markup."""
    if li.is_memo or not li.taxable:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    return (base * estimate.tax_rate / 100).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def _per_line_total(li, estimate):
    """Full line total for GC invoice (base + O&P + tax)."""
    if li.is_memo:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    return (base + _per_line_op(li, estimate) + _per_line_tax(li, estimate)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def _per_line_total_sub(li, estimate):
    """Full line total for sub invoice (base + tax only, no O&P)."""
    if li.is_memo:
        return Decimal('0.00')
    base = li.quantity * (li.remove_rate + li.replace_rate)
    return (base + _per_line_tax_sub(li, estimate)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def _section_totals_gc(section, estimate):
    """Returns (tax_sum, op_sum, total_sum) for GC invoice."""
    tax = op = tot = Decimal('0.00')
    for li in section.line_items.all():
        tax += _per_line_tax(li, estimate)
        op  += _per_line_op(li, estimate)
        tot += _per_line_total(li, estimate)
    return tax, op, tot


def _section_totals_sub(section, estimate):
    """Returns (tax_sum, total_sum) for sub invoice (no O&P)."""
    tax = tot = Decimal('0.00')
    for li in section.line_items.all():
        tax += _per_line_tax_sub(li, estimate)
        tot += _per_line_total_sub(li, estimate)
    return tax, tot


def _wrap(text, max_chars):
    """Simple word-wrap."""
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


def _today_str():
    """Date formatted as M/D/YYYY."""
    d = date.today()
    try:
        return d.strftime('%#m/%#d/%Y')   # Windows
    except Exception:
        try:
            return d.strftime('%-m/%-d/%Y')  # Unix
        except Exception:
            return d.strftime('%m/%d/%Y')


# ── XactimateDoc class ────────────────────────────────────────────────────────

class XactimateDoc:
    """
    Canvas-based Xactimate-format document builder.

    sub_doc=False → GC invoice (O&P column present)
    sub_doc=True  → Sub invoice (no O&P column; uses sub column positions)
    """

    def __init__(self, buf, estimate, company, company_short='', sub_doc=False):
        self.c             = rl_canvas.Canvas(buf, pagesize=letter)
        self.estimate      = estimate
        self.company       = company
        self.company_short = company_short or company.name
        self.sub_doc       = sub_doc
        self.page_num      = 0
        self._est_num      = estimate.estimate_number or f'EST-{str(estimate.id)[:8].upper()}'
        self._today        = _today_str()
        self.y             = BODY_TOP

    # ── Column helpers ────────────────────────────────────────────────────────

    def _rmv_r(self):  return SUB_COL_RMV_R if self.sub_doc else COL_RMV_R
    def _rep_r(self):  return SUB_COL_REP_R if self.sub_doc else COL_REP_R
    def _tax_r(self):  return SUB_COL_TAX_R if self.sub_doc else COL_TAX_R
    def _tot_r(self):  return SUB_COL_TOT_R if self.sub_doc else COL_TOT_R

    # ── Page management ───────────────────────────────────────────────────────

    def new_page(self):
        if self.page_num > 0:
            self._draw_footer()
            self.c.showPage()
        self.page_num += 1
        self._draw_header()
        self.y = BODY_TOP

    def check_space(self, need=LINE_H * 3):
        if self.y - need < BODY_BTM:
            self.new_page()

    # ── Header / footer ───────────────────────────────────────────────────────

    def _draw_header(self):
        c  = self.c
        co = self.company

        # Page number top-left
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
        if co.phone:
            ph = co.phone
            if co.contact_person:
                ph += f' {co.contact_person.upper()}'
            lines.append(ph)
        if co.email:
            lines.append(co.email.upper())
        if co.certification:
            lines.append(co.certification)

        for line in lines:
            if line.strip():
                c.drawString(x, y, line)
            y -= HDR_LINE_H

        # Rule under header
        c.setLineWidth(0.5)
        c.line(LM, HDR_RULE_Y, RM, HDR_RULE_Y)

    def _draw_footer(self):
        c = self.c
        c.setLineWidth(0.5)
        c.line(LM, FTR_RULE_Y, RM, FTR_RULE_Y)
        c.setFont(F_BODY, FS_SM)
        c.drawString(LM, FTR_Y, self._est_num)
        c.drawRightString(RM, FTR_Y, f'{self._today}    Page: {self.page_num}')

    # ── Low-level draw ────────────────────────────────────────────────────────

    def _text(self, x, y, text, font=F_BODY, size=FS_BODY, bold=False):
        self.c.setFont(F_BOLD if bold else font, size)
        self.c.drawString(x, y, str(text))

    def _text_r(self, x, y, text, font=F_MONO, size=FS_BODY):
        self.c.setFont(font, size)
        self.c.drawRightString(x, y, str(text))

    def _rule(self, y=None):
        if y is None:
            y = self.y
        self.c.setLineWidth(0.3)
        self.c.line(LM + 4, y, RM, y)

    def _separator(self, char='='):
        self.c.setFont(F_MONO, FS_SM)
        n = int((RM - LM) / 5.4)
        self.c.drawString(LM, self.y, char * n)
        self.y -= LINE_H

    def _section_heading(self, label, continued=False):
        self.check_space(LINE_H * 4)
        self.y -= LINE_H
        full = (('CONTINUED - ' if continued else '') + label).upper()
        self.c.setFont(F_BOLD, FS_BODY)
        w = self.c.stringWidth(full, F_BOLD, FS_BODY)
        self.c.drawString(LM + (RM - LM - w) / 2, self.y, full)
        self.y -= LINE_H * 2

    def _col_headers(self):
        """Draw the two-row column header. Sub docs omit O&P."""
        c, y = self.c, self.y
        c.setFont(F_BODY, FS_BODY)
        c.drawString(COL_CAT,      y, 'CAT')
        c.drawString(COL_SEL,      y, 'SEL')
        c.drawString(COL_SIGN + 2, y, 'ACT DESCRIPTION')
        y -= LINE_H
        c.drawString(COL_CALC, y, 'CALC')
        c.drawRightString(COL_QTY_R,    y, 'QTY')
        c.drawRightString(self._rmv_r(), y, 'REMOVE')
        c.drawRightString(self._rep_r(), y, 'REPLACE')
        c.drawRightString(self._tax_r(), y, 'TAX')
        if not self.sub_doc:
            c.drawRightString(COL_OP_R, y, 'O&P')
        c.drawRightString(self._tot_r(), y, 'TOTAL')
        self.y = y - LINE_H

    # ── Subcontractor info block ──────────────────────────────────────────────

    def _sub_block(self, sub):
        self.check_space(LINE_H * 7)
        self._separator('.')
        self._text(LM, self.y, '.............. SUBCONTRACTOR ..................')
        self.y -= LINE_H * 2
        c = self.c
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, self.y, f'{sub.name.upper()}  EIN # {sub.ein}')
        self.y -= LINE_H
        c.setFont(F_BODY, FS_BODY)
        for line in [
            sub.address,
            f'{sub.city}, {sub.state} {sub.zip_code}' if sub.city else '',
            (sub.phone + (' ' + sub.contact_person if sub.contact_person else '')) if sub.phone else '',
            sub.email,
        ]:
            if line and line.strip():
                c.drawString(LM + 4, self.y, line)
                self.y -= LINE_H
        if sub.certification:
            c.drawString(LM + 4, self.y, sub.certification)
            self.y -= LINE_H
        self._separator()

    # ── One line item (2-row format) ──────────────────────────────────────────

    def _line_item(self, num, li, estimate):
        """Render one line item. Sub docs skip the O&P value."""
        need = LINE_H * 2 + (LINE_H * len(_wrap(li.notes, 90)) if li.notes else 0)
        self.check_space(need + LINE_H)

        if self.sub_doc:
            op    = Decimal('0.00')
            tax   = _per_line_tax_sub(li, estimate)
            total = _per_line_total_sub(li, estimate)
        else:
            op    = _per_line_op(li, estimate)
            tax   = _per_line_tax(li, estimate)
            total = _per_line_total(li, estimate)

        c = self.c

        # Row 1: number, CAT, SEL, sign, description
        y = self.y
        c.setFont(F_BODY, FS_BODY)
        c.drawRightString(COL_NUM_R, y, f'{num}.')
        c.setFont(F_BOLD, FS_SM)
        c.drawString(COL_CAT, y, li.cat)
        c.drawString(COL_SEL, y, li.sel)

        sign = '-' if (li.remove_rate > 0 and li.replace_rate == 0) else '+'
        bid_marker = ''
        if li.is_bid_item:
            bid_marker = '[*E]' if not li.taxable else '[*]'
        c.setFont(F_BODY, FS_BODY)
        c.drawString(COL_SIGN, y, sign)
        if bid_marker:
            c.drawString(COL_SIGN + 8, y, bid_marker)

        desc_lines = _wrap(li.description, 70)
        c.drawString(COL_DESC + (22 if bid_marker else 0), y, desc_lines[0])
        self.y -= LINE_H

        for extra in desc_lines[1:]:
            self.check_space(LINE_H)
            c.drawString(COL_DESC, self.y, extra)
            self.y -= LINE_H

        # Row 2: calc/qty | numbers
        y2 = self.y
        c.setFont(F_MONO, FS_SM)
        calc_str = f'{li.calc_formula} ' if li.calc_formula else ''
        c.drawString(COL_CALC, y2, calc_str + f'{_n(li.quantity)}{li.unit}')

        if not li.is_memo:
            c.drawRightString(self._rmv_r(), y2, _n(li.remove_rate))
            c.drawString(self._rmv_r() + 2, y2, '+')
            c.drawRightString(self._rep_r(), y2, _n(li.replace_rate))
            c.drawString(self._rep_r() + 2, y2, '=')
            c.drawRightString(self._tax_r(), y2, _n(tax))
            if not self.sub_doc:
                c.drawRightString(COL_OP_R, y2, _n(op))
            c.drawRightString(self._tot_r(), y2, _n(total))

        self.y -= LINE_H

        if li.notes:
            c.setFont(F_BODY, FS_SM)
            for note_line in _wrap(li.notes, 90):
                self.check_space(LINE_H)
                c.drawString(COL_DESC, self.y, note_line)
                self.y -= LINE_H

    # ── Section total line ────────────────────────────────────────────────────

    def _section_total(self, label, tax, op, total):
        """GC section total (tax + O&P + total)."""
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

    def _section_total_sub(self, label, tax, total):
        """Sub section total (tax + total, no O&P)."""
        self.check_space(LINE_H * 2)
        self.y -= LINE_H // 2
        c = self.c
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, self.y, f'Totals: {label}')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(SUB_COL_TAX_R, self.y, _n(tax))
        c.drawRightString(SUB_COL_TOT_R, self.y, _n(total))
        self.y -= LINE_H * 2

    # ── Signature block ───────────────────────────────────────────────────────

    def _signature_block(self, name=''):
        """Formal signature block — added to every contract's Summary page."""
        self.check_space(LINE_H * 8)
        self.y -= LINE_H * 2
        c = self.c
        c.setFont(F_BODY, FS_BODY)
        line_w = 180

        rows = [
            ('Authorized Signature', ''),
            ('Print Name',           name.upper() if name else ''),
            ('Date',                 ''),
            ('Title',                ''),
        ]
        for label, prefill in rows:
            c.setFont(F_BOLD, FS_BODY)
            c.drawString(LM, self.y, f'{label}:')
            x_start = LM + 120
            if prefill:
                c.setFont(F_BODY, FS_BODY)
                c.drawString(x_start, self.y, prefill)
            # Underline
            c.setLineWidth(0.5)
            c.line(x_start, self.y - 2, x_start + line_w, self.y - 2)
            self.y -= LINE_H * 2

    # ── Cover page ────────────────────────────────────────────────────────────

    def build_cover_page(self):
        self.new_page()
        c     = self.c
        est   = self.estimate
        cli   = est.client

        def kv(label, value, label2='', value2=''):
            c.setFont(F_BOLD, FS_BODY)
            c.drawRightString(LM + 90, self.y, label + ':')
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, self.y, str(value))
            if label2:
                c.setFont(F_BOLD, FS_BODY)
                c.drawRightString(LM + 350, self.y, label2 + ':')
                c.setFont(F_BODY, FS_BODY)
                c.drawString(LM + 354, self.y, str(value2))
            self.y -= LINE_H

        phone = cli.cPhone or cli.DAPhone or ''
        kv('Client',   cli.pOwner or '—',    'Home', phone)
        kv('Billing',  cli.pAddress or '—')
        if cli.pCityStateZip:
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, self.y, cli.pCityStateZip)
            self.y -= LINE_H
        kv('Home',     cli.pAddress or '—')
        if cli.pCityStateZip:
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, self.y, cli.pCityStateZip)
            self.y -= LINE_H
        kv('Property', cli.pAddress or '—')
        if cli.pCityStateZip:
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 94, self.y, cli.pCityStateZip)
            self.y -= LINE_H
        self.y -= LINE_H

        estimator = est.estimator
        if estimator:
            kv('Operator', (estimator.email or '').split('@')[0].upper())
            self.y -= LINE_H
            kv('Estimator', estimator.contact_person or estimator.name,
               'Business', estimator.phone or '')
            kv('Company',   estimator.name, 'E-mail', estimator.email or '')
            kv('Business',  estimator.address or '')
            if estimator.city:
                c.setFont(F_BODY, FS_BODY)
                c.drawString(LM + 94, self.y,
                             f'{estimator.city}, {estimator.state} {estimator.zip_code}')
                self.y -= LINE_H
        self.y -= LINE_H

        kv('Reference', '', 'Business', cli.DAPhone or cli.fieldAdjEmail or '')
        kv('Company',   cli.insuranceCo_Name or '—',
           'E-mail',    cli.DAEmail or cli.fieldAdjEmail or '')
        self.y -= LINE_H

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
        ty = 'THANK YOU'
        cx = LM + (RM - LM - c.stringWidth(ty, F_BOLD, FS_HDR)) / 2
        c.drawString(cx, self.y, ty)

    # ── Section pages (shared by GC and sub) ─────────────────────────────────

    def build_section(self, section, item_counter_start=1):
        """Build pages for one section. Returns next item counter."""
        est   = self.estimate
        label = section.section_label
        sub   = section.subcontractor

        self.check_space(LINE_H * 8)
        self._section_heading(label, continued=False)

        c = self.c
        c.setFont(F_BODY, FS_BODY)
        nw = c.stringWidth(self._est_num, F_BODY, FS_BODY)
        c.drawString(LM + (RM - LM - nw) / 2, self.y, self._est_num)
        self.y -= LINE_H

        self._col_headers()

        # Sub info block inside GC invoice only
        if sub and not self.sub_doc:
            self._sub_block(sub)

        self._separator()

        item_num = item_counter_start
        for li in section.line_items.order_by('order'):
            if self.y - LINE_H * 4 < BODY_BTM:
                self.new_page()
                self._section_heading(label, continued=True)
                self._col_headers()
            self._line_item(item_num, li, est)
            item_num += 1

        if self.sub_doc:
            tax, tot = _section_totals_sub(section, est)
            self._section_total_sub(label, tax, tot)
        else:
            tax, op, tot = _section_totals_gc(section, est)
            self._section_total(label, tax, op, tot)

        return item_num

    # ── Line item totals line (GC only) ───────────────────────────────────────

    def build_line_totals(self, sections):
        total_tax = total_op = total_tot = Decimal('0.00')
        for s in sections:
            t, o, tt = _section_totals_gc(s, self.estimate)
            total_tax += t
            total_op  += o
            total_tot += tt

        self.check_space(LINE_H * 3)
        self.y -= LINE_H
        c = self.c
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, self.y, f'Line Item Totals: {self._est_num}')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(COL_TAX_R, self.y, _n(total_tax))
        c.drawRightString(COL_OP_R,  self.y, _n(total_op))
        c.drawRightString(COL_TOT_R, self.y, _n(total_tot))
        self.y -= LINE_H * 2
        return total_tax, total_op, total_tot

    # ── Summary page (GC — includes overhead, profit, O&P) ───────────────────

    def build_summary_page(self):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

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
            ('Line Item Total',        li_total, False),
            ('Overhead',               overhead, False),
            ('Profit',                 profit,   False),
            ('Total Tax',              tax,      False),
            ('',                       None,     False),
            ('Replacement Cost Value', rcv,      True),
            ('Net Claim',              rcv,      True),
        ]
        for label, val, bold in rows:
            if val is None:
                y -= LINE_H
                continue
            c.setFont(F_BOLD if bold else F_BODY, FS_BODY)
            c.drawString(LM + (0 if bold else 20), y, label)
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - (0 if bold else 20), y,
                              f'${_n(val)}' if bold else _n(val))
            y -= LINE_H

        # Estimator name (centered, bold) — matches real documents
        y -= LINE_H * 2
        gc_name = ''
        if est.estimator and est.estimator.contact_person:
            gc_name = est.estimator.contact_person
        elif est.gc_contractor:
            gc_name = est.gc_contractor.contact_person or est.gc_contractor.name
        if gc_name:
            c.setFont(F_BOLD, FS_HDR)
            sw = c.stringWidth(gc_name.upper(), F_BOLD, FS_HDR)
            c.drawString(LM + (RM - LM - sw) / 2, y, gc_name.upper())
            y -= LINE_H * 2

        self.y = y
        # Formal signature block on every contract
        self._signature_block(name=gc_name)

    # ── Summary page (Sub — no overhead/profit, just tax) ────────────────────

    def build_sub_summary_page(self, section):
        """Sub invoice Summary: Line Item Total + Total Tax = RCV. Then signature."""
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        c.setFont(F_BOLD, FS_HDR)
        hdr_w = c.stringWidth('Summary', F_BOLD, FS_HDR)
        c.drawString(LM + (RM - LM - hdr_w) / 2, y, 'Summary')
        y -= LINE_H * 2

        tax, tot = _section_totals_sub(section, est)
        base = tot - tax
        rcv  = float(tot)

        rows = [
            ('Line Item Total', float(base), False),
            ('Total Tax',       float(tax),  False),
            ('',                None,        False),
            ('Replacement Cost Value', rcv,  True),
            ('Net Claim',              rcv,  True),
        ]
        for label, val, bold in rows:
            if val is None:
                y -= LINE_H
                continue
            c.setFont(F_BOLD if bold else F_BODY, FS_BODY)
            c.drawString(LM + (0 if bold else 20), y, label)
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - (0 if bold else 20), y,
                              f'${_n(val)}' if bold else _n(val))
            y -= LINE_H

        # Estimator name centered (matches real sub docs — just "JOE JONES")
        y -= LINE_H * 2
        estimator_name = ''
        if est.estimator and est.estimator.contact_person:
            estimator_name = est.estimator.contact_person
        elif est.estimator:
            estimator_name = est.estimator.name
        if estimator_name:
            c.setFont(F_BOLD, FS_HDR)
            sw = c.stringWidth(estimator_name.upper(), F_BOLD, FS_HDR)
            c.drawString(LM + (RM - LM - sw) / 2, y, estimator_name.upper())
            y -= LINE_H * 2

        self.y = y
        # Formal signature block
        sub_name = section.subcontractor.contact_person if section.subcontractor else ''
        self._signature_block(name=sub_name or estimator_name)

    # ── Recap of Taxes ────────────────────────────────────────────────────────

    def build_recap_taxes_page(self, section=None):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        hdr = 'Recap of Taxes'
        c.setFont(F_BOLD, FS_HDR)
        c.drawString(LM + (RM - LM - c.stringWidth(hdr, F_BOLD, FS_HDR)) / 2, y, hdr)
        y -= LINE_H * 3

        if self.sub_doc and section:
            tax, tot = _section_totals_sub(section, est)
            tax_f    = float(tax)
        else:
            tax_f = float(est.tax_amount)

        c.setFont(F_BOLD, FS_BODY)
        c.drawRightString(LM + 480, y, f'Total Tax ({est.tax_rate}%)')
        y -= LINE_H
        c.setFont(F_BODY, FS_BODY)
        c.drawString(LM, y, 'Line Items')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(LM + 480, y, _n(tax_f))
        y -= LINE_H
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'Total')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(LM + 480, y, _n(tax_f))
        self.y = y - LINE_H

    # ── Recap by Room ─────────────────────────────────────────────────────────

    def build_recap_by_room_page(self, sections):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        hdr = 'Recap by Room'
        c.setFont(F_BOLD, FS_HDR)
        c.drawString(LM + (RM - LM - c.stringWidth(hdr, F_BOLD, FS_HDR)) / 2, y, hdr)
        y -= LINE_H
        c.setFont(F_BODY, FS_BODY)
        c.drawString(LM, y, f'Estimate: {self._est_num}')
        y -= LINE_H * 2

        totals = {}
        grand  = Decimal('0.00')
        for s in sections:
            base = sum(
                li.quantity * (li.remove_rate + li.replace_rate)
                for li in s.line_items.all() if not li.is_memo
            )
            totals[s.pk] = base
            grand += base
        if grand == 0:
            grand = Decimal('1')

        for s in sections:
            base = totals[s.pk]
            pct  = base / grand * 100
            c.setFont(F_BODY, FS_BODY)
            c.drawString(LM + 8, y, s.section_label.upper())
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - 60, y, _n(base))
            c.drawRightString(RM, y, f'{float(pct):.2f}%')
            y -= LINE_H

        y -= LINE_H // 2
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'Subtotal of Areas')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(RM - 60, y, _n(grand))
        c.drawRightString(RM, y, '100.00%')
        y -= LINE_H
        c.setFont(F_BOLD, FS_BODY)
        c.drawString(LM, y, 'Total')
        c.setFont(F_MONO, FS_BODY)
        c.drawRightString(RM - 60, y, _n(grand))
        c.drawRightString(RM, y, '100.00%')
        self.y = y - LINE_H

    # ── Recap by Category ─────────────────────────────────────────────────────

    def build_recap_by_category_page(self, sections):
        est = self.estimate
        self.new_page()
        c, y = self.c, self.y

        hdr = 'Recap by Category'
        c.setFont(F_BOLD, FS_HDR)
        c.drawString(LM + (RM - LM - c.stringWidth(hdr, F_BOLD, FS_HDR)) / 2, y, hdr)
        y -= LINE_H
        c.setFont(F_BODY, FS_BODY)
        c.drawString(LM, y, 'O&P Items' if not self.sub_doc else 'Items')
        c.drawRightString(RM - 60, y, 'Total')
        c.drawRightString(RM, y, '%')
        y -= LINE_H * 2

        cat_totals = {}
        grand = Decimal('0.00')
        for s in sections:
            for li in s.line_items.all():
                if li.is_memo:
                    continue
                base = li.quantity * (li.remove_rate + li.replace_rate)
                cat  = li.cat.upper()
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
        grand_f = float(grand)

        if self.sub_doc:
            c.setFont(F_BOLD, FS_BODY)
            c.drawString(LM, y, 'Subtotal')
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - 60, y, _n(grand_f))
            c.drawRightString(RM, y, '100.00%')
        else:
            overhead  = float(est.overhead_amount)
            profit    = float(est.profit_amount)
            tax       = float(est.tax_amount)
            total_f   = float(est.line_item_total)
            grand_doc = float(est.grand_total)

            c.setFont(F_BOLD, FS_BODY)
            c.drawString(LM, y, 'O&P Items Subtotal')
            c.setFont(F_MONO, FS_BODY)
            c.drawRightString(RM - 60, y, _n(total_f))
            c.drawRightString(RM, y, f'{(total_f / grand_doc * 100 if grand_doc else 0):.2f}%')
            y -= LINE_H
            for label, val in [('Overhead', overhead), ('Profit', profit),
                                ('Total Tax', tax), ('Total', grand_doc)]:
                c.setFont(F_BODY, FS_BODY)
                c.drawString(LM + 8, y, label)
                c.setFont(F_MONO, FS_BODY)
                c.drawRightString(RM - 60, y, _n(val))
                c.drawRightString(RM, y, f'{(val / grand_doc * 100 if grand_doc else 0):.2f}%')
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
    Full GC estimate PDF.
    Header = GC company. Columns include O&P. All sections.
    Sub info blocks appear inside each section.
    """
    buf   = io.BytesIO()
    gc    = estimate.gc_contractor
    short = gc.email.split('@')[0].upper() if gc.email else gc.name[:20].upper()

    doc = XactimateDoc(buf, estimate, gc, company_short=short, sub_doc=False)
    doc.build_cover_page()

    sections     = list(
        estimate.sections.prefetch_related('line_items', 'subcontractor').order_by('order')
    )
    item_counter = 1
    for section in sections:
        doc.new_page()
        item_counter = doc.build_section(section, item_counter)

    doc.build_line_totals(sections)
    doc.build_summary_page()
    doc.build_recap_taxes_page()
    doc.build_recap_by_room_page(sections)
    doc.build_recap_by_category_page(sections)

    doc.save()
    buf.seek(0)
    return buf


def generate_subcontractor_invoice_pdf(estimate, section) -> io.BytesIO:
    """
    Standalone sub invoice for one section.

    - Header = the sub's own company (not the GC)
    - Columns: REMOVE | REPLACE | TAX | TOTAL  (NO O&P — subs don't add O&P)
    - Tax = base × tax_rate  (no O&P markup in the base)
    - Full standalone document: cover → section → summary → recap pages
    - Signature block on summary page
    """
    buf = io.BytesIO()
    sub = section.subcontractor or estimate.gc_contractor   # fall back to GC if GC-direct
    gc  = estimate.gc_contractor

    short = sub.email.split('@')[0].upper() if sub.email else sub.name[:20].upper()

    doc = XactimateDoc(buf, estimate, sub, company_short=short, sub_doc=True)

    # Cover page — identical structure to GC cover but with sub's company in header
    doc.build_cover_page()

    # Section pages (single section)
    doc.new_page()
    doc.build_section(section, item_counter_start=1)

    # Line item totals line
    tax, tot = _section_totals_sub(section, estimate)
    doc.check_space(LINE_H * 3)
    doc.y -= LINE_H
    c = doc.c
    c.setFont(F_BOLD, FS_BODY)
    c.drawString(LM, doc.y, f'Line Item Totals: {doc._est_num}')
    c.setFont(F_MONO, FS_BODY)
    c.drawRightString(SUB_COL_TAX_R, doc.y, _n(tax))
    c.drawRightString(SUB_COL_TOT_R, doc.y, _n(tot))
    doc.y -= LINE_H * 2

    # Summary, recaps, signature
    doc.build_sub_summary_page(section)
    doc.build_recap_taxes_page(section=section)
    doc.build_recap_by_room_page([section])
    doc.build_recap_by_category_page([section])

    doc.save()
    buf.seek(0)
    return buf
