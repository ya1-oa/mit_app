"""
daily_reports/models.py

Two report types:
  - High Priority Daily Report: specific claims/items tracked until resolved
  - Weekly Deep Operations Report: aggregate app-level progress + user tasks
"""
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class DailyReportConfig(models.Model):
    """Global configuration for the daily high-priority report."""
    name = models.CharField(max_length=100, default='Daily Status Report')
    recipients = models.JSONField(
        default=list,
        help_text='List of email addresses to send the daily report to',
    )
    cc_emails = models.JSONField(default=list, blank=True)
    send_hour = models.PositiveSmallIntegerField(
        default=7,
        validators=[MaxValueValidator(23)],
        help_text='Hour of day (0-23) in Eastern Time to send the daily report',
    )
    is_active = models.BooleanField(default=True)

    # ── Sections ──────────────────────────────────────────────────────────────
    include_ppr_signatures  = models.BooleanField(default=True, verbose_name='PPR Pending Signatures')
    include_ppr_pricing     = models.BooleanField(default=True, verbose_name='PPR Pricing Incomplete')
    include_lease_sigs      = models.BooleanField(default=True, verbose_name='Lease Signature Status')
    include_lease_pipeline  = models.BooleanField(default=True, verbose_name='Lease Pipeline Overview')
    include_high_priority   = models.BooleanField(default=True, verbose_name='High Priority Tracked Items')

    # ── Attachments ───────────────────────────────────────────────────────────
    attach_ppr_pdf    = models.BooleanField(
        default=False,
        help_text='Attach generated Schedule of Loss PDF for each pending PPR session',
    )
    attach_lease_docs = models.BooleanField(
        default=False,
        help_text='Attach the latest lease document for each pending lease',
    )

    # ── Escalation ────────────────────────────────────────────────────────────
    escalation_days = models.PositiveSmallIntegerField(
        default=3,
        help_text='After this many days pending, items are marked URGENT in the report',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Daily Report Configuration'

    def __str__(self):
        return self.name


class HighPriorityItem(models.Model):
    """
    A specific claim item the user has flagged for daily tracking.
    Appears in every daily report (highlighted) until resolved.
    """
    ITEM_TYPE_CHOICES = [
        ('ppr',     'PPR Report'),
        ('lease',   'ALE Lease'),
        ('general', 'General Claim Item'),
    ]

    config      = models.ForeignKey(
        DailyReportConfig,
        on_delete=models.CASCADE,
        related_name='high_priority_items',
    )
    item_type   = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    client      = models.ForeignKey(
        'docsAppR.Client',
        on_delete=models.CASCADE,
        related_name='high_priority_report_items',
    )
    ppr_session = models.ForeignKey(
        'cps_report.CPSReportSession',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='high_priority_flags',
    )
    lease       = models.ForeignKey(
        'docsAppR.Lease',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='high_priority_flags',
    )

    # Why this is being tracked / what needs to happen
    priority_note          = models.TextField(blank=True, help_text='Why is this being tracked?')
    resolution_criteria    = models.TextField(blank=True, help_text='What needs to happen to resolve this?')
    demand_language        = models.TextField(
        blank=True,
        help_text='Specific demand text to include in the daily email for this item',
    )

    # Auto-resolve: if True, item is marked resolved when the underlying object reaches a terminal status
    auto_resolve = models.BooleanField(default=True)
    is_resolved  = models.BooleanField(default=False, db_index=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)

    added_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='added_high_priority_items',
    )
    added_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-added_at']
        verbose_name = 'High Priority Tracked Item'

    def __str__(self):
        return f"{self.get_item_type_display()} — {self.client} (added {self.added_at:%Y-%m-%d})"

    def check_auto_resolve(self):
        """Check if the underlying item has completed and auto-resolve if so."""
        if not self.auto_resolve or self.is_resolved:
            return False
        resolved = False
        if self.item_type == 'ppr' and self.ppr_session:
            resolved = self.ppr_session.status == 'complete' and not self.ppr_session.rooms.filter(
                signature_name=''
            ).exists()
        elif self.item_type == 'lease' and self.lease:
            resolved = self.lease.status in ('signed', 'completed', 'payment_received', 'package_sent')
        if resolved:
            self.is_resolved = True
            self.resolved_at = timezone.now()
            self.save(update_fields=['is_resolved', 'resolved_at'])
        return resolved


class OperationalTask(models.Model):
    """
    User-created operational task for tracking progress per Claimet app.
    Used in the Weekly Deep Operations Report.
    """
    APP_CHOICES = [
        ('cps_report',        'PPR / Schedule of Loss'),
        ('lease_manager',     'ALE Lease Manager'),
        ('claims',            'Claims'),
        ('equipment_checker', 'Equipment Checker'),
        ('box_calculator',    'Box Calculator'),
        ('encircle',          'Encircle Sync'),
        ('ar_tracking',       'AR Tracking'),
        ('contractor_hub',    'Contractor Hub'),
        ('scope_checklist',   'Scope Checklist'),
        ('email_manager',     'Email Manager'),
        ('dev_hub',           'Dev Hub'),
        ('general',           'General / Cross-App'),
    ]
    STATUS_CHOICES = [
        ('todo',        'To Do'),
        ('in_progress', 'In Progress'),
        ('blocked',     'Blocked'),
        ('done',        'Done'),
    ]
    PRIORITY_CHOICES = [
        ('low',      'Low'),
        ('normal',   'Normal'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]

    app              = models.CharField(max_length=40, choices=APP_CHOICES, db_index=True)
    title            = models.CharField(max_length=300)
    description      = models.TextField(blank=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo', db_index=True)
    priority         = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    percent_complete = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
    )
    due_date         = models.DateField(null=True, blank=True)
    notes            = models.TextField(blank=True)

    created_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_operational_tasks',
    )
    assigned_to  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_operational_tasks',
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Include in next weekly deep report
    queue_for_deep_report = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-priority', 'app', 'created_at']
        verbose_name = 'Operational Task'

    def __str__(self):
        return f"[{self.get_app_display()}] {self.title}"

    def save(self, *args, **kwargs):
        if self.status == 'done' and not self.completed_at:
            self.completed_at = timezone.now()
            self.percent_complete = 100
        super().save(*args, **kwargs)


class DailyReportLog(models.Model):
    """Audit log of each daily or deep report that was sent."""
    REPORT_TYPE_CHOICES = [
        ('daily',  'Daily High Priority Report'),
        ('deep',   'Weekly Deep Operations Report'),
    ]

    report_type  = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES, default='daily')
    config       = models.ForeignKey(
        DailyReportConfig,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='logs',
    )
    sent_at      = models.DateTimeField(auto_now_add=True)
    recipients   = models.JSONField(default=list)
    total_items  = models.PositiveIntegerField(default=0)
    urgent_items = models.PositiveIntegerField(default=0)
    email_success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Report Log'

    def __str__(self):
        status = 'OK' if self.email_success else 'FAILED'
        return f"{self.get_report_type_display()} — {self.sent_at:%Y-%m-%d %H:%M} [{status}]"
