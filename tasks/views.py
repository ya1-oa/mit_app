"""
Task Manager views.

Flows
-----
1. task_create  → saves task → if assigned_to set, emails assignee
2. task_edit    → saves task → if assigned_to changed, emails new assignee
3. task_complete → called by assignee → marks done, saves notes, emails
                   assigner + admin; for dev tasks also records audit flags
4. task_status  → lightweight column-move (no completion email; use
                   task_complete for 'done')
5. task_delete  → hard delete
6. api_tasks    → JSON list for dashboard widgets
"""

import json
import logging
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from docsAppR.models import TaskItem, Client, Lease, CustomUser

logger = logging.getLogger(__name__)

OWNER_EMAIL = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')
FROM_EMAIL  = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@claimetapp.com')
SITE_URL    = getattr(settings, 'SITE_URL', 'https://claimetapp.com')


# ── Dict serialiser ───────────────────────────────────────────────────────────

def _task_to_dict(task):
    return {
        'id':               str(task.id),
        'title':            task.title,
        'description':      task.description,
        'status':           task.status,
        'status_display':   task.get_status_display(),
        'priority':         task.priority,
        'priority_display': task.get_priority_display(),
        'priority_color':   task.priority_color,
        'category':         task.category,
        'category_display': task.get_category_display(),
        'assigned_to':      task.assigned_to.email if task.assigned_to else '',
        'assigned_to_id':   task.assigned_to_id,
        'due_date':         task.due_date.isoformat() if task.due_date else '',
        'is_overdue':       task.is_overdue,
        'related_client':   task.related_client.pOwner if task.related_client else '',
        'related_client_id': task.related_client_id,
        'related_lease_id': str(task.related_lease_id) if task.related_lease_id else '',
        'notes':            task.notes,
        'completed_by':     task.completed_by.email if task.completed_by else '',
        'completion_notes': task.completion_notes,
        'unit_tests_passed': task.unit_tests_passed,
        'beta_tested':      task.beta_tested,
        'test_notes':       task.test_notes,
        'created_at':       task.created_at.isoformat(),
    }


# ── Email helpers ─────────────────────────────────────────────────────────────

def _send_assignment_email(task, assigner):
    """
    Email the assignee when a task is created or re-assigned to them.
    assigner = the user who created/edited the task.
    """
    if not task.assigned_to or not task.assigned_to.email:
        return
    # Don't email someone who assigned it to themselves
    if assigner and task.assigned_to_id == assigner.id:
        return

    due_str  = task.due_date.strftime('%B %d, %Y') if task.due_date else 'No deadline set'
    client_s = f'\nRelated Claim: {task.related_client.pOwner}' if task.related_client else ''
    assigner_name = assigner.email if assigner else 'the system'

    body = f"""Hi {task.assigned_to.email},

{assigner_name} has assigned you a task in Claimet:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TASK:      {task.title}
 PRIORITY:  {task.get_priority_display()}
 CATEGORY:  {task.get_category_display()}
 DUE:       {due_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{client_s}

Description:
{task.description or '(no description)'}

Notes from assigner:
{task.notes or '(none)'}

View the task board: {SITE_URL}/tasks/

— Claimet App
"""
    try:
        msg = EmailMessage(
            subject=f'[Claimet] Task Assigned: {task.title}',
            body=body,
            from_email=FROM_EMAIL,
            to=[task.assigned_to.email],
            reply_to=[assigner.email] if assigner else [],
        )
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.warning('task assignment email failed: %s', exc)


def _send_completion_email(task, completer):
    """
    Email the task creator (assigner) + admin when a task is marked complete.
    completer = request.user who submitted the completion form.
    """
    recipients = []
    if task.created_by and task.created_by.email:
        recipients.append(task.created_by.email)
    if OWNER_EMAIL and OWNER_EMAIL not in recipients:
        recipients.append(OWNER_EMAIL)
    if not recipients:
        return

    # Time-to-complete
    if task.completed_at and task.created_at:
        delta   = task.completed_at - task.created_at
        days    = delta.days
        hours   = delta.seconds // 3600
        dur_str = f'{days}d {hours}h' if days else f'{hours}h {(delta.seconds % 3600) // 60}m'
    else:
        dur_str = 'unknown'

    due_str = task.due_date.strftime('%B %d, %Y') if task.due_date else '—'

    # Code audit block (development tasks only)
    audit_block = ''
    if task.category == 'development':
        ut  = '✓ PASSED' if task.unit_tests_passed is True \
              else ('✗ FAILED' if task.unit_tests_passed is False else '— N/A')
        bt  = '✓ YES'    if task.beta_tested is True \
              else ('✗ NO'     if task.beta_tested is False         else '— N/A')
        audit_block = f"""
CODE AUDIT
  Unit Tests:   {ut}
  Beta Tested:  {bt}
  Test Notes:   {task.test_notes or '(none)'}
"""

    body = f"""Hi,

{completer.email} has completed a task:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TASK:         {task.title}
 CATEGORY:     {task.get_category_display()}
 PRIORITY:     {task.get_priority_display()}
 DUE DATE:     {due_str}
 COMPLETED:    {task.completed_at.strftime('%B %d, %Y at %H:%M UTC') if task.completed_at else '—'}
 TIME TAKEN:   {dur_str}
 COMPLETED BY: {completer.email}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMPLETION NOTES:
{task.completion_notes or '(no notes provided)'}
{audit_block}
View the task board: {SITE_URL}/tasks/

— Claimet App
"""
    try:
        msg = EmailMessage(
            subject=f'[Claimet] ✓ Task Completed: {task.title}',
            body=body,
            from_email=FROM_EMAIL,
            to=recipients,
        )
        msg.send(fail_silently=True)
    except Exception as exc:
        logger.warning('task completion email failed: %s', exc)


