"""
dev_hub/tasks.py

Celery tasks for the Dev Hub:
  - send_weekly_progress_report  — runs every Monday at 8 AM via Beat
  - send_task_completion_email   — fires immediately when a dev task is marked done
"""
import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

NOTIFY_EMAIL = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tracking_pixel(sent_email, request=None):
    """Return a tracking pixel <img> tag for the given SentEmail."""
    base = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    url  = f'{base}/emails/track/{sent_email.tracking_pixel_id}/'
    return f'<img src="{url}" width="1" height="1" style="display:none;" alt="" />'


def _create_sent_email(subject, body_html, recipients, sent_by=None):
    """
    Persist a SentEmail record (for open-tracking) and send via Django email.
    Returns the SentEmail instance.
    """
    from docsAppR.models import SentEmail

    sent = SentEmail.objects.create(
        subject=subject,
        body=body_html,
        recipients=recipients if isinstance(recipients, list) else [recipients],
        sent_by=sent_by,
        notify_on_open=False,
    )

    pixel    = _get_tracking_pixel(sent)
    full_html = body_html + pixel

    email = EmailMessage(
        subject=subject,
        body=full_html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=sent.recipients,
    )
    email.content_subtype = 'html'
    email.send()
    return sent


# ---------------------------------------------------------------------------
# Task: send task-completion notification email (non-secretarial only)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_task_completion_email(self, task_id):
    """
    Sends an immediate notification email when a DevTask is marked done.
    Called only for non-secretarial tasks (feature/bug/test).
    Secretarial tasks route through the email compose page instead.
    """
    from dev_hub.models import DevTask

    try:
        task = DevTask.objects.select_related('module', 'added_by').get(id=task_id)
    except DevTask.DoesNotExist:
        logger.error('DevTask %s not found for completion email', task_id)
        return

    module  = task.module
    subject = f'[Dev Hub] Task Complete: {task.title}'

    body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px;">
      <h2 style="color: #1e40af;">Task Completed</h2>
      <hr style="border-color: #e2e8f0;">

      <table style="width: 100%; border-collapse: collapse;">
        <tr><td style="padding: 8px 0; color: #64748b; width: 120px;"><strong>Module</strong></td>
            <td>{module.name} ({module.get_status_display()})</td></tr>
        <tr><td style="padding: 8px 0; color: #64748b;"><strong>Task</strong></td>
            <td>{task.title}</td></tr>
        <tr><td style="padding: 8px 0; color: #64748b;"><strong>Type</strong></td>
            <td>{task.get_task_type_display()}</td></tr>
        <tr><td style="padding: 8px 0; color: #64748b;"><strong>Completed</strong></td>
            <td>{task.completed_at.strftime('%b %d, %Y %H:%M') if task.completed_at else 'Just now'}</td></tr>
        {'<tr><td style="padding: 8px 0; color: #64748b;"><strong>Notes</strong></td><td>' + task.description + '</td></tr>' if task.description else ''}
      </table>

      <hr style="border-color: #e2e8f0; margin-top: 20px;">
      <p style="color: #94a3b8; font-size: 12px;">
        Module progress: {module.completion_pct}% complete
        ({module.task_counts['done']} / {module.task_counts['total']} tasks done)
      </p>
    </div>
    """

    try:
        sent = _create_sent_email(subject, body, [NOTIFY_EMAIL])
        logger.info('Task completion email sent for task=%s, SentEmail=%s', task_id, sent.id)
    except Exception as exc:
        logger.error('Failed to send task completion email for task=%s: %s', task_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            pass


# ---------------------------------------------------------------------------
# Task: weekly progress report (Monday 8 AM via Beat)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def send_weekly_progress_report(self):
    """
    Sends the weekly progress report every Monday at 8 AM.

    Includes only DevTask entries with queue_for_weekly_report=True.
    After sending, clears queue_for_weekly_report on included tasks.
    Creates a ProgressReport record.
    """
    from dev_hub.models import AppModule, DevTask, ProgressReport

    now      = timezone.now()
    modules  = AppModule.objects.prefetch_related('tasks', 'test_coverage').order_by('order', 'name')

    # Collect queued tasks per module
    queued_tasks = DevTask.objects.filter(
        queue_for_weekly_report=True,
    ).select_related('module')

    if not queued_tasks.exists():
        logger.info('Weekly report: no queued tasks found, skipping send')
        return 0

    # Build snapshot
    snapshot = _build_modules_snapshot(modules)

    # Build email body
    body = _build_weekly_report_html(modules, queued_tasks, now)

    subject = f'Weekly Dev Progress Report — {now.strftime("%B %d, %Y")}'

    try:
        sent = _create_sent_email(subject, body, [NOTIFY_EMAIL])
    except Exception as exc:
        logger.error('Weekly report email failed: %s', exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return 0

    # Persist ProgressReport
    report = ProgressReport.objects.create(
        report_type='weekly',
        modules_snapshot=snapshot,
        email_log=sent,
        sent_by=None,
    )
    report.modules.set(modules)

    # Clear queue flags on the tasks that were included
    queued_tasks.update(queue_for_weekly_report=False)

    logger.info('Weekly progress report sent: %s tasks, SentEmail=%s', queued_tasks.count(), sent.id)
    return queued_tasks.count()


# ---------------------------------------------------------------------------
# Helpers: report building
# ---------------------------------------------------------------------------

def _build_modules_snapshot(modules):
    snapshot = []
    for m in modules:
        tc = getattr(m, 'test_coverage', None)
        snapshot.append({
            'id':           m.id,
            'name':         m.name,
            'status':       m.status,
            'completion':   m.completion_pct,
            'task_counts':  m.task_counts,
            'unit_tested':  tc.unit_tested  if tc else False,
            'human_tested': tc.human_tested if tc else False,
            'coverage_pct': float(tc.coverage_pct) if tc else 0,
        })
    return snapshot


def _build_weekly_report_html(modules, queued_tasks, now):
    # Group queued tasks by module
    by_module = {}
    for task in queued_tasks:
        by_module.setdefault(task.module_id, {'module': task.module, 'tasks': []})
        by_module[task.module_id]['tasks'].append(task)

    rows = ''
    for entry in by_module.values():
        m = entry['module']
        rows += f'<tr style="background:#f8fafc;"><td colspan="3" style="padding:10px 12px; font-weight:700; color:#1e40af; border-top:2px solid #e2e8f0;">{m.name} <span style="font-weight:400; color:#64748b;">({m.completion_pct}% complete)</span></td></tr>'
        for task in entry['tasks']:
            badge_color = {'feature': '#3b82f6', 'bug': '#ef4444', 'test': '#8b5cf6', 'secretarial': '#f59e0b'}.get(task.task_type, '#64748b')
            rows += f'''<tr>
              <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9;">{task.title}</td>
              <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9;">
                <span style="background:{badge_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{task.get_task_type_display()}</span>
              </td>
              <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9; color:#64748b; font-size:12px;">{task.completed_at.strftime('%b %d') if task.completed_at else 'completed'}</td>
            </tr>'''

    module_summary = ''
    for m in modules:
        tc = getattr(m, 'test_coverage', None)
        status_color = {'in_dev': '#94a3b8', 'alpha': '#f59e0b', 'beta': '#3b82f6', 'stable': '#16a34a'}.get(m.status, '#94a3b8')
        module_summary += f'''<tr>
          <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9; font-weight:600;">{m.name}</td>
          <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9;">
            <span style="background:{status_color};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;">{m.get_status_display()}</span>
          </td>
          <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9;">
            <div style="background:#e2e8f0;border-radius:4px;height:8px;width:100%;min-width:80px;">
              <div style="background:#1e40af;border-radius:4px;height:8px;width:{m.completion_pct}%;"></div>
            </div>
            <span style="font-size:11px;color:#64748b;">{m.completion_pct}%</span>
          </td>
          <td style="padding:8px 12px; border-bottom:1px solid #f1f5f9; font-size:12px;">
            {'✅' if tc and tc.unit_tested else '❌'} Unit&nbsp;&nbsp;
            {'✅' if tc and tc.human_tested else '❌'} Human
          </td>
        </tr>'''

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 680px; margin: 0 auto; padding: 24px;">
      <h1 style="color:#1e40af; font-size:22px; margin-bottom:4px;">Weekly Development Progress Report</h1>
      <p style="color:#64748b; font-size:13px; margin-bottom:24px;">{now.strftime('%A, %B %d, %Y')}</p>

      <h2 style="font-size:16px; color:#0f172a; margin-bottom:8px;">Completed This Week</h2>
      <table style="width:100%; border-collapse:collapse; margin-bottom:28px;">
        <thead>
          <tr style="background:#1e40af; color:#fff;">
            <th style="padding:10px 12px; text-align:left; font-size:13px;">Task</th>
            <th style="padding:10px 12px; text-align:left; font-size:13px;">Type</th>
            <th style="padding:10px 12px; text-align:left; font-size:13px;">Completed</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>

      <h2 style="font-size:16px; color:#0f172a; margin-bottom:8px;">Module Status Overview</h2>
      <table style="width:100%; border-collapse:collapse; margin-bottom:24px;">
        <thead>
          <tr style="background:#f1f5f9;">
            <th style="padding:8px 12px; text-align:left; font-size:12px; color:#64748b;">MODULE</th>
            <th style="padding:8px 12px; text-align:left; font-size:12px; color:#64748b;">STATUS</th>
            <th style="padding:8px 12px; text-align:left; font-size:12px; color:#64748b;">PROGRESS</th>
            <th style="padding:8px 12px; text-align:left; font-size:12px; color:#64748b;">TESTS</th>
          </tr>
        </thead>
        <tbody>{module_summary}</tbody>
      </table>

      <hr style="border-color:#e2e8f0;">
      <p style="color:#94a3b8; font-size:11px;">
        This report was generated automatically by the Dev Hub.
        Reply to this email to respond, or log in to add response notes.
      </p>
    </div>
    """



