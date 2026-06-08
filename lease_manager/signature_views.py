"""
lease_manager/signature_views.py

New views for the plug-and-play lease generation + custom e-signature system.
Imported and registered in urls.py alongside the original views.
"""
import datetime as dt
import hashlib
import json
import logging
import os
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from docsAppR.models import Client, Lease, LeaseActivity, LeaseDocument, LeaseSignatureRequest

from .views import _ale_to_lease_fields, _lease_contacts


# ============================================================================
# DOCUMENT GENERATION ENGINE
# ============================================================================

DOCUMENT_TYPE_MAP = {
    'Engagement Agreement': 'engagement_agreement',
    'Term Sheet':           'term_sheet',
    'Month to Month Rental': 'month_to_month_rental',
}

DOCUMENT_NAMES = list(DOCUMENT_TYPE_MAP.keys())


def _fmt_date(date_val):
    """Format a date or date-string as 'Month D, YYYY'."""
    if not date_val:
        return ''
    if hasattr(date_val, 'strftime'):
        return date_val.strftime('%B %d, %Y').replace(' 0', ' ')
    try:
        cleaned = re.sub(r'[^\d/-]', '', str(date_val))
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y'):
            try:
                return dt.datetime.strptime(cleaned, fmt).strftime('%B %d, %Y').replace(' 0', ' ')
            except ValueError:
                continue
    except Exception:
        pass
    return str(date_val)


def _fmt_agreement_date(date_val):
    """Format as 'Xth day of Month YYYY' for legal docs."""
    if not date_val:
        return ''
    d = date_val if hasattr(date_val, 'day') else None
    if d is None:
        try:
            cleaned = re.sub(r'[^\d/-]', '', str(date_val))
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y'):
                try:
                    d = dt.datetime.strptime(cleaned, fmt).date()
                    break
                except ValueError:
                    continue
        except Exception:
            return str(date_val)
    if d is None:
        return str(date_val)
    day = d.day
    suffix = 'th' if 10 <= day % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return f"{day}{suffix} day of {d.strftime('%B %Y')}"


def _landlord_data_from_lease(lease):
    """Build the landlord context dict from a Lease model instance."""
    return {
        # Lessor / landlord
        'full_name':  lease.lessor_name,
        'address':    lease.lessor_address,
        'city':       lease.lessor_city,
        'state':      lease.lessor_state,
        'zip_code':   lease.lessor_zip,
        'phone':      lease.lessor_phone,
        'email':      lease.lessor_email,
        'contact_person_1': lease.lessor_contact_person_1,
        'contact_person_2': getattr(lease, 'lessor_contact_person_2', ''),
        'contact_phone':    lease.lessor_contact_phone,
        'contact_email':    lease.lessor_contact_email,

        # Leased property
        'property_address': lease.property_address,
        'property_city':    lease.property_city,
        'property_state':   lease.property_state,
        'property_zip':     lease.property_zip,
        'bedrooms':         lease.bedrooms,

        # Term
        'term_start_date': lease.lease_start_date,
        'term_end_date':   lease.lease_end_date,
        'rental_months':   lease.rental_months,

        # Financials
        'default_rent_amount':        float(lease.monthly_rent      or 0),
        'default_security_deposit':   float(lease.security_deposit  or 0),
        'default_rent_due_day':       int(lease.rent_due_day        or 1),
        'default_late_fee':           float(lease.late_fee          or 0),
        'default_late_fee_start_day': int(lease.late_fee_start_day  or 5),
        'default_eviction_day':       int(lease.eviction_day        or 10),
        'default_nsf_fee':            float(lease.nsf_fee           or 0),
        'default_max_occupants':      int(lease.max_occupants       or 10),
        'default_parking_spaces':     int(lease.parking_spaces      or 2),
        'default_parking_fee':        float(lease.parking_fee       or 0),
        'default_inspection_fee':     float(lease.inspection_fee    or 300),

        # RE company
        'real_estate_company':     lease.real_estate_company,
        'company_mailing_address': lease.company_mailing_address,
        'company_city':            lease.company_city,
        'company_state':           lease.company_state,
        'company_zip':             lease.company_zip,
        'company_contact_person':  lease.company_contact_person,
        'company_phone':           lease.company_phone,
        'company_email':           lease.company_email,
        'broker_name':             lease.broker_name,
        'broker_phone':            lease.broker_phone,
        'broker_email':            lease.broker_email,

        # Notes & flags
        'lease_special_notes':      lease.special_notes,
        'is_renewal':               lease.is_renewal,
        'exclude_security_deposit': lease.exclude_security_deposit,
        'exclude_inspection_fee':   lease.exclude_inspection_fee,
    }