# ── Main board ────────────────────────────────────────────────────────────────

@login_required
def task_board(request):
    today    = date.today()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=7)

    f_status   = request.GET.get('status',   '')
    f_priority = request.GET.get('priority', '')
    f_mine     = request.GET.get('mine',     '')
    f_client   = request.GET.get('client',   '')
    f_category = request.GET.get('category', '')

    qs = TaskItem.objects.select_related(
        'assigned_to', 'created_by', 'completed_by',
        'related_client', 'related_lease',
    )
    if f_status:   qs = qs.filter(status=f_status)
    if f_priority: qs = qs.filter(priority=f_priority)
    if f_mine:     qs = qs.filter(assigned_to=request.user)
    if f_client:   qs = qs.filter(related_client__id=f_client)
    if f_category: qs = qs.filter(category=f_category)

    backlog = qs.filter(status='backlog').order_by('priority', 'due_date')[:30]
    todo    = qs.filter(status='todo').order_by('priority', 'due_date')
    in_prog = qs.filter(status='in_progress').order_by('priority', 'due_date')
    review  = qs.filter(status='review').order_by('priority', 'due_date')
    done_qs = qs.filter(status='done').order_by('-completed_at')[:20]

    base = TaskItem.objects
    stats = {
        'open':      base.exclude(status__in=['done', 'cancelled']).count(),
        'due_today': base.filter(due_date=today).exclude(status__in=['done', 'cancelled']).count(),
        'overdue':   base.filter(due_date__lt=today).exclude(status__in=['done', 'cancelled']).count(),
        'done_week': base.filter(status='done',
                         completed_at__date__gte=today - timedelta(days=7)).count(),
        'urgent':    base.filter(priority='urgent').exclude(status__in=['done', 'cancelled']).count(),
        'mine':      base.filter(assigned_to=request.user).exclude(status__in=['done', 'cancelled']).count(),
    }

    context = {
        'backlog': backlog, 'todo': todo, 'in_prog': in_prog,
        'review':  review,  'done_qs': done_qs, 'stats': stats,
        'today': today, 'tomorrow': tomorrow, 'week_end': week_end,
        'status_choices':   TaskItem.STATUS_CHOICES,
        'priority_choices': TaskItem.PRIORITY_CHOICES,
        'category_choices': TaskItem.CATEGORY_CHOICES,
        'all_clients':      Client.objects.order_by('pOwner')[:100],
        'all_users':        CustomUser.objects.filter(is_active=True).order_by('email'),
        'f_status': f_status, 'f_priority': f_priority, 'f_mine': f_mine,
        'f_client': f_client, 'f_category': f_category,
        'clients_json': json.dumps([
            {'id': c.id, 'name': c.pOwner}
            for c in Client.objects.order_by('pOwner')[:200]
        ]),
        'users_json': json.dumps([
            {'id': u.id, 'email': u.email}
            for u in CustomUser.objects.filter(is_active=True).order_by('email')
        ]),
    }
    return render(request, 'account/task_board.html', context)


# ── Create ────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def task_create(request):
    try:
        data  = json.loads(request.body) if request.content_type == 'application/json' \
                else request.POST
        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        due_date = None
        if data.get('due_date'):
            from django.utils.dateparse import parse_date
            due_date = parse_date(data['due_date'])

        task = TaskItem.objects.create(
            title=title,
            description=(data.get('description') or '').strip(),
            status=data.get('status', 'todo'),
            priority=data.get('priority', 'medium'),
            category=data.get('category', 'general'),
            due_date=due_date,
            notes=(data.get('notes') or '').strip(),
            created_by=request.user,
            assigned_to_id=data.get('assigned_to_id') or None,
            related_client_id=data.get('related_client_id') or None,
            related_lease_id=data.get('related_lease_id') or None,
        )

        _send_assignment_email(task, assigner=request.user)

        try:
            from docsAppR.models import log_activity
            log_activity('other', f'Task created: {title}',
                         user=request.user, client=task.related_client,
                         lease=task.related_lease)
        except Exception:
            pass

        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        logger.error('task_create: %s', exc)
        return JsonResponse({'error': str(exc)}, status=500)


