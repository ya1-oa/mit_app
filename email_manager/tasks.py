"""
email_manager/tasks.py

Celery tasks for scheduled email sends and campaign dispatch.

Registration in settings.CELERY_BEAT_SCHEDULE:
    'process-scheduled-emails': {
        'task': 'email_manager.tasks.send_scheduled_emails_task',
        'schedule': crontab(minute='*'),  # every minute
    }
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_and_send(subject, body, recipients, cc=None, bcc=None,
                    from_email=None, tracking_url=None):
    """
    Build an EmailMessage, inject tracking pixel, and send it.
    Returns the SentEmail instance (already saved).
    """
    from docsAppR.models import SentEmail, EmailOpenEvent

    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    cc  = cc  or []
    bcc = bcc or []

    # Create the SentEmail log BEFORE sending so we have a tracking_pixel_id
    sent = SentEmail.objects.create(
        subject=subject,
        body=body,
        recipients=recipients,
        cc=cc,
        bcc=bcc,
        sent_by_id=None,   # system-initiated; override in callers that have a user
        notify_on_open=False,
    )

    # Build absolute tracking URL if not supplied
    if not tracking_url:
        base = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        tracking_url = f'{base}/emails/track/{sent.tracking_pixel_id}/'

    pixel = (
        f'<img src="{tracking_url}" width="1" height="1" '
        f'style="display:none;" alt="" />'
    )
    html_body = f'<div style="white-space:pre-wrap;">{body}</div>{pixel}'

    email = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=from_email,
        to=recipients,
        cc=cc,
        bcc=bcc,
    )
    email.content_subtype = 'html'
    email.send()

    return sent


# ---------------------------------------------------------------------------
# Task 1: Process due EmailSchedule entries (fixes the broken scheduling)
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_scheduled_emails_task(self):
    """
    Poll EmailSchedule for entries that are due and have not yet been sent
    (or are due for their next recurrence).  Registered in CELERY_BEAT_SCHEDULE
    to run every minute.

    Bug that was here before: the management command send_scheduled_emails had
    `pass` in send_scheduled_email() — nothing was ever sent.
    """
    from docsAppR.models import EmailSchedule, SentEmail

    now = timezone.now()
    processed = 0

    # Active schedules whose start_date has passed
    candidates = EmailSchedule.objects.filter(
        is_active=True,
        start_date__lte=now,
    ).select_related('created_by')

    for schedule in candidates:
        # Determine whether this schedule is due for a send right now
        if schedule.last_sent is None:
            # First send — due if start_date <= now (already filtered above)
            due = True
        else:
            next_time = schedule.get_next_send_time(last_sent=schedule.last_sent)
            due = (next_time is not None) and (next_time <= now)

        if not due:
            continue

        # Enforce repeat_count limit (0 = unlimited)
        if schedule.repeat_count > 0 and schedule.send_count >= schedule.repeat_count:
            schedule.is_active = False
            schedule.save(update_fields=['is_active'])
            continue

        try:
            sent = _build_and_send(
                subject=schedule.subject,
                body=schedule.body,
                recipients=schedule.recipients,
            )

            # Link documents/attachments
            sent.documents.set(schedule.documents.all())
            sent.schedule = schedule
            # Set the real sender
            sent.sent_by = schedule.created_by
            sent.notify_on_open = schedule.notify_on_open
            sent.admin_notification_email = schedule.admin_notification_email
            sent.save(update_fields=['sent_by', 'notify_on_open',
                                     'admin_notification_email', 'schedule'])

            # Update tracking fields
            schedule.last_sent  = now
            schedule.send_count = (schedule.send_count or 0) + 1
            update_fields = ['last_sent', 'send_count']

            # Deactivate one-time schedules after first send
            if schedule.interval == 'none':
                schedule.is_active = False
                update_fields.append('is_active')

            # Deactivate if we've hit repeat_count
            if schedule.repeat_count > 0 and schedule.send_count >= schedule.repeat_count:
                schedule.is_active = False
                if 'is_active' not in update_fields:
                    update_fields.append('is_active')

            schedule.save(update_fields=update_fields)
            processed += 1
            logger.info('Sent scheduled email for schedule=%s (send #%s)',
                        schedule.id, schedule.send_count)

        except Exception as exc:
            logger.error('Failed to send scheduled email for schedule=%s: %s',
                         schedule.id, exc)
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                logger.error('Max retries exceeded for schedule=%s', schedule.id)

    logger.info('send_scheduled_emails_task: processed %s schedules', processed)
    return processed


# ---------------------------------------------------------------------------
# Task 2: Send one email in a campaign sequence
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_campaign_email_task(self, campaign_id, send_index):
    """
    Send the Nth email in an EmailCampaign.
    Scheduled via apply_async(eta=datetime) when the campaign is confirmed.
    """
    from docsAppR.models import EmailCampaign

    try:
        campaign = EmailCampaign.objects.get(id=campaign_id)
    except EmailCampaign.DoesNotExist:
        logger.error('Campaign %s not found', campaign_id)
        return

    if campaign.status == 'cancelled':
        logger.info('Campaign %s cancelled, skipping send #%s', campaign_id, send_index)
        return

    try:
        campaign.status = 'running'
        campaign.save(update_fields=['status'])

        sent = _build_and_send(
            subject=campaign.subject,
            body=campaign.body,
            recipients=campaign.recipients,
            cc=campaign.cc,
            bcc=campaign.bcc,
        )
        sent.sent_by   = campaign.created_by
        sent.save(update_fields=['sent_by'])
        campaign.sent_emails.add(sent)

        campaign.sends_completed = (campaign.sends_completed or 0) + 1
        if campaign.sends_completed >= campaign.total_sends:
            campaign.status = 'complete'
        campaign.save(update_fields=['sends_completed', 'status'])

        logger.info('Campaign %s: sent #%s/%s', campaign_id, send_index + 1, campaign.total_sends)

    except Exception as exc:
        logger.error('Campaign %s send #%s failed: %s', campaign_id, send_index, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error('Campaign %s send #%s max retries exceeded', campaign_id, send_index)
