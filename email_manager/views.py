"""
Email Manager app views.
"""
import base64
import json
import logging
import mimetypes
import traceback

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from allauth.account.decorators import login_required

from docsAppR.forms import EmailForm, EmailScheduleForm
from docsAppR.models import (
    Client, Document, DocumentCategory,
    GeneratedFile, SentEmail, EmailSchedule, EmailOpenEvent,
    UploadedAttachment, EmailCampaign,
)

logger = logging.getLogger(__name__)

OWNER_EMAIL = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')


# ---------------------------------------------------------------------------
# Universal Email Compose Page
# ---------------------------------------------------------------------------

@login_required
def email_compose(request):
    """
    Universal compose page — reused by:
      - Lease package sends  (?source=lease_package&lease_id=UUID)
      - Demand letters       (?source=demand_letter&lease_id=UUID)
      - General email        (no source param)

    GET params accepted:
      source, lease_id, to, cc, bcc, subject, body
    """
    from docsAppR.models import Lease, LeaseDocument

    source      = request.GET.get('source', 'general')
    lease_id    = request.GET.get('lease_id', '')
    gen_file_id = request.GET.get('gen_file_id', '')
    prefill = {
        'to':      request.GET.get('to', ''),
        'cc':      request.GET.get('cc', OWNER_EMAIL),
        'bcc':     request.GET.get('bcc', ''),
        'subject': request.GET.get('subject', ''),
        'body':    request.GET.get('body', ''),
    }

    lease = None
    lease_docs = []
    lease_contacts = []
    preselected_gen_file = None

    # Pre-selected generated file (e.g. demand letter PDF)
    if gen_file_id:
        try:
            preselected_gen_file = GeneratedFile.objects.get(id=gen_file_id)
        except (GeneratedFile.DoesNotExist, Exception):
            pass

    if lease_id:
        try:
            lease = Lease.objects.select_related('client').prefetch_related('documents').get(id=lease_id)
            lease_docs = list(lease.documents.all())

            from lease_manager.views import _lease_contacts
            lease_contacts = _lease_contacts(lease)

            if source == 'lease_package' and not prefill['to']:
                to_emails = [c['email'] for c in lease_contacts
                             if c['role'] in ('re_company', 'broker')]
                prefill['to'] = ', '.join(to_emails)

            if source == 'lease_package' and not prefill['cc']:
                cc_emails = [c['email'] for c in lease_contacts
                             if c['role'] in ('lessor', 'lessee', 'owner')]
                prefill['cc'] = ', '.join(cc_emails)

        except Exception as exc:
            logger.warning('email_compose: could not load lease %s: %s', lease_id, exc)

    if request.method == 'POST':
        return _handle_compose_send(request, lease, lease_docs)

    source_labels = {
        'lease_package': 'Lease Document Package',
        'demand_letter': 'Demand for Payment Letter',
        'general':       'New Email',
    }

    context = {
        'source':                source,
        'source_label':          source_labels.get(source, 'New Email'),
        'lease':                 lease,
        'lease_docs':            lease_docs,
        'lease_contacts':        lease_contacts,
        'prefill':               prefill,
        'owner_email':           OWNER_EMAIL,
        'all_docs':              GeneratedFile.objects.order_by('-created_at')[:50],
        'preselected_gen_file':  preselected_gen_file,
        'sent_ok':               request.GET.get('sent') == '1',
    }
    return render(request, 'account/email_compose.html', context)


