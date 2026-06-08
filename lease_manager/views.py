"""
Lease Manager app views.
"""
import json
import logging
import mimetypes
import os
import urllib.parse

from datetime import timedelta, date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.db.models import Count, Sum, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from docsAppR.models import (
    Client, Landlord, Lease, LeaseDocument, LeaseActivity,
)

from docsAppR.views import generate_document_from_html  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)

OWNER_EMAIL  = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')
FROM_EMAIL   = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@claimetapp.com')


# ============================================================================
# ALE → LEASE FIELD MAPPING
# ============================================================================

def _parse_city_state_zip(raw):
    """
    Robustly parse address strings into (city, state, zip).

    Handles all formats actually stored in the ALE fields:
      "Cleveland, OH 44102"   → ('Cleveland', 'OH', '44102')
      "Cleveland, 44102"      → ('Cleveland', '',   '44102')
      "Cleveland OH 44102"    → ('Cleveland', 'OH', '44102')
      "Cleveland 44102"       → ('Cleveland', '',   '44102')
      "44102"                 → ('',          '',   '44102')
      ""  / None              → ('',          '',   '')
    """
    if not raw:
        return '', '', ''
    raw = raw.strip()

    def _is_zip(token):
        # US ZIP: 5 digits or 5+4 with dash
        return token.replace('-', '').isdigit() and len(token.replace('-', '')) >= 5

    if ',' in raw:
        city, rest = raw.split(',', 1)
        city   = city.strip()
        tokens = rest.strip().split()
        if not tokens:
            return city, '', ''
        if _is_zip(tokens[-1]):
            zip_code = tokens[-1]
            state    = ' '.join(tokens[:-1]).strip()   # '' when no state token
        else:
            zip_code = ''
            state    = ' '.join(tokens).strip()
        return city, state, zip_code

    # No comma — split on whitespace
    tokens = raw.split()
    if not tokens:
        return '', '', ''
    if len(tokens) == 1:
        return ('', '', tokens[0]) if _is_zip(tokens[0]) else (tokens[0], '', '')
    if _is_zip(tokens[-1]):
        zip_code   = tokens[-1]
        inner      = tokens[:-1]
        # 2-letter all-alpha token before ZIP = state abbreviation
        if len(inner) >= 1 and len(inner[-1]) == 2 and inner[-1].isalpha():
            state = inner[-1].upper()
            city  = ' '.join(inner[:-1])
        else:
            state = ''
            city  = ' '.join(inner)
        return city, state, zip_code

    # Cannot identify zip — treat everything as city
    return raw, '', ''


def _ale_to_lease_fields(client):
    """
    Map every ALE field on Client to the corresponding Lease model field.
    Returns a dict ready for Lease.objects.create(**ale_fields).

    Coverage:
    - Lessor name, mailing address, city/state/zip, phone, email, contact person
    - Property (leased) address, city/state/zip, bedrooms
    - Rental terms: start/end dates, months, monthly rent
    - RE company: name, mailing address, city/state/zip, contact, phone, email
    - Broker: name, phone, email
    - Contact phone/email echoed from lessor fields (single source in ALE model)
    - Special notes: lessee info summary (Lease has no dedicated lessee fields)

    NOT mappable (no corresponding ALE field on Client):
    - security_deposit, rent_due_day, late_fee, late_fee_start_day,
      eviction_day, nsf_fee, max_occupants, parking_spaces, parking_fee,
      inspection_fee  — these stay at Lease model defaults.
    """
    # ── Parse compound address strings ────────────────────────────────────
    lessor_mail_city, lessor_mail_state, lessor_mail_zip = _parse_city_state_zip(
        client.ale_lessor_mailing_city_zip
    )
    prop_city, prop_state, prop_zip = _parse_city_state_zip(
        client.ale_lessor_city_zip
    )
    re_city, re_state, re_zip = _parse_city_state_zip(client.ale_re_city_zip)

    # ── Numeric coercion ──────────────────────────────────────────────────
    def _int(val, default=0):
        try:
            # strip non-numeric suffix like "12 months"
            cleaned = str(val).strip().split()[0] if val not in (None, '') else ''
            return int(float(cleaned)) if cleaned else default
        except (ValueError, TypeError):
            return default

    # ── Build lessee summary for special_notes (lessee has no Lease fields) ─
    lessee_parts = []
    if client.ale_lessee_name:
        lessee_parts.append(f'Lessee: {client.ale_lessee_name}')
    if client.ale_lessee_phone:
        lessee_parts.append(f'Phone: {client.ale_lessee_phone}')
    if client.ale_lessee_email:
        lessee_parts.append(f'Email: {client.ale_lessee_email}')
    if client.ale_lessee_home_address:
        lessee_parts.append(f'Home Address: {client.ale_lessee_home_address}')
    if client.ale_lessee_city_state_zip:
        lessee_parts.append(client.ale_lessee_city_state_zip)
    lessee_summary = ' | '.join(lessee_parts)

    return {
        # ── Lessor (landlord) ─────────────────────────────────────────────
        'lessor_name':             client.ale_lessor_name           or '',
        'lessor_address':          client.ale_lessor_mailing_address or '',
        'lessor_city':             lessor_mail_city,
        'lessor_state':            lessor_mail_state,
        'lessor_zip':              lessor_mail_zip,
        'lessor_phone':            client.ale_lessor_phone           or '',
        'lessor_email':            client.ale_lessor_email           or '',
        'lessor_contact_person_1': client.ale_lessor_contact_person  or '',
        # Contact phone/email: ALE has one phone/email field for lessor —
        # mirror it here so the template always has something to show.
        'lessor_contact_phone':    client.ale_lessor_phone           or '',
        'lessor_contact_email':    client.ale_lessor_email           or '',

        # ── Property (the leased address) ────────────────────────────────
        'property_address': client.ale_lessor_leased_address or client.pAddress or '',
        'property_city':    prop_city,
        'property_state':   prop_state,
        'property_zip':     prop_zip,
        'bedrooms':         _int(client.ale_rental_bedrooms, 1),

        # ── Rental terms ──────────────────────────────────────────────────
        'lease_start_date': client.ale_rental_start_date,
        'lease_end_date':   client.ale_rental_end_date,
        'rental_months':    _int(client.ale_rental_months, 12),
        'monthly_rent':     client.ale_rental_amount_per_month or 0,

        # ── Real estate company ───────────────────────────────────────────
        'real_estate_company':     client.ale_re_company_name     or '',
        'company_mailing_address': client.ale_re_mailing_address  or '',
        'company_city':            re_city,
        'company_state':           re_state,
        'company_zip':             re_zip,
        'company_contact_person':  client.ale_re_contact_person   or '',
        'company_phone':           client.ale_re_phone             or '',
        'company_email':           client.ale_re_email             or '',

        # ── Broker ────────────────────────────────────────────────────────
        'broker_name':  client.ale_re_owner_broker_name  or '',
        'broker_phone': client.ale_re_owner_broker_phone or '',
        'broker_email': client.ale_re_owner_broker_email or '',

        # ── Lessee (tenant) — now dedicated model fields ──────────────────
        'lessee_name':    client.ale_lessee_name           or client.pOwner or '',
        'lessee_email':   client.ale_lessee_email          or client.cEmail  or '',
        'lessee_phone':   client.ale_lessee_phone          or '',
        'lessee_address': (
            (client.ale_lessee_home_address or '') +
            (' ' + client.ale_lessee_city_state_zip if client.ale_lessee_city_state_zip else '')
        ).strip(),

        # Keep the summary in special_notes too (backwards compat)
        'special_notes': lessee_summary,
    }


