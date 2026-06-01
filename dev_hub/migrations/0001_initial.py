import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('docsAppR', '__first__'),
    ]

    operations = [
        # ── AppModule ─────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='AppModule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name',        models.CharField(max_length=100, unique=True)),
                ('slug',        models.SlugField(blank=True, max_length=110, unique=True)),
                ('description', models.TextField(blank=True)),
                ('status',      models.CharField(
                    choices=[
                        ('in_dev', 'In Development'), ('alpha', 'Alpha'),
                        ('beta', 'Beta'), ('stable', 'Stable'),
                    ],
                    default='in_dev', max_length=20,
                )),
                ('order',       models.PositiveIntegerField(default=0)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('updated_at',  models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['order', 'name']},
        ),

        # ── DevTask ───────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='DevTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('title',       models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('task_type',   models.CharField(
                    choices=[
                        ('feature', 'Feature'), ('bug', 'Bug Fix'),
                        ('test', 'Test'), ('secretarial', 'Secretarial'),
                    ],
                    default='feature', max_length=20,
                )),
                ('status',      models.CharField(
                    choices=[
                        ('todo', 'To Do'), ('in_progress', 'In Progress'), ('done', 'Done'),
                    ],
                    default='todo', max_length=20,
                )),
                ('completed_at',            models.DateTimeField(blank=True, null=True)),
                ('notify_on_complete',      models.BooleanField(default=False)),
                ('queue_for_weekly_report', models.BooleanField(default=False)),
                ('order',                   models.PositiveIntegerField(default=0)),
                ('created_at',              models.DateTimeField(auto_now_add=True)),
                ('updated_at',              models.DateTimeField(auto_now=True)),
                ('module', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tasks', to='dev_hub.appmodule',
                )),
                ('added_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='dev_tasks_added',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['order', 'created_at']},
        ),

        # ── TestCoverage ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='TestCoverage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('unit_tested',  models.BooleanField(default=False)),
                ('human_tested', models.BooleanField(default=False)),
                ('coverage_pct', models.DecimalField(decimal_places=2, default=0,
                                                      max_digits=5)),
                ('notes',        models.TextField(blank=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
                ('module', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='test_coverage', to='dev_hub.appmodule',
                )),
            ],
        ),

        # ── ProgressReport ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='ProgressReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('sent_at',           models.DateTimeField(auto_now_add=True)),
                ('report_type',       models.CharField(
                    choices=[('weekly', 'Weekly Automated'), ('adhoc', 'Ad-hoc')],
                    default='weekly', max_length=10,
                )),
                ('modules_snapshot',  models.JSONField()),
                ('response_notes',    models.TextField(blank=True)),
                ('email_log', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='progress_reports',
                    to='docsAppR.sentemail',
                )),
                ('sent_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('modules', models.ManyToManyField(
                    blank=True, related_name='progress_reports',
                    to='dev_hub.appmodule',
                )),
            ],
            options={'ordering': ['-sent_at']},
        ),
    ]
