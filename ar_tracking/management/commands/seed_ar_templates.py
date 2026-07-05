"""
Seed the 5 default global AR email templates.

Run once after the ar_tracking 0002 migration:
    docker compose exec web python manage.py seed_ar_templates

Idempotent — safe to re-run. Uses get_or_create keyed on (name, tenant=None)
so existing records are never duplicated. Use --force to overwrite the
subject_template and body_template on any existing record.
"""
from django.core.management.base import BaseCommand

from ar_tracking.models import AREmailTemplate

DEFAULTS = [
    (
        'Initial Invoice Notice',
        'initial_invoice',
        'Invoice – Claim #{claim_number} | {contractor_name}',
        (
            'Dear {insurer},\n\n'
            'Please find enclosed our invoice for services rendered on the above-referenced claim.\n\n'
            'Claim #: {claim_number}\n'
            'Policy #: {policy_number}\n'
            'Contractor: {contractor_name}\n'
            'Amount Due: ${amount}\n\n'
            'Please remit payment at your earliest convenience.\n\n'
            'Thank you,\n'
            'All Phase Consulting'
        ),
    ),
    (
        '30-Day Follow-up',
        'followup_30',
        'Follow-up: Claim #{claim_number} – 30 Days Outstanding',
        (
            'Dear {insurer},\n\n'
            'We are following up on our invoice for Claim #{claim_number}.\n\n'
            'The balance of ${amount} for {contractor_name} remains outstanding after 30 days. '
            'Please provide a status update or remit payment at your earliest convenience.\n\n'
            'Thank you,\n'
            'All Phase Consulting'
        ),
    ),
    (
        '60-Day Follow-up',
        'followup_60',
        'Second Notice: Claim #{claim_number} – 60 Days Outstanding',
        (
            'Dear {insurer},\n\n'
            'This is a second notice regarding the outstanding balance of ${amount} '
            'for Claim #{claim_number}.\n\n'
            'Despite our previous correspondence, payment has not been received after 60 days. '
            'We request immediate attention to this matter. '
            'If payment is not received within 10 business days, we will be required to escalate.\n\n'
            'Thank you,\n'
            'All Phase Consulting'
        ),
    ),
    (
        'Payment Demand',
        'demand',
        'DEMAND FOR PAYMENT – Claim #{claim_number}',
        (
            'Dear {insurer},\n\n'
            '[CLIENT TO FINALIZE DEMAND LETTER LANGUAGE AND FORMAT]\n\n'
            'Re: Claim #{claim_number} | Policy #{policy_number}\n'
            'Amount Demanded: ${amount}\n'
            'Contractor: {contractor_name}\n\n'
            'Formal demand is hereby made for payment in full of the above-referenced amount.\n\n'
            'All Phase Consulting'
        ),
    ),
    (
        'Supplement Request',
        'supplement',
        'Supplement Request – Claim #{claim_number}',
        (
            'Dear {insurer},\n\n'
            'We are writing to request a supplemental payment for additional scope items '
            'identified during our work on Claim #{claim_number}.\n\n'
            'Claim #: {claim_number}\n'
            'Policy #: {policy_number}\n'
            'Contractor: {contractor_name}\n\n'
            'Please find attached our supplemental estimate for your review and approval. '
            'We appreciate your prompt attention to this matter.\n\n'
            'Thank you,\n'
            'All Phase Consulting'
        ),
    ),
]


class Command(BaseCommand):
    help = 'Seed the 5 global default AR email templates (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite subject_template and body_template on existing records.',
        )

    def handle(self, *args, **options):
        force = options['force']
        created_count = updated_count = skipped_count = 0

        for name, category, subject, body in DEFAULTS:
            obj, created = AREmailTemplate.objects.get_or_create(
                name=name,
                tenant=None,
                defaults={
                    'category':         category,
                    'subject_template': subject,
                    'body_template':    body,
                    'is_default':       True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  CREATED  "{name}"'))
            elif force:
                obj.category         = category
                obj.subject_template = subject
                obj.body_template    = body
                obj.is_default       = True
                obj.save()
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'  UPDATED  "{name}"'))
            else:
                skipped_count += 1
                self.stdout.write(f'  skipped  "{name}" (already exists; use --force to overwrite)')

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\nDone. {created_count} created, {updated_count} updated, {skipped_count} skipped.'
        ))
