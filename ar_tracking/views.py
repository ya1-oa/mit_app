"""
ar_tracking/views.py

Accounts Receivable board: status-grouped view of contractor invoices
(GCEstimate), a per-invoice communication activity feed, and a "schedule
follow-up" action that reuses email_manager's existing scheduled-email +
follow-up Celery infrastructure (no new scheduling code).

NOTE on tenant scoping: GCEstimate/Client don't have a `tenant` column yet
(that lands in the multi-tenant retrofit's Phase 1) — until then, this board
shows estimates across all tenants, same as every other existing view in the
app today. CommunicationActivity rows created here ARE correctly tenant-
scoped from day one; the board's GCEstimate query will start filtering by
tenant automatically, with no code change here, once Phase 1 lands.
"""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from contractor_hub.models import EstimateStatus, GCEstimate
from docsAppR.models import EmailBatch, ScheduledEmail

from .models import CommunicationActivity

# Board columns, in display order. DRAFT/SUBMITTED/APPROVED are upstream of
# billing and intentionally excluded — the AR board starts once money is owed.
AR_BOARD_STATUSES = [
    (EstimateStatus.BILLED,  'Invoiced'),
    (EstimateStatus.DELAYED, 'Delayed'),
    (EstimateStatus.PAID,    'Paid'),
]


def _require_tenant(request):
    """
    CommunicationActivity.tenant is non-nullable (brand-new model, no
    backfill needed). If request.tenant is None — staff account, or a
    non-staff user whose tenant hasn't been backfilled yet — creating a row
    would raise a raw IntegrityError. Surface a clear message instead.
    Returns True if it's safe to proceed.
    """
    if request.tenant is None:
        messages.error(
            request,
            'Your account has no tenant assigned, so this action is blocked. '
            'Contact an admin to resolve your account setup.',
        )
        return False
    return True


@login_required
def ar_board(request):
    estimates = (
        GCEstimate.objects
        .filter(status__in=[s.value for s, _ in AR_BOARD_STATUSES])
        .select_related('client', 'gc_contractor')
        .order_by('-created_at')
    )

    columns = []
    for status_value, label in AR_BOARD_STATUSES:
        columns.append({
            'status': status_value,
            'label': label,
            'estimates': [e for e in estimates if e.status == status_value],
        })

    return render(request, 'ar_tracking/board.html', {'columns': columns})


@login_required
def ar_detail(request, estimate_id):
    estimate = get_object_or_404(
        GCEstimate.objects.select_related('client', 'gc_contractor', 'estimator'),
        id=estimate_id,
    )
    # Tenant-scoped (fail-closed) default manager — correct from day one for
    # this brand-new model, regardless of whether GCEstimate itself is scoped
    # yet. Returns empty until request.tenant is set (see _require_tenant).
    activities = (
        CommunicationActivity.objects
        .filter(estimate=estimate)
        .select_related('created_by', 'sent_email')
        .order_by('-created_at')
    )
    return render(request, 'ar_tracking/detail.html', {
        'estimate': estimate,
        'activities': activities,
        'status_choices': EstimateStatus.choices,
    })


@login_required
@require_POST
def ar_add_note(request, estimate_id):
    estimate = get_object_or_404(GCEstimate, id=estimate_id)
    if not _require_tenant(request):
        return redirect('ar_tracking:detail', estimate_id=estimate.id)

    note = (request.POST.get('notes') or '').strip()
    if not note:
        messages.error(request, 'Note cannot be empty.')
        return redirect('ar_tracking:detail', estimate_id=estimate.id)

    CommunicationActivity.objects.create(
        tenant=request.tenant,
        estimate=estimate,
        activity_type='manual_note',
        notes=note,
        created_by=request.user,
    )
    messages.success(request, 'Note added.')
    return redirect('ar_tracking:detail', estimate_id=estimate.id)


@login_required
@require_POST
def ar_mark_status(request, estimate_id):
    """Manual status change — the v1 stand-in for real reply auto-detection."""
    estimate = get_object_or_404(GCEstimate, id=estimate_id)
    if not _require_tenant(request):
        return redirect('ar_tracking:detail', estimate_id=estimate.id)

    new_status = request.POST.get('status', '').strip()
    valid_values = {s for s, _ in EstimateStatus.choices}
    if new_status not in valid_values:
        messages.error(request, 'Invalid status.')
        return redirect('ar_tracking:detail', estimate_id=estimate.id)

    old_status = estimate.status
    estimate.status = new_status
    estimate.save(update_fields=['status', 'updated_at'])

    CommunicationActivity.objects.create(
        tenant=request.tenant,
        estimate=estimate,
        activity_type='status_changed',
        notes=f'Status changed: {old_status} -> {new_status}',
        created_by=request.user,
    )
    messages.success(request, f'Marked as {estimate.get_status_display()}.')
    return redirect('ar_tracking:detail', estimate_id=estimate.id)


@login_required
@require_POST
def ar_schedule_followup(request, estimate_id):
    """
    Create a ScheduledEmail (inside a new EmailBatch) for this estimate.
    Reuses email_manager's existing process_scheduled_batch_emails /
    check_followup_triggers Celery tasks as-is — no new scheduling
    infrastructure. Those tasks pick this row up automatically.
    """
    estimate = get_object_or_404(GCEstimate.objects.select_related('client', 'gc_contractor'), id=estimate_id)
    if not _require_tenant(request):
        return redirect('ar_tracking:detail', estimate_id=estimate.id)

    to_email = (request.POST.get('to_email') or estimate.gc_contractor.email or '').strip()
    subject = (request.POST.get('subject') or '').strip()
    body = (request.POST.get('body') or '').strip()
    send_time_raw = request.POST.get('scheduled_send_time', '').strip()
    followup_trigger = request.POST.get('followup_trigger', '').strip()
    followup_days = request.POST.get('followup_days', '').strip()

    if not (to_email and subject and body and send_time_raw):
        messages.error(request, 'Recipient, subject, body, and send time are all required.')
        return redirect('ar_tracking:detail', estimate_id=estimate.id)

    scheduled_send_time = parse_datetime(send_time_raw)
    if scheduled_send_time is None:
        messages.error(request, 'Invalid date/time.')
        return redirect('ar_tracking:detail', estimate_id=estimate.id)
    if timezone.is_naive(scheduled_send_time):
        scheduled_send_time = timezone.make_aware(scheduled_send_time)

    batch = EmailBatch.objects.create(
        name=f'AR follow-up — {estimate.gc_contractor.name} ({estimate.estimate_number or estimate.id})',
        claim=estimate.client,
        created_by=request.user,
    )
    has_followup = followup_trigger in ('time', 'unopened', 'opened')
    ScheduledEmail.objects.create(
        batch=batch,
        subject=subject,
        body=body,
        recipients=[to_email],
        scheduled_send_time=scheduled_send_time,
        has_followup=has_followup,
        followup_trigger=followup_trigger if has_followup else '',
        followup_days=int(followup_days) if has_followup and followup_days.isdigit() else None,
        followup_subject=subject,
        followup_body=body,
    )

    CommunicationActivity.objects.create(
        tenant=request.tenant,
        estimate=estimate,
        activity_type='followup_scheduled',
        notes=f'Follow-up scheduled for {scheduled_send_time:%Y-%m-%d %H:%M} to {to_email}.',
        created_by=request.user,
    )
    messages.success(request, 'Follow-up scheduled.')
    return redirect('ar_tracking:detail', estimate_id=estimate.id)
