"""
lease_manager/signature_views.py

New views for the plug-and-play lease generation + custom e-signature system.
Imported and registered in urls.py alongside the original views.
"""
import copy
import datetime as dt
import hashlib
import json
import logging
import os
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

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

# Bundled static template fallbacks (version-controlled, always present on disk).
# Used when an admin-uploaded Document.file is missing from the media volume —
# this makes lease generation resilient to media-volume loss / fresh databases.
# Paths are relative to docsAppR/templates/.
STATIC_DOC_TEMPLATES = {
    'Engagement Agreement':  'account/short_term.html',
    'Term Sheet':            'account/term_sheet.html',
    'Month to Month Rental': 'account/lease.html',
}


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
        'term_start_date':  lease.lease_start_date,
        'term_end_date':    lease.lease_end_date,
        'rental_months':    lease.rental_months,
        # Agreement date: each lease owns this independently (set on lease detail).
        'agreement_date':   lease.lease_agreement_date,

        # Financials
        'default_rent_amount':        float(lease.monthly_rent      or 0),
        'default_security_deposit':   float(lease.security_deposit  or 0),
        'default_rent_due_day':       int(lease.rent_due_day        or 1),
        'default_late_fee':           float(lease.late_fee)  if lease.late_fee  else 50.0,
        'default_late_fee_start_day': int(lease.late_fee_start_day  or 5),
        'default_eviction_day':       int(lease.eviction_day        or 10),
        'default_nsf_fee':            float(lease.nsf_fee)   if lease.nsf_fee   else 35.0,
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


# ── Shared value coercion / parsing ──────────────────────────────────────────

def _dec(val, default):
    """Coerce val to Decimal; fall back to default on blank/invalid."""
    if val in (None, ''):
        return default
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _int_or(val, default):
    """Coerce val to int; fall back to default on blank/invalid."""
    if val in (None, ''):
        return default
    try:
        return int(float(str(val).strip().split()[0]))
    except (ValueError, TypeError, IndexError):
        return default


