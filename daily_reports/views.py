"""
daily_reports/views.py

Three views:
  - dashboard     — overview of active tracked items + report logs
  - config        — edit the DailyReportConfig
  - tasks         — create/edit OperationalTasks
  - flag_item     — AJAX: flag a claim/lease/PPR as high priority
  - send_now      — AJAX: trigger an immediate report send
  - resolve_item  — AJAX: manually resolve a high-priority item
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _get_or_create_config():
    from daily_reports.models import DailyReportConfig
    from django.conf import settings
    config, _ = DailyReportConfig.objects.get_or_create(
        id=1,
        defaults={
            'name': 'Daily Status Report',
            'recipients': [getattr(settings, 'NOTIFY_EMAIL', '')],
        },
    )
    return config


@login_required
def dashboard(request):
    from daily_reports.models import HighPriorityItem, DailyReportLog, OperationalTask

    config      = _get_or_create_config()
    hp_items    = HighPriorityItem.objects.filter(is_resolved=False).select_related(
        'client', 'ppr_session', 'lease', 'added_by'
    ).order_by('-added_at')
    recent_logs = DailyReportLog.objects.order_by('-sent_at')[:10]
    open_tasks  = OperationalTask.objects.exclude(status='done').select_related(
        'assigned_to', 'created_by'
    ).order_by('app', '-priority')

    # Live quick stats
    try:
        from cps_report.models import CPSReportSession
        ppr_unsigned = CPSReportSession.objects.filter(
            rooms__signature_name=''
        ).distinct().count()
        ppr_pending  = CPSReportSession.objects.filter(
            status__in=['pending', 'processing']
        ).count()
    except Exception:
        ppr_unsigned = ppr_pending = 0

    try:
        from docsAppR.models import Lease
        leases_awaiting = Lease.objects.filter(status='sent_for_signature').count()
        leases_draft    = Lease.objects.filter(status__in=['draft', 'generated']).count()
    except Exception:
        leases_awaiting = leases_draft = 0

    return render(request, 'daily_reports/dashboard.html', {
        'config':          config,
        'hp_items':        hp_items,
        'recent_logs':     recent_logs,
        'open_tasks':      open_tasks,
        'ppr_unsigned':    ppr_unsigned,
        'ppr_pending':     ppr_pending,
        'leases_awaiting': leases_awaiting,
        'leases_draft':    leases_draft,
    })


@login_required
def config_view(request):
    config = _get_or_create_config()

    if request.method == 'POST':
        p = request.POST
        config.name              = p.get('name', config.name)
        config.send_hour         = int(p.get('send_hour', config.send_hour))
        config.is_active         = 'is_active' in p
        config.escalation_days   = int(p.get('escalation_days', config.escalation_days))
        config.include_ppr_signatures = 'include_ppr_signatures' in p
        config.include_ppr_pricing    = 'include_ppr_pricing' in p
        config.include_lease_sigs     = 'include_lease_sigs' in p
        config.include_lease_pipeline = 'include_lease_pipeline' in p
        config.include_high_priority  = 'include_high_priority' in p
        config.attach_ppr_pdf         = 'attach_ppr_pdf' in p

        # Recipients — one per line
        raw = p.get('recipients', '')
        config.recipients = [e.strip() for e in raw.splitlines() if e.strip()]
        raw_cc = p.get('cc_emails', '')
        config.cc_emails  = [e.strip() for e in raw_cc.splitlines() if e.strip()]

        config.save()
        return redirect('daily_reports_dashboard')

    SECTIONS = [
        ('include_ppr_signatures', 'PPR — Awaiting Signatures'),
        ('include_ppr_pricing',    'PPR — Pricing Incomplete ($0 items)'),
        ('include_lease_sigs',     'ALE Leases — Signature Status'),
        ('include_lease_pipeline', 'ALE Leases — Full Pipeline Overview'),
        ('include_high_priority',  'High Priority Tracked Items (user-flagged)'),
    ]
    return render(request, 'daily_reports/config.html', {'config': config, 'sections': SECTIONS})


@login_required
def tasks_view(request):
    from daily_reports.models import OperationalTask
    from collections import defaultdict

    if request.method == 'POST':
        p = request.POST
        OperationalTask.objects.create(
            app=p.get('app', 'general'),
            title=p.get('title', '').strip(),
            description=p.get('description', '').strip(),
            status=p.get('status', 'todo'),
            priority=p.get('priority', 'normal'),
            percent_complete=int(p.get('percent_complete', 0)),
            due_date=p.get('due_date') or None,
            notes=p.get('notes', '').strip(),
            created_by=request.user,
        )
        return redirect('daily_reports_tasks')

    tasks = OperationalTask.objects.select_related('assigned_to', 'created_by').order_by(
        'app', '-priority', 'created_at'
    )
    by_app = defaultdict(list)
    for t in tasks:
        by_app[t.get_app_display()].append(t)

    return render(request, 'daily_reports/tasks.html', {
        'tasks':       tasks,
        'by_app':      dict(by_app),
        'app_choices': OperationalTask.APP_CHOICES,
        'status_choices': OperationalTask.STATUS_CHOICES,
        'priority_choices': OperationalTask.PRIORITY_CHOICES,
    })


@login_required
@require_POST
def update_task(request, task_id):
    from daily_reports.models import OperationalTask
    task = get_object_or_404(OperationalTask, id=task_id)
    p    = request.POST
    task.title            = p.get('title', task.title)
    task.status           = p.get('status', task.status)
    task.priority         = p.get('priority', task.priority)
    task.percent_complete = int(p.get('percent_complete', task.percent_complete))
    task.description      = p.get('description', task.description)
    task.notes            = p.get('notes', task.notes)
    due = p.get('due_date', '')
    task.due_date = due if due else None
    task.save()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def delete_task(request, task_id):
    from daily_reports.models import OperationalTask
    task = get_object_or_404(OperationalTask, id=task_id)
    task.delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def flag_item(request):
    """
    AJAX: Mark a claim/lease/PPR session as a high-priority tracked item.
    Body JSON: { item_type, client_id, ppr_session_id?, lease_id?,
                 priority_note?, resolution_criteria?, demand_language? }
    """
    from daily_reports.models import DailyReportConfig, HighPriorityItem
    from docsAppR.models import Client

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    config  = _get_or_create_config()
    client  = get_object_or_404(Client, id=data.get('client_id'))

    ppr_session = lease = None
    if data.get('ppr_session_id'):
        from cps_report.models import CPSReportSession
        ppr_session = get_object_or_404(CPSReportSession, id=data['ppr_session_id'])
    if data.get('lease_id'):
        from docsAppR.models import Lease
        lease = get_object_or_404(Lease, id=data['lease_id'])

    item = HighPriorityItem.objects.create(
        config=config,
        item_type=data.get('item_type', 'general'),
        client=client,
        ppr_session=ppr_session,
        lease=lease,
        priority_note=data.get('priority_note', ''),
        resolution_criteria=data.get('resolution_criteria', ''),
        demand_language=data.get('demand_language', ''),
        added_by=request.user,
    )
    return JsonResponse({'ok': True, 'item_id': item.id})


@login_required
@require_POST
def resolve_item(request, item_id):
    from daily_reports.models import HighPriorityItem
    item = get_object_or_404(HighPriorityItem, id=item_id)
    item.is_resolved = True
    item.resolved_at = timezone.now()
    item.save(update_fields=['is_resolved', 'resolved_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def send_now(request):
    """Trigger an immediate report send without waiting for Celery Beat."""
    from daily_reports.tasks import send_daily_high_priority_report, send_deep_operations_report
    report_type = request.POST.get('report_type', 'daily')
    try:
        if report_type == 'deep':
            send_deep_operations_report.delay()
        else:
            send_daily_high_priority_report.delay()
        return JsonResponse({'ok': True, 'queued': True})
    except Exception as exc:
        logger.error('send_now failed: %s', exc)
        return JsonResponse({'ok': False, 'error': str(exc)}, status=500)