# ---------------------------------------------------------------------------
# AI cost reporting & low-balance alerts
# ---------------------------------------------------------------------------

@shared_task
def send_weekly_ai_cost_report():
    """
    Fires every Monday 8 AM (via Celery Beat).
    Sends Joe a summary of last week's AI spend with top-up instructions.
    """
    from django.db.models import Sum, Count, Avg
    from docsAppR.models import AIUsageLog
    from datetime import timedelta

    now        = timezone.now()
    week_start = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    week = AIUsageLog.objects.filter(created_at__gte=week_start).aggregate(
        calls  = Count('id'),
        cost   = Sum('cost_usd'),
        images = Sum('images_count'),
    )
    month = AIUsageLog.objects.filter(created_at__gte=month_start).aggregate(
        cost = Sum('cost_usd'),
    )
    all_time = AIUsageLog.objects.aggregate(cost=Sum('cost_usd'))
    avg_room  = float(AIUsageLog.objects.filter(operation='cps_room').aggregate(a=Avg('cost_usd'))['a'] or 0)

    monthly_budget = getattr(settings, 'AI_MONTHLY_BUDGET_USD', 50.0)
    month_cost     = float(month['cost'] or 0)
    budget_pct     = round(month_cost / monthly_budget * 100, 1) if monthly_budget else 0

    subject = f'[Claimet] Weekly AI Cost Report — {now.strftime("%B %d, %Y")}'

    body = f"""Hi Joe,

Here's your weekly Claimet AI usage summary:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  LAST 7 DAYS
  API calls       : {week['calls'] or 0}
  Images processed: {week['images'] or 0}
  Total cost      : ${float(week['cost'] or 0):.4f}

  THIS MONTH
  Spent so far    : ${month_cost:.4f}
  Monthly budget  : ${monthly_budget:.2f}
  Budget used     : {budget_pct}%

  ALL TIME
  Total AI spend  : ${float(all_time['cost'] or 0):.4f}
  Avg cost/room   : ${avg_room:.5f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{f"⚠️  YOU ARE AT {budget_pct}% OF YOUR MONTHLY BUDGET — consider topping up soon." if budget_pct >= 80 else "✅  Usage is within normal range."}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO ADD CREDITS TO YOUR CLAUDE API ACCOUNT

1. Go to: https://console.anthropic.com/settings/billing
2. Sign in with your Anthropic account credentials.
3. Click "Add Credits" or "Manage Plan".
4. Enter the amount you want to add (minimum $5).
5. Complete payment — credits are available immediately.

If you want to set a spending limit or enable auto-reload:
  Console → Settings → Billing → Spending Limits
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

View live dashboard: https://claimetapp.com/dev-hub/ai-resources/

— Claimet App (automated report)
"""

    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[NOTIFY_EMAIL],
        )
        msg.send()
        logger.info(f"Weekly AI cost report sent to {NOTIFY_EMAIL}")
    except Exception as e:
        logger.error(f"Weekly AI cost report email failed: {e}", exc_info=True)


