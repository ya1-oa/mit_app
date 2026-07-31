"""
daily_reports/tasks.py

Celery tasks:
  - send_daily_high_priority_report  — runs every morning (Celery Beat)
  - send_deep_operations_report      — runs every Monday (Celery Beat)
  - trigger_daily_report_now         — on-demand send (from dashboard)
"""
import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

NOTIFY_EMAIL = getattr(settings, 'NOTIFY_EMAIL', 'wsbjoe9@gmail.com')


def _send_html_email(subject: str, html_body: str, recipients: list,
                     cc: list | None = None, attachments: list | None = None) -> bool:
    """
    Send an HTML email via Django's default SMTP backend.
    Persists a SentEmail record for open-tracking (same pattern as dev_hub).
    Returns True on success.
    """
    from docsAppR.models import SentEmail
    from django.conf import settings

    base = getattr(settings, 'SITE_URL', 'https://claimetapp.com')
    try:
        sent = SentEmail.objects.create(
            subject=subject,
            body=html_body,
            recipients=recipients,
            notify_on_open=False,
        )
        pixel = f'<img src="{base}/emails/track/{sent.tracking_pixel_id}/" width="1" height="1" style="display:none;" alt="" />'
        full_html = html_body + pixel

        msg = EmailMessage(
            subject=subject,
            body=full_html,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            cc=cc or [],
        )
        msg.content_subtype = 'html'
        if attachments:
            for name, data, mime in attachments:
                msg.attach(name, data, mime)
        msg.send()
        return True
    except Exception as exc:
        logger.error('daily_reports email failed: %s', exc)
        return False


def _get_active_config():
    """Return the first active DailyReportConfig, or None."""
    from daily_reports.models import DailyReportConfig
    return DailyReportConfig.objects.filter(is_active=True).first()


def _build_ppr_attachments(config) -> list:
    """
    If config.attach_ppr_pdf, generate Schedule of Loss PDFs for sessions
    with pending signatures and return as email attachments.
    """
    if not config.attach_ppr_pdf:
        return []

    attachments = []
    try:
        from cps_report.models import CPSReportSession
        from cps_report.pdf_builder import build_pdf
        from cps_report.views import _ppr_file_prefix

        sessions = (
            CPSReportSession.objects
            .filter(status='complete')
            .filter(rooms__signature_name='')
            .distinct()
            .select_related('client')[:5]   # cap at 5 to keep email size reasonable
        )
        for session in sessions:
            try:
                pdf_bytes = build_pdf(session)
                prefix    = _ppr_file_prefix(session)
                filename  = f"{prefix} NON SALVAGEABLE PPR SCHEDULE OF LOSS.pdf"
                attachments.append((filename, pdf_bytes, 'application/pdf'))
            except Exception as exc:
                logger.warning('Could not generate PDF for session %s: %s', session.id, exc)
    except Exception as exc:
        logger.warning('PDF attachment generation failed: %s', exc)

    return attachments


@shared_task(bind=True, max_retries=2, default_retry_delay=300, name='daily_reports.send_daily_report')
def send_daily_high_priority_report(self):
    """
    Send the daily High Priority Status Report.
    Scheduled via CELERY_BEAT_SCHEDULE at the configured send_hour.
    """
    from daily_reports.models import DailyReportConfig, DailyReportLog
    from daily_reports.report_builder import build_high_priority_html

    config = _get_active_config()
    if not config:
        logger.info('daily_reports: no active config found, skipping')
        return 0

    recipients = config.recipients or [NOTIFY_EMAIL]
    if not recipients:
        logger.info('daily_reports: no recipients configured, skipping')
        return 0

    try:
        html, total_items, urgent_items = build_high_priority_html(config)
    except Exception as exc:
        logger.error('daily_reports: report build failed: %s', exc, exc_info=True)
        DailyReportLog.objects.create(
            report_type='daily',
            config=config,
            recipients=recipients,
            total_items=0,
            urgent_items=0,
            email_success=False,
            error_message=str(exc),
        )
        return 0

    now     = timezone.now()
    subject = f'[Claimet] Daily Status Report — {now.strftime("%b %d, %Y")} · {total_items} items · {urgent_items} URGENT'

    attachments = _build_ppr_attachments(config)

    success = _send_html_email(
        subject=subject,
        html_body=html,
        recipients=recipients,
        cc=config.cc_emails or [],
        attachments=attachments,
    )

    DailyReportLog.objects.create(
        report_type='daily',
        config=config,
        recipients=recipients,
        total_items=total_items,
        urgent_items=urgent_items,
        email_success=success,
    )

    logger.info(
        'Daily report sent: %d items (%d urgent), success=%s',
        total_items, urgent_items, success,
    )
    return total_items


@shared_task(bind=True, max_retries=2, default_retry_delay=300, name='daily_reports.send_deep_report')
def send_deep_operations_report(self):
    """
    Send the Weekly Deep Operations Report every Monday.
    Scheduled via CELERY_BEAT_SCHEDULE.
    """
    from daily_reports.models import DailyReportConfig, DailyReportLog, OperationalTask
    from daily_reports.report_builder import build_deep_report_html

    config     = _get_active_config()
    recipients = (config.recipients if config else None) or [NOTIFY_EMAIL]
    now        = timezone.now()

    try:
        html = build_deep_report_html()
    except Exception as exc:
        logger.error('deep_report: build failed: %s', exc, exc_info=True)
        return 0

    subject = f'[Claimet] Weekly Deep Operations Report — {now.strftime("%b %d, %Y")}'

    success = _send_html_email(
        subject=subject,
        html_body=html,
        recipients=recipients,
        cc=config.cc_emails if config else [],
    )

    DailyReportLog.objects.create(
        report_type='deep',
        config=config,
        recipients=recipients,
        total_items=0,
        email_success=success,
    )

    # Clear queue_for_deep_report flags so tasks don't re-appear next week
    # unless the user re-queues them
    OperationalTask.objects.filter(status='done', queue_for_deep_report=True).update(
        queue_for_deep_report=False
    )

    logger.info('Deep operations report sent, success=%s', success)
    return 1


@shared_task(name='daily_reports.trigger_now')
def trigger_daily_report_now(report_type: str = 'daily'):
    """
    On-demand send triggered from the dashboard 'Send Now' button.
    report_type: 'daily' or 'deep'
    """
    if report_type == 'deep':
        return send_deep_operations_report.apply().get()
    return send_daily_high_priority_report.apply().get()
