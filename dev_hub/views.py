"""
dev_hub/views.py

Views for the internal development hub:
  - dashboard       — all AppModules overview
  - module_detail   — single module with tasks, coverage, report history
  - task_toggle     — AJAX: toggle task status + trigger notifications
  - task_add        — AJAX: add a new task inline
  - task_queue      — AJAX: toggle queue_for_weekly_report
  - report_adhoc    — trigger ad-hoc progress report
  - notify_client   — route to email compose pre-filled with feature context
  - report_response — save owner's response notes
"""
import json
import logging
import urllib.parse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AppModule, DevTask, TestCoverage, ProgressReport

logger = logging.getLogger(__name__)

NOTIFY_EMAIL = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')


# ---------------------------------------------------------------------------
# Dashboard — all modules
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    modules = AppModule.objects.prefetch_related(
        'tasks', 'test_coverage', 'progress_reports'
    ).order_by('order', 'name')

    # Annotate last report + open status
    module_data = []
    for m in modules:
        last = m.last_report
        module_data.append({
            'module':      m,
            'last_report': last,
            'opened':      last.email_log.is_opened if last and last.email_log else None,
        })

    context = {
        'module_data': module_data,
        'total_modules': modules.count(),
        'stable_count':  modules.filter(status='stable').count(),
        'in_dev_count':  modules.filter(status='in_dev').count(),
    }
    return render(request, 'dev_hub/dashboard.html', context)


# ---------------------------------------------------------------------------
# Module detail
# ---------------------------------------------------------------------------

@login_required
def module_detail(request, slug):
    module = get_object_or_404(AppModule, slug=slug)
    tasks  = module.tasks.select_related('added_by').order_by('order', 'created_at')
    try:
        coverage = module.test_coverage
    except TestCoverage.DoesNotExist:
        coverage = None

    reports = module.progress_reports.order_by('-sent_at')[:5]

    context = {
        'module':   module,
        'tasks':    tasks,
        'coverage': coverage,
        'reports':  reports,
        'task_counts': module.task_counts,
    }
    return render(request, 'dev_hub/module_detail.html', context)


# ---------------------------------------------------------------------------
# AJAX: toggle task status
# ---------------------------------------------------------------------------

@login_required
@require_POST
def task_toggle(request, task_id):
    """
    Toggle a task between done and todo.
    Returns JSON with new status, completion_pct, and whether notification
    should be a redirect (secretarial) or was auto-sent.
    """
    task = get_object_or_404(DevTask, id=task_id)
    was_done = (task.status == 'done')

    if was_done:
        task.mark_todo()
        action = 'reverted'
        notify_redirect = None
    else:
        task.mark_done()
        action = 'completed'
        notify_redirect = None

        if task.notify_on_complete:
            if task.is_secretarial:
                # Route to email compose pre-filled — frontend handles the redirect
                notify_redirect = _compose_url_for_task(task)
            else:
                # Auto-send email via Celery
                from dev_hub.tasks import send_task_completion_email
                send_task_completion_email.delay(str(task.id))

    return JsonResponse({
        'action':          action,
        'status':          task.status,
        'status_label':    task.get_status_display(),
        'completed_at':    task.completed_at.isoformat() if task.completed_at else None,
        'completion_pct':  task.module.completion_pct,
        'task_counts':     task.module.task_counts,
        'notify_redirect': notify_redirect,
    })


# ---------------------------------------------------------------------------
# AJAX: add task
# ---------------------------------------------------------------------------

@login_required
@require_POST
def task_add(request, module_id):
    module = get_object_or_404(AppModule, id=module_id)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = request.POST

    title               = (data.get('title') or '').strip()
    description         = (data.get('description') or '').strip()
    task_type           = data.get('task_type', 'feature')
    notify_on_complete  = bool(data.get('notify_on_complete', False))
    queue_for_report    = bool(data.get('queue_for_weekly_report', False))

    if not title:
        return JsonResponse({'error': 'Title is required'}, status=400)

    valid_types = [c[0] for c in DevTask.TASK_TYPE_CHOICES]
    if task_type not in valid_types:
        task_type = 'feature'

    task = DevTask.objects.create(
        module               = module,
        title                = title,
        description          = description,
        task_type            = task_type,
        notify_on_complete   = notify_on_complete,
        queue_for_weekly_report = queue_for_report,
        added_by             = request.user,
        order                = module.tasks.count(),
    )

    return JsonResponse({
        'id':          str(task.id),
        'title':       task.title,
        'task_type':   task.task_type,
        'type_label':  task.get_task_type_display(),
        'status':      task.status,
        'completion_pct': module.completion_pct,
        'task_counts': module.task_counts,
    }, status=201)


