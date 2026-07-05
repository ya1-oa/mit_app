"""
Management command: verify_beat_tasks

Lists all pending email-related Celery Beat / scheduled tasks with their
next run time.  Covers:
  1. CELERY_BEAT_SCHEDULE static entries
  2. django-celery-beat DB PeriodicTask / ClockedSchedule entries
  3. EmailSchedule DB records (pending / due / overdue)
  4. EmailCampaign records (scheduled / running) with next send time

Usage:
    python manage.py verify_beat_tasks
    python manage.py verify_beat_tasks --verbose
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone


class Command(BaseCommand):
    help = 'List all pending scheduled email tasks and their next run time'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose', '-v', action='store_true',
            help='Show extra detail (task kwargs, recipient lists)',
        )

    def handle(self, *args, **options):
        verbose = options['verbose']
        now     = timezone.now()

        self._section('CELERY_BEAT_SCHEDULE (static entries)')
        self._check_static_beat(now)

        self._section('django-celery-beat DB PeriodicTask entries')
        self._check_db_periodic_tasks(now, verbose)

        self._section('EmailSchedule records')
        self._check_email_schedules(now, verbose)

        self._section('EmailCampaign records')
        self._check_campaigns(now, verbose)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, title):
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO(f'=== {title} ==='))

    def _check_static_beat(self, now):
        beat_schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
        email_entries = {
            k: v for k, v in beat_schedule.items()
            if 'email' in k.lower() or 'email' in v.get('task', '').lower()
        }
        if not email_entries:
            self.stdout.write('  (no email-related static Beat entries)')
            return
        for name, entry in email_entries.items():
            task     = entry.get('task', 'unknown')
            schedule = entry.get('schedule', 'unknown')
            self.stdout.write(f'  {self.style.SUCCESS(name)}')
            self.stdout.write(f'    task:     {task}')
            self.stdout.write(f'    schedule: {schedule}')

    def _check_db_periodic_tasks(self, now, verbose):
        try:
            from django_celery_beat.models import PeriodicTask, ClockedSchedule
        except ImportError:
            self.stdout.write('  django-celery-beat not installed or not in INSTALLED_APPS')
            return

        tasks = PeriodicTask.objects.filter(
            enabled=True,
        ).filter(
            task__icontains='email'
        ).select_related('clocked', 'interval', 'crontab')

        if not tasks.exists():
            self.stdout.write('  (no enabled email-related DB PeriodicTasks found)')
            # Check if ALL periodic tasks are present (helps debug missing registration)
            total = PeriodicTask.objects.filter(enabled=True).count()
            self.stdout.write(f'  Total enabled PeriodicTasks in DB: {total}')
            return

        for task in tasks:
            status = self.style.SUCCESS('ENABLED')
            self.stdout.write(f'  [{status}] {task.name}')
            self.stdout.write(f'    task: {task.task}')
            if task.last_run_at:
                self.stdout.write(f'    last run: {task.last_run_at.strftime("%Y-%m-%d %H:%M:%S %Z")}')
            else:
                self.stdout.write(f'    last run: never')
            if task.clocked:
                clocked_dt = task.clocked.clocked_time
                overdue = 'OVERDUE' if clocked_dt < now else 'pending'
                self.stdout.write(
                    f'    clocked at: {clocked_dt.strftime("%Y-%m-%d %H:%M:%S %Z")} [{overdue}]'
                )
            if verbose and task.kwargs:
                self.stdout.write(f'    kwargs: {task.kwargs}')

    def _check_email_schedules(self, now, verbose):
        from docsAppR.models import EmailSchedule

        schedules = EmailSchedule.objects.filter(is_active=True).order_by('start_date')

        if not schedules.exists():
            self.stdout.write('  (no active EmailSchedule records)')
            return

        for s in schedules:
            next_send = s.get_next_send_time(last_sent=s.last_sent)

            if next_send is None:
                tag = self.style.WARNING('COMPLETE')
            elif next_send <= now:
                tag = self.style.ERROR('OVERDUE')
            else:
                delta = next_send - now
                hrs   = int(delta.total_seconds() // 3600)
                mins  = int((delta.total_seconds() % 3600) // 60)
                tag   = self.style.SUCCESS(f'due in {hrs}h {mins}m')

            self.stdout.write(
                f'  [{tag}] "{s.name}" (id={s.id})'
            )
            self.stdout.write(
                f'    interval: {s.interval}  '
                f'sends: {s.send_count}/{s.repeat_count if s.repeat_count else "unlimited"}  '
                f'next: {next_send.strftime("%Y-%m-%d %H:%M %Z") if next_send else "N/A"}'
            )
            if verbose:
                self.stdout.write(f'    recipients: {s.recipients}')

    def _check_campaigns(self, now, verbose):
        from docsAppR.models import EmailCampaign

        campaigns = EmailCampaign.objects.filter(
            status__in=['scheduled', 'running']
        ).order_by('start_at')

        if not campaigns.exists():
            self.stdout.write('  (no active EmailCampaign records)')
            return

        for c in campaigns:
            sends_left = c.total_sends - c.sends_completed
            send_times = c.compute_send_datetimes()

            # Find next unsent time
            next_send = next(
                (dt for i, dt in enumerate(send_times) if i >= c.sends_completed),
                None,
            )

            if next_send and next_send <= now:
                tag = self.style.ERROR('OVERDUE')
            elif next_send:
                delta = next_send - now
                hrs   = int(delta.total_seconds() // 3600)
                mins  = int((delta.total_seconds() % 3600) // 60)
                tag   = self.style.SUCCESS(f'next in {hrs}h {mins}m')
            else:
                tag = self.style.WARNING('COMPLETE')

            self.stdout.write(
                f'  [{tag}] "{c.name}" status={c.status} '
                f'({c.sends_completed}/{c.total_sends} sent, {sends_left} remaining)'
            )
            if next_send:
                self.stdout.write(
                    f'    next send: {next_send.strftime("%Y-%m-%d %H:%M %Z")}'
                )
            if verbose:
                self.stdout.write(f'    recipients: {c.recipients}')
                self.stdout.write(f'    beat_task_ids: {c.beat_task_ids}')
