import uuid

from django.db import models


class CPSReportSession(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('complete', 'Complete'),
        ('error', 'Error'),
    ]

    PRICING_MODE_CHOICES = [
        ('normal',  'Normal Pricing'),
        ('premium', 'Premium / High-End Pricing'),
    ]

    AI_MODEL_CHOICES = [
        ('claude-haiku-4-5-20251001', 'Haiku 4.5 — faster / cheaper'),
        ('claude-sonnet-5',           'Sonnet 5 — higher accuracy'),
    ]

    client = models.ForeignKey(
        'docsAppR.Client',
        on_delete=models.CASCADE,
        related_name='cps_report_sessions',
    )
    encircle_claim_id = models.CharField(max_length=100)
    encircle_structure_id = models.CharField(max_length=100, blank=True)
    claim_number = models.CharField(max_length=100, blank=True)
    insured_name = models.CharField(max_length=255, blank=True)
    loss_type = models.CharField(max_length=100, blank=True)
    loss_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    pricing_mode = models.CharField(max_length=16, choices=PRICING_MODE_CHOICES, default='normal')
    # Which Claude model performs item identification (stage 1). Prices come from
    # live web search (Serper.dev), not the model, so this only affects naming accuracy.
    ai_model = models.CharField(max_length=60, choices=AI_MODEL_CHOICES, default='claude-haiku-4-5-20251001')
    celery_task_id = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True)
    # Which room series were selected at session-start, e.g. ["400s","100s","bu"]
    room_sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"PPR Schedule of Loss — {self.client.pOwner} ({self.updated_at:%Y-%m-%d})"

    def total_replacement_value(self):
        total = 0
        for room in self.rooms.all():
            for item in room.items.filter(structural=False):
                total += (item.replacement_value_each or 0) * (item.qty or 1)
        return total


class CPSReportRoom(models.Model):
    ROOM_SOURCE_PRIMARY  = 'primary'
    ROOM_SOURCE_OVERVIEW = 'overview'
    ROOM_SOURCE_BU       = 'bu'
    ROOM_SOURCE_CHOICES  = [
        ('primary',  'Primary (400s PPR / 300s CPS)'),
        ('overview', 'Overview (100s)'),
        ('bu',       'Backup Photos (BU)'),
    ]

    session = models.ForeignKey(
        CPSReportSession,
        on_delete=models.CASCADE,
        related_name='rooms',
    )
    share_token = models.UUIDField(default=uuid.uuid4, unique=True)
    room_name = models.CharField(max_length=200)
    room_number = models.CharField(max_length=20, blank=True)
    encircle_room_id = models.CharField(max_length=100, blank=True)
    encircle_room_label = models.CharField(max_length=300, blank=True)
    # Secondary Encircle room — populated when a 300-series room is paired with its 400-series counterpart
    encircle_room_id_secondary = models.CharField(max_length=100, blank=True)
    encircle_room_label_secondary = models.CharField(max_length=300, blank=True)
    room_source = models.CharField(
        max_length=20,
        choices=ROOM_SOURCE_CHOICES,
        default=ROOM_SOURCE_PRIMARY,
    )
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('processing', 'Processing'),
                 ('complete', 'Complete'), ('error', 'Error')],
        default='pending',
    )
    images_used = models.PositiveIntegerField(default=0)
    analyzed_image_urls = models.JSONField(default=list, blank=True)
    ai_confidence = models.CharField(max_length=20, blank=True)
    ai_notes = models.TextField(blank=True)
    signature_name = models.CharField(max_length=255, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    signer_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['order', 'room_number']

    def __str__(self):
        return f"{self.room_number} {self.room_name}"

    @property
    def total_rcv(self):
        return sum(
            float(i.replacement_value_each or 0) * (i.qty or 1)
            for i in self.items.filter(structural=False)
        )


class CPSReportItem(models.Model):
    room = models.ForeignKey(
        CPSReportRoom,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order = models.PositiveIntegerField(default=0)

    description = models.CharField(max_length=500)
    brand = models.CharField(max_length=200, blank=True)
    disposition = models.CharField(max_length=100, default='Replacement')
    condition = models.CharField(max_length=50, blank=True)
    qty = models.PositiveIntegerField(default=1)
    model_number = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=200, blank=True)
    retailer = models.CharField(max_length=200, blank=True)
    replacement_source = models.CharField(max_length=200, blank=True)

    purchase_price_each = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    age_years = models.PositiveSmallIntegerField(null=True, blank=True)
    age_months = models.PositiveIntegerField(null=True, blank=True)
    replacement_value_each = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    depreciation_category = models.CharField(max_length=100, blank=True)
    depreciation_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    ai_suggested = models.BooleanField(default=True)
    # Flagged by the structural-item filter in ai_analyzer — permanently attached
    # to the building (walls, floors, fixtures, etc.) rather than personal property.
    structural = models.BooleanField(default=False)
    # URLs of the specific images Claude attributed this item to (1–N per item).
    # Populated at analysis time; used by the photo PDF to show item-level photos.
    source_image_urls = models.JSONField(default=list, blank=True)

    # ── Live pricing (Serper.dev web search) ──────────────────────────────────
    # The search string used to look this item up.
    search_query = models.CharField(max_length=500, blank=True)
    # All listings found: [{"vendor","price","url","title","in_stock"}].
    price_options = models.JSONField(default=list, blank=True)
    # The listing the AI selected as the replacement source.
    price_source_url    = models.CharField(max_length=1000, blank=True)
    price_source_vendor = models.CharField(max_length=200,  blank=True)
    # One-line justification the AI gave for choosing this listing.
    price_selection_reason = models.CharField(max_length=500, blank=True)
    # How replacement_value_each was derived: 'live' (verified listing) or
    # 'ai_estimate' (no listing found — fell back to an AI estimate).
    price_method = models.CharField(max_length=20, blank=True)
    # True when no live listing was found — prompts a human to verify the item
    # was named correctly (a well-named common item should return listings).
    price_needs_review = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.description

    @property
    def replacement_value_total(self):
        if self.replacement_value_each is None:
            return None
        return self.replacement_value_each * self.qty

    @property
    def depreciation_amount(self):
        if self.replacement_value_total is None or self.depreciation_pct is None:
            return None
        return self.replacement_value_total * (self.depreciation_pct / 100)

    @property
    def acv_each(self):
        if self.replacement_value_each is None or self.depreciation_pct is None:
            return None
        return self.replacement_value_each * (1 - self.depreciation_pct / 100)

    @property
    def acv_total(self):
        if self.acv_each is None:
            return None
        return self.acv_each * self.qty

    def to_dict(self):
        return {
            'id': self.id,
            'description': self.description,
            'brand': self.brand,
            'disposition': self.disposition,
            'condition': self.condition,
            'qty': self.qty,
            'model_number': self.model_number,
            'serial_number': self.serial_number,
            'retailer': self.retailer,
            'replacement_source': self.replacement_source,
            'purchase_price_each': float(self.purchase_price_each) if self.purchase_price_each else None,
            'age_years': self.age_years,
            'age_months': self.age_months,
            'replacement_value_each': float(self.replacement_value_each) if self.replacement_value_each else None,
            'replacement_value_total': float(self.replacement_value_total) if self.replacement_value_total else None,
            'notes': self.notes,
            'ai_suggested': self.ai_suggested,
            'structural': self.structural,
        }
