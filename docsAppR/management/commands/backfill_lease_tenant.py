"""
Backfill tenant_id for existing leases.

Run this command to populate the tenant field for all leases that were created
before the multi-tenant retrofit. This ensures old leases appear in the correct
tenant's lease list.

Usage:
    python manage.py backfill_lease_tenant --user-email <admin@example.com>
"""
from django.core.management.base import BaseCommand, CommandError
from docsAppR.models import Lease, Client, CustomUser


class Command(BaseCommand):
    help = 'Backfill tenant_id for existing leases'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-email',
            type=str,
            required=True,
            help='Email of the workspace admin user who owns this tenant'
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Find the workspace admin by email
        user = User.objects.filter(email=options['user_email']).first()
        if not user:
            raise CommandError(f'User with email {options["user_email"]} not found')
        
        if not user.is_tenant_admin:
            raise CommandError(f'{user.email} is not a workspace admin')
        
        if not user.tenant:
            raise CommandError(f'{user.email} does not have a tenant assigned yet')
        
        tenant = user.tenant
        self.stdout.write(self.style.SUCCESS(f'Found tenant: {tenant.name} (id={tenant.id})'))
        
        # Get all leases for clients that belong to this tenant
        # Clients are linked to tenants through the workspace admin's relationship
        client_ids = Client.objects.filter(
            contractor__tenant=tenant.id if user.tenant else None
        ).values_list('id', flat=True)
        
        if not client_ids:
            self.stdout.write(self.style.WARNING('No clients found for this tenant'))
            return
        
        # Get all leases for these clients that don't have a tenant set
        leases_without_tenant = Lease.objects.unscoped.filter(
            client_id__in=client_ids,
            tenant__isnull=True
        )
        
        count = 0
        for lease in leases_without_tenant:
            # Set the tenant based on the contractor relationship
            if lease.client.contractor and lease.client.contractor.tenant:
                lease.tenant = lease.client.contractor.tenant
            else:
                # If no contractor, use the workspace admin's tenant
                lease.tenant = tenant
            
            lease.save(update_fields=['tenant'])
            count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'Backfilled tenant_id for {count} leases in tenant {tenant.name}'
        ))
