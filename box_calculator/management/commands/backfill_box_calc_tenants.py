"""
box_calculator/management/commands/backfill_box_calc_tenants.py

Recovers box_calculator records that became invisible after the
0005_tenant_fks migration ran before any Tenant existed.

The migration's backfill function contained an early-exit guard:
    if not dt: return
If no Tenant row existed at migration time, ALL BoxCalcSession,
BoxCalcRoom, BoxCalcItem, BoxCalcCPSSession, and BoxCalcCPSRoom
records were left with tenant_id=NULL — making them invisible to
TenantScopedManager for every subsequent request.

This command derives the correct tenant from each record's linked
Client and writes it back.

Usage (inside Docker container):
    # Dry-run first — see counts without touching DB
    python manage.py backfill_box_calc_tenants --dry-run

    # Run the backfill
    python manage.py backfill_box_calc_tenants

    # Verbose output (one line per updated row)
    python manage.py backfill_box_calc_tenants --verbose
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Backfill tenant_id=NULL on BoxCalc* records from their linked Client'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Count records that would be updated without writing anything',
        )
        parser.add_argument(
            '--verbose', action='store_true',
            help='Print one line per updated record',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']

        from box_calculator.models import (
            BoxCalcSession, BoxCalcRoom, BoxCalcItem,
            BoxCalcCPSSession, BoxCalcCPSRoom,
        )

        if dry_run:
            self.stdout.write('\n[DRY RUN] No changes will be written.\n')

        total_updated = 0

        # ── 1. BoxCalcCPSSession ────────────────────────────────────────────
        total_updated += self._backfill_via_client(
            qs=BoxCalcCPSSession.objects.filter(tenant__isnull=True).select_related('client__tenant'),
            label='BoxCalcCPSSession',
            dry_run=dry_run, verbose=verbose,
        )

        # ── 2. BoxCalcCPSRoom (derive from session → client → tenant) ───────
        total_updated += self._backfill_via_session(
            qs=BoxCalcCPSRoom.objects.filter(tenant__isnull=True).select_related('session__client__tenant'),
            label='BoxCalcCPSRoom',
            dry_run=dry_run, verbose=verbose,
        )

        # ── 3. BoxCalcSession ───────────────────────────────────────────────
        total_updated += self._backfill_via_client(
            qs=BoxCalcSession.objects.filter(tenant__isnull=True).select_related('client__tenant'),
            label='BoxCalcSession',
            dry_run=dry_run, verbose=verbose,
        )

        # ── 4. BoxCalcRoom (session → client → tenant) ──────────────────────
        total_updated += self._backfill_via_session(
            qs=BoxCalcRoom.objects.filter(tenant__isnull=True).select_related('session__client__tenant'),
            label='BoxCalcRoom',
            dry_run=dry_run, verbose=verbose,
        )

        # ── 5. BoxCalcItem (room → session → client → tenant) ──────────────
        total_updated += self._backfill_item(
            dry_run=dry_run, verbose=verbose,
        )

        mode = 'Would update' if dry_run else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ {mode} {total_updated} record(s) across all BoxCalc models.'
        ))
        if not dry_run and total_updated:
            self.stdout.write(
                'BoxCalc records are now visible via TenantScopedManager.\n'
                'Verify by loading the Box Calculator in the web app.'
            )

    # ── helpers ────────────────────────────────────────────────────────────

    def _backfill_via_client(self, qs, label, dry_run, verbose):
        """Records with a direct ForeignKey to Client."""
        count = 0
        skipped = 0
        for obj in qs:
            tenant = getattr(getattr(obj, 'client', None), 'tenant', None)
            if not tenant:
                skipped += 1
                if verbose:
                    self.stdout.write(f'  SKIP {label} pk={obj.pk} — client has no tenant')
                continue
            if not dry_run:
                with transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(tenant=tenant)
            count += 1
            if verbose:
                self.stdout.write(f'  {"WOULD UPDATE" if dry_run else "UPDATED"} {label} pk={obj.pk} → tenant={tenant.pk}')
        total = count + skipped
        self.stdout.write(
            f'  {label}: {count} updated, {skipped} skipped (no client tenant)  [{total} null-tenant records found]'
        )
        return count

    def _backfill_via_session(self, qs, label, dry_run, verbose):
        """Records with a FK to a session (which has a client FK)."""
        count = 0
        skipped = 0
        for obj in qs:
            tenant = getattr(
                getattr(getattr(obj, 'session', None), 'client', None), 'tenant', None
            )
            if not tenant:
                skipped += 1
                if verbose:
                    self.stdout.write(f'  SKIP {label} pk={obj.pk} — chain has no tenant')
                continue
            if not dry_run:
                with transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(tenant=tenant)
            count += 1
            if verbose:
                self.stdout.write(f'  {"WOULD UPDATE" if dry_run else "UPDATED"} {label} pk={obj.pk} → tenant={tenant.pk}')
        total = count + skipped
        self.stdout.write(
            f'  {label}: {count} updated, {skipped} skipped (no chain tenant)  [{total} null-tenant records found]'
        )
        return count

    def _backfill_item(self, dry_run, verbose):
        """BoxCalcItem: room → session → client → tenant (3-level chain)."""
        from box_calculator.models import BoxCalcItem
        qs = BoxCalcItem.objects.filter(tenant__isnull=True).select_related(
            'room__session__client__tenant'
        )
        count = 0
        skipped = 0
        for obj in qs:
            try:
                tenant = obj.room.session.client.tenant
            except AttributeError:
                tenant = None
            if not tenant:
                skipped += 1
                if verbose:
                    self.stdout.write(f'  SKIP BoxCalcItem pk={obj.pk} — chain has no tenant')
                continue
            if not dry_run:
                with transaction.atomic():
                    BoxCalcItem.objects.filter(pk=obj.pk).update(tenant=tenant)
            count += 1
            if verbose:
                self.stdout.write(f'  {"WOULD UPDATE" if dry_run else "UPDATED"} BoxCalcItem pk={obj.pk} → tenant={tenant.pk}')
        total = count + skipped
        self.stdout.write(
            f'  BoxCalcItem: {count} updated, {skipped} skipped (no chain tenant)  [{total} null-tenant records found]'
        )
        return count
