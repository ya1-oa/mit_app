"""
Contractor Bid Hub — Models

Key concepts:
  Contractor   = any company doing work (GC or sub). NOT the same as docsAppR.Client.
  Client       = docsAppR.Client — the homeowner / insurance claimant.
  GCEstimate   = one per claim. Links Client → GC Contractor. Contains 8 fixed sections.
  GCSection    = one of the 8 fixed sections. Optionally linked to a sub Contractor.
  GCLineItem   = individual Xactimate line item inside a section.
  RateItem     = seeded rate library (all standard Xactimate codes + rates).
"""

import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings


# ---------------------------------------------------------------------------
# Contractor Registry
# ---------------------------------------------------------------------------

class ContractorRole(models.TextChoices):
    GC             = 'gc',            'General Contractor'
    ESTIMATOR      = 'estimator',     'Estimator / Project Manager'
    PACKING        = 'packing',       'CPS Packing & Evaluation'
    ADMINISTRATIVE = 'administrative','Administrative Services'
    STORAGE        = 'storage',       'Storage'
    CLEANING       = 'cleaning',      'Contents Cleaning'
    DEMO           = 'demo',          'Demo & Rubbish Removal'
    TRANSPORT      = 'transport',     'Transport'
    OTHER          = 'other',         'Other'


class Contractor(models.Model):
    """
    A company that performs work on a claim — either the GC or a subcontractor.
    This is NOT docsAppR.Client (which is the homeowner/insured).
    """
    name            = models.CharField(max_length=255)
    ein             = models.CharField(max_length=20, blank=True, verbose_name='EIN / TIN')
    role            = models.CharField(max_length=30, choices=ContractorRole.choices, default=ContractorRole.OTHER)
    address         = models.CharField(max_length=500, blank=True)
    city            = models.CharField(max_length=100, blank=True)
    state           = models.CharField(max_length=50, blank=True)
    zip_code        = models.CharField(max_length=20, blank=True)
    phone           = models.CharField(max_length=50, blank=True)
    phone2          = models.CharField(max_length=50, blank=True)
    email           = models.EmailField(blank=True)
    email2          = models.EmailField(blank=True)
    website         = models.URLField(blank=True)
    contact_person  = models.CharField(max_length=255, blank=True)
    certification   = models.CharField(max_length=500, blank=True, help_text='e.g., Lead Paint Cert#')
    notes           = models.TextField(blank=True)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        ein = f' (EIN {self.ein})' if self.ein else ''
        return f'{self.name}{ein}'

    @property
    def full_address(self):
        parts = [self.address, self.city, self.state, self.zip_code]
        return ', '.join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Rate Library (seeded — all standard Xactimate line item rates)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Price List Version (tracks every import)
# ---------------------------------------------------------------------------

class PriceListVersion(models.Model):
    """
    Tracks each Xactimate price list import.
    One record per import run (e.g. OHCL8X_MAR26, OHCL8X_JUN26).
    """
    code            = models.CharField(max_length=50, unique=True,
                                       help_text='e.g. OHCL8X_MAR26')
    market          = models.CharField(max_length=100, blank=True,
                                       help_text='e.g. Ohio - Cleveland')
    effective_date  = models.DateField(null=True, blank=True)
    source_file     = models.CharField(max_length=500, blank=True)
    total_items     = models.PositiveIntegerField(default=0)
    items_created   = models.PositiveIntegerField(default=0)
    items_updated   = models.PositiveIntegerField(default=0)
    items_skipped   = models.PositiveIntegerField(default=0)
    imported_at     = models.DateTimeField(auto_now_add=True)
    imported_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='imported_price_lists',
    )
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['-imported_at']
        verbose_name = 'Price List Version'

    def __str__(self):
        return self.code


# ---------------------------------------------------------------------------
# Rate Item
# ---------------------------------------------------------------------------

class RateItem(models.Model):
    """
    Standard Xactimate rate library.
    Seeded via seed_contractor_hub, updated via import_price_list.
    Rates come directly from the Xactimate price list (e.g. OHCL8X_MAR26).
    """
    UNIT_CHOICES = [
        ('EA', 'Each (EA)'),
        ('HR', 'Hour (HR)'),
        ('LF', 'Linear Foot (LF)'),
        ('SF', 'Square Foot (SF)'),
        ('CF', 'Cubic Foot (CF)'),
        ('MO', 'Month (MO)'),
        ('LS', 'Lump Sum (LS)'),
    ]

    cat                  = models.CharField(max_length=10, verbose_name='CAT')
    sel                  = models.CharField(max_length=20, verbose_name='SEL')
    description          = models.CharField(max_length=500)
    unit                 = models.CharField(max_length=5, choices=UNIT_CHOICES, default='EA')
    remove_rate          = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    replace_rate         = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxable              = models.BooleanField(default=True)
    is_bid_item          = models.BooleanField(default=False,
                                               help_text='[*] bid item — qty locked to 1, rate is total')
    section_hint         = models.CharField(max_length=30, blank=True,
                                            help_text='Which section this rate typically belongs to')

    # Price list tracking
    price_list_version   = models.ForeignKey(
        PriceListVersion,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rate_items',
    )
    previous_replace_rate = models.DecimalField(max_digits=10, decimal_places=2,
                                                null=True, blank=True)
    previous_remove_rate  = models.DecimalField(max_digits=10, decimal_places=2,
                                                null=True, blank=True)
    last_updated_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['cat', 'sel']
        unique_together = [('cat', 'sel')]
        verbose_name = 'Rate Item'

    def __str__(self):
        return f'{self.cat} {self.sel} — {self.description} ({self.unit})'

    @property
    def rate_changed(self):
        """True if the last import changed this rate."""
        if self.previous_replace_rate is None:
            return False
        return self.replace_rate != self.previous_replace_rate or \
               self.remove_rate != self.previous_remove_rate


