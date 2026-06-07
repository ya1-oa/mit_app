"""
Custom allauth account adapter for Claimet.

Behaviour changes vs DefaultAccountAdapter:
  - If someone re-registers with an email that already exists but is
    *unverified*, resend the confirmation link and show a friendly error
    instead of the generic "A user is already registered with this
    e-mail address." message.
  - Verified duplicates still hit the standard error (they should use
    Forgot Password).
"""

import logging

from django import forms
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress

logger = logging.getLogger(__name__)


class AccountAdapter(DefaultAccountAdapter):

    def validate_unique_email(self, email):
        """
        Check for duplicate e-mail at sign-up.

        ┌─────────────────────────────┬──────────────────────────────────────┐
        │ State                       │ Outcome                              │
        ├─────────────────────────────┼──────────────────────────────────────┤
        │ Email doesn't exist         │ No error — proceed normally          │
        │ Email exists, NOT verified  │ Resend confirmation + friendly error │
        │ Email exists, verified      │ Fall through → allauth default error │
        └─────────────────────────────┴──────────────────────────────────────┘
        """
        try:
            existing = EmailAddress.objects.get(email__iexact=email)

            if not existing.verified:
                # Re-send so they don't have to hunt for the old link
                try:
                    existing.send_confirmation()
                    logger.info(
                        "Re-sent confirmation email to unverified address: %s", email
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not resend confirmation to %s: %s", email, exc
                    )

                raise forms.ValidationError(
                    "This email is registered but hasn't been verified yet. "
                    "We've just resent your verification link — "
                    "check your inbox (and spam folder)."
                )

            # Verified duplicate → fall through to allauth's default error,
            # which tells them to use Forgot Password.

        except EmailAddress.DoesNotExist:
            pass  # Brand-new email — all good

        return super().validate_unique_email(email)