@shared_task
def check_ai_budget_alert():
    """
    Runs every hour. Sends a one-time alert email when monthly spend
    crosses AI_LOW_BALANCE_THRESHOLD (default 80%) of AI_MONTHLY_BUDGET_USD.
    Uses Django cache to avoid spamming — alert fires at most once per day.
    """
    from django.db.models import Sum
    from django.core.cache import cache
    from docsAppR.models import AIUsageLog

    monthly_budget    = getattr(settings, 'AI_MONTHLY_BUDGET_USD', 50.0)
    alert_threshold   = getattr(settings, 'AI_LOW_BALANCE_THRESHOLD', 0.80)
    if not monthly_budget:
        return

    now         = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_cost  = float(
        AIUsageLog.objects.filter(created_at__gte=month_start)
        .aggregate(t=Sum('cost_usd'))['t'] or 0
    )
    fraction = month_cost / monthly_budget

    if fraction < alert_threshold:
        return  # All good, nothing to do

    cache_key = f'ai_budget_alert_sent_{now.strftime("%Y%m%d")}'
    if cache.get(cache_key):
        return  # Already alerted today

    pct = round(fraction * 100, 1)
    subject = f'[Claimet] ⚠️ AI Credits at {pct}% — Top up your Claude account'
    body = f"""Hi Joe,

Your Claimet AI budget is at {pct}% for this month.

  Spent this month : ${month_cost:.2f}
  Monthly budget   : ${monthly_budget:.2f}
  Remaining        : ${monthly_budget - month_cost:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO TOP UP YOUR CLAUDE API CREDITS

1. Go to: https://console.anthropic.com/settings/billing
2. Sign in with your Anthropic account.
3. Click "Add Credits" — credits are available immediately after payment.
4. Recommended: enable "Auto-reload" so claims never fail mid-run.

If a claim fails because credits ran out, the rooms will show as "error" status.
You can re-run them individually from the CPS Report session page after topping up.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Live dashboard: https://claimetapp.com/dev-hub/ai-resources/

— Claimet App
"""
    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[NOTIFY_EMAIL],
        )
        msg.send()
        cache.set(cache_key, True, 60 * 60 * 20)  # suppress for 20 hours
        logger.info(f"AI budget alert sent — {pct}% of budget used")
    except Exception as e:
        logger.error(f"AI budget alert email failed: {e}", exc_info=True)