def _lease_contacts(lease):
    """
    Return prioritised contact list for a lease.
    Priority order (per spec): RE company → broker → lessor → lessee → owner.
    Returns list of dicts: {label, email, role, priority}
    """
    contacts = []

    def add(label, email, role, priority):
        if email and email.strip():
            contacts.append({
                'label':    label,
                'email':    email.strip(),
                'role':     role,
                'priority': priority,
            })

    client = lease.client

    # 1. Real-estate company contact
    add(f'RE Company — {lease.real_estate_company or client.ale_re_company_name}',
        lease.company_email or client.ale_re_email, 're_company', 1)

    # 2. Broker
    add(f'Broker — {lease.broker_name or client.ale_re_owner_broker_name}',
        lease.broker_email or client.ale_re_owner_broker_email, 'broker', 2)

    # 3. RE company contact person (sometimes different email)
    if client.ale_re_contact_person and client.ale_re_email != lease.company_email:
        add(f'RE Contact — {client.ale_re_contact_person}',
            client.ale_re_email, 're_contact', 3)

    # 4. Lessor (landlord)
    add(f'Lessor — {lease.lessor_name or client.ale_lessor_name}',
        lease.lessor_email or client.ale_lessor_email, 'lessor', 4)

    # 5. Lessor contact person
    add(f'Lessor Contact — {lease.lessor_contact_person_1 or client.ale_lessor_contact_person}',
        lease.lessor_contact_email or '', 'lessor_contact', 5)

    # 6. Lessee (the insured / ALE recipient)
    add(f'Lessee — {client.ale_lessee_name or client.pOwner}',
        client.ale_lessee_email or client.cEmail, 'lessee', 6)

    # 7. Client primary email (insurance policyholder)
    add(f'Client — {client.pOwner}', client.cEmail, 'client', 7)

    # 8. Owner (always included, pre-checked as CC)
    add('Owner — wsbjoe9', OWNER_EMAIL, 'owner', 8)

    # Deduplicate by email
    seen = set()
    unique = []
    for c in sorted(contacts, key=lambda x: x['priority']):
        if c['email'].lower() not in seen:
            seen.add(c['email'].lower())
            unique.append(c)
    return unique


# ============================================================================
# ALE DATA CHECK  — confirms whether a client actually has ALE fields filled
# ============================================================================

@login_required
def api_ale_check(request, client_id):
    """
    GET: Return a summary of which ALE fields are filled on a client.
    Used to confirm pre-population before creating a lease.
    """
    client = get_object_or_404(Client, id=client_id)

    ale_summary = {
        'has_lessor':    bool(client.ale_lessor_name),
        'has_property':  bool(client.ale_lessor_leased_address),
        'has_dates':     bool(client.ale_rental_start_date and client.ale_rental_end_date),
        'has_rent':      bool(client.ale_rental_amount_per_month),
        'has_re':        bool(client.ale_re_company_name or client.ale_re_email),
        'has_broker':    bool(client.ale_re_owner_broker_email),
        'filled_count':  sum([
            bool(client.ale_lessor_name),
            bool(client.ale_lessor_leased_address),
            bool(client.ale_rental_start_date),
            bool(client.ale_rental_end_date),
            bool(client.ale_rental_amount_per_month),
            bool(client.ale_re_company_name),
            bool(client.ale_re_email),
            bool(client.ale_re_owner_broker_email),
            bool(client.ale_lessor_email),
            bool(client.ale_lessor_phone),
        ]),
        'total_checked': 10,
        # Raw values for UI display
        'lessor_name':       client.ale_lessor_name,
        'leased_address':    client.ale_lessor_leased_address,
        'start_date':        client.ale_rental_start_date.isoformat() if client.ale_rental_start_date else '',
        'end_date':          client.ale_rental_end_date.isoformat() if client.ale_rental_end_date else '',
        'monthly_rent':      str(client.ale_rental_amount_per_month or ''),
        're_company':        client.ale_re_company_name,
        're_email':          client.ale_re_email,
        'broker_email':      client.ale_re_owner_broker_email,
        'lessor_email':      client.ale_lessor_email,
        'lessee_name':       client.ale_lessee_name,
    }

    return JsonResponse({
        'success':     True,
        'client_name': client.pOwner,
        'has_ale_data': ale_summary['filled_count'] > 0,
        'ale_summary':  ale_summary,
        'warning':      '' if ale_summary['filled_count'] > 0
                        else 'This claim has no ALE data. Fill in the ALE section of the claim first.',
    })


# ============================================================================
# DEMAND LETTER  —  select which ALE payments are outstanding, generate letter
# ============================================================================

DEMAND_PAYMENT_ITEMS = [
    # key, label, lease_field (or None for computed)
    ('rent_total',       'Total Rent',                    None),          # monthly_rent × rental_months
    ('security_deposit', 'Security Deposit',              'security_deposit'),
    ('brokerage_fee',    'Brokerage Fee (1 month rent)',  None),          # = monthly_rent
    ('inspection_fee',   'Inspection / Cleanup Fee',      'inspection_fee'),
    ('parking_fee',      'Parking Fee',                   'parking_fee'),
    ('late_fee',         'Late Fee',                      'late_fee'),
]


def _payment_items_for_lease(lease):
    """Build the list of payment items with computed amounts."""
    items = []
    monthly = float(lease.monthly_rent or 0)
    months  = lease.rental_months or 1

    amounts = {
        'rent_total':       round(monthly * months, 2),
        'security_deposit': float(lease.security_deposit or 0),
        'brokerage_fee':    monthly,
        'inspection_fee':   float(lease.inspection_fee or 0),
        'parking_fee':      float(lease.parking_fee or 0),
        'late_fee':         float(lease.late_fee or 0),
    }
    for key, label, field in DEMAND_PAYMENT_ITEMS:
        amount = amounts[key]
        if amount > 0:
            items.append({'key': key, 'label': label, 'amount': amount})
    return items


