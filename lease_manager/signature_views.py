"""
lease_manager/signature_views.py

New views for the plug-and-play lease generation + custom e-signature system.
Imported and registered in urls.py alongside the original views.
"""
import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from docsAppR.models import Client, Lease, LeaseActivity, LeaseSignatureRequest

from .views import _ale_to_lease_fields, _lease_contacts

logger = logging.getLogger(__name__)

OWNER_EMAIL = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')
FROM_EMAIL  = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@claimetapp.com')
SITE_URL    = getattr(settings, 'SITE_URL', 'https://claimetapp.com')


# ============================================================================
# QUICK GENERATE — one-click from a claim page
# ============================================================================

@login_required
@require_POST
def quick_generate_lease(request, client_id):
    """
    One-click lease creation: reads ALE fields from the Client, creates
    the Lease, stamps it as 'generated', then redirects to the detail page.
    If a non-cancelled lease already exists for this client it redirects
    straight to that lease's detail page instead of creating a duplicate.
    """
    from docsAppR.models import PipelineStageAssignment, LeaseStageCompletion

    client = get_object_or_404(Client, id=client_id)

    # Don't create duplicates
    existing = (
        Lease.objects.filter(client=client)
        .exclude(status='cancelled')
        .order_by('-created_at')
        .first()
    )
    if existing:
        messages.info(request, f'Existing lease found for {client.pOwner}.')
        return redirect('lease_detail', lease_id=str(existing.id))

    ale_fields = _ale_to_lease_fields(client)
    lease = Lease.objects.create(
        client=client,
        status='generated',
        generated_at=timezone.now(),
        created_by=request.user,
        last_modified_by=request.user,
        **ale_fields,
    )

    # Stage tracking
    for assignment in PipelineStageAssignment.objects.all():
        completion = LeaseStageCompletion.objects.create(
            lease=lease,
            stage=assignment.stage,
            assigned_user=assignment.assigned_user,
            is_completed=False,
        )
        if assignment.stage in ('draft', 'generated'):
            completion.is_completed = True
            completion.completed_by = request.user
            completion.completed_at = timezone.now()
            completion.save()

    LeaseActivity.objects.create(
        lease=lease,
        activity_type='generated',
        description=(
            f'Lease generated from ALE data for {client.pOwner} — '
            f'{lease.property_address}, ${lease.monthly_rent}/mo, '
            f'{lease.lease_start_date} to {lease.lease_end_date}'
        ),
        performed_by=request.user,
    )

    messages.success(request, f'Lease generated for {client.pOwner}.')
    return redirect('lease_detail', lease_id=str(lease.id))


# ============================================================================
# LEASE DETAIL
# ============================================================================

@login_required
def lease_detail(request, lease_id):
    """
    Main hub for a single lease: docs list, signature status panel,
    activity feed, and action buttons.
    """
    lease        = get_object_or_404(Lease, id=lease_id)
    sig_requests = lease.signature_requests.all().order_by('signer_role')
    docs         = lease.documents.all()
    activities   = lease.activities.order_by('-created_at')[:30]
    contacts     = _lease_contacts(lease)

    all_signed = sig_requests.exists() and all(
        s.status == 'signed' for s in sig_requests
    )

    context = {
        'lease':        lease,
        'client':       lease.client,
        'sig_requests': sig_requests,
        'docs':         docs,
        'activities':   activities,
        'contacts':     contacts,
        'all_signed':   all_signed,
        'can_send': lease.status not in ('signed', 'cancelled', 'completed'),
    }
    return render(request, 'lease_manager/lease_detail.html', context)


# ============================================================================
# SEND FOR SIGNATURE
# ============================================================================

@login_required
@require_POST
def send_for_signature(request, lease_id):
    """
    POST JSON body:
        {
          "signers": [
            {"role": "tenant",   "name": "Jane Smith", "email": "jane@example.com"},
            {"role": "landlord", "name": "Bob Owner",  "email": "bob@example.com"}
          ]
        }
    Creates a LeaseSignatureRequest per signer and emails each one.
    """
    lease = get_object_or_404(Lease, id=lease_id)

    try:
        body    = json.loads(request.body)
        signers = body.get('signers', [])
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not signers:
        return JsonResponse({'error': 'No signers provided'}, status=400)

    # Document hash — proves terms haven't changed after signing
    doc_hash_src = (
        f"{lease.id}|{lease.property_address}|{lease.monthly_rent}"
        f"|{lease.lease_start_date}|{lease.lease_end_date}"
        f"|{lease.lessee_name}|{lease.lessor_name}"
    )
    document_hash = hashlib.sha256(doc_hash_src.encode()).hexdigest()
    expires_at    = timezone.now() + timedelta(days=7)

    created = []
    for s in signers:
        role  = (s.get('role') or '').strip()
        name  = (s.get('name') or '').strip()
        email = (s.get('email') or '').strip()
        if not all([role, name, email]):
            continue

        sig_req = LeaseSignatureRequest.objects.create(
            lease=lease,
            signer_role=role,
            signer_name=name,
            signer_email=email,
            document_hash=document_hash,
            expires_at=expires_at,
        )
        signing_url = f"{SITE_URL}/lease-manager/sign/{sig_req.token}/"
        _send_signature_request_email(sig_req, lease, signing_url)
        created.append({'role': role, 'name': name, 'email': email})

    # Advance lease status
    lease.status                 = 'sent_for_signature'
    lease.sent_for_signature_at  = timezone.now()
    lease.last_modified_by       = request.user
    lease.save(update_fields=[
        'status', 'sent_for_signature_at', 'last_modified_by', 'updated_at'
    ])

    LeaseActivity.objects.create(
        lease=lease,
        activity_type='sent_for_signature',
        description=(
            f'Sent for signature to {len(created)} party/parties: '
            + ', '.join(c["name"] for c in created)
        ),
        performed_by=request.user,
    )

    return JsonResponse({'success': True, 'sent_to': created})