def generate_lease_pdfs(lease, base_url='https://claimetapp.com/'):
    """
    Generate all lease documents (Engagement Agreement, Term Sheet,
    Month to Month Rental, Input Sheet) from the Lease model instance.

    Saves PDFs to MEDIA_ROOT/lease_documents/<client_slug>/
    Creates or updates LeaseDocument records.

    Returns a list of dicts: [{doc_type, doc_name, file_path, success, error}]
    """
    from docsAppR.models import Document
    try:
        from weasyprint import HTML as WeasyHTML
    except ImportError:
        logger.error('weasyprint not installed — cannot generate PDFs')
        return [{'success': False, 'error': 'weasyprint not available'}]

    client      = lease.client
    client_slug = client.pOwner.replace(' ', '_')
    lease_dir   = os.path.join(settings.MEDIA_ROOT, 'lease_documents', client_slug)
    os.makedirs(lease_dir, exist_ok=True)

    landlord_data = _landlord_data_from_lease(lease)
    today_str     = dt.datetime.now().strftime('%B %d, %Y')

    # Build agreement date context
    agreement_date = lease.lease_agreement_date or lease.lease_start_date
    context_base = {
        'client':                    client,
        'preview':                   False,
        'today':                     today_str,
        'formatted_agreement_date':  _fmt_agreement_date(agreement_date),
        'lease_agreement_date':      str(agreement_date or ''),
        'formatted_start_date':      _fmt_date(lease.lease_start_date),
        'formatted_end_date':        _fmt_date(lease.lease_end_date),
        'term_start_date':           str(lease.lease_start_date or ''),
        'term_end_date':             str(lease.lease_end_date   or ''),
        'is_renewal':                lease.is_renewal,
        'exclude_security_deposit':  lease.exclude_security_deposit,
        'exclude_inspection_fee':    lease.exclude_inspection_fee,
        'landlord':                  landlord_data,
    }

    results = []

    # ── Main documents from Document model templates ──────────────────────────
    doc_templates = Document.objects.filter(name__in=DOCUMENT_NAMES)
    found_names   = set(doc_templates.values_list('name', flat=True))

    if not doc_templates.exists():
        logger.warning('No Document template records found in DB for lease generation.')

    for doc_obj in doc_templates:
        result = {'doc_name': doc_obj.name, 'success': False, 'error': ''}
        try:
            if not doc_obj.file:
                result['error'] = 'No template file attached to Document record'
                results.append(result)
                continue

            template_path = doc_obj.file.path
            if not os.path.exists(template_path):
                result['error'] = f'Template file missing: {template_path}'
                results.append(result)
                continue

            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()

            ctx = Context({**context_base, 'document': doc_obj})
            html_str  = Template(template_content).render(ctx)
            pdf_bytes = WeasyHTML(string=html_str, base_url=base_url).write_pdf()

            filename  = f"{doc_obj.name.replace(' ', '_')}_{client_slug}.pdf"
            abs_path  = os.path.join(lease_dir, filename)
            rel_path  = f"lease_documents/{client_slug}/{filename}"

            with open(abs_path, 'wb') as f:
                f.write(pdf_bytes)

            doc_type = DOCUMENT_TYPE_MAP.get(doc_obj.name, 'engagement_agreement')
            _upsert_lease_document(lease, doc_type, f"{doc_obj.name} - {client.pOwner}", rel_path)

            result.update({'success': True, 'file_path': rel_path, 'doc_type': doc_type})
            logger.info('Generated %s → %s', doc_obj.name, abs_path)

        except Exception as exc:
            logger.error('PDF generation failed for %s: %s', doc_obj.name, exc)
            result['error'] = str(exc)

        results.append(result)

    # ── Input Sheet from static template file ─────────────────────────────────
    input_sheet_template = os.path.join(
        settings.BASE_DIR, 'docsAppR', 'templates', 'account', 'lease_input_sheet.html'
    )
    if os.path.exists(input_sheet_template):
        try:
            with open(input_sheet_template, 'r', encoding='utf-8') as f:
                content = f.read()
            ctx      = Context({**context_base})
            html_str = Template(content).render(ctx)
            pdf_bytes = WeasyHTML(string=html_str, base_url=base_url).write_pdf()

            filename = f"Input_Sheet_{client_slug}.pdf"
            abs_path = os.path.join(lease_dir, filename)
            rel_path = f"lease_documents/{client_slug}/{filename}"
            with open(abs_path, 'wb') as f:
                f.write(pdf_bytes)
            _upsert_lease_document(lease, 'input_sheet', f"Input Sheet - {client.pOwner}", rel_path)
            results.append({'doc_name': 'Input Sheet', 'success': True, 'file_path': rel_path})
        except Exception as exc:
            logger.error('Input sheet generation failed: %s', exc)
            results.append({'doc_name': 'Input Sheet', 'success': False, 'error': str(exc)})

    return results