# ── Edit ──────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def task_edit(request, task_id):
    task = get_object_or_404(TaskItem, id=task_id)
    try:
        data  = json.loads(request.body) if request.content_type == 'application/json' \
                else request.POST
        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        due_date = None
        if data.get('due_date'):
            from django.utils.dateparse import parse_date
            due_date = parse_date(data['due_date'])

        old_assignee_id = task.assigned_to_id
        old_status      = task.status
        new_status      = data.get('status', task.status)
        new_assignee_id = data.get('assigned_to_id') or None

        task.title       = title
        task.description = (data.get('description') or '').strip()
        task.status      = new_status
        task.priority    = data.get('priority', task.priority)
        task.category    = data.get('category', task.category)
        task.due_date    = due_date
        task.notes       = (data.get('notes') or '').strip()
        task.assigned_to_id    = new_assignee_id
        task.related_client_id = data.get('related_client_id') or None
        task.related_lease_id  = data.get('related_lease_id') or None

        if new_status == 'done' and old_status != 'done':
            task.completed_at = timezone.now()
        elif new_status != 'done':
            task.completed_at = None
        task.save()

        # Email if assignee changed
        if new_assignee_id and new_assignee_id != old_assignee_id:
            _send_assignment_email(task, assigner=request.user)

        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        logger.error('task_edit: %s', exc)
        return JsonResponse({'error': str(exc)}, status=500)


# ── Complete (with notes + code audit) ───────────────────────────────────────

@login_required
@require_POST
def task_complete(request, task_id):
    """
    Mark a task done, save completion notes, optionally record code-audit
    flags (unit_tests_passed, beta_tested, test_notes), and email the
    assigner + admin about the completion.
    """
    task = get_object_or_404(TaskItem, id=task_id)

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' \
               else request.POST

        task.status           = 'done'
        task.completed_by     = request.user
        task.completed_at     = timezone.now()
        task.completion_notes = (data.get('completion_notes') or '').strip()

        # Code audit fields — only meaningful for development tasks
        if task.category == 'development':
            ut = data.get('unit_tests_passed')
            bt = data.get('beta_tested')
            task.unit_tests_passed = (True  if ut in (True,  'true',  '1', 1) else
                                       False if ut in (False, 'false', '0', 0) else None)
            task.beta_tested       = (True  if bt in (True,  'true',  '1', 1) else
                                       False if bt in (False, 'false', '0', 0) else None)
            task.test_notes = (data.get('test_notes') or '').strip()

        task.save()

        _send_completion_email(task, completer=request.user)

        try:
            from docsAppR.models import log_activity
            log_activity('other', f'Task completed: {task.title}',
                         user=request.user, client=task.related_client,
                         lease=task.related_lease)
        except Exception:
            pass

        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        logger.error('task_complete: %s', exc)
        return JsonResponse({'error': str(exc)}, status=500)


# ── Quick status update (column move, NOT the full completion flow) ────────────

@login_required
@require_POST
def task_status(request, task_id):
    task = get_object_or_404(TaskItem, id=task_id)
    try:
        data       = json.loads(request.body)
        new_status = data.get('status', '').strip()
        valid      = [s for s, _ in TaskItem.STATUS_CHOICES]
        if new_status not in valid:
            return JsonResponse({'error': f'Invalid status: {new_status}'}, status=400)
        # Block moving directly to 'done' without notes — frontend should
        # intercept this and open the completion modal instead.
        if new_status == 'done':
            return JsonResponse(
                {'error': 'use_complete_flow', 'task_id': str(task.id)},
                status=400,
            )

        task.status       = new_status
        task.completed_at = None
        task.save(update_fields=['status', 'completed_at', 'updated_at'])

        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


# ── Delete ────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def task_delete(request, task_id):
    task  = get_object_or_404(TaskItem, id=task_id)
    title = task.title
    task.delete()
    return JsonResponse({'success': True, 'deleted_title': title})


# ── JSON list ─────────────────────────────────────────────────────────────────

@login_required
def api_tasks(request):
    status = request.GET.get('status', '')
    mine   = request.GET.get('mine',   '')
    limit  = int(request.GET.get('limit', 50))

    qs = TaskItem.objects.select_related('assigned_to', 'completed_by', 'related_client')
    if status: qs = qs.filter(status=status)
    if mine:   qs = qs.filter(assigned_to=request.user)

    tasks = [_task_to_dict(t) for t in qs[:limit]]
    return JsonResponse({'tasks': tasks, 'count': len(tasks)})
