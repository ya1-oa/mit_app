"""
docsAppR/management/commands/push_missing_encircle_claims.py

Backfill: find Client records that were never pushed to Encircle
(encircle_claim_id is null/blank) and queue them via the existing
push_claim_to_encircle_task Celery task.

Usage (inside Docker container):
    # Dry-run — see what would be pushed
    python manage.py push_missing_encircle_claims --dry-run

    # Queue all missing claims (Celery workers must be running)
    python manage.py push_missing_encircle_claims

    # Cap at 10 to test with a small batch first
    python manage.py push_missing_encircle_claims --limit 10

    # Re-push a single specific client (by UUID)
    python manage.py push_missing_encircle_claims --client-id <uuid>

    # Force re-push even if a claim already has an encircle_claim_id
    python manage.py push_missing_encircle_claims --force
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from docsAppR.models import Client
from docsAppR.tasks import push_claim_to_encircle_task


class Command(BaseCommand):
    help = 'Queue push_claim_to_encircle_task for clients with no Encircle claim ID'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be pushed without actually queuing tasks',
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Maximum number of claims to queue (useful for testing)',
        )
        parser.add_argument(
            '--client-id', type=str, default=None,
            help='Push a single client by UUID (bypasses the missing-only filter)',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Re-push claims that already have an encircle_claim_id',
        )

    def handle(self, *args, **options):
        dry_run   = options['dry_run']
        limit     = options['limit']
        client_id = options['client_id']
        force     = options['force']

        # ── Build the queryset ────────────────────────────────────────────────
        if client_id:
            qs = Client.unscoped.filter(pk=client_id)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f'Client {client_id} not found'))
                return
        else:
            qs = Client.unscoped.all().order_by('created_at')
            if not force:
                qs = qs.filter(Q(encircle_claim_id__isnull=True) | Q(encircle_claim_id=''))

        total = qs.count()
        if limit:
            qs = qs[:limit]

        queued = 0
        skipped = 0

        self.stdout.write(
            f"\n{'[DRY RUN] ' if dry_run else ''}Found {total} client(s) to process"
            + (f' (limited to {limit})' if limit else '')
        )

        for client in qs:
            label = f'{client.pOwner or "(no name)"} [{client.pk}]'
            has_encircle = bool(client.encircle_claim_id)

            if has_encircle and not force:
                self.stdout.write(f'  SKIP (already synced, id={client.encircle_claim_id}): {label}')
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f'  WOULD PUSH: {label}'
                    + (f'  (current encircle_claim_id={client.encircle_claim_id})' if has_encircle else '')
                )
            else:
                push_claim_to_encircle_task.delay(str(client.pk))
                self.stdout.write(self.style.SUCCESS(f'  Queued: {label}'))

            queued += 1

        mode = 'Would queue' if dry_run else 'Queued'
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ {mode} {queued} task(s). Skipped {skipped}.'
            )
        )
        if not dry_run and queued:
            self.stdout.write(
                'Tasks dispatched to Celery. Monitor progress with:\n'
                '  docker compose logs -f celery\n'
                'or check the Encircle push log in the admin panel.'
            )
