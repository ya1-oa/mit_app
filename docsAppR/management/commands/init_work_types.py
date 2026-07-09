# docsAppR/management/commands/init_work_types.py

from django.core.management.base import BaseCommand
from docsAppR.models import WorkType


class Command(BaseCommand):
    help = 'Initialize standard work types'

    def handle(self, *args, **options):
        work_types = [
            # Standard work types (100-700)
            (100, 'Overview', 0, True),
            (200, 'Source', 1, True),
            (300, 'CPS', 2, True),
            (400, 'PPR', 3, False),
            (500, 'Demo', 4, False),
            (600, 'Mitigation', 5, False),
            (700, 'HMR', 6, False),

            # MC Day Readings (8000-series, renamed from 6000s by migration 0022)
            (8100, 'MC DAY 1', 7, False),
            (8200, 'MC DAY 2', 8, False),
            (8300, 'MC DAY 3', 9, False),
            (8400, 'MC DAY 4', 10, False),
        ]

        created_count = 0
        updated_count = 0

        for wt_id, name, order, applies_all in work_types:
            wt, created = WorkType.objects.update_or_create(
                work_type_id=wt_id,
                defaults={
                    'name': name,
                    'display_order': order,
                    'applies_to_all_rooms': applies_all,
                    'is_active': True
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created work type {wt_id}: {name}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'⟳ Updated work type {wt_id}: {name}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Completed: {created_count} created, {updated_count} updated'
            )
        )
