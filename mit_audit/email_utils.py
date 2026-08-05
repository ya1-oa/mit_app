"""
mit_audit/email_utils.py

Sends the MIT Day 3 completion notification email with links to:
  - The populated MIT Day 3 workbook (download)
  - Required Equipment PDF
  - Missing Equipment & Photos PDF

Uses Django's standard email backend (distinct from lease_manager's custom flow).
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse

logger = logging.getLogger(__name__)


def send_mit_completion_email(audit, request=None) -> bool:
    """
    Send the completion notification for *audit*.

    Returns True if email was dispatched without error.
    Uses settings.NOTIFY_EMAIL (list or string) as the recipient list;
    falls back to settings.DEFAULT_FROM_EMAIL.
    """
    recipients = getattr(settings, 'NOTIFY_EMAIL', None)
    if isinstance(recipients, str):
        recipients = [recipients]
    if not recipients:
        recipients = [settings.DEFAULT_FROM_EMAIL]

    client  = audit.client
    claim   = client.claimNumber or f'Audit #{audit.pk}'
    owner   = client.pOwner or 'Unknown Client'
    addr    = getattr(client, 'propertyAddress', '') or ''
    from_em = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@claimet.app')

    subject = f'Mitigation Day 3 Review Ready — {owner} / {claim}'

    # Build URLs
    def abs_url(path):
        if request:
            return request.build_absolute_uri(path)
        base = getattr(settings, 'SITE_URL', 'https://app.claimet.com')
        return base.rstrip('/') + path

    dashboard_url = abs_url(reverse('mit_audit:dashboard'))

    # Gather report download URLs
    reports = {r.report_type: r for r in audit.reports.all()}
    req_url  = ''
    miss_url = ''
    if 'required_equipment' in reports:
        req_url = abs_url(reports['required_equipment'].get_download_url())
    if 'missing_equipment' in reports:
        miss_url = abs_url(reports['missing_equipment'].get_download_url())

    # Count items needing attention
    needs_review = audit.required_equipment.filter(
        photo_observation__status__in=['missing', 'partial', 'manual']
    ).count()

    review_notice = ''
    if needs_review:
        review_notice = (
            f'<div style="background:#fff3e0; border-left:4px solid #f57c00; '
            f'padding:10px 14px; margin:12px 0;">'
            f'<strong>⚠ Manual Review Required:</strong> {needs_review} equipment '
            f'item(s) need attention (missing or partially documented).'
            f'</div>'
        )
    manual_count = audit.required_equipment.filter(
        photo_observation__status='manual'
    ).count()
    if manual_count:
        review_notice += (
            f'<div style="background:#f3e5f5; border-left:4px solid #6a1b9a; '
            f'padding:10px 14px; margin:12px 0;">'
            f'<strong>? AI Review Uncertain:</strong> {manual_count} item(s) could '
            f'not be confirmed by AI and require manual photo verification.'
            f'</div>'
        )

    html_body = f"""
    <div style="font-family:Arial,sans-serif; max-width:600px; margin:auto; color:#212121;">
      <div style="background:#1a237e; padding:20px; color:#fff; border-radius:4px 4px 0 0;">
        <h2 style="margin:0; font-size:18px;">Mitigation Day 3 Review Ready</h2>
        <p style="margin:4px 0 0; font-size:13px; opacity:.9;">Claimet App — Equipment Audit</p>
      </div>
      <div style="border:1px solid #e0e0e0; border-top:none; padding:20px; border-radius:0 0 4px 4px;">
        <table style="width:100%; font-size:13px; color:#555; margin-bottom:16px;">
          <tr><td><strong>Claim:</strong></td><td>{claim}</td></tr>
          <tr><td><strong>Client:</strong></td><td>{owner}</td></tr>
          <tr><td><strong>Address:</strong></td><td>{addr or '—'}</td></tr>
          <tr><td><strong>Audit #:</strong></td><td>{audit.pk}</td></tr>
        </table>
        {review_notice}
        <p style="font-size:13px; margin-top:16px;">The following documents are ready:</p>
        <table style="width:100%; margin:8px 0;">
          <tr>
            <td style="padding:6px 0;">📄 <a href="{dashboard_url}" style="color:#1a237e;">
              View Audit Dashboard</a></td>
          </tr>
          {'<tr><td style="padding:6px 0;">📊 <a href="' + req_url + '" style="color:#1a237e;">Required Equipment Report (PDF)</a></td></tr>' if req_url else ''}
          {'<tr><td style="padding:6px 0;">🔍 <a href="' + miss_url + '" style="color:#c62828;">Missing Equipment & Photos Report (PDF)</a></td></tr>' if miss_url else ''}
        </table>
        <p style="font-size:11px; color:#888; margin-top:24px; border-top:1px solid #eee; padding-top:10px;">
          Automated notification from Claimet App — MIT Day 3 Equipment Audit system.
        </p>
      </div>
    </div>
    """

    plain_body = (
        f'MIT Day 3 Review Ready — {owner} / {claim}\n\n'
        f'Claim: {claim}\nClient: {owner}\nAddress: {addr}\n\n'
        f'View dashboard: {dashboard_url}\n'
        + (f'Required Equipment PDF: {req_url}\n' if req_url else '')
        + (f'Missing Equipment PDF:  {miss_url}\n' if miss_url else '')
        + (f'\n⚠ {needs_review} item(s) need attention.\n' if needs_review else '')
    )

    try:
        msg = EmailMultiAlternatives(subject, plain_body, from_em, recipients)
        msg.attach_alternative(html_body, 'text/html')
        msg.send()
        logger.info('[MIT] Completion email sent for audit #%d → %s', audit.pk, recipients)
        return True
    except Exception as exc:
        logger.error('[MIT] Failed to send completion email for audit #%d: %s', audit.pk, exc)
        return False