# ---------------------------------------------------------------------------
# AJAX: toggle queue_for_weekly_report
# ---------------------------------------------------------------------------

@login_required
@require_POST
def task_queue_toggle(request, task_id):
    task = get_object_or_404(DevTask, id=task_id)
    task.queue_for_weekly_report = not task.queue_for_weekly_report
    task.save(update_fields=['queue_for_weekly_report', 'updated_at'])
    return JsonResponse({'queued': task.queue_for_weekly_report})


# ---------------------------------------------------------------------------
# Ad-hoc progress report
# ---------------------------------------------------------------------------

@login_required
@require_POST
def report_adhoc(request):
    """
    Trigger an ad-hoc progress report for selected (or all) modules.
    Builds the report and sends via email system.
    """
    from dev_hub.tasks import (
        _build_modules_snapshot, _build_weekly_report_html, _create_sent_email,
    )

    module_ids = request.POST.getlist('module_ids')
    if module_ids:
        modules = AppModule.objects.filter(id__in=module_ids).prefetch_related(
            'tasks', 'test_coverage'
        )
    else:
        modules = AppModule.objects.prefetch_related('tasks', 'test_coverage').order_by('order')

    queued_tasks = DevTask.objects.filter(
        module__in=modules, queue_for_weekly_report=True,
    ).select_related('module')

    snapshot = _build_modules_snapshot(modules)
    now      = timezone.now()
    body     = _build_weekly_report_html(modules, queued_tasks, now)
    subject  = f'Dev Progress Update — {now.strftime("%B %d, %Y")}'

    try:
        sent = _create_sent_email(subject, body, [NOTIFY_EMAIL], sent_by=request.user)
    except Exception as exc:
        messages.error(request, f'Failed to send report: {exc}')
        return redirect('dev_hub:dashboard')

    report = ProgressReport.objects.create(
        report_type='adhoc',
        modules_snapshot=snapshot,
        email_log=sent,
        sent_by=request.user,
    )
    report.modules.set(modules)
    queued_tasks.update(queue_for_weekly_report=False)

    messages.success(request, f'Progress report sent to {NOTIFY_EMAIL}.')
    return redirect('dev_hub:dashboard')


# ---------------------------------------------------------------------------
# Notify client of a specific feature — routes to email compose pre-filled
# ---------------------------------------------------------------------------

@login_required
def notify_client(request, task_id):
    """
    Redirect to the central email compose page with context pre-filled.
    Works for any task type when the owner wants to manually notify the client.
    """
    task   = get_object_or_404(DevTask, id=task_id)
    params = _compose_params_for_task(task)
    return redirect(f'/emails/?{urllib.parse.urlencode(params)}')


# ---------------------------------------------------------------------------
# Save response notes on a report
# ---------------------------------------------------------------------------

@login_required
@require_POST
def report_response(request, report_id):
    report = get_object_or_404(ProgressReport, id=report_id)
    notes  = request.POST.get('response_notes', '').strip()
    report.response_notes = notes
    report.save(update_fields=['response_notes'])
    messages.success(request, 'Response notes saved.')
    return redirect(request.POST.get('next', 'dev_hub:dashboard'))


# ---------------------------------------------------------------------------
# Coverage update (inline from module detail)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def coverage_update(request, module_id):
    module   = get_object_or_404(AppModule, id=module_id)
    coverage, _ = TestCoverage.objects.get_or_create(module=module)

    coverage.unit_tested  = 'unit_tested'  in request.POST
    coverage.human_tested = 'human_tested' in request.POST
    try:
        coverage.coverage_pct = float(request.POST.get('coverage_pct', 0))
    except (TypeError, ValueError):
        coverage.coverage_pct = 0
    coverage.notes = request.POST.get('notes', '').strip()
    coverage.save()

    messages.success(request, 'Test coverage updated.')
    return redirect('dev_hub:module_detail', slug=module.slug)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compose_params_for_task(task):
    """Build query-string parameters for the email compose page pre-fill."""
    subject = f'Update: {task.title} — {task.module.name}'
    body    = (
        f'Hi,\n\n'
        f'I wanted to let you know that the following has been completed:\n\n'
        f'Module: {task.module.name}\n'
        f'Task: {task.title}\n'
        f'Type: {task.get_task_type_display()}\n'
        + (f'\nDetails: {task.description}' if task.description else '')
        + f'\n\nModule is now {task.module.completion_pct}% complete.\n\n'
        f'Best regards'
    )
    return {
        'prefill_subject': subject,
        'prefill_body':    body,
        'prefill_to':      NOTIFY_EMAIL,
    }