@login_required
def demand_letter_compose(request, lease_id):
    """
    GET : Show the demand letter form — select outstanding items, preview letter.
    POST: Build the letter body and redirect to the universal compose page.
    """
    lease  = get_object_or_404(Lease.objects.select_related('client'), id=lease_id)
    client = lease.client

    payment_items = _payment_items_for_lease(lease)

    if request.method == 'GET':
        # Determine insurance company contacts for demand letter "To"
        ins_contacts = []
        def _add_ins(label, email):
            if email and email.strip():
                ins_contacts.append({'label': label, 'email': email.strip()})

        _add_ins(f'Insurance Co — {client.insuranceCo_Name}',   client.emailInsCo)
        _add_ins(f'Desk Adjuster — {client.deskAdjusterDA}',    client.DAEmail)
        _add_ins(f'Field Adjuster — {client.fieldAdjusterName}', client.fieldAdjEmail)
        _add_ins('Owner',                                         OWNER_EMAIL)

        context = {
            'lease':         lease,
            'client':        client,
            'payment_items': payment_items,
            'ins_contacts':  ins_contacts,
            'today':         timezone.now().date(),
            'deadline_days': 30,
        }
        return render(request, 'account/lease_demand_letter.html', context)

    # ── POST: build letter data ───────────────────────────────────────────
    outstanding_keys = request.POST.getlist('outstanding_items')
    custom_amounts   = {}
    for key, _, _ in DEMAND_PAYMENT_ITEMS:
        raw = request.POST.get(f'amount_{key}', '')
        if raw:
            try:
                custom_amounts[key] = float(raw)
            except ValueError:
                pass

    outstanding = []
    for item in payment_items:
        if item['key'] in outstanding_keys:
            amt = custom_amounts.get(item['key'], item['amount'])
            outstanding.append({'label': item['label'], 'amount': amt})

    total_due = sum(i['amount'] for i in outstanding)

    letter_date    = timezone.now().date()
    deadline       = letter_date + timedelta(days=int(request.POST.get('deadline_days', 30)))
    insured_name   = client.ale_lessee_name or client.pOwner or ''
    claim_number   = client.claimNumber or ''
    ins_company    = client.insuranceCo_Name or 'Insurance Company'
    property_addr  = lease.property_address or ''
    ale_start      = lease.lease_start_date.strftime('%B %d, %Y') if lease.lease_start_date else 'TBD'
    ale_end        = lease.lease_end_date.strftime('%B %d, %Y')   if lease.lease_end_date   else 'TBD'
    re_company     = lease.real_estate_company or ''
    contact_name   = request.POST.get('contact_name', 'Julius Cartwright')
    contact_phone  = request.POST.get('contact_phone', '(216) 990-1501')
    contact_email  = request.POST.get('contact_email', OWNER_EMAIL)

    disbursed = [i for i in payment_items if i['key'] not in outstanding_keys]
    disbursed_text = ' and '.join(
        f'{i["label"]} (${custom_amounts.get(i["key"], i["amount"]):,.2f})'
        for i in disbursed
    ) if disbursed else 'other components'

    # ── Generate the demand letter PDF ───────────────────────────────────
    letter_data = {
        'date_str':        letter_date.strftime('%B %d, %Y'),
        'insured_name':    insured_name,
        'claim_number':    claim_number,
        'ins_company':     ins_company,
        'property_addr':   property_addr,
        're_company':      re_company or 'Dream Team Realty, Inc.',
        'ale_start':       ale_start,
        'ale_end':         ale_end,
        'outstanding_items': outstanding,
        'disbursed_text':  disbursed_text,
        'total_due':       total_due,
        'deadline_str':    deadline.strftime('%B %d, %Y'),
        'contact_name':    contact_name,
        'contact_phone':   contact_phone,
        'contact_email':   contact_email,
    }

    gen_file_id = ''
    try:
        from docsAppR.pdf_utils import generate_demand_letter_pdf
        from docsAppR.models import GeneratedFile
        import os

        pdf_buf = generate_demand_letter_pdf(letter_data)

        # Save PDF to media/demand_letters/
        safe_name = f'demand_letter_{insured_name.replace(" ", "_")}_{claim_number}_{letter_date.strftime("%Y%m%d")}.pdf'
        rel_dir   = os.path.join('demand_letters', str(letter_date.year))
        abs_dir   = os.path.join(settings.MEDIA_ROOT, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        abs_path  = os.path.join(abs_dir, safe_name)
        with open(abs_path, 'wb') as fh:
            fh.write(pdf_buf.read())

        gf = GeneratedFile.objects.create(
            name=f'Demand Letter — {insured_name} — Claim #{claim_number}',
            file_path=abs_path,
            mime_type='application/pdf',
            category='pdf',
            client=client,
            created_by=request.user,
        )
        gen_file_id = str(gf.id)
    except Exception as exc:
        logger.error('demand_letter PDF generation failed: %s', exc)

    # ── Build plain-text email body (kept as fallback / message body) ────
    items_text = '\n'.join(
        f'  • {i["label"]}: ${i["amount"]:,.2f}' for i in outstanding
    )
    body = (
        f'DEMAND FOR PAYMENT\n\n'
        f'Date: {letter_date.strftime("%B %d, %Y")}\n'
        f'Via Certified Mail – Return Receipt Requested\n\n'
        f'TO: {ins_company}\n    Attn: Claims Department / Additional Living Expense Unit\n\n'
        f'RE: Insured: {insured_name} | Claim #{claim_number} | Amount Due: ${total_due:,.2f}\n\n'
        f'This letter serves as FORMAL DEMAND FOR PAYMENT of ${total_due:,.2f} owed to '
        f'{re_company or "Dream Team Realty, Inc."} in connection with the above-referenced '
        f'Additional Living Expense (ALE) claim for your insured, {insured_name}.\n\n'
        f'{re_company or "Dream Team Realty"} located, procured, and executed a lease on behalf '
        f'of your insured at {property_addr}, for the ALE period {ale_start} through {ale_end}.\n\n'
        f'{ins_company} has disbursed {disbursed_text}. The following item(s) remain outstanding:\n\n'
        f'{items_text}\n\nTOTAL AMOUNT DUE: ${total_due:,.2f}\n\n'
        f'Payment demanded on or before {deadline.strftime("%B %d, %Y")}.\n\n'
        f'Contact: {contact_name} | {contact_phone} | {contact_email}\n\n'
        f'All rights and remedies are expressly reserved.\n\nSincerely,\n{contact_name}\n'
        f'{re_company or "Dream Team Realty, Inc."}\n\n'
        f'Enclosures: Engagement Agreement | Term Sheet | Monthly Short-Term Rental Agreement'
    )

    # ── Log activity ─────────────────────────────────────────────────────
    LeaseActivity.objects.create(
        lease=lease,
        activity_type='note_added',
        description=f'Demand letter generated — ${total_due:,.2f} outstanding to {ins_company}',
        performed_by=request.user,
    )
    try:
        from docsAppR.models import log_activity
        log_activity('demand_letter',
                     f'Demand letter generated for {insured_name} | Claim #{claim_number} | ${total_due:,.2f} due',
                     user=request.user, client=client, lease=lease,
                     ins_company=ins_company, total_due=str(total_due))
    except Exception:
        pass

    # ── Redirect to universal compose page ────────────────────────────────
    to_email = request.POST.get('to_email', client.emailInsCo or client.DAEmail or '')
    params_dict = {
        'source':    'demand_letter',
        'lease_id':  str(lease.id),
        'to':        to_email,
        'cc':        OWNER_EMAIL,
        'subject':   f'Demand for Payment — {insured_name} | Claim #{claim_number} | ${total_due:,.2f} Due',
        'body':      body,
    }
    if gen_file_id:
        params_dict['gen_file_id'] = gen_file_id
    return redirect(f'/emails/compose/?{urllib.parse.urlencode(params_dict)}')


# ============================================================================
# EXISTING VIEWS (unchanged logic, fixed ALE import in create_draft_lease)
# ============================================================================

def lease_manager(request):
    """Main Lease Manager Dashboard"""
    from docsAppR.models import PipelineStageAssignment, LeaseStageCompletion

    status_filter = request.GET.get('status', '')
    client_filter = request.GET.get('client', '')
    date_filter   = request.GET.get('date_range', '30')

    try:
        days = int(date_filter)
    except ValueError:
        days = 30
    date_threshold = timezone.now() - timedelta(days=days)
    today = date.today()

    leases_query = Lease.objects.select_related(
        'client', 'created_by', 'last_modified_by'
    ).prefetch_related(
        'documents', 'stage_completions',
        'stage_completions__assigned_user', 'stage_completions__completed_by'
    )

    if status_filter:
        leases_query = leases_query.filter(status=status_filter)
    if client_filter:
        leases_query = leases_query.filter(client__id=client_filter)

    all_leases = leases_query.order_by('-created_at')[:100]

    recent_activity = LeaseActivity.objects.select_related(
        'lease', 'lease__client', 'performed_by'
    ).filter(created_at__gte=date_threshold).order_by('-created_at')[:50]

    pipeline_stats = Lease.objects.values('status').annotate(count=Count('id')).order_by('status')
    status_counts  = {item['status']: item['count'] for item in pipeline_stats}

    STATUS_ORDER = [
        'draft', 'generated', 'review', 'sent_for_signature',
        'signed', 'invoice_created', 'package_sent',
        'payment_pending', 'payment_received', 'completed',
    ]
    cumulative_counts  = {}
    total_non_cancelled = Lease.objects.exclude(status='cancelled').count()
    for i, status in enumerate(STATUS_ORDER):
        cumulative_counts[status] = Lease.objects.filter(
            status__in=STATUS_ORDER[i:]
        ).exclude(status='cancelled').count()

    stage_assignments = PipelineStageAssignment.objects.select_related('assigned_user').order_by('order')

    pipeline_steps = []
    for i, (status_value, status_label) in enumerate(Lease.LEASE_STATUS_CHOICES):
        if status_value == 'cancelled':
            continue
        assignment      = stage_assignments.filter(stage=status_value).first()
        assignee_email  = assignment.assigned_user.email if assignment and assignment.assigned_user else 'Unassigned'
        assignee_initials = ''.join([p[0].upper() for p in assignee_email.split('@')[0].split('.')[:2]]) \
            if assignment and assignment.assigned_user else '?'
        pipeline_steps.append({
            'value':            status_value,
            'label':            status_label,
            'order':            i,
            'assignee_email':   assignee_email,
            'assignee_initials': assignee_initials,
            'current_count':    status_counts.get(status_value, 0),
            'cumulative_count': cumulative_counts.get(status_value, 0),
        })

    total_active    = Lease.objects.filter(lease_start_date__lte=today, lease_end_date__gte=today).exclude(status__in=['completed', 'cancelled']).count()
    total_completed = Lease.objects.filter(status='completed').count()
    total_expired   = Lease.objects.filter(lease_end_date__lt=today).exclude(status__in=['completed', 'cancelled']).count()

    clients_with_leases = Client.objects.filter(leases__isnull=False).distinct().prefetch_related(
        'leases', 'leases__documents'
    ).annotate(
        lease_count=Count('leases', distinct=True),
        active_lease_count=Count(
            'leases',
            filter=Q(leases__lease_start_date__lte=today) & Q(leases__lease_end_date__gte=today)
                   & ~Q(leases__status__in=['completed', 'cancelled']),
            distinct=True,
        )
    ).order_by('-leases__created_at')

    total_monthly_rent = Lease.objects.filter(
        lease_start_date__lte=today, lease_end_date__gte=today
    ).exclude(status__in=['completed', 'cancelled']).aggregate(total=Sum('monthly_rent'))['total'] or 0

    context = {
        'leases':               all_leases,
        'recent_activity':      recent_activity,
        'status_counts':        status_counts,
        'cumulative_counts':    cumulative_counts,
        'pipeline_steps':       pipeline_steps,
        'stage_assignments':    stage_assignments,
        'total_active':         total_active,
        'total_completed':      total_completed,
        'total_expired':        total_expired,
        'total_non_cancelled':  total_non_cancelled,
        'clients_with_leases':  clients_with_leases,
        'all_clients':          Client.objects.all().order_by('pOwner'),
        'status_choices':       Lease.LEASE_STATUS_CHOICES,
        'current_status_filter': status_filter,
        'current_client_filter': client_filter,
        'current_date_filter':  date_filter,
        'total_monthly_rent':   total_monthly_rent,
        'today':                today,
    }
    return render(request, 'account/lease_manager.html', context)


def create_draft_lease(request):
    """
    Auto-create a draft lease pre-filled from the client's ALE data.
    Now maps ALL ALE fields — not just property address.
    """
    from docsAppR.models import PipelineStageAssignment, LeaseStageCompletion

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data       = json.loads(request.body)
        client_id  = data.get('client_id')
        client_name = data.get('client_name')

        if not client_id and not client_name:
            return JsonResponse({'error': 'client_id or client_name required'}, status=400)

        client = Client.objects.get(id=client_id) if client_id else Client.objects.get(pOwner=client_name)

        existing = Lease.objects.filter(client=client, status='draft').first()
        if existing:
            return JsonResponse({'success': True, 'lease_id': str(existing.id),
                                  'message': 'Existing draft found', 'is_new': False})

        # ── Auto-fill from ALE data (the fix) ────────────────────────────
        ale_fields = _ale_to_lease_fields(client)

        lease = Lease.objects.create(
            client=client,
            status='draft',
            created_by=request.user if request.user.is_authenticated else None,
            last_modified_by=request.user if request.user.is_authenticated else None,
            **ale_fields,
        )

        LeaseActivity.objects.create(
            lease=lease,
            activity_type='draft',
            description=f'Draft lease created for {client.pOwner} — ALE data auto-imported',
            performed_by=request.user if request.user.is_authenticated else None,
        )

        stage_assignments = PipelineStageAssignment.objects.all()
        for assignment in stage_assignments:
            LeaseStageCompletion.objects.create(
                lease=lease, stage=assignment.stage,
                assigned_user=assignment.assigned_user, is_completed=False,
            )
        draft_completion = LeaseStageCompletion.objects.filter(lease=lease, stage='draft').first()
        if draft_completion:
            draft_completion.is_completed = True
            draft_completion.completed_by = request.user if request.user.is_authenticated else None
            draft_completion.completed_at = timezone.now()
            draft_completion.save()

        try:
            from docsAppR.models import log_activity
            log_activity(
                'lease_created',
                f'Draft lease created for {client.pOwner} with ALE data auto-imported',
                user=request.user if request.user.is_authenticated else None,
                client=client, lease=lease,
            )
        except Exception:
            pass

        # Return the ALE data so the UI can show what was auto-filled
        return JsonResponse({
            'success':   True,
            'lease_id':  str(lease.id),
            'message':   'Draft lease created with ALE data',
            'is_new':    True,
            'ale_filled': {k: str(v) for k, v in ale_fields.items() if v},
        })

    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    except Exception as exc:
        logger.error('Error creating draft lease: %s', exc)
        return JsonResponse({'error': str(exc)}, status=500)


# ============================================================================
# NEW: ALE → LEASE IMPORT ON EXISTING LEASE
# ============================================================================

@login_required
@require_POST
def api_ale_import(request, lease_id):
    """
    POST: Re-import all ALE fields from the linked Client into an existing Lease.
    Overwrites only blank fields unless ?overwrite=1 is passed.
    Returns the updated field values so the UI can reflect changes immediately.
    """
    lease    = get_object_or_404(Lease, id=lease_id)
    overwrite = request.GET.get('overwrite', '0') == '1'

    ale_fields = _ale_to_lease_fields(lease.client)
    updated    = {}
    skipped    = {}

    for field, value in ale_fields.items():
        current = getattr(lease, field, None)
        # Only overwrite if field is blank/zero OR overwrite flag is set
        if overwrite or not current or current in (0, '', None):
            setattr(lease, field, value)
            updated[field] = str(value) if value is not None else ''
        else:
            skipped[field] = str(current)

    if updated:
        lease.save()
        LeaseActivity.objects.create(
            lease=lease,
            activity_type='note_added',
            description=f'ALE data re-imported from claim ({len(updated)} fields updated)',
            performed_by=request.user,
        )
        try:
            from docsAppR.models import log_activity
            log_activity(
                'ale_sync',
                f'ALE data synced for {lease.client.pOwner} — {len(updated)} fields updated',
                user=request.user, client=lease.client, lease=lease,
                updated_count=len(updated),
            )
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'updated_count': len(updated),
        'skipped_count': len(skipped),
        'updated': updated,
        'skipped': skipped,
    })


