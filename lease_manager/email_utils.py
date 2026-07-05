"""
lease_manager/email_utils.py

A dedicated email sender for lease- and signature-related mail (signing invites,
OTP codes, document packages, signing notifications). These send from the firm's
ALE/lease mailbox (e.g. an Outlook account) instead of the default system inbox.

Configured via the LEASE_EMAIL_* settings, which read from the environment. When
the lease mailbox isn't configured, callers transparently fall back to Django's
default email connection — so nothing breaks until you set it up.
"""
import logging

from django.conf import settings
from django.core.mail import get_connection

logger = logging.getLogger(__name__)


def lease_email_configured():
    """True when a dedicated lease/signature mailbox is configured."""
    return bool(
        getattr(settings, 'LEASE_EMAIL_HOST_USER', '')
        and getattr(settings, 'LEASE_EMAIL_HOST_PASSWORD', '')
    )


def get_lease_email_connection():
    """
    Return an SMTP connection for the lease/signature mailbox, or None when it
    isn't configured (callers pass None straight to EmailMessage, which then
    uses the default connection). The connection isn't opened until .send().
    """
    if not lease_email_configured():
        return None
    try:
        return get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=settings.LEASE_EMAIL_HOST,
            port=settings.LEASE_EMAIL_PORT,
            username=settings.LEASE_EMAIL_HOST_USER,
            password=settings.LEASE_EMAIL_HOST_PASSWORD,
            use_tls=settings.LEASE_EMAIL_USE_TLS,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error('Could not build lease email connection: %s', exc)
        return None


def get_lease_from_email():
    """
    From-address for lease/signature emails. Uses the dedicated lease mailbox
    when configured, otherwise the system default.
    """
    return (
        getattr(settings, 'LEASE_FROM_EMAIL', '')
        or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        or 'noreply@claimetapp.com'
    )
