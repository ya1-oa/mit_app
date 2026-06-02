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


# ──────────────────────────────────────────────────────────────────────────────
# BATCH EMAIL SCHEDULING
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(name='email_manager.tasks.process_scheduled_batch_emails')
def process_scheduled_batch_emails():
    """
    Send scheduled emails from batches.
    Runs every minute. Checks for emails whose scheduled_send_time has passed.
    """
    from docsAppR.models import ScheduledEmail, SentEmail

    now = timezone.now()
    pending = ScheduledEmail.objects.filter(is_sent=False, scheduled_send_time__lte=now).order_by('scheduled_send_time')[:10]

    for scheduled in pending:
        try:
            # Build and send email
            sent = SentEmail.objects.create(
                subject=scheduled.subject,
                body=scheduled.body,
                recipients=scheduled.recipients,
                cc=scheduled.cc,
                bcc=scheduled.bcc,
                claim=scheduled.batch.claim,
                sent_at=now,
                notify_on_open=False,
            )

            # Attach files
            sent.generated_files.set(scheduled.generated_files.all())
            sent.uploaded_attachments.set(scheduled.uploaded_attachments.all())

            # Actually send
            msg = EmailMessage(
                subject=scheduled.subject,
                body=scheduled.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=scheduled.recipients,
                cc=scheduled.cc,
                bcc=scheduled.bcc,
            )
            msg.send(fail_silently=False)

            # Mark as sent
            scheduled.is_sent = True
            scheduled.sent_at = now
            scheduled.save(update_fields=['is_sent', 'sent_at'])

            logger.info(f'Batch email sent: {scheduled.subject} → {len(scheduled.recipients)} recipients')

            # If follow-up configured, create follow-up scheduled email
            if scheduled.has_followup:
                from datetime import timedelta
                if scheduled.followup_trigger == 'time':
                    followup_time = now + timedelta(days=scheduled.followup_days or 3)
                    ScheduledEmail.objects.create(
                        batch=scheduled.batch,
                        subject=scheduled.followup_subject,
                        body=scheduled.followup_body,
                        recipients=scheduled.recipients,
                        cc=scheduled.cc,
                        bcc=scheduled.bcc,
                        scheduled_send_time=followup_time,
                        has_followup=False,
                    )
                    logger.info(f'Follow-up scheduled for {followup_time}')
                # Note: unopened/opened triggers are checked separately by check_followup_triggers

        except Exception as exc:
            logger.error(f'Error sending scheduled email {scheduled.id}: {exc}')


@shared_task(name='email_manager.tasks.check_followup_triggers')
def check_followup_triggers():
    """
    Check for unopened/opened follow-up triggers.
    Runs hourly. Creates follow-up emails when conditions are met.
    """
    from docsAppR.models import ScheduledEmail, SentEmail
    from datetime import timedelta

    now = timezone.now()

    # Find all scheduled emails with unopened follow-up that are due
    for scheduled in ScheduledEmail.objects.filter(has_followup=True, is_sent=True, followup_trigger='unopened'):
        threshold = scheduled.sent_at + timedelta(days=scheduled.followup_days or 3)
        if now >= threshold and not SentEmail.objects.filter(
            created_at__gt=scheduled.sent_at,
            recipients__contains=scheduled.recipients[0] if scheduled.recipients else ''
        ).exists():
            # Email wasn't opened within X days, create follow-up
            ScheduledEmail.objects.create(
                batch=scheduled.batch,
                subject=scheduled.followup_subject,
                body=scheduled.followup_body,
                recipients=scheduled.recipients,
                cc=scheduled.cc,
                bcc=scheduled.bcc,
                scheduled_send_time=now,
                has_followup=False,
            )
            logger.info(f'Unopened follow-up created for {scheduled.id}')