# ============================================================================
# NEW: ALE PREFILL DATA (read-only, for display before import)
# ============================================================================

@login_required
def api_ale_prefill(request, client_id):
    """
    GET: Return the ALE data for a client as JSON so the UI can preview
    what will be imported before the user commits.
    """
    client = get_object_or_404(Client, id=client_id)
    fields = _ale_to_lease_fields(client)

    # Also return raw contact list for the send-package UI
    contacts = []
    def add_contact(label, email, role):
        if email and email.strip():
            contacts.append({'label': label, 'email': email.strip(), 'role': role})

    add_contact(f'RE Company — {client.ale_re_company_name}', client.ale_re_email, 're_company')
    add_contact(f'Broker — {client.ale_re_owner_broker_name}', client.ale_re_owner_broker_email, 'broker')
    add_contact(f'Lessor — {client.ale_lessor_name}', client.ale_lessor_email, 'lessor')
    add_contact(f'Lessee — {client.ale_lessee_name or client.pOwner}', client.ale_lessee_email or client.cEmail, 'lessee')
    add_contact('Owner — wsbjoe9', OWNER_EMAIL, 'owner')

    return JsonResponse({
        'success':  True,
        'client':   {'id': client.id, 'name': client.pOwner},
        'ale_data': {k: str(v) if v is not None else '' for k, v in fields.items()},
        'contacts': contacts,
        'has_ale_data': bool(client.ale_lessor_name or client.ale_re_company_name),
    })


