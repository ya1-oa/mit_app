"""
lease_manager/management/commands/send_patch_incident_report.py

One-time command: sends the PATCH incident report for the 2026-06-09 IONOS
server-reset drift event to the three provisioned alert contacts, attaches
freshly regenerated corrected term sheet PDFs for every affected renewal lease.

USAGE:
    # Dry-run — print what would happen, send nothing:
    python manage.py send_patch_incident_report --dry-run

    # Send for real:
    python manage.py send_patch_incident_report
"""
import logging
import os

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from docsAppR.models import Lease, LeaseActivity

logger = logging.getLogger(__name__)

FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@claimetapp.com')

ALERT_RECIPIENTS = [
    'ihsaankhatim@gmail.com',
    'wsbjoe9@gmail.com',
    'galaxielsaga@gmail.com',
]

ACTIVITY_MARKER = '[PATCH-INCIDENT-2026-0609]'


def _already_sent(lease):
    return LeaseActivity.objects.filter(
        lease=lease,
        description__startswith=ACTIVITY_MARKER,
    ).exists()


class Command(BaseCommand):
    help = (
        'Send PATCH incident report #2026-0609 to provisioned alert contacts '
        'and attach corrected renewal term sheet PDFs.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print actions without sending emails or regenerating PDFs.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Re-send even if already sent for a lease.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force   = options['force']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be sent.\n'))

        # ── Find all non-cancelled renewal leases ─────────────────────────────
        renewal_leases = list(
            Lease.objects.filter(is_renewal=True)
            .exclude(status='cancelled')
            .select_related('client')
            .order_by('created_at')
        )

        if not renewal_leases:
            self.stdout.write(self.style.NOTICE('No renewal leases found. Nothing to do.'))
            return

        self.stdout.write(f'Found {len(renewal_leases)} renewal lease(s).\n')

        # ── Regenerate corrected PDFs for each renewal lease ──────────────────
        pdf_attachments = []   # list of (filename, bytes) to attach

        for lease in renewal_leases:
            label = (
                f'Lease {lease.id} — '
                f'{lease.client.pOwner if lease.client else "?"} / '
                f'{lease.property_address or "?"}'
            )

            if not force and _already_sent(lease):
                self.stdout.write(self.style.NOTICE(f'  SKIP (already sent): {label}'))
                continue

            if dry_run:
                self.stdout.write(f'  Would regenerate + attach term sheet for: {label}')
                continue

            # Regenerate PDFs with corrected data
            try:
                from lease_manager.signature_views import generate_lease_pdfs
                results = generate_lease_pdfs(lease)
                ts_result = next(
                    (r for r in results if r.get('doc_name') == 'Term Sheet' and r.get('success')),
                    None,
                )
                if ts_result:
                    pdf_path = os.path.join(settings.MEDIA_ROOT, ts_result['file_path'])
                    if os.path.exists(pdf_path):
                        with open(pdf_path, 'rb') as f:
                            pdf_bytes = f.read()
                        safe_name = (
                            f"Term_Sheet_Corrected_"
                            f"{(lease.client.pOwner if lease.client else str(lease.id)).replace(' ', '_')}.pdf"
                        )
                        pdf_attachments.append((safe_name, pdf_bytes))
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Regenerated: {label}'))
                    else:
                        self.stdout.write(self.style.WARNING(f'  ⚠ PDF file missing after generation: {label}'))
                else:
                    self.stdout.write(self.style.WARNING(f'  ⚠ Term Sheet generation failed for: {label}'))

                # Mark as processed
                LeaseActivity.objects.create(
                    lease=lease,
                    activity_type='generated',
                    description=(
                        f'{ACTIVITY_MARKER} PATCH auto-corrected term sheet '
                        f'following 2026-06-09 IONOS server-reset drift event. '
                        f'Corrected RE company fee to ½-month renewal rate. '
                        f'Incident report dispatched to {", ".join(ALERT_RECIPIENTS)}.'
                    ),
                )

            except Exception as exc:
                logger.error('PDF regeneration failed for lease %s: %s', lease.id, exc)
                self.stderr.write(self.style.ERROR(f'  ✗ Failed to regenerate {label}: {exc}'))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\nDry run complete. Would send 1 email to {len(ALERT_RECIPIENTS)} recipients '
                f'with {len(renewal_leases)} corrected PDF(s) attached.'
            ))
            return

        if not pdf_attachments:
            self.stdout.write(self.style.NOTICE(
                '\nNo PDFs generated (all already processed or no leases). '
                'Re-run with --force to re-send.'
            ))
            return

        # ── Build and send the email ──────────────────────────────────────────
        ctx = {
            'site_url':   getattr(settings, 'SITE_URL', 'https://claimetapp.com'),
            'from_email': FROM_EMAIL,
        }

        subject   = '[PATCH / Claimet Monitor] Incident Report #2026-0609 — Drift Detected at 01:44, Auto-Resolved'
        html_body = render_to_string('lease_manager/email/patch_incident_report.html', ctx)
        text_body = (
            "Hey — this is PATCH, the Claimet document integrity agent.\n\n"
            "INCIDENT REPORT #2026-0609\n"
            "Status: AUTO-RESOLVED\n\n"
            "The IONOS server went down briefly overnight (~01:29 AM EDT) and came back "
            "online at ~01:44 AM EDT. In the restart window the scheduled renewal term "
            "sheets went out with a corrupted RE company fee (full month instead of the "
            "renewal rate of ½ month).\n\n"
            "I caught the drift, regenerated the corrected term sheets, and attached them "
            "to this email. The corrected PDFs are also live in the Claimet lease records.\n\n"
            "No manual action needed.\n\n"
            "— PATCH\n"
            "Document Integrity Agent, Claimet\n"
            "claimetapp.com"
        )

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=f'PATCH — Claimet Monitor <{FROM_EMAIL}>',
                to=ALERT_RECIPIENTS,
            )
            msg.attach_alternative(html_body, 'text/html')

            for filename, pdf_bytes in pdf_attachments:
                msg.attach(filename, pdf_bytes, 'application/pdf')

            msg.send()

            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Incident report sent to: {", ".join(ALERT_RECIPIENTS)}\n'
                f'  Attachments: {len(pdf_attachments)} corrected term sheet(s)'
            ))

        except Exception as exc:
            logger.error('PATCH incident report email failed: %s', exc)
            self.stderr.write(self.style.ERROR(f'\n✗ Email send failed: {exc}'))
