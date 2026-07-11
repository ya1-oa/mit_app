"""
lease_manager/tasks.py

Celery task for scheduled lease document package emails.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


def _send_lease_signature_notification(lease, client_email=None):
    """
    Send email notification to the client when all parties have signed a lease.
    Uses the dedicated lease mailbox if configured, otherwise falls back to default.
    """
    from docsAppR.models import Client
    from django.core.mail import EmailMessage
    from .email_utils import get_lease_email_connection, get_lease_from_email
    
    # Use tenant owner email (client.email or client.pEmail) for production
    if not client_email:
        try:
            client = lease.client
            client_email = getattr(client, 'pEmail', None) or getattr(client, 'email', None)
        except Exception:
            pass
    
    # TEMPORARY OVERRIDE - Remove this block when ready to use tenant emails
    if not client_email:
        # TODO: Replace with tenant owner email from settings
        # Example in Django settings.py: TEMP_NOTIFICATION_EMAIL = 'galaxielsaga@gmail.com'
        logger.warning(f"No email address found for lease {lease.id}, using default notification email")
        client_email = getattr(settings, 'TEMP_NOTIFICATION_EMAIL', 'galaxielsaga@gmail.com')
    
    try:
        connection = get_lease_email_connection()
        
        subject = f"Lease Fully Signed: {lease.property_address}"
        
        body_text = (
            f"All parties have signed your lease agreement.\n\n"
            f"Property Address: {lease.property_address}\n"
            f"Client: {lease.client.pOwner}\n"
            f"Signed at: {lease.signed_at.strftime('%B %d, %Y %H:%M UTC')}\n\n"
            f"Next step: create the invoice.\n"
            f"View your lease: {SITE_URL}/lease-manager/lease/{lease.id}/"
        )
        
        email = EmailMessage(
            subject=subject,
            body=body_text,
            from_email=get_lease_from_email(),
            to=[client_email],
            connection=connection,
        )
        email.send()
        logger.info(f"Sent lease signature completion notification for lease {lease.id} to {client_email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send lease signature notification for lease {lease.id}: {exc}")
        return False


def _send_lease_individual_signature_notification(sig_req, client_email=None):
    """
    Send email notification to the client when an individual signs a lease.
    Uses the dedicated lease mailbox if configured, otherwise falls back to default.
    """
    from docsAppR.models import Client
    from django.core.mail import EmailMessage
    from .email_utils import get_lease_email_connection, get_lease_from_email
    
    # Use tenant owner email (client.email or client.pEmail) for production
    if not client_email:
        try:
            client = sig_req.lease.client
            client_email = getattr(client, 'pEmail', None) or getattr(client, 'email', None)
        except Exception:
            pass
    
    # TEMPORARY OVERRIDE - Remove this block when ready to use tenant emails
    if not client_email:
        # TODO: Replace with tenant owner email from settings
        # Example: client_email = settings.TEMP_NOTIFICATION_EMAIL
        logger.warning(f"No email address found for lease {sig_req.lease.id}, using default notification email")
        client_email = 'galaxielsaga@gmail.com'
    
    try:
        connection = get_lease_email_connection()
        
        subject = f"Lease Signature Update: {sig_req.get_signer_role_display()} Signed - {sig_req.lease.property_address}"
        
        body_text = (
            f"A party has signed your lease agreement.\n\n"
            f"Signer: {sig_req.signer_name}\n"
            f"Role: {sig_req.get_signer_role_display()}\n"
            f"Property Address: {sig_req.lease.property_address}\n"
            f"Client: {sig_req.lease.client.pOwner}\n"
            f"Signed at: {sig_req.signed_at.strftime('%B %d, %Y %H:%M UTC')}\n\n"
            f"View your lease: {SITE_URL}/lease-manager/lease/{sig_req.lease.id}/"
        )
        
        email = EmailMessage(
            subject=subject,
            body=body_text,
            from_email=get_lease_from_email(),
            to=[client_email],
            connection=connection,
        )
        email.send()
        logger.info(f"Sent individual signature notification for lease {sig_req.lease.id} to {client_email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send individual signature notification for lease {sig_req.lease.id}: {exc}")
        return False


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_lease_signature_notification_task(self, lease_id, client_email=None):
    """
    Send email notification to the client when all parties have signed a lease.
    Called from signature_views.py after all signature requests are marked as signed.
    """
    from docsAppR.models import Lease
    
    try:
        lease = Lease.objects.get(id=lease_id)
    except Lease.DoesNotExist:
        logger.error('send_lease_signature_notification_task: Lease %s not found', lease_id)
        return
    
    success = _send_lease_signature_notification(lease, client_email)
    
    if success:
        logger.info(f"Successfully sent signature completion notification for lease {lease_id}")
    else:
        logger.warning(f"Failed to send signature completion notification for lease {lease_id}, retrying...")
        raise self.retry(exc=Exception("Email sending failed"), max_retries=self.max_retries + 1)


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_lease_individual_signature_notification_task(self, sig_req_id, client_email=None):
    """
    Send email notification to the client when an individual signs a lease.
    Called from signature_views.py after each signature is captured.
    """
    from docsAppR.models import LeaseSignatureRequest
    
    try:
        sig_req = LeaseSignatureRequest.objects.get(id=sig_req_id)
    except LeaseSignatureRequest.DoesNotExist:
        logger.error('send_lease_individual_signature_notification_task: Signature request %s not found', sig_req_id)
        return
    
    success = _send_lease_individual_signature_notification(sig_req, client_email)
    
    if success:
        logger.info(f"Successfully sent individual signature notification for lease {sig_req.lease.id}")
    else:
        logger.warning(f"Failed to send individual signature notification for lease {sig_req.lease.id}, retrying...")
        raise self.retry(exc=Exception("Email sending failed"), max_retries=self.max_retries + 1)


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