def _bool(val, default):
    """Coerce a form/JSON value to bool; None → default."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def _parse_date(val):
    """Parse 'YYYY-MM-DD' (or a few common formats) → date, else None."""
    if not val:
        return None
    if hasattr(val, 'year') and not hasattr(val, 'hour'):   # already a date
        return val
    s = str(val).strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d'):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# Descriptive (non-term) fields that should always reflect the claim's CURRENT
# ALE data — parties, company, contacts, property. The term/financial fields
# (rent, deposit, months, the dates, renewal/exclude flags, special_notes) are
# deliberately NOT in this list: they stay on the lease so each lease keeps its
# own independent terms.
_DESCRIPTIVE_LEASE_FIELDS = [
    'lessor_name', 'lessor_address', 'lessor_city', 'lessor_state', 'lessor_zip',
    'lessor_phone', 'lessor_email', 'lessor_contact_person_1',
    'lessor_contact_phone', 'lessor_contact_email',
    'property_address', 'property_city', 'property_state', 'property_zip', 'bedrooms',
    'real_estate_company', 'company_mailing_address', 'company_city', 'company_state',
    'company_zip', 'company_contact_person', 'company_phone', 'company_email',
    'broker_name', 'broker_phone', 'broker_email',
    'lessee_name', 'lessee_email', 'lessee_phone', 'lessee_address',
]


def _sync_descriptive_from_claim(lease, save=False):
    """
    Refresh the lease's descriptive (non-term) fields from the claim's current
    ALE data, so updating party/company/contact info on the claim flows through
    to the lease and its documents. Term fields are left untouched.

    save=False → mutate in memory only (used for rendering / live preview).
    save=True  → persist the changed fields (used when (re)generating PDFs).
    """
    # Only a fully-executed (signed) lease stays frozen — its document must
    # remain exactly as signed. Every other lease, INCLUDING old ones made
    # before this system, refreshes from the claim's current ALE.
    if lease.status == 'signed':
        return lease
    claim = _ale_to_lease_fields(lease.client)
    changed = []
    for f in _DESCRIPTIVE_LEASE_FIELDS:
        if f in claim and getattr(lease, f) != claim[f]:
            setattr(lease, f, claim[f])
            changed.append(f)
    if save and changed:
        lease.save(update_fields=changed)
    return lease


def _build_lease_context(lease, overrides=None, preview=False):
    """
    Build the full template context for a lease, optionally applying live
    overrides (rent / deposit / dates / flags) WITHOUT writing to the DB.

    The same context feeds both the live HTML preview and the final PDF, so
    what the user sees while editing is exactly what gets generated.
    """
    overrides = overrides or {}

    # Descriptive info (parties, company, contacts, property) always reflects the
    # claim's CURRENT ALE — refreshed on an in-memory copy so it never silently
    # rewrites the stored lease here. The term fields below still come from the
    # lease itself, keeping each lease's terms independent.
    live = copy.copy(lease)
    _sync_descriptive_from_claim(live, save=False)
    landlord = _landlord_data_from_lease(live)

    # Effective scalar values (override → lease)
    rent       = _dec(overrides.get('monthly_rent'),     lease.monthly_rent)
    deposit    = _dec(overrides.get('security_deposit'), lease.security_deposit)
    months     = _int_or(overrides.get('rental_months'), lease.rental_months)
    is_renewal = _bool(overrides.get('is_renewal'),                lease.is_renewal)
    excl_sd    = _bool(overrides.get('exclude_security_deposit'),  lease.exclude_security_deposit)
    excl_if    = _bool(overrides.get('exclude_inspection_fee'),    lease.exclude_inspection_fee)

    # Effective dates (override → lease)
    start     = _parse_date(overrides.get('lease_start_date'))     or lease.lease_start_date
    end       = _parse_date(overrides.get('lease_end_date'))       or lease.lease_end_date
    agreement = _parse_date(overrides.get('lease_agreement_date')) or lease.lease_agreement_date

    # Special notes: user-entered only. An explicit '' override stays empty;
    # an absent key falls back to whatever the user previously saved.
    notes = overrides.get('special_notes')
    if notes is None:
        notes = lease.special_notes or ''

    # Renewal pricing rules:
    #   • Inspection / clean-up fee = ½ month's rent (not the stored inspection_fee)
    #   • Security deposit is waived (hidden on the term sheet)
    rent_f   = float(rent or 0)
    months_i = int(months or 0)
    effective_inspection_fee = round(rent_f / 2, 2) if is_renewal else float(landlord['default_inspection_fee'])
    re_company_fee           = round(rent_f, 2)   # always 1 month's rent
    base_rent                = round(rent_f * months_i, 2)
    security_deposit_f       = float(deposit or 0)

    if is_renewal:
        # Renewal total: (rent × months) + RE fee + ½-rent inspection fee
        # Security deposit is waived — not included.
        term_sheet_total = round(base_rent + re_company_fee + effective_inspection_fee, 2)
    else:
        # Standard total: (rent × months) + security deposit + RE fee + inspection fee
        term_sheet_total = round(base_rent + security_deposit_f + re_company_fee + float(landlord['default_inspection_fee']), 2)

    # Patch the override-able landlord keys
    landlord['default_rent_amount']        = rent_f
    landlord['default_security_deposit']   = security_deposit_f
    landlord['is_renewal']                 = is_renewal
    landlord['exclude_security_deposit']   = excl_sd
    landlord['exclude_inspection_fee']     = excl_if
    landlord['term_start_date']            = start
    landlord['term_end_date']              = end
    landlord['agreement_date']             = agreement
    landlord['lease_special_notes']        = notes
    landlord['rental_months']              = months
    landlord['effective_inspection_fee']   = effective_inspection_fee
    landlord['re_company_fee']             = re_company_fee
    landlord['base_rent']                  = base_rent
    landlord['term_sheet_total']           = term_sheet_total

    return {
        'client':                    lease.client,
        'preview':                   preview,
        'today':                     dt.datetime.now().strftime('%B %d, %Y'),
        'formatted_agreement_date':  _fmt_agreement_date(agreement),
        'lease_agreement_date':      str(agreement or ''),
        'formatted_start_date':      _fmt_date(start),
        'formatted_end_date':        _fmt_date(end),
        'term_start_date':           str(start or ''),
        'term_end_date':             str(end or ''),
        'is_renewal':                is_renewal,
        'exclude_security_deposit':  excl_sd,
        'exclude_inspection_fee':    excl_if,
        'effective_inspection_fee':  effective_inspection_fee,
        're_company_fee':            re_company_fee,
        'base_rent':                 base_rent,
        'term_sheet_total':          term_sheet_total,
        'landlord':                  landlord,
    }


def _resolve_doc_template(doc_name, uploaded_map):
    """
    Resolve a document's template content, preferring the admin-uploaded
    Document.file (if present on disk) and falling back to the bundled static
    repo template. Returns (content_or_None, source, doc_obj).
    """
    doc_obj = uploaded_map.get(doc_name)
    if doc_obj and doc_obj.file:
        try:
            up_path = doc_obj.file.path
            if os.path.exists(up_path):
                with open(up_path, 'r', encoding='utf-8') as f:
                    return f.read(), 'uploaded', doc_obj
        except (ValueError, OSError):
            pass
    static_rel = STATIC_DOC_TEMPLATES.get(doc_name)
    if static_rel:
        static_path = os.path.join(settings.BASE_DIR, 'docsAppR', 'templates', static_rel)
        if os.path.exists(static_path):
            with open(static_path, 'r', encoding='utf-8') as f:
                return f.read(), 'static', doc_obj
    return None, None, doc_obj


# Maps canonical Document name → the JSON/template key used by the live preview.
DOC_PREVIEW_KEYS = {
    'Engagement Agreement':  'engagement_agreement',
    'Term Sheet':            'term_sheet',
    'Month to Month Rental': 'month_to_month_rental',
}


def _render_all_lease_html(lease, overrides=None, preview=True):
    """
    Render all 4 lease documents to HTML strings (no PDF, no DB writes).
    Used by the live-preview endpoint and the initial detail page render.
    Returns: {engagement_agreement, term_sheet, month_to_month_rental, input_sheet}
    """
    from docsAppR.models import Document

    ctx_dict = _build_lease_context(lease, overrides=overrides, preview=preview)
    uploaded = {d.name: d for d in Document.objects.filter(name__in=DOCUMENT_NAMES)}

    def _err(label, msg):
        return (f'<div style="padding:2rem;font-family:sans-serif;color:#b91c1c;">'
                f'<strong>Could not render {label}.</strong><br>{msg}</div>')

    out = {}
    for doc_name in DOCUMENT_NAMES:
        key = DOC_PREVIEW_KEYS[doc_name]
        content, _source, doc_obj = _resolve_doc_template(doc_name, uploaded)
        if content is None:
            out[key] = _err(doc_name, 'No template available.')
            continue
        try:
            out[key] = Template(content).render(Context({**ctx_dict, 'document': doc_obj}))
        except Exception as exc:   # noqa: BLE001
            out[key] = _err(doc_name, str(exc))

    # Input Sheet (static template only)
    input_path = os.path.join(
        settings.BASE_DIR, 'docsAppR', 'templates', 'account', 'lease_input_sheet.html'
    )
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            out['input_sheet'] = Template(f.read()).render(Context({**ctx_dict}))
    except Exception as exc:        # noqa: BLE001
        out['input_sheet'] = _err('Input Sheet', str(exc))

    return out


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
    # IMPORTANT: each lease gets its OWN sub-folder keyed by lease id. Without
    # this, two leases for the same claim (e.g. an original + a renewal) wrote to
    # identical paths and overwrote each other's PDFs — so sending a renewal
    # attached the original's documents.
    lease_slug  = str(lease.id)
    lease_dir   = os.path.join(settings.MEDIA_ROOT, 'lease_documents', client_slug, lease_slug)
    rel_dir     = f"lease_documents/{client_slug}/{lease_slug}"
    os.makedirs(lease_dir, exist_ok=True)

    # Pull current party/company/contact info from the claim and persist it, so
    # the generated documents (and the detail page) reflect the latest claim data.
    _sync_descriptive_from_claim(lease, save=True)

    # Same context the live preview uses → preview matches the PDF exactly.
    context_base = _build_lease_context(lease, overrides=None, preview=False)

    results = []

    # ── Main documents ────────────────────────────────────────────────────────
    # Each template is resolved preferring the admin-uploaded Document.file and
    # falling back to the bundled static repo template (see _resolve_doc_template),
    # so generation never fails just because the media volume lost the uploads.
    # We iterate the canonical DOCUMENT_NAMES (not the DB rows) so generation
    # works even on a fresh database with zero Document records.
    uploaded = {d.name: d for d in Document.objects.filter(name__in=DOCUMENT_NAMES)}

    for doc_name in DOCUMENT_NAMES:
        result = {'doc_name': doc_name, 'success': False, 'error': ''}
        try:
            template_content, source, doc_obj = _resolve_doc_template(doc_name, uploaded)

            if template_content is None:
                result['error'] = (
                    f'No template available for "{doc_name}" '
                    f'(uploaded file missing and no static fallback found)'
                )
                results.append(result)
                continue

            ctx       = Context({**context_base, 'document': doc_obj})
            html_str  = Template(template_content).render(ctx)
            pdf_bytes = WeasyHTML(string=html_str, base_url=base_url).write_pdf()

            filename  = f"{doc_name.replace(' ', '_')}.pdf"
            abs_path  = os.path.join(lease_dir, filename)
            rel_path  = f"{rel_dir}/{filename}"

            with open(abs_path, 'wb') as f:
                f.write(pdf_bytes)

            doc_type = DOCUMENT_TYPE_MAP.get(doc_name, 'engagement_agreement')
            _upsert_lease_document(lease, doc_type, f"{doc_name} - {client.pOwner}", rel_path)

            result.update({
                'success':   True,
                'file_path': rel_path,
                'doc_type':  doc_type,
                'source':    source,
            })
            logger.info('Generated %s (%s template) → %s', doc_name, source, abs_path)

        except Exception as exc:
            logger.error('PDF generation failed for %s: %s', doc_name, exc)
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

            filename = "Input_Sheet.pdf"
            abs_path = os.path.join(lease_dir, filename)
            rel_path = f"{rel_dir}/{filename}"
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
    Lease generation with confirmation step.

    GET  → Show a read-only preview of the ALE data that will populate the
           lease, plus a Confirm button.  No lease is created yet.
    POST → Create the lease from ALE data, generate PDFs, redirect to detail.

    Passing ?new=1 (GET) or force=1 (POST) creates a new lease even when one
    already exists (renewal flow).
    """
    from docsAppR.models import PipelineStageAssignment, LeaseStageCompletion

    client = get_object_or_404(Client, id=client_id)

    force_new = bool(request.POST.get('force') or request.GET.get('new'))
    existing = (
        Lease.objects.filter(client=client)
        .exclude(status='cancelled')
        .order_by('-created_at')
        .first()
    )

    # ── GET: show the confirmation / preview page ─────────────────────────
    if request.method == 'GET':
        if existing and not force_new:
            messages.info(request, f'Existing lease found for {client.pOwner}.')
            return redirect('lease_manager:lease_detail', lease_id=str(existing.id))

        ale_preview = _ale_to_lease_fields(client)
        is_renewal  = bool(existing)
        return render(request, 'lease_manager/lease_generate_confirm.html', {
            'client':      client,
            'ale':         ale_preview,
            'is_renewal':  is_renewal,
            'existing':    existing,
            'force_new':   force_new,
        })

    # ── POST: confirmed — create the lease ───────────────────────────────
    ale_fields = _ale_to_lease_fields(client)
    if existing:
        ale_fields['is_renewal'] = True

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
            f'Lease record created but no documents could be generated. '
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
            'error': 'No documents could be generated — no lease templates are available '
                     '(neither uploaded nor bundled). Contact support.',
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

    # All non-cancelled leases for this claim, ordered oldest → newest.
    # Used to show an "Other Leases" switcher so users can jump between
    # the original and any renewals without going back to the list.
    sibling_leases = (
        Lease.objects.filter(client=lease.client)
        .exclude(status='cancelled')
        .order_by('created_at')
        .only('id', 'status', 'lease_start_date', 'lease_end_date', 'monthly_rent')
    )

    context = {
        'lease':          lease,
        'client':         lease.client,
        'sig_requests':   sig_requests,
        'docs':           docs,
        'activities':     activities,
        'contacts':       contacts,
        'all_signed':     all_signed,
        'sibling_leases': sibling_leases,
        'can_send':    lease.status not in ('signed', 'cancelled', 'completed'),
        # Terms are locked once the lease is finalised — editing them after
        # signing would invalidate the executed document.
        'terms_locked': lease.status in ('signed', 'cancelled', 'completed'),
    }
    return render(request, 'lease_manager/lease_detail.html', context)


