"""
Task Manager views.
"""
import json
import logging
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from docsAppR.models import TaskItem, Client, Lease, CustomUser

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _task_to_dict(task):
    return {
        'id':          str(task.id),
        'title':       task.title,
        'description': task.description,
        'status':      task.status,
        'status_display': task.get_status_display(),
        'priority':    task.priority,
        'priority_display': task.get_priority_display(),
        'priority_color':   task.priority_color,
        'category':    task.category,
        'category_display': task.get_category_display(),
        'assigned_to': task.assigned_to.email if task.assigned_to else '',
        'assigned_to_id': task.assigned_to_id,
        'due_date':    task.due_date.isoformat() if task.due_date else '',
        'is_overdue':  task.is_overdue,
        'related_client': task.related_client.pOwner if task.related_client else '',
        'related_client_id': task.related_client_id,
        'related_lease_id':  str(task.related_lease_id) if task.related_lease_id else '',
        'notes':       task.notes,
        'created_at':  task.created_at.isoformat(),
    }


# ── Main board ────────────────────────────────────────────────────────────────

@login_required
def task_board(request):
    """
    Kanban task board — To Do / In Progress / Review / Done.
    """
    today     = date.today()
    tomorrow  = today + timedelta(days=1)
    week_end  = today + timedelta(days=7)

    # Filters
    f_status   = request.GET.get('status', '')
    f_priority = request.GET.get('priority', '')
    f_mine     = request.GET.get('mine', '')
    f_client   = request.GET.get('client', '')
    f_category = request.GET.get('category', '')

    qs = TaskItem.objects.select_related(
        'assigned_to', 'created_by', 'related_client', 'related_lease'
    )

    if f_status:
        qs = qs.filter(status=f_status)
    if f_priority:
        qs = qs.filter(priority=f_priority)
    if f_mine:
        qs = qs.filter(assigned_to=request.user)
    if f_client:
        qs = qs.filter(related_client__id=f_client)
    if f_category:
        qs = qs.filter(category=f_category)

    # Group into columns
    active   = qs.exclude(status__in=['done', 'cancelled', 'backlog'])
    backlog  = qs.filter(status='backlog').order_by('priority', 'due_date')[:30]
    todo     = qs.filter(status='todo').order_by('priority', 'due_date')
    in_prog  = qs.filter(status='in_progress').order_by('priority', 'due_date')
    review   = qs.filter(status='review').order_by('priority', 'due_date')
    done_qs  = qs.filter(status='done').order_by('-completed_at')[:20]

    # Stats (global, ignore filters for the stats cards)
    base = TaskItem.objects
    stats = {
        'open':      base.exclude(status__in=['done', 'cancelled']).count(),
        'due_today': base.filter(due_date=today).exclude(status__in=['done', 'cancelled']).count(),
        'overdue':   base.filter(due_date__lt=today).exclude(status__in=['done', 'cancelled']).count(),
        'done_week': base.filter(status='done', completed_at__date__gte=today - timedelta(days=7)).count(),
        'urgent':    base.filter(priority='urgent').exclude(status__in=['done', 'cancelled']).count(),
        'mine':      base.filter(assigned_to=request.user).exclude(status__in=['done', 'cancelled']).count(),
    }

    context = {
        'backlog':   backlog,
        'todo':      todo,
        'in_prog':   in_prog,
        'review':    review,
        'done_qs':   done_qs,
        'stats':     stats,
        'today':     today,
        'tomorrow':  tomorrow,
        'week_end':  week_end,

        # For filters
        'status_choices':   TaskItem.STATUS_CHOICES,
        'priority_choices': TaskItem.PRIORITY_CHOICES,
        'category_choices': TaskItem.CATEGORY_CHOICES,
        'all_clients':      Client.objects.order_by('pOwner')[:100],
        'all_users':        CustomUser.objects.filter(is_active=True).order_by('email'),

        # Active filters
        'f_status':   f_status,
        'f_priority': f_priority,
        'f_mine':     f_mine,
        'f_client':   f_client,
        'f_category': f_category,

        # Prefill for create modal
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
        data = json.loads(request.body) if request.content_type == 'application/json' \
               else request.POST

        title    = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        due_raw   = data.get('due_date', '')
        due_date  = None
        if due_raw:
            from django.utils.dateparse import parse_date
            due_date = parse_date(due_raw)

        client_id = data.get('related_client_id') or None
        lease_id  = data.get('related_lease_id') or None
        user_id   = data.get('assigned_to_id') or None

        task = TaskItem.objects.create(
            title=title,
            description=(data.get('description') or '').strip(),
            status=data.get('status', 'todo'),
            priority=data.get('priority', 'medium'),
            category=data.get('category', 'general'),
            due_date=due_date,
            notes=(data.get('notes') or '').strip(),
            created_by=request.user,
            assigned_to_id=user_id,
            related_client_id=client_id if client_id else None,
            related_lease_id=lease_id if lease_id else None,
        )

        try:
            from docsAppR.models import log_activity
            log_activity('other', f'Task created: {title}',
                         user=request.user,
                         client=task.related_client,
                         lease=task.related_lease)
        except Exception:
            pass

        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        logger.error('task_create error: %s', exc)
        return JsonResponse({'error': str(exc)}, status=500)


# ── Edit ──────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def task_edit(request, task_id):
    task = get_object_or_404(TaskItem, id=task_id)
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' \
               else request.POST

        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        due_raw  = data.get('due_date', '')
        due_date = None
        if due_raw:
            from django.utils.dateparse import parse_date
            due_date = parse_date(due_raw)

        old_status = task.status
        new_status = data.get('status', task.status)

        task.title       = title
        task.description = (data.get('description') or '').strip()
        task.status      = new_status
        task.priority    = data.get('priority', task.priority)
        task.category    = data.get('category', task.category)
        task.due_date    = due_date
        task.notes       = (data.get('notes') or '').strip()
        task.assigned_to_id   = data.get('assigned_to_id') or None
        task.related_client_id = data.get('related_client_id') or None
        task.related_lease_id  = data.get('related_lease_id') or None

        if new_status == 'done' and old_status != 'done':
            task.completed_at = timezone.now()
        elif new_status != 'done':
            task.completed_at = None

        task.save()
        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        logger.error('task_edit error: %s', exc)
        return JsonResponse({'error': str(exc)}, status=500)


# ── Quick status update (drag-and-drop / column move) ─────────────────────────

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

        old_status    = task.status
        task.status   = new_status
        if new_status == 'done' and old_status != 'done':
            task.completed_at = timezone.now()
        elif new_status != 'done':
            task.completed_at = None
        task.save(update_fields=['status', 'completed_at', 'updated_at'])

        return JsonResponse({'success': True, 'task': _task_to_dict(task)})

    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


# ── Delete ────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def task_delete(request, task_id):
    task = get_object_or_404(TaskItem, id=task_id)
    title = task.title
    task.delete()
    return JsonResponse({'success': True, 'deleted_title': title})


# ── JSON list (used by dashboard widget / quick popups) ───────────────────────

@login_required
def api_tasks(request):
    status   = request.GET.get('status', '')
    mine     = request.GET.get('mine', '')
    limit    = int(request.GET.get('limit', 50))

    qs = TaskItem.objects.select_related('assigned_to', 'related_client')
    if status:
        qs = qs.filter(status=status)
    if mine:
        qs = qs.filter(assigned_to=request.user)

    tasks = [_task_to_dict(t) for t in qs[:limit]]
    return JsonResponse({'tasks': tasks, 'count': len(tasks)})
