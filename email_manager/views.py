"""
Email Manager app views.
"""
import base64
import json
import logging
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

from allauth.account.decorators import login_required

from docsAppR.forms import EmailForm, EmailScheduleForm
from docsAppR.models import Document, DocumentCategory, SentEmail, EmailSchedule, EmailOpenEvent

logger = logging.getLogger(__name__)


@login_required
@login_required
def emails(request):
    # Get filter parameters
    category_id = request.GET.get('category')
    client_name = request.GET.get('client')
    date_range = request.GET.get('date_range', 'recent')

    # Base queryset - use Document model
    documents = Document.objects.filter(created_by=request.user)

    # Apply filters
    if category_id:
        documents = documents.filter(category_id=category_id)
    if client_name:
        documents = documents.filter(client_name__icontains=client_name)

    # Date range filters
    if date_range == 'today':
        documents = documents.filter(created_at__date=timezone.now().date())
    elif date_range == 'week':
        week_ago = timezone.now() - timezone.timedelta(days=7)
        documents = documents.filter(created_at__gte=week_ago)
    elif date_range == 'month':
        month_ago = timezone.now() - timezone.timedelta(days=30)
        documents = documents.filter(created_at__gte=month_ago)
    else:  # recent - last 50
        documents = documents.order_by('-created_at')[:50]

    categories = DocumentCategory.objects.all()
    sent_emails = SentEmail.objects.filter(sent_by=request.user)[:20]
    schedules = EmailSchedule.objects.filter(created_by=request.user, is_active=True)

    if request.method == 'POST':
        form = EmailForm(request.POST)
        # Set queryset to user's documents
        form.fields['documents'].queryset = documents
        if form.is_valid():
            try:
                # Get selected documents
                selected_docs = form.cleaned_data['documents']
                # Recipients is already a list from clean_recipients()
                recipients = form.cleaned_data['recipients']

                # Check if user pasted Excel data
                pasted_excel_data = request.POST.get('pasted_excel_data', '').strip()

                # Check if user wants to embed Excel as HTML (from request POST)
                embed_excel = request.POST.get('embed_excel', False)

                # Create email
                email = EmailMessage(
                    subject=form.cleaned_data['subject'],
                    body=form.cleaned_data['body'],
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=recipients,
                )

                # Handle pasted Excel data (highest priority)
                excel_embedded = False
                if pasted_excel_data:
                    try:
                        # Convert pasted Excel data to HTML
                        excel_html = convert_pasted_excel_to_html(pasted_excel_data)
                        email.body = excel_html
                        email.content_subtype = "html"
                        excel_embedded = True
                        messages.success(request, 'Pasted Excel data converted to HTML email body.')
                    except Exception as e:
                        messages.warning(request, f'Could not convert pasted data: {str(e)}')

                # Handle Excel file embedding or attachment
                if not excel_embedded:
                    for doc in selected_docs:
                        # Check if document is Excel and user wants it embedded
                        if embed_excel and doc.file.name.endswith(('.xlsx', '.xls')):
                            try:
                                # Convert Excel to HTML and use as email body
                                excel_html = convert_excel_to_html(doc.file.path)
                                email.body = excel_html
                                email.content_subtype = "html"
                                excel_embedded = True
                                # Don't attach the Excel file if embedded
                                continue
                            except Exception as e:
                                messages.warning(request, f'Could not embed Excel as HTML: {str(e)}. Attaching instead.')

                        # Attach all other documents (or Excel if embedding failed)
                        email.attach_file(doc.file.path)

                # Create SentEmail record for tracking
                sent_email = SentEmail.objects.create(
                    subject=form.cleaned_data['subject'],
                    body=form.cleaned_data['body'],
                    recipients=recipients,
                    sent_by=request.user,
                    notify_on_open=form.cleaned_data['notify_on_open'],
                    admin_notification_email=form.cleaned_data['admin_notification_email'] or request.user.email,
                    scheduled_send_time=timezone.now() if form.cleaned_data['send_now'] else form.cleaned_data['scheduled_time']
                )
                sent_email.documents.set(selected_docs)

                # Add tracking pixel to email
                tracking_url = request.build_absolute_uri(
                    f'/emails/track/{sent_email.tracking_pixel_id}/'
                )

                if email.content_subtype == "html" or excel_embedded:
                    # Add tracking pixel to HTML email
                    email.body += f'<img src="{tracking_url}" width="1" height="1" />'
                else:
                    # Convert plain text to HTML with tracking pixel
                    html_body = f'<div style="white-space: pre-wrap;">{form.cleaned_data["body"]}</div>'
                    html_body += f'<img src="{tracking_url}" width="1" height="1" />'
                    email.body = html_body
                    email.content_subtype = "html"

                # Send email
                if form.cleaned_data['send_now'] or not form.cleaned_data['scheduled_time']:
                    email.send()
                    messages.success(request, 'Email sent successfully!')
                else:
                    # For scheduled emails, you'd typically use Celery
                    messages.success(request, 'Email scheduled successfully!')

            except Exception as e:
                error_details = traceback.format_exc()
                logger.error(f"Error sending email: {str(e)}\n{error_details}")
                messages.error(request, f'Error sending email: {str(e)}')

            return redirect('emails')
        else:
            # Form validation failed - show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = EmailForm()
        # Set queryset to user's documents for GET request
        form.fields['documents'].queryset = documents

    context = {
        'documents': documents,
        'categories': categories,
        'sent_emails': sent_emails,
        'schedules': schedules,
        'form': form,
        'current_filters': {
            'category_id': category_id,
            'client_name': client_name,
            'date_range': date_range,
        }
    }

    return render(request, 'account/emails.html', context)