# ============================================================================
# LIVE PREVIEW + EDIT TERMS  (streamlined plug-n-play editor)
# ============================================================================

@login_required
@require_POST
def lease_live_preview(request, lease_id):
    """
    POST JSON of override values (monthly_rent, security_deposit,
    lease_agreement_date, lease_start_date, lease_end_date, is_renewal,
    exclude_security_deposit, exclude_inspection_fee).

    Renders all 4 documents to HTML with those overrides applied — WITHOUT
    saving anything — and returns them for live in-page preview.
    """
    lease = get_object_or_404(Lease, id=lease_id)
    try:
        overrides = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        overrides = {}

    documents = _render_all_lease_html(lease, overrides=overrides, preview=True)
    return JsonResponse({'success': True, 'documents': documents})


@login_required
@require_POST
def lease_update_terms(request, lease_id):
    """
    POST JSON: persist the editable lease terms, then regenerate the PDFs so
    the saved documents match. Returns the recomputed display values.
    """
    lease = get_object_or_404(Lease, id=lease_id)

    if lease.status in ('signed', 'cancelled', 'completed'):
        return JsonResponse(
            {'error': 'This lease is finalised and can no longer be edited.'},
            status=400,
        )

    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    # Apply the editable fields (only the ones present in the payload)
    if 'monthly_rent' in data:
        lease.monthly_rent = _dec(data.get('monthly_rent'), lease.monthly_rent)
    if 'security_deposit' in data:
        lease.security_deposit = _dec(data.get('security_deposit'), lease.security_deposit)
    if 'rental_months' in data:
        lease.rental_months = _int_or(data.get('rental_months'), lease.rental_months)

    start = _parse_date(data.get('lease_start_date'))
    if start:
        lease.lease_start_date = start
    end = _parse_date(data.get('lease_end_date'))
    if end:
        lease.lease_end_date = end
    agreement = _parse_date(data.get('lease_agreement_date'))
    if agreement:
        lease.lease_agreement_date = agreement

    lease.is_renewal               = _bool(data.get('is_renewal'),               lease.is_renewal)
    lease.exclude_security_deposit = _bool(data.get('exclude_security_deposit'), lease.exclude_security_deposit)
    lease.exclude_inspection_fee   = _bool(data.get('exclude_inspection_fee'),   lease.exclude_inspection_fee)
    # Special notes — user-entered only; an empty box clears it.
    if 'special_notes' in data:
        lease.special_notes = (data.get('special_notes') or '').strip()
    lease.last_modified_by = request.user
    lease.save()

    # ── Mirror the edited terms back to the Client's ALE data ────────────────
    # Only the ORIGINAL lease (the claim's oldest active lease) syncs its terms
    # back to the claim. Renewals keep their own independent terms and never
    # write back — so a 3-month renewal can't clobber the original's term, and
    # editing the original still keeps the claim's ALE in sync.
    client = lease.client
    original = (
        Lease.objects.filter(client=client)
        .exclude(status='cancelled')
        .order_by('created_at')
        .first()
    )
    synced = original is not None and original.id == lease.id
    if synced:
        client.ale_rental_amount_per_month = lease.monthly_rent
        client.ale_rental_security_deposit = lease.security_deposit
        client.ale_rental_months           = str(lease.rental_months)
        client.ale_rental_start_date       = lease.lease_start_date
        client.ale_rental_end_date         = lease.lease_end_date
        client.save(update_fields=[
            'ale_rental_amount_per_month',
            'ale_rental_security_deposit',
            'ale_rental_months',
            'ale_rental_start_date',
            'ale_rental_end_date',
        ])

    # Regenerate PDFs so the downloadable/sendable docs reflect the new terms.
    base_url = request.build_absolute_uri('/')
    results  = generate_lease_pdfs(lease, base_url=base_url)
    ok_count = sum(1 for r in results if r.get('success'))

    LeaseActivity.objects.create(
        lease=lease,
        activity_type='generated',
        description=(
            f'Lease terms updated — rent ${lease.monthly_rent}, '
            f'deposit ${lease.security_deposit}, {lease.rental_months} month(s), '
            f'{lease.lease_start_date} → {lease.lease_end_date}'
            f'{" (renewal)" if lease.is_renewal else ""}. '
            f'{ok_count} document(s) regenerated.'
            + ('' if synced else ' Renewal — terms kept independent (not synced to the claim).')
        ),
        performed_by=request.user,
    )

    return JsonResponse({
        'success':          True,
        'ok_count':         ok_count,
        'monthly_rent':     float(lease.monthly_rent),
        'security_deposit': float(lease.security_deposit),
        'rental_months':    lease.rental_months,
        'synced_to_claim':  synced,
        'message':          (
            f'Saved — {ok_count} document(s) regenerated.'
            + ('' if synced else ' (Renewal — independent terms, not synced to the claim.)')
        ),
    })


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
