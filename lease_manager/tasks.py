"""
lease_manager/tasks.py

Celery task for scheduled lease document package emails.
"""
import logging
from celery import shared_task

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