def _send_signature_request_email(sig_req, lease, signing_url):
    subject = (
        f'Action Required: Sign your lease — '
        f'{lease.property_address or lease.client.pOwner}'
    )
    try:
        html_body = render_to_string(
            'lease_manager/email/signature_request.html',
            {
                'sig_req':     sig_req,
                'lease':       lease,
                'signing_url': signing_url,
            }
        )
    except Exception:
        html_body = None

    text_body = (
        f"Hi {sig_req.signer_name},\n\n"
        f"You have a lease document to review and sign.\n\n"
        f"Property: {lease.property_address}\n"
        f"Your role: {sig_req.get_signer_role_display()}\n"
        f"Monthly rent: ${lease.monthly_rent}\n"
        f"Lease term: {lease.lease_start_date} to {lease.lease_end_date}\n\n"
        f"Sign here (link expires {sig_req.expires_at.strftime('%B %d, %Y')}):\n"
        f"{signing_url}\n\n"
        f"This is a legally binding electronic signature. "
        f"By signing you agree to the terms of the lease.\n\n"
        f"— The Claimet Team"
    )

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=FROM_EMAIL,
            to=[sig_req.signer_email],
        )
        if html_body:
            msg.attach_alternative(html_body, 'text/html')
        msg.send()
        logger.info('Signature request sent to %s (lease %s)', sig_req.signer_email, lease.id)
    except Exception as exc:
        logger.error('Signature request email failed for %s: %s', sig_req.signer_email, exc)


# ============================================================================
# PUBLIC SIGNING PAGES  (no login required)
# ============================================================================

def sign_page(request, token):
    """
    Public page: signer visits from their email. Shows lease summary + canvas.
    No login required — access controlled by the secret token.
    """
    sig_req = get_object_or_404(LeaseSignatureRequest, token=token)
    lease   = sig_req.lease

    if sig_req.status == 'signed':
        return render(request, 'lease_manager/sign_complete.html',
                      {'sig_req': sig_req, 'lease': lease, 'already_signed': True})
    if sig_req.status == 'declined':
        return render(request, 'lease_manager/sign_declined.html',
                      {'sig_req': sig_req, 'lease': lease})
    if sig_req.is_expired_flag:
        sig_req.status = 'expired'
        sig_req.save(update_fields=['status'])
        return render(request, 'lease_manager/sign_expired.html',
                      {'sig_req': sig_req, 'lease': lease})

    # Mark as viewed on first open
    if sig_req.status == 'pending':
        sig_req.status    = 'viewed'
        sig_req.viewed_at = timezone.now()
        sig_req.save(update_fields=['status', 'viewed_at'])

    return render(request, 'lease_manager/sign.html', {
        'sig_req': sig_req,
        'lease':   lease,
        'client':  lease.client,
    })


