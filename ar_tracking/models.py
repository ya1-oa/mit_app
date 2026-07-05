"""
ar_tracking/models.py

Accounts Receivable tracking: communication activity log for contractor
invoices (GCEstimate). NOT a document/letter generator — this is purely
inbox-style activity tracking and follow-up scheduling.

v1 (this turn): manual "mark as responded" + automated scheduled follow-ups,
reusing email_manager's existing ScheduledEmail/process_scheduled_batch_emails
Celery machinery (no new scheduling infrastructure). Real inbox
auto-detection (IMAP/webhook) is a deliberate fast-follow, not built here —
see the multi-tenant retrofit plan, D3-v2.

Tenant-native from day one: this model is brand new (no existing rows), so
`tenant` is non-nullable from its first migration — no backfill needed,
unlike the older models being retrofitted elsewhere. NOTE: GCEstimate/Client
do not have a `tenant` column yet (that lands in the retrofit's Phase 1) — so
until that lands, the AR board itself shows estimates across all tenants,
the same as every other existing view in the app today. This model's own
rows are correctly isolated regardless.
"""
from django.conf import settings
from django.db import models

from docsAppR.tenancy import TenantScopedModel


class AREmailTemplate(models.Model):
    """
    Reusable email templates for AR follow-up emails.
    tenant=None means global default (available to all tenants).
    Per-tenant templates override globals when the names collide.
    """

    class Category(models.TextChoices):
        INITIAL_INVOICE = 'initial_invoice', 'Initial Invoice'
        FOLLOWUP_30     = 'followup_30',     '30-Day Follow-up'
        FOLLOWUP_60     = 'followup_60',     '60-Day Follow-up'
        DEMAND          = 'demand',          'Payment Demand'
        SUPPLEMENT      = 'supplement',      'Supplement Request'
        GENERAL         = 'general',         'General'

    tenant = models.ForeignKey(
        'docsAppR.Tenant', on_delete=models.CASCADE,
        null=True, blank=True, db_index=True,
        help_text='Null = global default available to all tenants.',
    )
    name     = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.GENERAL)
    subject_template = models.CharField(
        max_length=500,
        help_text='Placeholders: {claim_number} {policy_number} {insurer} {contractor_name} {amount} {date}',
    )
    body_template = models.TextField(
        help_text='Same placeholders as subject_template.',
    )
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'AR Email Template'
        verbose_name_plural = 'AR Email Templates'

    def __str__(self):
        prefix = f'[{self.tenant}] ' if self.tenant else '[Global] '
        return f'{prefix}{self.get_category_display()} — {self.name}'


class CommunicationActivity(TenantScopedModel):
    """One entry in an invoice's communication activity feed."""

    ACTIVITY_TYPES = [
        ('email_sent',     'Email Sent'),
        ('manual_note',    'Manual Note'),
        ('reply_logged',   'Reply Logged'),
        ('status_changed', 'Status Changed'),
        ('followup_scheduled', 'Follow-up Scheduled'),
    ]

    # Brand-new model, no existing rows to backfill -> tenant is required from
    # day one. Overrides TenantScopedModel's migration-window nullable default.
    tenant = models.ForeignKey('docsAppR.Tenant', on_delete=models.PROTECT, db_index=True)

    estimate = models.ForeignKey(
        'contractor_hub.GCEstimate', on_delete=models.CASCADE,
        related_name='ar_activities',
    )
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    notes = models.TextField(blank=True)

    # Link back to the actual outbound email when this activity IS one
    # (manual notes / reply-logged entries leave this blank).
    sent_email = models.ForeignKey(
        'docsAppR.SentEmail', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ar_activities',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Communication activities'

    def __str__(self):
        return f'{self.get_activity_type_display()} — {self.estimate_id} ({self.created_at:%Y-%m-%d})'
