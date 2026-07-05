"""
dev_hub/models.py

Internal project management hub.  Tracks development status across all
platform sub-apps, with task management and automated client notification.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# AppModule
# ---------------------------------------------------------------------------

class AppModule(models.Model):
    STATUS_CHOICES = [
        ('in_dev',  'In Development'),
        ('alpha',   'Alpha'),
        ('beta',    'Beta'),
        ('stable',  'Stable'),
    ]

    name        = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(max_length=110, unique=True, blank=True)
    description = models.TextField(blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_dev')
    order       = models.PositiveIntegerField(default=0, help_text='Display order on dashboard')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    # ── Computed helpers ──────────────────────────────────────────────────

    @property
    def completion_pct(self):
        """Percentage of tasks with status='done'."""
        total = self.tasks.count()
        if not total:
            return 0
        done = self.tasks.filter(status='done').count()
        return round(done / total * 100)

    @property
    def task_counts(self):
        qs = self.tasks
        return {
            'total':       qs.count(),
            'done':        qs.filter(status='done').count(),
            'in_progress': qs.filter(status='in_progress').count(),
            'todo':        qs.filter(status='todo').count(),
        }

    @property
    def status_color(self):
        return {
            'in_dev': 'secondary',
            'alpha':  'warning',
            'beta':   'info',
            'stable': 'success',
        }.get(self.status, 'secondary')

    @property
    def last_report(self):
        return self.progress_reports.order_by('-sent_at').first()


# ---------------------------------------------------------------------------
# DevTask
# ---------------------------------------------------------------------------

class DevTask(models.Model):
    TASK_TYPE_CHOICES = [
        ('feature',     'Feature'),
        ('bug',         'Bug Fix'),
        ('test',        'Test'),
        ('secretarial', 'Secretarial'),
    ]
    STATUS_CHOICES = [
        ('todo',        'To Do'),
        ('in_progress', 'In Progress'),
        ('done',        'Done'),
    ]

    id                    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module                = models.ForeignKey(AppModule, on_delete=models.CASCADE,
                                               related_name='tasks')
    title                 = models.CharField(max_length=255)
    description           = models.TextField(blank=True)
    task_type             = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES,
                                              default='feature')
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                              default='todo')
    completed_at          = models.DateTimeField(null=True, blank=True)
    added_by              = models.ForeignKey(settings.AUTH_USER_MODEL,
                                               on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name='dev_tasks_added')
    notify_on_complete    = models.BooleanField(
        default=False,
        help_text='Send email when this task is marked done',
    )
    queue_for_weekly_report = models.BooleanField(
        default=False,
        help_text='Include in next Monday weekly progress report',
    )
    order                 = models.PositiveIntegerField(default=0)
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'[{self.module.name}] {self.title}'

    @property
    def is_secretarial(self):
        return self.task_type == 'secretarial'

    @property
    def status_color(self):
        return {'todo': 'secondary', 'in_progress': 'warning', 'done': 'success'}.get(self.status, 'secondary')

    def mark_done(self):
        """Mark the task done and set completed_at. Does NOT send notifications."""
        self.status       = 'done'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_todo(self):
        """Revert a done task back to todo."""
        self.status       = 'todo'
        self.completed_at = None
        self.save(update_fields=['status', 'completed_at', 'updated_at'])


# ---------------------------------------------------------------------------
# TestCoverage
# ---------------------------------------------------------------------------

class TestCoverage(models.Model):
    module        = models.OneToOneField(AppModule, on_delete=models.CASCADE,
                                          related_name='test_coverage')
    unit_tested   = models.BooleanField(default=False)
    human_tested  = models.BooleanField(default=False)
    coverage_pct  = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                         help_text='Automated test coverage percentage')
    notes         = models.TextField(blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.module.name} — coverage'


# ---------------------------------------------------------------------------
# ProgressReport
# ---------------------------------------------------------------------------

class ProgressReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ('weekly', 'Weekly Automated'),
        ('adhoc',  'Ad-hoc'),
    ]

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sent_at           = models.DateTimeField(auto_now_add=True)
    report_type       = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES,
                                          default='weekly')
    modules_snapshot  = models.JSONField(
        help_text='Snapshot of all module statuses and queued tasks at send time',
    )
    email_log         = models.ForeignKey(
        'docsAppR.SentEmail',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='progress_reports',
    )
    sent_by           = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    response_notes    = models.TextField(
        blank=True,
        help_text='Owner fills in after the client responds',
    )

    # M2M to AppModule so we can show "last report" per module
    modules           = models.ManyToManyField(AppModule, blank=True,
                                                related_name='progress_reports')

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.get_report_type_display()} report — {self.sent_at.strftime("%Y-%m-%d")}'


# ---------------------------------------------------------------------------
# WeeklyReport — internal weekly + daily dev progress checklist
# ---------------------------------------------------------------------------

class WeeklyReport(models.Model):
    """
    Editable weekly + daily development progress report for the dev team.

    Renders as a dynamic HTML page (the current weekday is highlighted so the
    same document can be reused throughout the week) and exports to PDF.

    Structure mirrors the client-facing progress template:
      - weekly_objectives / next_week_priorities : checklist of {text, done}
      - days                                     : per-weekday content blocks
      - completed_deliverables                   : flat bullet list
    """
    WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title          = models.CharField(max_length=200,
                                       default='Software Development Progress Report')
    week_of        = models.DateField(help_text='Monday of the report week')
    overall_status = models.CharField(max_length=100, default='In Progress')

    # Checklist items: [{"text": str, "done": bool}, ...]
    weekly_objectives    = models.JSONField(default=list, blank=True)
    next_week_priorities = models.JSONField(default=list, blank=True)

    # Flat bullet list: ["...", ...]
    completed_deliverables = models.JSONField(default=list, blank=True)

    # Per-day content keyed by weekday name:
    #   {"Monday": {"objectives": [...], "accomplishments": [...], "goal_progress": [...]}}
    days           = models.JSONField(default=dict, blank=True)

    created_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name='weekly_reports')
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-week_of', '-created_at']

    def __str__(self):
        return f'{self.title} — week of {self.week_of:%b %d, %Y}'

    @property
    def week_of_display(self):
        return self.week_of.strftime('%B %d, %Y') if self.week_of else ''

    def day_rows(self):
        """Ordered Mon–Fri rows with their content, for template iteration."""
        rows = []
        for name in self.WEEKDAYS:
            content = (self.days or {}).get(name, {})
            rows.append({
                'name':            name,
                'objectives':      content.get('objectives', []),
                'accomplishments': content.get('accomplishments', []),
                'goal_progress':   content.get('goal_progress', []),
            })
        return rows

    @property
    def objectives_done_count(self):
        return sum(1 for o in (self.weekly_objectives or []) if o.get('done'))

    @staticmethod
    def default_payload():
        """Starting content for a new report (the standard team template)."""
        return {
            'overall_status': 'In Progress',
            'weekly_objectives': [
                {'text': 'Implement signature signing feature for lease system', 'done': True},
                {'text': 'Add new room to default room list', 'done': True},
                {'text': 'Remove incorrect "$8,000" value from basic room list display', 'done': True},
                {'text': 'Enable drag-and-drop room management', 'done': True},
                {'text': 'Automatically update room numbering after reordering or removal', 'done': True},
            ],
            'days': {
                'Monday': {
                    'objectives': ['Implement lease signature functionality',
                                   'Begin room list improvements'],
                    'accomplishments': [
                        'Implemented signature signing functionality for the lease system.',
                        'Added support for capturing and storing lease signatures.',
                        'Began review of room list management workflow.'],
                    'goal_progress': ['Signature feature completed.',
                                      'Room management improvements in progress.'],
                },
                'Tuesday': {
                    'objectives': ['Add new room option to default room list',
                                   'Remove incorrect room list values'],
                    'accomplishments': [
                        'Added new room to the default room list.',
                        'Removed the incorrect "$8,000" value from appearing in the basic room list.',
                        'Performed validation testing on room list display.'],
                    'goal_progress': ['Room list updates completed.',
                                      'Preparing drag-and-drop enhancements.'],
                },
                'Wednesday': {
                    'objectives': ['Implement drag-and-drop room management'],
                    'accomplishments': [
                        'Added drag-and-drop functionality for room ordering.',
                        'Users can now rearrange rooms directly within the interface.',
                        'Improved room management workflow and usability.'],
                    'goal_progress': ['Core drag-and-drop functionality completed.'],
                },
                'Thursday': {
                    'objectives': ['Implement automatic room number updates',
                                   'Test room removal workflow'],
                    'accomplishments': [
                        'Implemented automatic room numbering updates after room reordering.',
                        'Implemented automatic numbering updates after room removal.',
                        'Tested room sequence integrity across multiple scenarios.'],
                    'goal_progress': ['Room management workflow completed.'],
                },
                'Friday': {
                    'objectives': ['Testing and final validation',
                                   'Bug fixes and deployment readiness'],
                    'accomplishments': [
                        'Completed feature testing across lease and room management modules.',
                        'Resolved minor UI and workflow issues.',
                        'Verified successful operation of all completed weekly objectives.'],
                    'goal_progress': ['All planned objectives completed.',
                                      'Features ready for client review and acceptance.'],
                },
            },
            'completed_deliverables': [
                'Lease signature signing feature implemented',
                'New room added to default room list',
                'Removed incorrect "$8,000" value from room list display',
                'Drag-and-drop room management functionality implemented',
                'Automatic room numbering updates after reordering or deletion',
            ],
            'next_week_priorities': [
                {'text': 'Client feedback review', 'done': False},
                {'text': 'Additional UI improvements', 'done': False},
                {'text': 'Workflow optimizations', 'done': False},
                {'text': 'Bug fixes and enhancements identified during testing', 'done': False},
            ],
        }
