"""
lease_manager/management/commands/send_term_sheet_correction.py

One-time (and ongoing) command to detect renewal leases whose term-sheet PDFs
were generated with the old, non-halved inspection fee, and send a corrected
term-sheet to the RE company / landlord contacts.

WHAT IT CHECKS (drift detection rules):
  Rule 1 — Renewal RE company fee should be exactly ½ × monthly_rent.
            If the term sheet was generated before this rule existed the
            RE fee shows the full month's rent — that document needs a correction.

USAGE:
  # Dry-run (prints detections, sends nothing):
  python manage.py send_term_sheet_correction --dry-run

  # Send corrections for all drifted renewal leases:
  python manage.py send_term_sheet_correction

  # Send correction for one specific lease:
  python manage.py send_term_sheet_correction --lease <uuid>

This command is idempotent: it logs each correction in LeaseActivity so it
will not send duplicates on re-runs.

FUTURE FEATURE SCAFFOLD:
  _detect_drift(lease) → list[str]
  Each rule returns a human-readable string when it fires.
  Add new rules here as the document standard evolves.
  Wire this into a nightly Celery task (or cron) to auto-correct as leases
  are created/updated.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from docsAppR.models import Lease, LeaseActivity
from lease_manager.email_utils import get_lease_email_connection, get_lease_from_email

logger = logging.getLogger(__name__)

FROM_EMAIL  = get_lease_from_email()
OWNER_EMAIL = getattr(settings, 'NOTIFY_EMAIL',        'wsbjoe9@gmail.com')
SITE_URL    = getattr(settings, 'SITE_URL',             'https://claimetapp.com')

# Correction already sent marker (stored in LeaseActivity.description prefix)
CORRECTION_MARKER = '[AUTO-CORRECTION SENT]'


# ── Drift detection rules ─────────────────────────────────────────────────────

def _detect_drift(lease):
    """
    Run all drift-detection rules against a lease.
    Returns a list of human-readable issue strings (empty = no drift).

    Add new rules here as the document standard evolves.
    """
    issues = []

    if not lease.is_renewal:
        return issues   # rules below only apply to renewals

    rent = float(lease.monthly_rent or 0)
    expected_re_fee = round(rent / 2, 2)

    # Rule 1: Renewal RE company fee should be ½ × monthly rent.
    # The term sheet always shows re_company_fee computed at render time, but
    # any previously-generated PDFs (before this rule) would have shown the
    # full month's rent — flag those leases for a correction email.
    # We detect this by checking whether the stored inspection_fee on the lease
    # is the full-month value, as a proxy for "generated with old template".
    stored_inspection = float(lease.inspection_fee or 0)
    if stored_inspection > expected_re_fee:
        issues.append(
            f'RE company fee was the full month (${rent:.2f}) on previous term sheet; '
            f'renewal rate is ${expected_re_fee:.2f} (½ × ${rent:.2f}).'
        )

    # Rule 2: Security deposit should be $0 / waived on renewals
    security = float(lease.security_deposit or 0)
    if security > 0:
        issues.append(
            f'Security deposit ${security:.2f} should be $0 on a renewal — '
            f'set "Exclude Security Deposit" on the lease.'
        )

    # ── Add future rules here ──────────────────────────────────────────────────
    # e.g. Rule 3: late fee must be ≥ $50
    # e.g. Rule 4: rental_months must be ≥ 1

    return issues


# ── Email helpers ─────────────────────────────────────────────────────────────

def _correction_already_sent(lease):
    return LeaseActivity.objects.filter(
        lease=lease,
        activity_type='generated',
        description__startswith=CORRECTION_MARKER,
    ).exists()


def _build_correction_context(lease):
    rent      = float(lease.monthly_rent or 0)
    old_re    = round(rent, 2)          # old: full month's rent
    new_re    = round(rent / 2, 2)      # corrected: half month's rent
    insp      = float(lease.inspection_fee or 0) if not lease.exclude_inspection_fee else 0.0
    months    = int(lease.rental_months or 0)
    new_total = round(rent * months + new_re + insp, 2)

    # Preferred recipient: RE company contact, then lessor, then owner fallback
    recipient_email = (
        lease.company_email
        or lease.lessor_email
        or OWNER_EMAIL
    )
    recipient_name = (
        lease.company_contact_person
        or lease.lessor_name
        or 'Team'
    )

    return {
        'recipient_name':   recipient_name,
        'recipient_email':  recipient_email,
        'client_name':      lease.client.pOwner if lease.client else '',
        'property_address': lease.property_address or '',
        'term_start':       str(lease.lease_start_date or ''),
        'term_end':         str(lease.lease_end_date or ''),
        'monthly_rent':     f'{rent:,.2f}',
        'old_re_fee':       f'{old_re:,.2f}',
        'new_re_fee':       f'{new_re:,.2f}',
        'new_total':        f'{new_total:,.2f}',
        'contact_email':    FROM_EMAIL,
        'lease_url':        f'{SITE_URL}/lease-manager/lease/{lease.id}/',
    }


def _send_correction_email(lease, ctx, dry_run=False):
    """Generate a corrected term sheet PDF and send the correction email."""
    from lease_manager.signature_views import generate_lease_pdfs

    subject = (
        f'[Claimet] Corrected Term Sheet — {ctx["property_address"] or ctx["client_name"]}'
    )

    html_body = render_to_string(
        'lease_manager/email/term_sheet_correction.html', ctx
    )
    text_body = (
        f'Hi {ctx["recipient_name"]},\n\n'
        f'Please disregard the previously sent term sheet for '
        f'{ctx["property_address"]}.\n\n'
        f'Our automated monitor detected an incorrect inspection fee:\n'
        f'  Previous: ${ctx["old_inspection_fee"]}\n'
        f'  Corrected: ${ctx["new_inspection_fee"]} (½ × monthly rent)\n'
        f'  New total: ${ctx["new_total"]}\n\n'
        f'The corrected term sheet PDF is attached.\n\n'
        f'— The Claimet Team\n{SITE_URL}'
    )

    if dry_run:
        return ctx['recipient_email'], None

    # Re-generate fresh PDFs with the corrected data
    results = generate_lease_pdfs(lease)
    term_sheet_result = next(
        (r for r in results if r.get('doc_name') == 'Term Sheet' and r.get('success')),
        None,
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=FROM_EMAIL,
        to=[ctx['recipient_email']],
        reply_to=[FROM_EMAIL],
        connection=get_lease_email_connection(),
    )
    msg.attach_alternative(html_body, 'text/html')

    if term_sheet_result:
        import os
        from django.conf import settings as dj_settings
        pdf_path = os.path.join(dj_settings.MEDIA_ROOT, term_sheet_result['file_path'])
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                msg.attach('Term_Sheet_Corrected.pdf', f.read(), 'application/pdf')

    msg.send()
    return ctx['recipient_email'], results


# ── Management command ────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Detect renewal leases with drifted term-sheet data (wrong inspection fee, '
        'security deposit not waived) and send auto-corrected documents.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print detections without sending emails or regenerating PDFs.',
        )
        parser.add_argument(
            '--lease', dest='lease_id', default=None,
            help='Check and correct only this specific lease UUID.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Re-send even if a correction was already sent for this lease.',
        )

    def handle(self, *args, **options):
        dry_run  = options['dry_run']
        force    = options['force']
        lease_id = options.get('lease_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no emails will be sent.\n'))

        if lease_id:
            try:
                leases = [Lease.objects.get(id=lease_id)]
            except Lease.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'Lease {lease_id} not found.'))
                return
        else:
            leases = list(
                Lease.objects.filter(is_renewal=True)
                .exclude(status='cancelled')
                .select_related('client')
            )

        self.stdout.write(f'Checking {len(leases)} renewal lease(s)...\n')

        detected = corrected = skipped = 0

        for lease in leases:
            issues = _detect_drift(lease)
            if not issues:
                continue

            detected += 1
            label = f'Lease {lease.id} — {lease.client.pOwner if lease.client else "?"} / {lease.property_address}'

            self.stdout.write(self.style.WARNING(f'\n⚠  {label}'))
            for iss in issues:
                self.stdout.write(f'   • {iss}')

            if not force and _correction_already_sent(lease):
                self.stdout.write(self.style.NOTICE('   → Correction already sent, skipping. (use --force to re-send)'))
                skipped += 1
                continue

            if dry_run:
                ctx = _build_correction_context(lease)
                self.stdout.write(self.style.SUCCESS(f'   → Would send correction to: {ctx["recipient_email"]}'))
                continue

            ctx = _build_correction_context(lease)
            try:
                recipient, _results = _send_correction_email(lease, ctx, dry_run=False)
                LeaseActivity.objects.create(
                    lease=lease,
                    activity_type='generated',
                    description=(
                        f'{CORRECTION_MARKER} Claimet AI monitor detected document drift '
                        f'and sent an auto-corrected term sheet to {recipient}. '
                        f'Issues: {"; ".join(issues)}'
                    ),
                )
                corrected += 1
                self.stdout.write(self.style.SUCCESS(f'   ✓ Correction sent to {recipient}'))
            except Exception as exc:
                logger.error('send_term_sheet_correction failed for lease %s: %s', lease.id, exc)
                self.stderr.write(self.style.ERROR(f'   ✗ Failed: {exc}'))

        self.stdout.write(
            f'\nDone. {detected} lease(s) with drift detected, '
            f'{corrected} correction(s) sent, {skipped} skipped.\n'
        )
        if detected == 0:
            self.stdout.write(self.style.SUCCESS('All renewal leases look correct.'))