# ============================================================================
# NEW: LEASE CONTACTS (prioritised for send-package)
# ============================================================================

@login_required
def api_lease_contacts(request, lease_id):
    """
    GET: Return prioritised contact list for a lease.
    RE company and broker come first; owner (wsbjoe9) always included.
    """
    lease    = get_object_or_404(Lease, id=lease_id)
    contacts = _lease_contacts(lease)
    return JsonResponse({'success': True, 'contacts': contacts})


# ============================================================================
# NEW: SEND LEASE DOCUMENT PACKAGE
# ============================================================================

@login_required
def lease_send_package(request, lease_id):
    """
    GET:  Render the send-package compose page.
    POST: Actually send the email with all lease documents attached.
    """
    lease    = get_object_or_404(Lease.objects.select_related('client').prefetch_related('documents'), id=lease_id)
    client   = lease.client
    contacts = _lease_contacts(lease)
    documents = lease.documents.all()

    if request.method == 'GET':
        # Build default subject + body
        subject = (
            f'ALE Lease Package — {client.pOwner}'
            + (f' | {lease.property_address}' if lease.property_address else '')
        )
        body = _default_package_body(lease, client)

        # Split contacts by default role
        to_contacts  = [c for c in contacts if c['role'] in ('re_company', 'broker', 're_contact')]
        cc_contacts  = [c for c in contacts if c['role'] in ('lessor', 'lessee', 'client', 'owner')]

        context = {
            'lease':        lease,
            'client':       client,
            'documents':    documents,
            'contacts':     contacts,
            'to_contacts':  to_contacts,
            'cc_contacts':  cc_contacts,
            'subject':      subject,
            'body':         body,
            'owner_email':  OWNER_EMAIL,
        }
        return render(request, 'account/lease_send_package.html', context)

    # ── POST: send the email ──────────────────────────────────────────────
    to_emails   = [e.strip() for e in request.POST.get('to', '').split(',') if e.strip()]
    cc_emails   = [e.strip() for e in request.POST.get('cc', '').split(',') if e.strip()]
    bcc_emails  = [e.strip() for e in request.POST.get('bcc', '').split(',') if e.strip()]
    subject     = request.POST.get('subject', '').strip()
    body_text   = request.POST.get('body', '').strip()
    doc_ids     = request.POST.getlist('document_ids')
    schedule_at = request.POST.get('schedule_at', '').strip()

    if not to_emails:
        messages.error(request, 'At least one To recipient is required.')
        return redirect('lease_send_package', lease_id=lease_id)

    if not subject:
        subject = f'ALE Lease Package — {client.pOwner}'

    # ── Build and send (or schedule) ─────────────────────────────────────
    if schedule_at:
        # Schedule via Celery eta
        _schedule_lease_package_email(
            lease=lease,
            to_emails=to_emails,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            body_text=body_text,
            doc_ids=doc_ids,
            send_at=schedule_at,
            user=request.user,
        )
        messages.success(request, f'Package email scheduled for {schedule_at}.')
    else:
        sent_ok, error = _send_lease_package_email(
            lease=lease,
            to_emails=to_emails,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            body_text=body_text,
            doc_ids=doc_ids,
            user=request.user,
        )
        if sent_ok:
            messages.success(request, f'Lease package sent to {", ".join(to_emails)}.')
        else:
            messages.error(request, f'Failed to send: {error}')

    return redirect('lease_manager:lease_manager')


