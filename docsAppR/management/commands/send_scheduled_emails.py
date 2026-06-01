"""
Management command: send_scheduled_emails

Delegates to the Celery task synchronously.  Useful for cron fallback or
manual invocation when the Beat worker is not running.

Usage:
    python manage.py send_scheduled_emails
    python manage.py send_scheduled_emails --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Process due EmailSchedule entries and send emails (Beat fallback)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print which schedules are due without sending',
        )

    def handle(self, *args, **options):
        from docsAppR.models import EmailSchedule

        dry_run = options['dry_run']
        now = timezone.now()

        candidates = EmailSchedule.objects.filter(
            is_active=True,
            start_date__lte=now,
        )

        if not candidates.exists():
            self.stdout.write('No active due schedules found.')
            return

        due = []
        for schedule in candidates:
            if schedule.last_sent is None:
                due.append(schedule)
            else:
                next_time = schedule.get_next_send_time(last_sent=schedule.last_sent)
                if next_time and next_time <= now:
                    due.append(schedule)

        if not due:
            self.stdout.write('No schedules are due right now.')
            return

        self.stdout.write(f'Found {len(due)} due schedule(s).')

        if dry_run:
            for s in due:
                self.stdout.write(
                    f'  [DRY RUN] Would send: "{s.name}" '
                    f'(send #{s.send_count + 1}, to={s.recipients})'
                )
            return

        # Run the real task inline (synchronous)
        from email_manager.tasks import send_scheduled_emails_task
        count = send_scheduled_emails_task.apply().get()
        self.stdout.write(self.style.SUCCESS(f'Processed {count} schedule(s).'))
