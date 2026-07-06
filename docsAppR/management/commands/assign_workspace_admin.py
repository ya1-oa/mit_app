"""
One-time command to designate one user as the workspace admin (contractor)
and ensure all other non-staff users are members of the same tenant.

Usage (inside the container):
    python manage.py assign_workspace_admin wsbjoe9@gmail.com

What it does:
  1. Finds the existing default Tenant (the one from bootstrap_default_tenant).
  2. Finds or creates the user with the given email.
  3. Assigns that user to the tenant and sets is_tenant_admin=True.
  4. Sets the tenant's primary_contact_email to that address.
  5. Assigns every other non-staff user to the same tenant (idempotent).
  6. Prints a full roster of all affected accounts.

Safe to re-run — all operations are idempotent.
"""
import secrets
import string

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Assign a user as workspace admin and attach all non-staff users to their tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            'admin_email',
            help='Email address of the contractor/admin account (e.g. wsbjoe9@gmail.com).',
        )
        parser.add_argument(
            '--tenant-slug',
            default='default',
            help="Slug of the tenant to use (default: 'default').",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making any changes.',
        )

    def handle(self, *args, **options):
        from docsAppR.models import CustomUser, Tenant

        admin_email  = options['admin_email'].strip().lower()
        tenant_slug  = options['tenant_slug'].strip()
        dry_run      = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be written.\n'))

        # ── 1. Find the tenant ────────────────────────────────────────────────
        try:
            tenant = Tenant.objects.get(slug=tenant_slug)
        except Tenant.DoesNotExist:
            raise CommandError(
                f"No Tenant with slug '{tenant_slug}' found. "
                "Run bootstrap_default_tenant first, or pass --tenant-slug."
            )

        self.stdout.write(f'Tenant : {tenant.name} (slug={tenant.slug}, status={tenant.status})')

        # ── 2. Find or create the admin user ──────────────────────────────────
        try:
            admin_user = CustomUser.objects.get(email__iexact=admin_email)
            created = False
        except CustomUser.DoesNotExist:
            created = True
            if not dry_run:
                # Generate a temporary password and tell the operator
                tmp_pw = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
                admin_user = CustomUser.objects.create_user(
                    email=admin_email,
                    username=admin_email,
                    password=tmp_pw,
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"\nCreated NEW user {admin_email}.\n"
                        f"Temporary password: {tmp_pw}\n"
                        "→ Have this user log in and change their password immediately,\n"
                        "  or use the Django admin / allauth password-reset flow.\n"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING(
                    f'[DRY RUN] Would create new user: {admin_email}'
                ))
                admin_user = None

        if admin_user:
            self.stdout.write(
                f'Admin  : {admin_user.email}'
                f'{"  ← NEW" if created else ""}'
                f' (currently is_tenant_admin={admin_user.is_tenant_admin},'
                f' tenant={admin_user.tenant})'
            )

        # ── 3. Apply changes ──────────────────────────────────────────────────
        with transaction.atomic():
            if dry_run:
                self.stdout.write('\n[DRY RUN] Would apply:')
            else:
                if admin_user:
                    admin_user.tenant          = tenant
                    admin_user.is_tenant_admin = True
                    admin_user.is_staff        = False   # admin is a customer, not ClaiMetApp staff
                    admin_user.save(update_fields=['tenant', 'is_tenant_admin', 'is_staff'])

                tenant.primary_contact_email = admin_email
                tenant.save(update_fields=['primary_contact_email'])

            # All other non-staff users → same tenant, is_tenant_admin=False
            others = CustomUser.objects.filter(is_staff=False).exclude(email__iexact=admin_email)

            if dry_run:
                self.stdout.write(f'  → Set {admin_email} as tenant admin of "{tenant.name}"')
                self.stdout.write(f'  → Move {others.count()} other user(s) into the same tenant')
            else:
                moved = others.filter(tenant__isnull=True).update(tenant=tenant)
                # Don't demote existing admins in other tenants — only touch this tenant's users
                others.filter(tenant=tenant).update(is_tenant_admin=False)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Set {admin_email} as tenant admin for "{tenant.name}".\n'
                        f'Backfilled {moved} previously-unassigned user(s) into the tenant.'
                    )
                )

        if dry_run:
            transaction.set_rollback(True)
            return

        # ── 4. Print final roster ─────────────────────────────────────────────
        self.stdout.write('\n' + '─' * 60)
        self.stdout.write(f'Workspace: {tenant.name}  ({tenant.slug})')
        self.stdout.write(f'Contact  : {tenant.primary_contact_email}')
        self.stdout.write('─' * 60)

        all_members = CustomUser.objects.filter(tenant=tenant).order_by('-is_tenant_admin', 'email')
        for u in all_members:
            role = 'ADMIN (contractor)' if u.is_tenant_admin else 'Member (worker)'
            self.stdout.write(f'  {"★" if u.is_tenant_admin else " "} {u.email:<40} {role}')

        staff = CustomUser.objects.filter(is_staff=True)
        if staff.exists():
            self.stdout.write('\nInternal staff (no tenant, by design):')
            for u in staff:
                self.stdout.write(f'    {u.email}')

        self.stdout.write('─' * 60)
        self.stdout.write(self.style.SUCCESS('Done.'))