@csrf_exempt
@require_POST
def sign_submit(request, token):
    """
    AJAX POST from the signing canvas page.
    Body JSON: { signature_image, typed_name, agreed }
    """
    sig_req = get_object_or_404(LeaseSignatureRequest, token=token)

    if sig_req.status in ('signed', 'declined', 'expired'):
        return JsonResponse({'error': 'This request is already finalised.'}, status=400)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    sig_image  = (body.get('signature_image') or '').strip()
    typed_name = (body.get('typed_name') or '').strip()
    agreed     = bool(body.get('agreed', False))

    if not sig_image or not sig_image.startswith('data:image/'):
        return JsonResponse({'error': 'Please draw your signature above.'}, status=400)
    if not typed_name:
        return JsonResponse({'error': 'Please type your full name.'}, status=400)
    if not agreed:
        return JsonResponse({'error': 'You must agree to sign electronically.'}, status=400)

    ip = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', '')
    ) or None
    ua = request.META.get('HTTP_USER_AGENT', '')

    sig_req.signature_image = sig_image
    sig_req.typed_name      = typed_name
    sig_req.agreed_to_esign = True
    sig_req.ip_address      = ip
    sig_req.user_agent      = ua
    sig_req.status          = 'signed'
    sig_req.signed_at       = timezone.now()
    sig_req.save()

    lease = sig_req.lease
    LeaseActivity.objects.create(
        lease=lease,
        activity_type='signed',
        description=(
            f'{sig_req.get_signer_role_display()} "{sig_req.signer_name}" '
            f'signed electronically (IP: {ip})'
        ),
    )

    # Check if all parties have signed
    all_reqs = lease.signature_requests.all()
    if all_reqs.exists() and all(r.status == 'signed' for r in all_reqs):
        lease.status    = 'signed'
        lease.signed_at = timezone.now()
        lease.save(update_fields=['status', 'signed_at', 'updated_at'])
        LeaseActivity.objects.create(
            lease=lease,
            activity_type='signed',
            description='All parties have signed — lease is fully executed.',
        )
        _notify_all_signed(lease)

    _notify_staff_signature(sig_req, lease)

    return JsonResponse({
        'success':  True,
        'redirect': f'/lease-manager/sign/{token}/complete/',
    })


def sign_complete(request, token):
    """Thank-you confirmation shown after signing."""
    sig_req = get_object_or_404(LeaseSignatureRequest, token=token)
    return render(request, 'lease_manager/sign_complete.html', {
        'sig_req': sig_req,
        'lease':   sig_req.lease,
    })


@require_POST
def sign_decline(request, token):
    """Signer declines to sign."""
    sig_req = get_object_or_404(LeaseSignatureRequest, token=token)

    if sig_req.status not in ('pending', 'viewed'):
        return JsonResponse({'error': 'Already finalised.'}, status=400)

    sig_req.status      = 'declined'
    sig_req.declined_at = timezone.now()
    sig_req.save(update_fields=['status', 'declined_at'])

    LeaseActivity.objects.create(
        lease=sig_req.lease,
        activity_type='note_added',
        description=(
            f'{sig_req.get_signer_role_display()} "{sig_req.signer_name}" declined to sign.'
        ),
    )
    _notify_staff_decline(sig_req)

    return JsonResponse({
        'success':  True,
        'redirect': f'/lease-manager/sign/{token}/declined/',
    })


def sign_declined_page(request, token):
    """Confirmation page shown after declining."""
    sig_req = get_object_or_404(LeaseSignatureRequest, token=token)
    return render(request, 'lease_manager/sign_declined.html', {
        'sig_req': sig_req,
        'lease':   sig_req.lease,
    })


# ── Notification helpers ──────────────────────────────────────────────────────

def _notify_staff_signature(sig_req, lease):
    try:
        EmailMessage(
            subject=(
                f'[Claimet] Signed: {sig_req.get_signer_role_display()} — '
                f'{lease.property_address}'
            ),
            body=(
                f'{sig_req.signer_name} ({sig_req.signer_email}) signed as '
                f'{sig_req.get_signer_role_display()}.\n'
                f'Signed at: {sig_req.signed_at.strftime("%B %d, %Y %H:%M UTC")}\n'
                f'Property: {lease.property_address}\n'
                f'Client: {lease.client.pOwner}\n\n'
                f'View: {SITE_URL}/lease-manager/lease/{lease.id}/'
            ),
            from_email=FROM_EMAIL,
            to=[OWNER_EMAIL],
        ).send()
    except Exception as exc:
        logger.error('notify_staff_signature failed: %s', exc)


def _notify_staff_decline(sig_req):
    try:
        EmailMessage(
            subject=f'[Claimet] Declined: {sig_req.signer_name} refused to sign',
            body=(
                f'{sig_req.signer_name} ({sig_req.signer_email}) declined to sign as '
                f'{sig_req.get_signer_role_display()}.\n\n'
                f'Property: {sig_req.lease.property_address}\n'
                f'Action needed: contact them and resend if appropriate.\n\n'
                f'View: {SITE_URL}/lease-manager/lease/{sig_req.lease.id}/'
            ),
            from_email=FROM_EMAIL,
            to=[OWNER_EMAIL],
        ).send()
    except Exception as exc:
        logger.error('notify_staff_decline failed: %s', exc)


def _notify_all_signed(lease):
    try:
        EmailMessage(
            subject=f'[Claimet] Fully Signed: {lease.property_address}',
            body=(
                f'All parties have signed the lease.\n\n'
                f'Property: {lease.property_address}\n'
                f'Client: {lease.client.pOwner}\n'
                f'Signed at: {lease.signed_at.strftime("%B %d, %Y %H:%M UTC")}\n\n'
                f'Next step: create the invoice.\n'
                f'View: {SITE_URL}/lease-manager/lease/{lease.id}/'
            ),
            from_email=FROM_EMAIL,
            to=[OWNER_EMAIL],
        ).send()
    except Exception as exc:
        logger.error('notify_all_signed failed: %s', exc)
