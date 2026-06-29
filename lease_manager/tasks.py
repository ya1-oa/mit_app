"""
lease_manager/tasks.py

Celery tasks for scheduled lease document package emails and the signature
reminder cadence.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_lease_package_task(self, lease_id, to_emails, cc_emails, bcc_emails,
                             subject, body_text, doc_ids, user_id=None):
    """
    Send the lease document package email at a scheduled time (eta).
    Called via apply_async(eta=datetime) from lease_send_package view.
    """
    from docsAppR.models import Lease
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        logger.error('send_lease_package_task: Lease %s not found', lease_id)
        return

    user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass

    from lease_manager.views import _send_lease_package_email

    ok, error = _send_lease_package_email(
        lease=lease,
        to_emails=to_emails,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        subject=subject,
        body_text=body_text,
        doc_ids=doc_ids,
        user=user,
    )

    if not ok:
        logger.error('send_lease_package_task: send failed for lease %s: %s', lease_id, error)
        try:
            raise self.retry(exc=Exception(error))
        except self.MaxRetriesExceededError:
            logger.error('send_lease_package_task: max retries for lease %s', lease_id)
    else:
        logger.info('send_lease_package_task: lease %s package sent to %s', lease_id, to_emails)


# Reminder thresholds: each measured from the PREVIOUS reminder's own
# timestamp (or sent_at for the first one) — not all from sent_at directly.
# 24h after sending -> 48h after that -> 72h after that (final).
_REMINDER_STAGES = [
    ('24h', 'sent_at',              'reminder_24h_sent_at', timedelta(hours=24)),
    ('48h', 'reminder_24h_sent_at', 'reminder_48h_sent_at', timedelta(hours=48)),
    ('72h', 'reminder_48h_sent_at', 'reminder_72h_sent_at', timedelta(hours=72)),
]


@shared_task(bind=True, max_retries=1)
def send_signature_reminders_task(self):
    """
    Runs periodically (see CELERY_BEAT_SCHEDULE). Scans signature requests
    that are not yet signed/declined/expired and sends the next due reminder
    in the 24h -> 48h -> 72h cadence. A request that gets signed simply stops
    appearing in the `status__in=['pending', 'viewed']` filter below — no
    separate "all signed, stop" branch is needed.
    """
    from docsAppR.models import LeaseSignatureRequest, LeaseActivity
    from lease_manager.signature_views import _send_signature_reminder_email

    now = timezone.now()
    sent_count = 0

    pending = LeaseSignatureRequest.objects.filter(status__in=['pending', 'viewed'])

    for sig_req in pending:
        stage_to_send = None
        for stage, from_field, to_field, threshold in _REMINDER_STAGES:
            if getattr(sig_req, to_field) is not None:
                continue  # this stage already sent
            from_ts = getattr(sig_req, from_field)
            if from_ts is None:
                break  # previous stage hasn't fired yet — nothing to do this pass
            if now - from_ts >= threshold:
                stage_to_send = (stage, to_field)
            break  # only ever consider the next unsent stage in sequence

        if stage_to_send is None:
            continue

        stage, to_field = stage_to_send
        try:
            _send_signature_reminder_email(sig_req, stage=stage)
        except Exception as exc:
            logger.error(
                'send_signature_reminders_task: failed for sig_req %s (%s): %s',
                sig_req.id, stage, exc,
            )
            continue

        setattr(sig_req, to_field, now)
        sig_req.save(update_fields=[to_field])

        LeaseActivity.objects.create(
            lease=sig_req.lease,
            activity_type='note_added',
            description=(
                f'{stage} reminder sent to {sig_req.get_signer_role_display()} '
                f'"{sig_req.signer_name}" (not yet signed).'
            ),
        )
        sent_count += 1

    if sent_count:
        logger.info('send_signature_reminders_task: sent %d reminder(s)', sent_count)
    return {'reminders_sent': sent_count}