def convert_pasted_excel_to_html(pasted_data):
    """
    Convert pasted Excel data (tab-separated values) to styled HTML table
    """
    try:
        # Split into rows
        rows = [line.split('\t') for line in pasted_data.strip().split('\n')]

        if not rows:
            return "<p>No data provided</p>"

        # Build HTML table
        html_table = "<table class='email-table'>\n"

        # First row as header
        html_table += "  <thead>\n    <tr>\n"
        for cell in rows[0]:
            html_table += f"      <th>{cell.strip()}</th>\n"
        html_table += "    </tr>\n  </thead>\n"

        # Rest as body
        html_table += "  <tbody>\n"
        for row in rows[1:]:
            html_table += "    <tr>\n"
            for cell in row:
                html_table += f"      <td>{cell.strip()}</td>\n"
            html_table += "    </tr>\n"
        html_table += "  </tbody>\n"
        html_table += "</table>"

        # Add professional CSS styling
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, Helvetica, sans-serif;
                    background-color: #f4f4f4;
                    padding: 20px;
                }}
                .email-container {{
                    max-width: 900px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .email-table {{
                    border-collapse: collapse;
                    width: 100%;
                    font-size: 14px;
                    margin: 20px 0;
                }}
                .email-table thead {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .email-table th {{
                    padding: 12px 15px;
                    text-align: left;
                    font-weight: 600;
                    border: 1px solid #ddd;
                }}
                .email-table td {{
                    padding: 10px 15px;
                    border: 1px solid #ddd;
                }}
                .email-table tbody tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                .email-table tbody tr:hover {{
                    background-color: #e9ecef;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                {html_table}
            </div>
        </body>
        </html>
        """

        return styled_html

    except Exception as e:
        return f"<p>Error converting pasted data to HTML: {str(e)}</p>"


def convert_excel_to_html(excel_file_path):
    """
    Convert Excel file to styled HTML table for email body
    """
    import pandas as pd

    try:
        # Read Excel file (first sheet by default)
        df = pd.read_excel(excel_file_path, engine='openpyxl')

        # Convert to HTML with styling
        html_table = df.to_html(
            index=False,
            classes='email-table',
            border=0,
            escape=False,
            na_rep=''
        )

        # Add professional CSS styling
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, Helvetica, sans-serif;
                    background-color: #f4f4f4;
                    padding: 20px;
                }}
                .email-container {{
                    max-width: 900px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .email-table {{
                    border-collapse: collapse;
                    width: 100%;
                    font-size: 14px;
                    margin: 20px 0;
                }}
                .email-table thead {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .email-table th {{
                    padding: 12px 15px;
                    text-align: left;
                    font-weight: 600;
                    border: 1px solid #ddd;
                }}
                .email-table td {{
                    padding: 10px 15px;
                    border: 1px solid #ddd;
                }}
                .email-table tbody tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                .email-table tbody tr:hover {{
                    background-color: #e9ecef;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                {html_table}
            </div>
        </body>
        </html>
        """

        return styled_html

    except Exception as e:
        return f"<p>Error converting Excel to HTML: {str(e)}</p>"


@login_required
def track_email_open(request, tracking_pixel_id):
    try:
        sent_email = SentEmail.objects.get(tracking_pixel_id=tracking_pixel_id)
        sent_email.is_opened = True
        sent_email.opened_at = timezone.now()
        sent_email.save()

        # Create open event
        EmailOpenEvent.objects.create(
            sent_email=sent_email,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        # Send notification if enabled
        if sent_email.notify_on_open and sent_email.admin_notification_email:
            try:
                notification_email = EmailMessage(
                    subject=f"Email Opened: {sent_email.subject}",
                    body=f"""
                    Your email has been opened!

                    Email: {sent_email.subject}
                    Opened at: {timezone.now()}
                    Recipient: {', '.join(sent_email.recipients)}
                    """,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[sent_email.admin_notification_email],
                )
                notification_email.send()
            except Exception as e:
                # Log error but don't break the tracking
                print(f"Error sending notification: {e}")

    except SentEmail.DoesNotExist:
        pass

    # Return a 1x1 transparent GIF
    response = HttpResponse(
        base64.b64decode(b'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'),
        content_type='image/gif'
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
def create_schedule(request):
    if request.method == 'POST':
        form = EmailScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.created_by = request.user
            schedule.recipients = form.cleaned_data['recipients']
            schedule.save()
            form.save_m2m()  # Save many-to-many relationships

            messages.success(request, 'Email schedule created successfully!')
            return redirect('emails')
    else:
        form = EmailScheduleForm()

    return render(request, 'account/email_schedule_form.html', {'form': form})


@login_required
def document_list_api(request):
    """API endpoint for document filtering"""
    category_id = request.GET.get('category')
    client_name = request.GET.get('client')
    search = request.GET.get('search', '')

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

    data = []
    for doc in documents:
        data.append({
            'id': str(doc.id),
            'filename': doc.filename,
            'client_name': doc.client_name,
            'category': doc.category.name if doc.category else '',
            'created_at': doc.created_at.strftime('%Y-%m-%d %H:%M'),
            'description': doc.description,
        })

    return JsonResponse({'documents': data})