# ============================================================================
# SEND HELPERS
# ============================================================================

def _default_package_body(lease, client):
    lessor  = lease.lessor_name or client.ale_lessor_name or ''
    address = lease.property_address or ''
    start   = lease.lease_start_date.strftime('%B %d, %Y') if lease.lease_start_date else 'TBD'
    end     = lease.lease_end_date.strftime('%B %d, %Y')   if lease.lease_end_date   else 'TBD'
    rent    = f'${lease.monthly_rent:,.2f}/month' if lease.monthly_rent else 'TBD'

    return (
        f'Dear {lessor or "Lessor/Agent"},\n\n'
        f'Please find attached the ALE lease document package for the following tenancy:\n\n'
        f'  Tenant:   {client.ale_lessee_name or client.pOwner}\n'
        f'  Property: {address}\n'
        f'  Term:     {start} – {end}\n'
        f'  Rent:     {rent}\n\n'
        f'This package contains the complete ALE agreement, addenda, and supporting documents '
        f'required for execution. Please review, sign where indicated, and return a copy at '
        f'your earliest convenience.\n\n'
        f'If you have any questions, please do not hesitate to contact us.\n\n'
        f'Best regards,\n'
        f'Claimet App'
    )


def _send_lease_package_email(lease, to_emails, cc_emails, bcc_emails,
                               subject, body_text, doc_ids, user):
    """
    Build, attach, and send the lease document package email.
    Creates a SentEmail tracking record and logs a LeaseActivity entry.
    Returns (True, None) on success or (False, error_string) on failure.
    """
    from docsAppR.models import SentEmail

    try:
        # Create SentEmail for open-tracking
        sent = SentEmail.objects.create(
            subject=subject,
            body=body_text,
            recipients=to_emails,
            cc=cc_emails,
            bcc=bcc_emails,
            sent_by=user,
            notify_on_open=True,
            admin_notification_email=OWNER_EMAIL,
        )

        # Tracking pixel
        base = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        pixel = (
            f'<img src="{base}/emails/track/{sent.tracking_pixel_id}/" '
            f'width="1" height="1" style="display:none;" alt="" />'
        )
        html_body = f'<div style="white-space:pre-wrap;">{body_text}</div>{pixel}'

        email = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=FROM_EMAIL,
            to=to_emails,
            cc=cc_emails,
            bcc=bcc_emails,
        )
        email.content_subtype = 'html'

        # Attach selected documents
        selected_docs = (
            lease.documents.filter(id__in=doc_ids) if doc_ids
            else lease.documents.all()
        )
        attached = []
        for doc in selected_docs:
            if not doc.file_path:
                continue
            full_path = os.path.join(settings.MEDIA_ROOT, doc.file_path)
            if not os.path.exists(full_path):
                logger.warning('Lease doc not found on disk: %s', full_path)
                continue
            mime, _ = mimetypes.guess_type(full_path)
            with open(full_path, 'rb') as fh:
                email.attach(doc.document_name or os.path.basename(full_path),
                              fh.read(), mime or 'application/pdf')
            attached.append(doc.document_name)

        email.send()

        # Log activity
        LeaseActivity.objects.create(
            lease=lease,
            activity_type='package_sent',
            description=(
                f'Lease package emailed to {", ".join(to_emails)}'
                + (f' ({len(attached)} docs attached)' if attached else '')
            ),
            performed_by=user,
        )

        try:
            from docsAppR.models import log_activity
            log_activity(
                'package_sent',
                f'Lease package sent to {", ".join(to_emails)} — {lease.client.pOwner}',
                user=user, client=lease.client, lease=lease,
                recipients=to_emails, docs_attached=len(attached),
            )
        except Exception:
            pass

        # Advance lease status if still at draft/generated
        if lease.status in ('draft', 'generated', 'review'):
            lease.status        = 'package_sent'
            lease.package_sent_at = timezone.now()
            lease.save(update_fields=['status', 'package_sent_at'])

        return True, None

    except Exception as exc:
        logger.error('Failed to send lease package: %s', exc)
        return False, str(exc)


def _schedule_lease_package_email(lease, to_emails, cc_emails, bcc_emails,
                                   subject, body_text, doc_ids, send_at, user):
    """Schedule the lease package email via Celery apply_async(eta=...)."""
    from lease_manager.tasks import send_lease_package_task
    from django.utils.dateparse import parse_datetime

    send_dt = parse_datetime(send_at)
    if send_dt and timezone.is_naive(send_dt):
        send_dt = timezone.make_aware(send_dt)

    if not send_dt:
        logger.error('Could not parse schedule time: %s', send_at)
        return

    send_lease_package_task.apply_async(
        kwargs={
            'lease_id':   str(lease.id),
            'to_emails':  to_emails,
            'cc_emails':  cc_emails,
            'bcc_emails': bcc_emails,
            'subject':    subject,
            'body_text':  body_text,
            'doc_ids':    doc_ids,
            'user_id':    user.id if user else None,
        },
        eta=send_dt,
    )
    LeaseActivity.objects.create(
        lease=lease,
        activity_type='note_added',
        description=f'Lease package email scheduled for {send_at} → {", ".join(to_emails)}',
        performed_by=user,
    )


# ============================================================================
# EXISTING VIEWS (unchanged)
# ============================================================================

