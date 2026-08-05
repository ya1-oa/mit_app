"""
mit_audit/models.py

Data models for the MIT Day 3 Equipment Audit feature.

Pipeline:
  MITDay3Config        — singleton: template path + cell map (admin-editable)
  MITDay3Audit         — one per job/claim, tracks status through the pipeline
  MITRoomDimension     — room L/W/H extracted from Encircle floor plan
  MITRequiredEquipment — items with qty > 0 from the Total Equipment tab
  MITPhotoObservation  — AI review result: visible vs required per item
  MITReport            — generated PDF (two types per audit)
"""
import secrets

from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Configuration singleton
# ---------------------------------------------------------------------------

class MITDay3Config(models.Model):
    """
    Singleton (always id=1).  Edit via Django admin or the settings page.
    Stores the template workbook path and the JSON cell-address maps that tell
    the workbook service where to write dimensions and where to read results.
    """
    # Relative to MEDIA_ROOT  e.g.  'mit_templates/MIT_Day3_Template.xlsx'
    template_path = models.CharField(
        max_length=512, blank=True,
        help_text='Path to the MIT Day 3 .xlsx template, relative to MEDIA_ROOT.',
    )
    # --- Sheet names (may differ across template versions) ---
    job_info_sheet       = models.CharField(max_length=100, default='Job Information')
    total_equipment_sheet = models.CharField(max_length=100, default='Total Equipment')

    # --- Dimension cell map ---
    # Keys the workbook_service uses to locate room-dimension rows:
    # {
    #   "room_start_row": 8,        <- first data row on job_info_sheet
    #   "room_name_col":  "B",      <- column holding the room label
    #   "length_col":     "C",
    #   "width_col":      "D",
    #   "height_col":     "E",
    #   "max_rows":       40        <- stop scanning after this many rows
    # }
    dimension_cell_map = models.JSONField(
        default=dict, blank=True,
        help_text='JSON describing where room dimensions live on the Job Info sheet.',
    )

    # --- Equipment cell map ---
    # JSON array, one entry per named equipment row:
    # [
    #   { "row": 14, "name_col": "B", "qty_col": "D",
    #     "equipment_type": "dehumidifier", "category": "dehumidifier" },
    #   ...
    # ]
    # Populated once you have the finalised workbook template.
    equipment_cell_map = models.JSONField(
        default=list, blank=True,
        help_text='JSON array mapping Total Equipment rows to equipment types.',
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'MIT Day 3 Config'

    def __str__(self):
        return 'MIT Day 3 Config (singleton)'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


# ---------------------------------------------------------------------------
# Audit record (one per job)
# ---------------------------------------------------------------------------

class MITDay3Audit(models.Model):
    """
    Master record for a single MIT equipment audit, tied to one Client (= claim).
    Status moves through the pipeline; errors set status='error' + error_message.
    """
    STATUS_CHOICES = [
        ('pending',            'Pending'),
        ('extracting_dims',    'Extracting Dimensions'),
        ('dims_review',        'Awaiting Dimension Review'),
        ('populating_wb',      'Populating Workbook'),
        ('calculating',        'Calculating Equipment'),
        ('reviewing_photos',   'Reviewing Photos'),
        ('generating_reports', 'Generating Reports'),
        ('complete',           'Complete'),
        ('error',              'Error'),
    ]

    client = models.ForeignKey(
        'docsAppR.Client',
        on_delete=models.CASCADE,
        related_name='mit_audits',
    )
    # Encircle claim ID that triggered this audit (may differ from client.encircle_claim_id
    # if a claim has multiple encircle entries — store the one that fired the webhook)
    encircle_claim_id = models.CharField(max_length=100, blank=True, db_index=True)

    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default='pending', db_index=True
    )
    error_message = models.TextField(blank=True)

    # Absolute path to the populated workbook produced for this job.
    # Copied from the template and filled with room dimensions before recalc.
    workbook_path = models.CharField(max_length=512, blank=True)

    # Celery chain task IDs (stored for status polling)
    celery_task_id = models.CharField(max_length=200, blank=True)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='mit_audits_triggered',
    )
    triggered_by_webhook = models.BooleanField(default=False,
        help_text='True when this audit was automatically started by an Encircle floor-plan webhook.')

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'MIT Day 3 Audit'
        verbose_name_plural = 'MIT Day 3 Audits'

    def __str__(self):
        return f'MIT Audit #{self.pk} — {self.client} ({self.get_status_display()})'

    def set_status(self, status, error=''):
        """Convenience: update status + optional error without a full save."""
        self.status = status
        if error:
            self.error_message = error
        self.save(update_fields=['status', 'error_message', 'updated_at'])


# ---------------------------------------------------------------------------
# Room dimensions
# ---------------------------------------------------------------------------

class MITRoomDimension(models.Model):
    """
    One row per room extracted from the Encircle floor plan for this job.
    Low-confidence rows (< 0.75) are flagged for manual correction before
    the workbook is populated.
    """
    audit      = models.ForeignKey(
        MITDay3Audit, on_delete=models.CASCADE, related_name='room_dimensions'
    )
    room_name  = models.CharField(max_length=200)
    length     = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width      = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    height     = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    square_feet = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cubic_feet  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    source_floorplan_id = models.CharField(max_length=100, blank=True)
    confidence_score = models.FloatField(default=1.0,
        help_text='0.0–1.0; auto-flagged for review when below 0.75')
    needs_review = models.BooleanField(default=False, db_index=True)
    approved     = models.BooleanField(default=False,
        help_text='Must be True before the workbook population step runs.')
    # Set by the workbook service after writing
    workbook_row = models.PositiveIntegerField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['room_name']
        verbose_name = 'MIT Room Dimension'

    def save(self, *args, **kwargs):
        if self.length and self.width:
            self.square_feet = round(float(self.length) * float(self.width), 2)
        if self.square_feet and self.height:
            self.cubic_feet = round(float(self.square_feet) * float(self.height), 2)
        if self.confidence_score < 0.75:
            self.needs_review = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.room_name} ({self.length}×{self.width}×{self.height} ft)'