def _upsert_lease_document(lease, doc_type, doc_name, rel_path):
    """Create or update the LeaseDocument record for this lease+type."""
    obj, _ = LeaseDocument.objects.get_or_create(
        lease=lease,
        document_type=doc_type,
        defaults={'document_name': doc_name, 'file_path': rel_path},
    )
    if obj.file_path != rel_path or obj.document_name != doc_name:
        obj.file_path     = rel_path
        obj.document_name = doc_name
        obj.save(update_fields=['file_path', 'document_name'])

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
    the Lease, generates all PDFs, then redirects to the detail page.
    If a non-cancelled lease already exists, redirects to it instead.
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
        return redirect('lease_manager:lease_detail', lease_id=str(existing.id))

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

    # Generate PDFs immediately
    base_url = request.build_absolute_uri('/')
    results  = generate_lease_pdfs(lease, base_url=base_url)
    ok_count = sum(1 for r in results if r.get('success'))

    LeaseActivity.objects.create(
        lease=lease,
        activity_type='generated',
        description=(
            f'Lease generated from ALE data for {client.pOwner} — '
            f'{lease.property_address}, ${lease.monthly_rent}/mo, '
            f'{lease.lease_start_date} to {lease.lease_end_date}. '
            f'{ok_count}/{len(results)} documents generated.'
        ),
        performed_by=request.user,
    )

    if ok_count == 0 and results:
        messages.warning(
            request,
            f'Lease record created but document templates were not found in the database. '
            f'You can regenerate documents once the templates are loaded. '
            f'Error: {results[0].get("error", "unknown")}'
        )
    else:
        messages.success(request, f'Lease generated for {client.pOwner} — {ok_count} document(s) ready.')

    return redirect('lease_manager:lease_detail', lease_id=str(lease.id))


# ============================================================================
# REGENERATE DOCUMENTS — for existing leases with broken/missing files
# ============================================================================

@login_required
@require_POST
def regenerate_documents(request, lease_id):
    """
    POST: Re-generate all PDFs for an existing lease using its stored data.
    Updates LeaseDocument records with fresh file paths.
    """
    lease    = get_object_or_404(Lease, id=lease_id)
    base_url = request.build_absolute_uri('/')
    results  = generate_lease_pdfs(lease, base_url=base_url)

    ok       = [r for r in results if r.get('success')]
    failed   = [r for r in results if not r.get('success')]

    LeaseActivity.objects.create(
        lease=lease,
        activity_type='generated',
        description=(
            f'Documents regenerated: {len(ok)} succeeded, {len(failed)} failed.'
            + ((' Errors: ' + '; '.join(f['error'] for f in failed)) if failed else '')
        ),
        performed_by=request.user,
    )

    if not results:
        return JsonResponse({
            'success': False,
            'error': 'No Document template records found. '
                     'Please ensure the 3 lease templates are uploaded in Admin → Documents.',
        })

    return JsonResponse({
        'success':  len(ok) > 0,
        'ok_count': len(ok),
        'failed':   failed,
        'message':  (
            f'{len(ok)} document(s) regenerated successfully.'
            if ok else
            f'All {len(failed)} document(s) failed. '
            f'Check that lease document templates exist in the admin.'
        ),
    })


# ============================================================================
# DELETE LEASE
# ============================================================================

@login_required
@require_POST
def delete_lease(request, lease_id):
    """
    POST: Hard-delete a lease and all its documents/signature requests.
    Also removes the physical PDF files from disk.
    """
    lease = get_object_or_404(Lease, id=lease_id)
    client_name = lease.client.pOwner
    client_id   = lease.client.id

    # Remove physical PDF files
    for doc in lease.documents.all():
        if doc.file_path:
            full = os.path.join(settings.MEDIA_ROOT, doc.file_path)
            try:
                if os.path.exists(full):
                    os.remove(full)
            except OSError:
                pass

    lease.delete()
    messages.success(request, f'Lease for {client_name} deleted.')
    return redirect('lease_manager:lease_manager')


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