def update_lease_status(request):
    from docsAppR.models import LeaseStageCompletion

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data       = json.loads(request.body)
        lease_id   = data.get('lease_id')
        new_status = data.get('status')
        if not lease_id or not new_status:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        lease      = Lease.objects.get(id=lease_id)
        old_status = lease.status
        lease.status          = new_status
        lease.last_modified_by = request.user if request.user.is_authenticated else None
        now = timezone.now()
        ts_map = {
            'generated': 'generated_at', 'review': 'reviewed_at',
            'sent_for_signature': 'sent_for_signature_at', 'signed': 'signed_at',
            'invoice_created': 'invoice_created_at', 'package_sent': 'package_sent_at',
            'payment_received': 'payment_received_at', 'completed': 'completed_at',
        }
        if new_status in ts_map:
            setattr(lease, ts_map[new_status], now)
        lease.save()
        sc = LeaseStageCompletion.objects.filter(lease=lease, stage=new_status).first()
        if sc and not sc.is_completed:
            sc.is_completed = True
            sc.completed_by = request.user if request.user.is_authenticated else None
            sc.completed_at = now
            sc.save()
        LeaseActivity.objects.create(
            lease=lease, activity_type=new_status,
            description=f'Status changed from "{old_status}" to "{new_status}"',
            old_status=old_status, new_status=new_status,
            performed_by=request.user if request.user.is_authenticated else None,
        )
        try:
            from docsAppR.models import log_activity
            log_activity(
                'lease_status_changed',
                f'Lease status changed: {old_status} → {new_status} — {lease.client.pOwner}',
                user=request.user if request.user.is_authenticated else None,
                client=lease.client, lease=lease,
                old_status=old_status, new_status=new_status,
            )
        except Exception:
            pass
        return JsonResponse({'success': True, 'new_status': new_status,
                             'status_display': lease.get_status_display()})
    except Lease.DoesNotExist:
        return JsonResponse({'error': 'Lease not found'}, status=404)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


def get_leases_by_client(request, client_id):
    today = date.today()
    try:
        client = Client.objects.get(id=client_id)
        leases = Lease.objects.filter(client=client).prefetch_related('documents').order_by('-created_at')
        leases_data = []
        for lease in leases:
            docs = [{
                'id':                    str(doc.id),
                'document_type':         doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'document_name':         doc.document_name,
                'file_path':             doc.file_path,
            } for doc in lease.documents.all()]
            leases_data.append({
                'id':               str(lease.id),
                'lessor_name':      lease.lessor_name,
                'property_address': lease.full_property_address,
                'monthly_rent':     float(lease.monthly_rent) if lease.monthly_rent else None,
                'lease_start_date': lease.lease_start_date.isoformat() if lease.lease_start_date else None,
                'lease_end_date':   lease.lease_end_date.isoformat() if lease.lease_end_date else None,
                'status':           lease.status,
                'status_display':   lease.get_status_display(),
                'status_color':     lease.get_status_color(),
                'is_active':        lease.is_active,
                'is_expired':       lease.is_expired,
                'is_renewal':       lease.is_renewal,
                'created_at':       lease.created_at.isoformat(),
                'created_by':       lease.created_by.email if lease.created_by else None,
                'documents':        docs,
            })
        return JsonResponse({'success': True,
                             'client': {'id': client.id, 'name': client.pOwner, 'address': client.pAddress},
                             'leases': leases_data})
    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