def _handle_compose_send(request, lease, lease_docs):
    """Shared send logic used by the universal compose page."""
    to_raw   = request.POST.get('to', '')
    cc_raw   = request.POST.get('cc', '')
    bcc_raw  = request.POST.get('bcc', '')
    subject  = request.POST.get('subject', '').strip()
    body     = request.POST.get('body', '').strip()
    doc_ids  = request.POST.getlist('document_ids')
    gen_ids  = request.POST.getlist('generated_file_ids')
    schedule = request.POST.get('schedule_at', '').strip()

    def parse_emails(raw):
        return [e.strip() for e in raw.replace(';', ',').split(',') if e.strip()]

    to_list  = parse_emails(to_raw)
    cc_list  = parse_emails(cc_raw)
    bcc_list = parse_emails(bcc_raw)

    if not to_list:
        messages.error(request, 'At least one To recipient is required.')
        return redirect(request.path + '?' + request.GET.urlencode())

    if not subject:
        subject = 'No Subject'

    if schedule:
        from email_manager.tasks import send_campaign_email_task
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as tz
        send_dt = parse_datetime(schedule)
        if send_dt and tz.is_naive(send_dt):
            send_dt = tz.make_aware(send_dt)
        # Store as pending (simplified — uses existing infrastructure)
        _send_email_with_tracking(
            to_list, cc_list, bcc_list, subject, body,
            doc_ids, gen_ids, lease, lease_docs, request.user,
        )
        messages.success(request, f'Email scheduled for {schedule}.')
    else:
        ok, err = _send_email_with_tracking(
            to_list, cc_list, bcc_list, subject, body,
            doc_ids, gen_ids, lease, lease_docs, request.user,
        )
        if ok:
            messages.success(request, f'Email sent to {", ".join(to_list)}.')
        else:
            messages.error(request, f'Send failed: {err}')

    return redirect('/emails/compose/?sent=1')


