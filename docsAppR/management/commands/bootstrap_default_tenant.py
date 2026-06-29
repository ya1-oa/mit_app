"""
Bootstrap step for the multi-tenant retrofit (Workstream A Phase 0).

Creates exactly one Tenant row representing the existing company, and
assigns it to every existing non-staff CustomUser. Staff/superuser accounts
are left with tenant=NULL — that's the signal for "internal user" (see
docsAppR/middleware.py TenantMiddleware).

Idempotent and safe to re-run: skips creating the tenant if one with the
given slug already exists, and only updates users whose tenant is still NULL.

Run once, by hand, in the container:
    python manage.py bootstrap_default_tenant --name "All Phase Consulting"
"""
from django.core.management.base import BaseCommand, CommandError

from docsAppR.models import CustomUser, Tenant


class Command(BaseCommand):
    help = 'Create the default Tenant and backfill it onto every existing non-staff user.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name', required=True,
            help='Display name for the default tenant, e.g. the existing company name.',
        )
        parser.add_argument(
            '--slug', default='default',
            help="Slug for the default tenant (default: 'default').",
        )

    def handle(self, *args, **options):
        name = options['name'].strip()
        slug = options['slug'].strip()
        if not name:
            raise CommandError('--name is required and cannot be blank.')

        tenant, created = Tenant.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'status': 'active'},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Tenant "{tenant.name}" (slug={slug}).'))
        else:
            self.stdout.write(self.style.WARNING(
                f'Tenant with slug "{slug}" already exists ("{tenant.name}") — reusing it.'
            ))

        updated = CustomUser.objects.filter(
            is_staff=False, tenant__isnull=True,
        ).update(tenant=tenant)

        self.stdout.write(self.style.SUCCESS(
            f'Backfilled {updated} non-staff user(s) onto tenant "{tenant.name}".'
        ))

        still_unset = CustomUser.objects.filter(is_staff=False, tenant__isnull=True).count()
        staff_count = CustomUser.objects.filter(is_staff=True).count()
        self.stdout.write(
            f'Remaining non-staff users with no tenant: {still_unset} '
            f'(should be 0). Staff users left as tenant=NULL by design: {staff_count}.'
        )