# ---------------------------------------------------------------------------
# Required equipment (from Total Equipment tab)
# ---------------------------------------------------------------------------

class MITRequiredEquipment(models.Model):
    """
    One row per equipment item that has required_quantity > 0 after the
    workbook is recalculated.  This is the source of truth for the photo audit.
    """
    CATEGORY_CHOICES = [
        ('dehumidifier',  'Dehumidifier'),
        ('air_cleaner',   'Air Cleaner / Scrubber'),
        ('zipper_wall',   'Zipper Wall & Poles'),
        ('double_zipper', 'Double Zipper Wall & Poles'),
        ('blower',        'Blower / Air Mover'),
        ('wall_cavity',   'Wall Cavity Drying'),
        ('floor_drying',  'Floor Drying Equipment'),
        ('heater',        'Heater'),
        ('other',         'Other'),
    ]

    audit             = models.ForeignKey(
        MITDay3Audit, on_delete=models.CASCADE, related_name='required_equipment'
    )
    equipment_type    = models.CharField(max_length=100)
    display_name      = models.CharField(max_length=200)
    category          = models.CharField(
        max_length=30, choices=CATEGORY_CHOICES, default='other', db_index=True
    )
    required_quantity = models.PositiveIntegerField()

    # Workbook provenance
    source_sheet  = models.CharField(max_length=100, default='Total Equipment')
    workbook_row  = models.PositiveIntegerField(null=True, blank=True)
    workbook_cell = models.CharField(max_length=20, blank=True,
        help_text='e.g. D14 — the quantity cell that was read')

    # Dry-chamber / stabilization items require a specific stabilization photo
    requires_stabilization_photo = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'display_name']
        verbose_name = 'MIT Required Equipment'
        verbose_name_plural = 'MIT Required Equipment'

    def __str__(self):
        return f'{self.display_name} × {self.required_quantity}'


# ---------------------------------------------------------------------------
# Photo observation (AI review result)
# ---------------------------------------------------------------------------

class MITPhotoObservation(models.Model):
    """
    AI review result per required equipment item:
    how many units were visible in Encircle photos vs how many are required.
    """
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('partial',   'Partial'),
        ('missing',   'Missing'),
        ('manual',    'Needs Manual Review'),
    ]

    required_item = models.OneToOneField(
        MITRequiredEquipment,
        on_delete=models.CASCADE,
        related_name='photo_observation',
    )
    visible_quantity = models.PositiveIntegerField(default=0)
    missing_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='missing', db_index=True
    )

    # JSON list of Encircle photo IDs / URLs that support the finding
    supporting_photo_ids = models.JSONField(default=list)

    ai_confidence = models.CharField(max_length=20, default='medium',
        help_text='high | medium | low')
    ai_notes = models.TextField(blank=True)

    # For stabilization items: did a valid stab photo exist?
    stabilization_photo_found = models.BooleanField(null=True, blank=True)

    recommended_action = models.TextField(blank=True)
    ai_model = models.CharField(max_length=100, blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'MIT Photo Observation'

    def save(self, *args, **kwargs):
        req_qty = self.required_item.required_quantity if self.required_item_id else 0
        self.missing_quantity = max(req_qty - self.visible_quantity, 0)
        if self.status not in ('manual',):
            if self.missing_quantity == 0:
                self.status = 'confirmed'
            elif self.visible_quantity > 0:
                self.status = 'partial'
            else:
                self.status = 'missing'
        super().save(*args, **kwargs)

    def __str__(self):
        req = self.required_item.required_quantity if self.required_item_id else '?'
        return (
            f'{self.required_item.display_name}: '
            f'{self.visible_quantity}/{req} — {self.status}'
        )


# ---------------------------------------------------------------------------
# Generated reports
# ---------------------------------------------------------------------------

class MITReport(models.Model):
    """
    One PDF report per type per audit.  Two are generated:
      • required_equipment — what the workbook calculated
      • missing_equipment  — comparison vs photo review
    download_token enables unauthenticated links inside notification emails.
    """
    TYPE_CHOICES = [
        ('required_equipment', 'Required Equipment Report'),
        ('missing_equipment',  'Missing Equipment & Photos Report'),
    ]

    audit         = models.ForeignKey(
        MITDay3Audit, on_delete=models.CASCADE, related_name='reports'
    )
    report_type   = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    file_path     = models.CharField(max_length=512, blank=True,
        help_text='Absolute path to the generated PDF on disk.')
    file_size_bytes = models.PositiveIntegerField(default=0)
    download_token  = models.CharField(max_length=64, blank=True, unique=True)
    generated_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-generated_at']
        verbose_name = 'MIT Report'

    def save(self, *args, **kwargs):
        if not self.download_token:
            self.download_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def get_download_url(self):
        from django.urls import reverse
        return reverse('mit_audit:download_report', args=[self.download_token])

    def __str__(self):
        return f'{self.get_report_type_display()} — {self.audit}'