def _compose_url_for_task(task):
    params = _compose_params_for_task(task)
    return f'/emails/?{urllib.parse.urlencode(params)}'


# ---------------------------------------------------------------------------
# AI Resources — cost & usage dashboard
# ---------------------------------------------------------------------------

@login_required
def ai_resources(request):
    """
    Internal dashboard showing AI token usage, cost per operation,
    cost per CPS session, and all-time totals across the platform.
    """
    from django.db.models import Sum, Count, Avg, F
    from docsAppR.models import AIUsageLog

    # ── All-time summary ────────────────────────────────────────────────────
    totals = AIUsageLog.objects.aggregate(
        total_calls    = Count('id'),
        total_input    = Sum('input_tokens'),
        total_output   = Sum('output_tokens'),
        total_cost     = Sum('cost_usd'),
        total_images   = Sum('images_count'),
    )

    # ── Per-operation breakdown ──────────────────────────────────────────────
    by_operation = list(
        AIUsageLog.objects.values('operation')
        .annotate(
            calls        = Count('id'),
            input_tok    = Sum('input_tokens'),
            output_tok   = Sum('output_tokens'),
            cost         = Sum('cost_usd'),
            images       = Sum('images_count'),
            avg_cost     = Avg('cost_usd'),
        )
        .order_by('-cost')
    )

    # ── Per-model breakdown ──────────────────────────────────────────────────
    by_model = list(
        AIUsageLog.objects.values('model')
        .annotate(calls=Count('id'), cost=Sum('cost_usd'))
        .order_by('-cost')
    )

    # ── Last 30 CPS sessions with their cost ────────────────────────────────
    from cps_report.models import CPSReportSession
    recent_sessions = []
    for s in CPSReportSession.objects.order_by('-created_at')[:30]:
        cost = float(
            AIUsageLog.objects.filter(cps_session_id=s.id)
            .aggregate(t=Sum('cost_usd'))['t'] or 0
        )
        rooms = s.rooms.count()
        recent_sessions.append({
            'id':           s.id,
            'insured':      s.insured_name or '—',
            'claim':        s.claim_number or '—',
            'rooms':        rooms,
            'cost':         cost,
            'cost_per_room': round(cost / rooms, 4) if rooms else 0,
            'date':         s.created_at,
            'status':       s.status,
        })

    # ── Average cost per room across all sessions ───────────────────────────
    avg_cost_per_room = (
        AIUsageLog.objects.filter(operation='cps_room')
        .aggregate(avg=Avg('cost_usd'))['avg'] or 0
    )
    avg_images_per_room = (
        AIUsageLog.objects.filter(operation='cps_room')
        .aggregate(avg=Avg('images_count'))['avg'] or 0
    )

    # ── Recent log entries ──────────────────────────────────────────────────
    recent_logs = AIUsageLog.objects.order_by('-created_at')[:50]

    # ── Estimated budget left (using configured threshold) ─────────────────
    MONTHLY_BUDGET = float(getattr(settings, 'AI_MONTHLY_BUDGET_USD', 50.0))
    from django.utils import timezone as tz
    from datetime import datetime
    month_start = tz.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_cost  = float(
        AIUsageLog.objects.filter(created_at__gte=month_start)
        .aggregate(t=Sum('cost_usd'))['t'] or 0
    )
    budget_pct  = min(100, round((month_cost / MONTHLY_BUDGET * 100) if MONTHLY_BUDGET else 0, 1))

    return render(request, 'dev_hub/ai_resources.html', {
        'totals':            totals,
        'by_operation':      by_operation,
        'by_model':          by_model,
        'recent_sessions':   recent_sessions,
        'recent_logs':       recent_logs,
        'avg_cost_per_room': float(avg_cost_per_room),
        'avg_images_per_room': float(avg_images_per_room),
        'monthly_budget':    MONTHLY_BUDGET,
        'month_cost':        month_cost,
        'budget_pct':        budget_pct,
    })


@login_required
def ai_usage_data(request):
    """JSON endpoint — daily cost series for the last 30 days (chart data)."""
    from django.db.models import Sum
    from django.db.models.functions import TruncDate
    from docsAppR.models import AIUsageLog

    rows = (
        AIUsageLog.objects
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(cost=Sum('cost_usd'), calls=Sum('id'))
        .order_by('day')
    )
    return JsonResponse({
        'labels': [str(r['day']) for r in rows],
        'costs':  [float(r['cost']) for r in rows],
    })
