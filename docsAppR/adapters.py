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
from django.db.models import F
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

    def save_user(self, request, user, form, commit=True):
        """
        Phase 4 — two signup paths:

        1. Worker path — form contains a valid invite_code → join the tenant
           that issued the code (use_count is incremented atomically).
        2. Contractor path — no invite code → create a new Tenant, making
           this user the first admin for their company's workspace.

        Staff accounts (is_staff=True) skip both paths and stay tenant=None —
        that is the signal distinguishing internal ClaiMetApp accounts.
        """
        user = super().save_user(request, user, form, commit=False)

        if not user.is_staff:
            try:
                from .models import Tenant, TenantInvite
                import re

                invite_code = (form.cleaned_data or {}).get('invite_code', '').strip()

                if invite_code:
                    # ── Worker path: join existing tenant via invite code ──────
                    try:
                        invite = TenantInvite.objects.select_related('tenant').get(code=invite_code)
                    except TenantInvite.DoesNotExist:
                        invite = None

                    if invite and invite.is_valid():
                        user.tenant = invite.tenant
                        # Increment use_count after user is saved (see post-save below)
                        # We store the invite on the user object temporarily
                        user._pending_invite = invite
                        logger.info(
                            "Phase-4: user %s joined tenant %s via invite %s",
                            user.email, invite.tenant.slug, invite_code,
                        )
                    else:
                        logger.warning(
                            "Phase-4: invalid/expired invite code '%s' for %s",
                            invite_code, user.email,
                        )
                        # Fall through with tenant=None; middleware will deny access
                        # until an admin manually assigns a tenant.

                else:
                    # ── Contractor path: create a new tenant workspace ─────────
                    domain = user.email.split('@')[-1].lower()
                    slug_base = re.sub(r'[^a-z0-9]+', '-', domain.split('.')[0])[:40]
                    tenant = Tenant.objects.filter(slug=slug_base).first()
                    if tenant is None:
                        name = domain.split('.')[0].replace('-', ' ').title()
                        tenant = Tenant.objects.create(
                            name=name, slug=slug_base, status='active',
                            primary_contact_email=user.email,
                        )
                        logger.info(
                            "Phase-4: created tenant '%s' for contractor %s",
                            slug_base, user.email,
                        )
                    user.tenant = tenant
                    user.is_tenant_admin = True  # first sign-up without code = workspace owner

            except Exception as exc:
                logger.error("Phase-4: tenant provisioning failed for %s: %s", user.email, exc)

        if commit:
            user.save()
            # Increment invite use_count only after the user row is safely committed
            invite = getattr(user, '_pending_invite', None)
            if invite is not None:
                from .models import TenantInvite
                TenantInvite.objects.filter(pk=invite.pk).update(use_count=F('use_count') + 1)

        return user