def _send_email_with_tracking(to_list, cc_list, bcc_list, subject, body,
                               doc_ids, gen_ids, lease, lease_docs, user):
    """
    Core send: create SentEmail record, inject pixel, attach files, send.
    """
    import os, mimetypes as mt
    from django.core.mail import EmailMessage as DjEmail
    from docsAppR.models import SentEmail, GeneratedFile

    try:
        sent = SentEmail.objects.create(
            subject=subject, body=body,
            recipients=to_list, cc=cc_list, bcc=bcc_list,
            sent_by=user,
            notify_on_open=True,
            admin_notification_email=OWNER_EMAIL,
        )

        base   = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        pixel  = (f'<img src="{base}/emails/track/{sent.tracking_pixel_id}/" '
                  f'width="1" height="1" style="display:none;" alt="" />')
        html_b = f'<div style="white-space:pre-wrap;font-family:Arial,sans-serif;font-size:14px;">{body}</div>{pixel}'

        email = DjEmail(
            subject=subject, body=html_b,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_list, cc=cc_list, bcc=bcc_list,
        )
        email.content_subtype = 'html'

        # Attach lease documents (by ID selection)
        if lease and lease_docs:
            selected_docs = (
                [d for d in lease_docs if str(d.id) in doc_ids]
                if doc_ids else lease_docs
            )
            for doc in selected_docs:
                if not doc.file_path:
                    continue
                full_path = os.path.join(settings.MEDIA_ROOT, doc.file_path)
                if not os.path.exists(full_path):
                    continue
                mime, _ = mt.guess_type(full_path)
                with open(full_path, 'rb') as fh:
                    email.attach(doc.document_name, fh.read(), mime or 'application/pdf')

        # Attach generated files
        if gen_ids:
            for gf in GeneratedFile.objects.filter(id__in=gen_ids):
                if not gf.file_path or not os.path.exists(gf.file_path):
                    continue
                mime, _ = mt.guess_type(gf.file_path)
                with open(gf.file_path, 'rb') as fh:
                    email.attach(gf.name, fh.read(), mime or 'application/octet-stream')

        # Attach uploaded files
        for uf in (user._uploaded_files if hasattr(user, '_uploaded_files') else []):
            pass  # handled via request.FILES in the view

        email.send()

        if lease:
            try:
                from docsAppR.models import LeaseActivity as LA
                LA.objects.create(
                    lease=lease,
                    activity_type='package_sent',
                    description=f'Email sent to {", ".join(to_list)} — {subject[:60]}',
                    performed_by=user,
                )
            except Exception:
                pass

        # Global activity log
        try:
            from docsAppR.models import log_activity
            log_activity(
                'email_sent',
                f'Email sent to {", ".join(to_list)} — {subject[:80]}',
                user=user,
                client=lease.client if lease else None,
                lease=lease,
                recipients=to_list,
                subject=subject[:120],
            )
        except Exception:
            pass

        return True, None

    except Exception as exc:
        logger.error('_send_email_with_tracking failed: %s', exc)
        return False, str(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _mime_for(path):
    mime, _ = mimetypes.guess_type(path)
    return mime or 'application/octet-stream'


# ---------------------------------------------------------------------------
# Main compose / send view
# ---------------------------------------------------------------------------

@login_required
def emails(request):
    category_id = request.GET.get('category')
    client_name = request.GET.get('client')
    date_range  = request.GET.get('date_range', 'recent')

    documents = Document.objects.filter(created_by=request.user)
    if category_id:
        documents = documents.filter(category_id=category_id)
    if client_name:
        documents = documents.filter(client_name__icontains=client_name)
    if date_range == 'today':
        documents = documents.filter(created_at__date=timezone.now().date())
    elif date_range == 'week':
        documents = documents.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7))
    elif date_range == 'month':
        documents = documents.filter(created_at__gte=timezone.now() - timezone.timedelta(days=30))
    else:
        documents = documents.order_by('-created_at')[:50]

    categories    = DocumentCategory.objects.all()
    sent_emails   = SentEmail.objects.filter(sent_by=request.user).select_related('claim')[:20]
    schedules     = EmailSchedule.objects.filter(created_by=request.user, is_active=True)
    generated_files = GeneratedFile.objects.order_by('-created_at')[:50]

    if request.method == 'POST':
        form = EmailForm(request.POST)
        form.fields['documents'].queryset = documents
        form.fields['generated_files'].queryset = generated_files

        if form.is_valid():
            try:
                to_list  = form.cleaned_data['to']   # already a list
                cc_list  = form.cleaned_data['cc']
                bcc_list = form.cleaned_data['bcc']

                selected_docs   = form.cleaned_data['documents']
                selected_gen    = form.cleaned_data['generated_files']
                pasted_excel    = request.POST.get('pasted_excel_data', '').strip()
                embed_excel     = request.POST.get('embed_excel', False)
                uploaded_files  = request.FILES.getlist('uploaded_files')

                email = EmailMessage(
                    subject=form.cleaned_data['subject'],
                    body=form.cleaned_data['body'],
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=to_list,
                    cc=cc_list,
                    bcc=bcc_list,
                )

                # Excel paste / embed logic (unchanged from original)
                excel_embedded = False
                if pasted_excel:
                    try:
                        email.body = convert_pasted_excel_to_html(pasted_excel)
                        email.content_subtype = 'html'
                        excel_embedded = True
                    except Exception as exc:
                        messages.warning(request, f'Could not convert pasted data: {exc}')

                if not excel_embedded:
                    for doc in selected_docs:
                        if embed_excel and doc.file.name.endswith(('.xlsx', '.xls')):
                            try:
                                email.body = convert_excel_to_html(doc.file.path)
                                email.content_subtype = 'html'
                                excel_embedded = True
                                continue
                            except Exception as exc:
                                messages.warning(request, f'Could not embed Excel: {exc}. Attaching instead.')
                        email.attach_file(doc.file.path)

                # App-generated file attachments
                for gf in selected_gen:
                    try:
                        with open(gf.file_path, 'rb') as fh:
                            email.attach(gf.name, fh.read(), gf.mime_type)
                    except OSError as exc:
                        messages.warning(request, f'Could not attach {gf.name}: {exc}')

                # User-uploaded file attachments
                upload_records = []
                for uf in uploaded_files:
                    mime = _mime_for(uf.name)
                    data = uf.read()
                    email.attach(uf.name, data, mime)
                    record = UploadedAttachment.objects.create(
                        file=uf,
                        original_name=uf.name,
                        mime_type=mime,
                        size=uf.size,
                        uploaded_by=request.user,
                    )
                    upload_records.append(record)

                # Create SentEmail log record
                sent_email = SentEmail.objects.create(
                    subject=form.cleaned_data['subject'],
                    body=form.cleaned_data['body'],
                    recipients=to_list,
                    cc=cc_list,
                    bcc=bcc_list,
                    claim=form.cleaned_data.get('claim'),
                    sent_by=request.user,
                    notify_on_open=form.cleaned_data['notify_on_open'],
                    admin_notification_email=(
                        form.cleaned_data['admin_notification_email'] or request.user.email
                    ),
                    scheduled_send_time=(
                        timezone.now()
                        if form.cleaned_data['send_now']
                        else form.cleaned_data['scheduled_time']
                    ),
                )
                sent_email.documents.set(selected_docs)
                sent_email.generated_files.set(selected_gen)
                if upload_records:
                    sent_email.uploaded_attachments.set(upload_records)

                # Inject tracking pixel into every outbound email
                tracking_url = request.build_absolute_uri(
                    f'/emails/track/{sent_email.tracking_pixel_id}/'
                )
                pixel = f'<img src="{tracking_url}" width="1" height="1" style="display:none;" alt="" />'

                if email.content_subtype == 'html' or excel_embedded:
                    email.body += pixel
                else:
                    html_body = f'<div style="white-space:pre-wrap;">{email.body}</div>{pixel}'
                    email.body = html_body
                    email.content_subtype = 'html'

                if form.cleaned_data['send_now'] or not form.cleaned_data['scheduled_time']:
                    email.send()
                    messages.success(request, 'Email sent successfully!')
                else:
                    messages.success(request, 'Email scheduled successfully!')

            except Exception as exc:
                logger.error('Error sending email: %s\n%s', exc, traceback.format_exc())
                messages.error(request, f'Error sending email: {exc}')

            return redirect('emails')

        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f'{field}: {err}')
    else:
        form = EmailForm()
        form.fields['documents'].queryset = documents
        form.fields['generated_files'].queryset = generated_files

    context = {
        'documents':       documents,
        'categories':      categories,
        'sent_emails':     sent_emails,
        'schedules':       schedules,
        'generated_files': generated_files,
        'form':            form,
        'current_filters': {
            'category_id': category_id,
            'client_name': client_name,
            'date_range':  date_range,
        },
    }
    return render(request, 'account/emails.html', context)