# ---------------------------------------------------------------------------
# GC Estimate
# ---------------------------------------------------------------------------

class EstimateStatus(models.TextChoices):
    DRAFT       = 'draft',       'Draft'
    SUBMITTED   = 'submitted',   'Submitted to Insurance'
    APPROVED    = 'approved',    'Approved'
    BILLED      = 'billed',      'Billed'
    PAID        = 'paid',        'Paid'
    CANCELLED   = 'cancelled',   'Cancelled'


class GCEstimate(models.Model):
    """
    One GC estimate per insurance claim (one per Client).
    The GC is a Contractor record — NOT the homeowner Client.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The claim this estimate is for (homeowner)
    client          = models.ForeignKey(
        'docsAppR.Client',
        on_delete=models.CASCADE,
        related_name='gc_estimates',
    )
    # The GC performing the work
    gc_contractor   = models.ForeignKey(
        Contractor,
        on_delete=models.PROTECT,
        related_name='gc_estimates',
        limit_choices_to={'role': ContractorRole.GC},
    )
    # Estimator / project manager (may differ from GC)
    estimator       = models.ForeignKey(
        Contractor,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='estimated_jobs',
        limit_choices_to={'role': ContractorRole.ESTIMATOR},
    )

    # Estimate metadata
    estimate_number = models.CharField(max_length=100, blank=True,
                                       help_text='e.g., OH26Q-HAYNES-CPS-PK1')
    price_list      = models.CharField(max_length=50, blank=True,
                                       help_text='e.g., OHCL8X_MAR26')
    type_of_estimate= models.CharField(max_length=50, blank=True, default='Fire')
    date_entered    = models.DateField(null=True, blank=True)

    # Financial settings (standardized)
    overhead_pct    = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    profit_pct      = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    tax_rate        = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8.25'))

    status          = models.CharField(max_length=20, choices=EstimateStatus.choices,
                                       default=EstimateStatus.DRAFT)
    notes           = models.TextField(blank=True)

    created_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_gc_estimates',
    )
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Enforce one active estimate per client
        constraints = [
            models.UniqueConstraint(
                fields=['client'],
                condition=models.Q(status__in=['draft', 'submitted', 'approved', 'billed']),
                name='one_active_estimate_per_client',
            )
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['client', 'status']),
        ]

    def __str__(self):
        return f'{self.estimate_number or self.id} — {self.client}'

    # ── Computed totals ──────────────────────────────────────────────────────

    @property
    def line_item_total(self):
        """Sum of all section pre-OP subtotals."""
        return sum(s.section_subtotal for s in self.sections.all())

    @property
    def overhead_amount(self):
        return (self.line_item_total * self.overhead_pct / 100).quantize(Decimal('0.01'))

    @property
    def profit_amount(self):
        return (self.line_item_total * self.profit_pct / 100).quantize(Decimal('0.01'))

    @property
    def tax_amount(self):
        taxable = sum(
            li.line_total
            for s in self.sections.all()
            for li in s.line_items.filter(taxable=True)
        )
        return (taxable * self.tax_rate / 100).quantize(Decimal('0.01'))

    @property
    def grand_total(self):
        return self.line_item_total + self.overhead_amount + self.profit_amount + self.tax_amount


# ---------------------------------------------------------------------------
# GC Estimate Sections (8 fixed, pre-seeded per estimate)
# ---------------------------------------------------------------------------

class SectionType(models.TextChoices):
    EXHAUST      = 'exhaust',      'Exhaust Per Level'
    ADMIN        = 'admin',        'Administrative Expenses'
    PACKING      = 'packing',      'CPS Packing Handling & Evaluation'
    TRANSPORT    = 'transport',    'Transporting Contents'
    STORAGE      = 'storage',      'Storage Info Contents'
    CLEANING     = 'cleaning',     'Contents Cleaning'
    DEMO         = 'demo',         'DMO & Rubbish Removal'
    PORCHES      = 'porches',      'Porches Exterior'


# Fixed ordering for all estimates
SECTION_ORDER = {
    SectionType.EXHAUST:   1,
    SectionType.ADMIN:     2,
    SectionType.PACKING:   3,
    SectionType.TRANSPORT: 4,
    SectionType.STORAGE:   5,
    SectionType.CLEANING:  6,
    SectionType.DEMO:      7,
    SectionType.PORCHES:   8,
}

# Which sections are GC-direct vs subcontracted
SUBCONTRACTED_SECTIONS = {
    SectionType.ADMIN,
    SectionType.PACKING,
    SectionType.STORAGE,
    SectionType.CLEANING,
    SectionType.DEMO,
}


class GCSection(models.Model):
    """
    One of the 8 fixed trade sections within a GCEstimate.
    Subcontracted sections have a linked Contractor (the sub).
    GC-direct sections (exhaust, transport, porches) have no sub.
    """
    estimate        = models.ForeignKey(GCEstimate, on_delete=models.CASCADE,
                                        related_name='sections')
    section_type    = models.CharField(max_length=20, choices=SectionType.choices)
    order           = models.PositiveIntegerField(default=0)  # controlled by SECTION_ORDER

    # Subcontractor (null for GC-direct sections)
    subcontractor   = models.ForeignKey(
        Contractor,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_sections',
    )

    # Bid status (for subcontracted sections)
    class BidStatus(models.TextChoices):
        PENDING   = 'pending',   'Pending'
        SENT      = 'sent',      'Sent to Sub'
        ACCEPTED  = 'accepted',  'Accepted'
        REJECTED  = 'rejected',  'Rejected'

    bid_status      = models.CharField(max_length=20, choices=BidStatus.choices,
                                       default=BidStatus.PENDING)
    bid_accepted_at = models.DateTimeField(null=True, blank=True)
    notes           = models.TextField(blank=True)

    class Meta:
        ordering = ['order']
        unique_together = [('estimate', 'section_type')]

    def __str__(self):
        return f'{self.get_section_type_display()} — {self.estimate}'

    @property
    def is_subcontracted(self):
        return self.section_type in SUBCONTRACTED_SECTIONS

    @property
    def section_subtotal(self):
        """Pre-O&P, pre-tax sum of all line items in this section."""
        return sum(li.line_total for li in self.line_items.all())

    @property
    def section_label(self):
        """The exact heading text used in the PDF."""
        labels = {
            SectionType.EXHAUST:   'EXHAUST PER LEVEL',
            SectionType.ADMIN:     'ADMINISTRATIVE EXPENSES ..... PER LEVEL',
            SectionType.PACKING:   'CPS PACKING HANDLING & EVALUATION',
            SectionType.TRANSPORT: 'TRANSPORTING CONTENTS',
            SectionType.STORAGE:   'STORAGE INFO CONTENTS',
            SectionType.CLEANING:  'CONTENTS CLEANING',
            SectionType.DEMO:      'DMO & RUBBISH REMOVAL',
            SectionType.PORCHES:   'PORCHES EXTERIOR',
        }
        return labels.get(self.section_type, self.get_section_type_display())


# ---------------------------------------------------------------------------
# GC Line Items
# ---------------------------------------------------------------------------

class GCLineItem(models.Model):
    """
    One Xactimate row inside a GCSection.
    Columns: CAT | SEL | DESCRIPTION | CALC | QTY | REMOVE | REPLACE | TAX | O&P | TOTAL
    O&P and tax are computed at the estimate level, not per line.
    """
    section         = models.ForeignKey(GCSection, on_delete=models.CASCADE,
                                        related_name='line_items')
    rate_item       = models.ForeignKey(RateItem, on_delete=models.PROTECT,
                                        null=True, blank=True,
                                        related_name='used_in_lines')

    # Xactimate columns
    cat             = models.CharField(max_length=10)
    sel             = models.CharField(max_length=20)
    description     = models.CharField(max_length=500)
    calc_formula    = models.CharField(max_length=100, blank=True,
                                       help_text='e.g., LL*.3*2, 4*4*30, F*.065')
    quantity        = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    unit            = models.CharField(max_length=5, default='EA')
    remove_rate     = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    replace_rate    = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxable         = models.BooleanField(default=True)
    is_bid_item     = models.BooleanField(default=False,
                                          help_text='[*] marker — single bid amount from sub')
    is_memo         = models.BooleanField(default=False,
                                          help_text='Zero-dollar descriptive/separator line')
    order           = models.PositiveIntegerField(default=0)
    notes           = models.TextField(blank=True)

    # Auto-calc flag: set True for lines that are computed from CPS box counts
    auto_calculated = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.cat} {self.sel} × {self.quantity} — {self.description[:40]}'

    @property
    def line_total(self):
        """
        Base line total before O&P and tax.
        = qty × (remove_rate + replace_rate)
        For bid items [*], replace_rate IS the total (qty always 1).
        """
        if self.is_memo:
            return Decimal('0.00')
        return (self.quantity * (self.remove_rate + self.replace_rate)).quantize(Decimal('0.01'))