def download_lease_document(request, document_id):
    try:
        lease_doc = LeaseDocument.objects.select_related('lease').get(id=document_id)
        if not lease_doc.file_path:
            return HttpResponse(
                f'<p>Document has no file path. '
                f'<a href="/lease-manager/lease/{lease_doc.lease.id}/">Go back</a> and click '
                f'"Regenerate Documents" to rebuild the PDFs.</p>', status=404,
                content_type='text/html'
            )
        full_path = os.path.join(settings.MEDIA_ROOT, lease_doc.file_path)
        if not os.path.exists(full_path):
            return HttpResponse(
                f'<p>PDF file not found on server (<code>{lease_doc.file_path}</code>). '
                f'<a href="/lease-manager/lease/{lease_doc.lease.id}/">Go back</a> and click '
                f'"Regenerate Documents" to rebuild it.</p>', status=404,
                content_type='text/html'
            )
        LeaseActivity.objects.create(lease=lease_doc.lease, activity_type='downloaded',
                                     description=f'Downloaded {lease_doc.document_name}',
                                     performed_by=request.user if request.user.is_authenticated else None)
        with open(full_path, 'rb') as f:
            content = f.read()
        ct, _ = mimetypes.guess_type(full_path)
        resp = HttpResponse(content, content_type=ct or 'application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="{lease_doc.document_name}.pdf"'
        return resp
    except LeaseDocument.DoesNotExist:
        return HttpResponse('Document not found', status=404)
    except Exception as exc:
        return HttpResponse(f'Error: {exc}', status=500)


def view_lease_document(request, document_id):
    try:
        lease_doc = LeaseDocument.objects.select_related('lease').get(id=document_id)
        if not lease_doc.file_path:
            return HttpResponse(
                f'<p>Document has no file path. '
                f'<a href="/lease-manager/lease/{lease_doc.lease.id}/">Go back</a> and click '
                f'"Regenerate Documents".</p>', status=404, content_type='text/html'
            )
        full_path = os.path.join(settings.MEDIA_ROOT, lease_doc.file_path)
        if not os.path.exists(full_path):
            return HttpResponse(
                f'<p>PDF not found on server. '
                f'<a href="/lease-manager/lease/{lease_doc.lease.id}/">Go back</a> and click '
                f'"Regenerate Documents" to rebuild it.</p>', status=404, content_type='text/html'
            )
        LeaseActivity.objects.create(lease=lease_doc.lease, activity_type='viewed',
                                     description=f'Viewed {lease_doc.document_name}',
                                     performed_by=request.user if request.user.is_authenticated else None)
        with open(full_path, 'rb') as f:
            content = f.read()
        ct, _ = mimetypes.guess_type(full_path)
        resp = HttpResponse(content, content_type=ct or 'application/pdf')
        resp['Content-Disposition'] = f'inline; filename="{lease_doc.document_name}.pdf"'
        return resp
    except LeaseDocument.DoesNotExist:
        return HttpResponse('Document not found', status=404)
    except Exception as exc:
        return HttpResponse(f'Error: {exc}', status=500)


def add_lease_note(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data     = json.loads(request.body)
        lease_id = data.get('lease_id')
        note     = data.get('note', '').strip()
        if not lease_id or not note:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        lease    = Lease.objects.get(id=lease_id)
        ts       = timezone.now().strftime('%Y-%m-%d %H:%M')
        user_name = request.user.email if request.user.is_authenticated else 'Anonymous'
        new_note = f'[{ts}] {user_name}: {note}'
        lease.notes = f'{lease.notes}\n\n{new_note}' if lease.notes else new_note
        lease.save()
        LeaseActivity.objects.create(lease=lease, activity_type='note_added',
                                     description=f'Note added: {note[:100]}',
                                     performed_by=request.user if request.user.is_authenticated else None)
        return JsonResponse({'success': True, 'note': new_note})
    except Lease.DoesNotExist:
        return JsonResponse({'error': 'Lease not found'}, status=404)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


def lease_activity_feed(request):
    page       = int(request.GET.get('page', 1))
    per_page   = int(request.GET.get('per_page', 20))
    client_filter = request.GET.get('client', '')
    offset     = (page - 1) * per_page
    query      = LeaseActivity.objects.select_related('lease', 'lease__client', 'performed_by')
    if client_filter:
        query  = query.filter(lease__client__id=client_filter)
    total_count = query.count()
    activities  = query.order_by('-created_at')[offset:offset + per_page]
    activity_data = [{
        'id':                   str(a.id),
        'activity_type':        a.activity_type,
        'activity_type_display': a.get_activity_type_display(),
        'description':          a.description,
        'client_name':          a.lease.client.pOwner if a.lease else 'Unknown',
        'client_id':            a.lease.client.id if a.lease else None,
        'lease_id':             str(a.lease.id) if a.lease else None,
        'performed_by':         a.performed_by.email if a.performed_by else 'System',
        'created_at':           a.created_at.isoformat(),
        'time_ago':             _get_time_ago(a.created_at),
    } for a in activities]
    return JsonResponse({'success': True, 'activities': activity_data,
                         'total_count': total_count, 'page': page,
                         'per_page': per_page, 'has_more': offset + per_page < total_count})


def _get_time_ago(dt):
    diff = timezone.now() - dt
    if diff.days > 30:     return dt.strftime('%b %d, %Y')
    if diff.days > 0:      return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    if diff.seconds > 3600:
        h = diff.seconds // 3600
        return f"{h} hour{'s' if h > 1 else ''} ago"
    if diff.seconds > 60:
        m = diff.seconds // 60
        return f"{m} minute{'s' if m > 1 else ''} ago"
    return 'Just now'


def save_landlord(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            landlord_data = {
                'full_name':               request.POST.get('full_name'),
                'address':                 request.POST.get('address'),
                'city':                    request.POST.get('city'),
                'state':                   request.POST.get('state'),
                'zip_code':                request.POST.get('zip_code'),
                'phone':                   request.POST.get('phone'),
                'email':                   request.POST.get('email'),
                'property_address':        request.POST.get('property_address'),
                'property_city':           request.POST.get('property_city'),
                'property_state':          request.POST.get('property_state'),
                'property_zip':            request.POST.get('property_zip'),
                'term_start_date':         request.POST.get('term_start_date'),
                'term_end_date':           request.POST.get('term_end_date'),
                'default_rent_amount':     request.POST.get('default_rent_amount', 0),
                'default_security_deposit': request.POST.get('default_security_deposit', 0),
                'default_rent_due_day':    request.POST.get('default_rent_due_day', 1),
                'default_late_fee':        request.POST.get('default_late_fee', 0),
                'default_late_fee_start_day': request.POST.get('default_late_fee_start_day', 5),
                'default_eviction_day':    request.POST.get('default_eviction_day', 10),
                'default_nsf_fee':         request.POST.get('default_nsf_fee', 0),
                'default_max_occupants':   request.POST.get('default_max_occupants', 10),
                'default_parking_spaces':  request.POST.get('default_parking_spaces', 2),
                'default_parking_fee':     request.POST.get('default_parking_fee', 0),
                'default_inspection_fee':  request.POST.get('default_inspection_fee', 300.00),
                'bedrooms':                request.POST.get('bedrooms', 1),
                'rental_months':           request.POST.get('rental_months'),
                'contact_person_1':        request.POST.get('contact_person_1'),
                'contact_person_2':        request.POST.get('contact_person_2'),
                'contact_phone':           request.POST.get('contact_phone'),
                'contact_email':           request.POST.get('contact_email'),
                'real_estate_company':     request.POST.get('real_estate_company'),
                'company_mailing_address': request.POST.get('company_mailing_address'),
                'company_city':            request.POST.get('company_city'),
                'company_state':           request.POST.get('company_state'),
                'company_zip':             request.POST.get('company_zip'),
                'company_contact_person':  request.POST.get('company_contact_person'),
                'company_phone':           request.POST.get('company_phone'),
                'company_email':           request.POST.get('company_email'),
                'broker_name':             request.POST.get('broker_name'),
                'broker_phone':            request.POST.get('broker_phone'),
                'broker_email':            request.POST.get('broker_email'),
            }
            for f in ('term_start_date', 'term_end_date'):
                if landlord_data[f]:
                    landlord_data[f] = parse_date(landlord_data[f])
            for f in landlord_data:
                if landlord_data[f] == '':
                    landlord_data[f] = None
            required = ['full_name', 'address', 'city', 'state', 'zip_code', 'phone',
                        'property_address', 'property_city', 'property_state', 'property_zip']
            missing = [f for f in required if not landlord_data.get(f)]
            if missing:
                return JsonResponse({'success': False, 'error': f'Missing: {", ".join(missing)}'})
            decimal_fields = ['default_rent_amount', 'default_security_deposit', 'default_late_fee',
                              'default_nsf_fee', 'default_inspection_fee']
            int_fields = ['default_rent_due_day', 'default_late_fee_start_day', 'default_eviction_day',
                          'default_max_occupants', 'default_parking_spaces', 'default_parking_fee']
            for f in decimal_fields:
                if landlord_data[f] is not None:
                    landlord_data[f] = float(landlord_data[f])
            for f in int_fields:
                if landlord_data[f] is not None:
                    landlord_data[f] = int(landlord_data[f])
            landlord, created = Landlord.objects.update_or_create(
                property_address=landlord_data['property_address'], defaults=landlord_data,
            )
            return JsonResponse({'success': True, 'created': created, 'landlord_id': landlord.id})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc), 'type': type(exc).__name__})
    return JsonResponse({'success': False, 'error': 'Invalid request'})


# ──────────────────────────────────────────────────────────────────────────────
# ALE WORKFLOW TASK TRACKING
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def update_lease_task(request, task_id):
    """
    Mark a lease task as complete. Mobile-friendly endpoint.
    Called from claim detail page when user checks off a task.
    """
    from docsAppR.models import LeaseTask

    task = get_object_or_404(LeaseTask, id=task_id)
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        is_completed = data.get('is_completed', False)
        notes = (data.get('notes') or '').strip()

        task.is_completed = is_completed
        task.notes = notes
        if is_completed:
            task.completed_by = request.user
            task.completed_at = timezone.now()
        else:
            task.completed_by = None
            task.completed_at = None
        task.save()

        # Log activity
        try:
            from docsAppR.models import log_activity
            action = f'Lease task {"completed" if is_completed else "uncompleted"}: {task.get_task_type_display()}'
            log_activity(
                'other', action,
                user=request.user,
                client=task.lease.client,
                lease=task.lease,
                **{'lease_task_id': str(task.id), 'is_completed': is_completed}
            )
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'task': {
                'id': str(task.id),
                'task_type': task.task_type,
                'is_completed': task.is_completed,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            }
        })
    except Exception as exc:
        logger.error('update_lease_task: %s', exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)