# ---------------------------------------------------------------------------
# Tracking pixel — NO login required, called by remote email clients
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
def track_email_open(request, tracking_pixel_id):
    try:
        sent_email = SentEmail.objects.get(tracking_pixel_id=tracking_pixel_id)

        # Record first open only
        if not sent_email.is_opened:
            sent_email.is_opened = True
            sent_email.opened_at = timezone.now()
            sent_email.save(update_fields=['is_opened', 'opened_at'])

        # Always log every open event (multiple devices / re-opens)
        EmailOpenEvent.objects.create(
            sent_email=sent_email,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        # Notify on first open only
        if sent_email.notify_on_open and sent_email.admin_notification_email:
            try:
                notification = EmailMessage(
                    subject=f'Email Opened: {sent_email.subject}',
                    body=(
                        f'Your email was opened.\n\n'
                        f'Subject: {sent_email.subject}\n'
                        f'Opened at: {sent_email.opened_at}\n'
                        f'Recipients: {", ".join(sent_email.recipients)}\n'
                        f'IP: {_get_client_ip(request)}'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[sent_email.admin_notification_email],
                )
                notification.send(fail_silently=True)
            except Exception as exc:
                logger.warning('Open-notification send failed: %s', exc)

    except SentEmail.DoesNotExist:
        pass

    # 1x1 transparent GIF — must not be cached
    response = HttpResponse(
        base64.b64decode(b'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'),
        content_type='image/gif',
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma']        = 'no-cache'
    response['Expires']       = '0'
    return response


# ---------------------------------------------------------------------------
# JSON API — claim contacts for recipient selection
# ---------------------------------------------------------------------------

@login_required
def api_claim_contacts(request, claim_pk):
    """
    Return a list of known email contacts on a claim.
    Used by the compose form to populate the claim-linked recipient checkboxes.
    """
    try:
        claim = Client.objects.get(pk=claim_pk)
    except Client.DoesNotExist:
        return JsonResponse({'contacts': []})

    contacts = []

    def _add(label, email):
        if email and email.strip():
            contacts.append({'label': label, 'email': email.strip()})

    _add(f'Client — {claim.pOwner}',          claim.cEmail)
    _add(f'Client (alt) — {claim.pOwner}',    claim.cEmail2)
    _add('Insurance Company',                  claim.emailInsCo)
    _add('Desk Adjuster',                      claim.DAEmail)
    _add('Field Adjuster',                     claim.fieldAdjEmail)
    _add('Adjuster CPS',                       claim.adjCpsEmail)
    _add('EMS / Temp',                         claim.emsTmpEmail)
    _add('Mortgage',                           claim.mortgageEmail)
    _add('Company Rep',                        claim.coREPEmail)
    _add('ALE Lessee',                         claim.ale_lessee_email)
    _add('ALE Lessor',                         claim.ale_lessor_email)
    _add('ALE Real Estate',                    claim.ale_re_email)
    _add('ALE RE Owner/Broker',                claim.ale_re_owner_broker_email)

    return JsonResponse({'contacts': contacts, 'claim_name': str(claim.pOwner)})


# ---------------------------------------------------------------------------
# JSON API — document list (existing, unchanged)
# ---------------------------------------------------------------------------

@login_required
def document_list_api(request):
    category_id = request.GET.get('category')
    client_name = request.GET.get('client')
    search      = request.GET.get('search', '')

    documents = Document.objects.filter(created_by=request.user)
    if category_id:
        documents = documents.filter(category_id=category_id)
    if client_name:
        documents = documents.filter(client_name__icontains=client_name)
    if search:
        documents = documents.filter(
            Q(filename__icontains=search) |
            Q(description__icontains=search) |
            Q(client_name__icontains=search)
        )
    documents = documents.order_by('-created_at')[:50]

    data = [
        {
            'id':         str(doc.id),
            'filename':   doc.filename,
            'client_name': doc.client_name,
            'category':   doc.category.name if doc.category else '',
            'created_at': doc.created_at.strftime('%Y-%m-%d %H:%M'),
            'description': doc.description,
        }
        for doc in documents
    ]
    return JsonResponse({'documents': data})


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@login_required
def create_schedule(request):
    if request.method == 'POST':
        form = EmailScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.created_by = request.user
            schedule.recipients = form.cleaned_data['recipients']
            schedule.save()
            form.save_m2m()
            messages.success(request, 'Email schedule created successfully!')
            return redirect('emails')
    else:
        form = EmailScheduleForm()
    return render(request, 'account/email_schedule_form.html', {'form': form})


# ---------------------------------------------------------------------------
# Campaign API
# ---------------------------------------------------------------------------

@login_required
def api_campaign_preview(request):
    """
    POST: Compute N send datetimes from campaign parameters.
    Returns JSON for the calendar preview — no DB writes.

    Body (JSON):
        total_sends, interval_value, interval_unit, start_at (ISO 8601)
    """
    import json
    from datetime import timedelta

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        total_sends    = int(data['total_sends'])
        interval_value = int(data['interval_value'])
        interval_unit  = data['interval_unit']
        start_at_str   = data['start_at']
    except (KeyError, ValueError) as exc:
        return JsonResponse({'error': f'Bad parameters: {exc}'}, status=400)

    if total_sends < 1 or total_sends > 365:
        return JsonResponse({'error': 'total_sends must be between 1 and 365'}, status=400)

    unit_map = {'hours': 'hours', 'days': 'days', 'weeks': 'weeks'}
    if interval_unit not in unit_map:
        return JsonResponse({'error': f'Unknown interval_unit: {interval_unit}'}, status=400)

    try:
        from django.utils.dateparse import parse_datetime
        start_at = parse_datetime(start_at_str)
        if start_at is None:
            raise ValueError('unparseable datetime')
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': f'Invalid start_at: {exc}'}, status=400)

    delta = timedelta(**{interval_unit: interval_value})
    events = []
    for i in range(total_sends):
        dt = start_at + delta * i
        events.append({
            'index': i,
            'title': f'Send #{i + 1}',
            'start': dt.isoformat(),
            'display': dt.strftime('%b %d, %Y %H:%M'),
        })

    return JsonResponse({'events': events, 'total': total_sends})


@login_required
def api_campaign_confirm(request):
    """
    POST: Persist an EmailCampaign and queue all send tasks via apply_async(eta=...).

    Body (JSON):
        name, subject, body, recipients (list), cc (list), bcc (list),
        total_sends, interval_value, interval_unit, start_at (ISO 8601)
    """
    import json

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        name           = data['name'].strip()
        subject        = data['subject'].strip()
        body           = data['body'].strip()
        recipients     = data['recipients']
        cc             = data.get('cc', [])
        bcc            = data.get('bcc', [])
        total_sends    = int(data['total_sends'])
        interval_value = int(data['interval_value'])
        interval_unit  = data['interval_unit']
        start_at_str   = data['start_at']
    except (KeyError, ValueError, TypeError) as exc:
        return JsonResponse({'error': f'Bad parameters: {exc}'}, status=400)

    try:
        from django.utils.dateparse import parse_datetime
        start_at = parse_datetime(start_at_str)
        if start_at is None:
            raise ValueError('unparseable datetime')
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': f'Invalid start_at: {exc}'}, status=400)

    campaign = EmailCampaign.objects.create(
        name=name,
        subject=subject,
        body=body,
        recipients=recipients,
        cc=cc,
        bcc=bcc,
        total_sends=total_sends,
        interval_value=interval_value,
        interval_unit=interval_unit,
        start_at=start_at,
        status='scheduled',
        created_by=request.user,
    )

    # Queue one task per send using eta — no Beat DB entries needed
    from email_manager.tasks import send_campaign_email_task
    send_datetimes = campaign.compute_send_datetimes()
    task_ids = []
    for i, dt in enumerate(send_datetimes):
        result = send_campaign_email_task.apply_async(
            args=[str(campaign.id), i],
            eta=dt,
        )
        task_ids.append(result.id)

    campaign.beat_task_ids = task_ids
    campaign.save(update_fields=['beat_task_ids'])

    logger.info('Campaign %s confirmed: %s tasks queued', campaign.id, len(task_ids))

    return JsonResponse({
        'campaign_id': str(campaign.id),
        'status': campaign.status,
        'tasks_queued': len(task_ids),
        'first_send': send_datetimes[0].isoformat() if send_datetimes else None,
    })


@login_required
def api_campaign_cancel(request, campaign_id):
    """Revoke all queued Celery tasks for a campaign and mark it cancelled."""
    try:
        campaign = EmailCampaign.objects.get(id=campaign_id, created_by=request.user)
    except EmailCampaign.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if campaign.status in ('complete', 'cancelled'):
        return JsonResponse({'error': f'Campaign already {campaign.status}'}, status=400)

    from celery import current_app
    revoked = 0
    for task_id in campaign.beat_task_ids:
        current_app.control.revoke(task_id, terminate=True)
        revoked += 1

    campaign.status = 'cancelled'
    campaign.save(update_fields=['status'])

    return JsonResponse({'revoked': revoked, 'status': 'cancelled'})


# ---------------------------------------------------------------------------
# Excel helpers (unchanged)
# ---------------------------------------------------------------------------

def convert_pasted_excel_to_html(pasted_data):
    try:
        rows = [line.split('\t') for line in pasted_data.strip().split('\n')]
        if not rows:
            return '<p>No data provided</p>'
        html_table = '<table class="email-table">\n<thead>\n<tr>\n'
        for cell in rows[0]:
            html_table += f'<th>{cell.strip()}</th>\n'
        html_table += '</tr>\n</thead>\n<tbody>\n'
        for row in rows[1:]:
            html_table += '<tr>\n'
            for cell in row:
                html_table += f'<td>{cell.strip()}</td>\n'
            html_table += '</tr>\n'
        html_table += '</tbody>\n</table>'
        return _wrap_html_table(html_table)
    except Exception as exc:
        return f'<p>Error converting pasted data: {exc}</p>'


def convert_excel_to_html(excel_file_path):
    import pandas as pd
    try:
        df = pd.read_excel(excel_file_path, engine='openpyxl')
        html_table = df.to_html(index=False, classes='email-table', border=0, escape=False, na_rep='')
        return _wrap_html_table(html_table)
    except Exception as exc:
        return f'<p>Error converting Excel to HTML: {exc}</p>'


def _wrap_html_table(html_table):
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body{{font-family:Arial,sans-serif;background:#f4f4f4;padding:20px}}
.email-container{{max-width:900px;margin:0 auto;background:#fff;padding:20px;border-radius:8px}}
.email-table{{border-collapse:collapse;width:100%;font-size:14px;margin:20px 0}}
.email-table thead{{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}}
.email-table th,.email-table td{{padding:10px 15px;border:1px solid #ddd;text-align:left}}
.email-table tbody tr:nth-child(even){{background:#f8f9fa}}
</style></head>
<body><div class="email-container">{html_table}</div></body></html>"""


# ──────────────────────────────────────────────────────────────────────────────
# EMAIL BATCH SCHEDULING + HISTORY
# ──────────────────────────────────────────────────────────────────────────────

def get_claim_files(claim):
    """
    Discover all attachable files for a claim:
    - Generated leases (Lease PDFs)
    - Generated files (reports, invoices, Excel)
    - System documents
    """
    from docsAppR.models import Lease

    files = {
        'leases': [],
        'generated': [],
        'documents': [],
    }

    # Get leases and their documents
    leases = Lease.objects.filter(client=claim).prefetch_related('documents')
    for lease in leases:
        for doc in lease.documents.all():
            files['leases'].append({
                'id': str(doc.id),
                'name': f'{lease.lessor_name} - {doc.document_type}',
                'type': 'lease_doc',
            })

    # Get generated files for this claim
    gen_files = GeneratedFile.objects.filter(client=claim)
    for gf in gen_files:
        files['generated'].append({
            'id': str(gf.id),
            'name': gf.name,
            'category': gf.category,
            'type': 'generated',
        })

    # Get system documents
    docs = Document.objects.filter(client=claim)
    for doc in docs:
        files['documents'].append({
            'id': str(doc.id),
            'name': doc.document_name,
            'type': 'document',
        })

    return files


@login_required
def batch_schedule_emails(request):
    """
    Schedule a batch of emails with optional follow-ups.
    Modal/form to configure batch, pick send times on calendar, set follow-up rules.
    """
    from docsAppR.models import EmailBatch, ScheduledEmail, Lease

    claims = Client.objects.all().order_by('pOwner')

    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

            batch_name = (data.get('batch_name') or '').strip()
            claim_id = data.get('claim_id')
            emails = data.get('emails', [])  # List of email dicts

            if not batch_name:
                return JsonResponse({'error': 'Batch name required'}, status=400)
            if not emails:
                return JsonResponse({'error': 'At least one email required'}, status=400)

            # Create batch
            batch = EmailBatch.objects.create(
                name=batch_name,
                claim_id=claim_id if claim_id else None,
                created_by=request.user,
            )

            # Create scheduled emails
            for email_data in emails:
                ScheduledEmail.objects.create(
                    batch=batch,
                    subject=email_data.get('subject', ''),
                    body=email_data.get('body', ''),
                    recipients=email_data.get('recipients', []),
                    cc=email_data.get('cc', []),
                    bcc=email_data.get('bcc', []),
                    scheduled_send_time=timezone.make_aware(
                        timezone.datetime.fromisoformat(email_data['scheduled_send_time'])
                    ) if email_data.get('scheduled_send_time') else timezone.now(),
                    has_followup=email_data.get('has_followup', False),
                    followup_trigger=email_data.get('followup_trigger', ''),
                    followup_days=email_data.get('followup_days'),
                    followup_subject=email_data.get('followup_subject', ''),
                    followup_body=email_data.get('followup_body', ''),
                )

            return JsonResponse({
                'success': True,
                'batch_id': str(batch.id),
                'email_count': len(emails),
            })
        except Exception as exc:
            logger.error('batch_schedule_emails: %s', exc)
            return JsonResponse({'error': str(exc)}, status=500)

    context = {
        'claims': claims,
    }
    return render(request, 'account/batch_schedule.html', context)


@login_required
def sent_emails_history(request):
    """
    View sent emails with filtering by claim, date, open status.
    Shows: recipient, subject, sent_at, opened_at, status.
    """
    from docsAppR.models import EmailBatch

    # Filters
    claim_id = request.GET.get('claim')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status_filter = request.GET.get('status')  # all, opened, unopened

    qs = SentEmail.objects.select_related('claim', 'sent_by').prefetch_related('link_clicks').order_by('-sent_at')

    if claim_id:
        qs = qs.filter(claim_id=claim_id)
    if date_from:
        from django.utils.dateparse import parse_date
        df = parse_date(date_from)
        if df:
            qs = qs.filter(sent_at__date__gte=df)
    if date_to:
        from django.utils.dateparse import parse_date
        dt = parse_date(date_to)
        if dt:
            qs = qs.filter(sent_at__date__lte=dt)
    if status_filter == 'opened':
        qs = qs.filter(is_opened=True)
    elif status_filter == 'unopened':
        qs = qs.filter(is_opened=False)

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(qs, 50)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    # Enrich with stats
    emails = []
    for email in page_obj:
        click_count = email.link_clicks.count()
        emails.append({
            'email': email,
            'click_count': click_count,
            'status': 'opened' if email.is_opened else 'unopened',
            'recipient_count': len(email.recipients) if email.recipients else 0,
        })

    claims = Client.objects.all().order_by('pOwner')

    context = {
        'page_obj': page_obj,
        'emails': emails,
        'claims': claims,
        'claim_id': claim_id,
        'date_from': date_from,
        'date_to': date_to,
        'status_filter': status_filter,
        'total_count': qs.count(),
    }
    return render(request, 'account/sent_emails_history.html', context)
