from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('cps_report', '0017_session_archived'),
        ('docsAppR', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyReportConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Daily Status Report', max_length=100)),
                ('recipients', models.JSONField(default=list, help_text='List of email addresses to send the daily report to')),
                ('cc_emails', models.JSONField(blank=True, default=list)),
                ('send_hour', models.PositiveSmallIntegerField(default=7, help_text='Hour of day (0-23) in Eastern Time to send the daily report', validators=[django.core.validators.MaxValueValidator(23)])),
                ('is_active', models.BooleanField(default=True)),
                ('include_ppr_signatures', models.BooleanField(default=True, verbose_name='PPR Pending Signatures')),
                ('include_ppr_pricing', models.BooleanField(default=True, verbose_name='PPR Pricing Incomplete')),
                ('include_lease_sigs', models.BooleanField(default=True, verbose_name='Lease Signature Status')),
                ('include_lease_pipeline', models.BooleanField(default=True, verbose_name='Lease Pipeline Overview')),
                ('include_high_priority', models.BooleanField(default=True, verbose_name='High Priority Tracked Items')),
                ('attach_ppr_pdf', models.BooleanField(default=False, help_text='Attach generated Schedule of Loss PDF for each pending PPR session')),
                ('attach_lease_docs', models.BooleanField(default=False, help_text='Attach the latest lease document for each pending lease')),
                ('escalation_days', models.PositiveSmallIntegerField(default=3, help_text='After this many days pending, items are marked URGENT in the report')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Daily Report Configuration',
            },
        ),
        migrations.CreateModel(
            name='HighPriorityItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_type', models.CharField(choices=[('ppr', 'PPR Report'), ('lease', 'ALE Lease'), ('general', 'General Claim Item')], max_length=20)),
                ('priority_note', models.TextField(blank=True, help_text='Why is this being tracked?')),
                ('resolution_criteria', models.TextField(blank=True, help_text='What needs to happen to resolve this?')),
                ('demand_language', models.TextField(blank=True, help_text='Specific demand text to include in the daily email for this item')),
                ('auto_resolve', models.BooleanField(default=True)),
                ('is_resolved', models.BooleanField(db_index=True, default=False)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('added_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='added_high_priority_items', to=settings.AUTH_USER_MODEL)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='high_priority_report_items', to='docsAppR.client')),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='high_priority_items', to='daily_reports.dailyreportconfig')),
                ('lease', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='high_priority_flags', to='docsAppR.lease')),
                ('ppr_session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='high_priority_flags', to='cps_report.cpsreportsession')),
            ],
            options={
                'verbose_name': 'High Priority Tracked Item',
                'ordering': ['-added_at'],
            },
        ),
        migrations.CreateModel(
            name='OperationalTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('app', models.CharField(choices=[('cps_report', 'PPR / Schedule of Loss'), ('lease_manager', 'ALE Lease Manager'), ('claims', 'Claims'), ('equipment_checker', 'Equipment Checker'), ('box_calculator', 'Box Calculator'), ('encircle', 'Encircle Sync'), ('ar_tracking', 'AR Tracking'), ('contractor_hub', 'Contractor Hub'), ('scope_checklist', 'Scope Checklist'), ('email_manager', 'Email Manager'), ('dev_hub', 'Dev Hub'), ('general', 'General / Cross-App')], db_index=True, max_length=40)),
                ('title', models.CharField(max_length=300)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('todo', 'To Do'), ('in_progress', 'In Progress'), ('blocked', 'Blocked'), ('done', 'Done')], db_index=True, default='todo', max_length=20)),
                ('priority', models.CharField(choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('critical', 'Critical')], default='normal', max_length=20)),
                ('percent_complete', models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(100)])),
                ('due_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('queue_for_deep_report', models.BooleanField(db_index=True, default=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_operational_tasks', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_operational_tasks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Operational Task',
                'ordering': ['-priority', 'app', 'created_at'],
            },
        ),
        migrations.CreateModel(
            name='DailyReportLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_type', models.CharField(choices=[('daily', 'Daily High Priority Report'), ('deep', 'Weekly Deep Operations Report')], default='daily', max_length=10)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('recipients', models.JSONField(default=list)),
                ('total_items', models.PositiveIntegerField(default=0)),
                ('urgent_items', models.PositiveIntegerField(default=0)),
                ('email_success', models.BooleanField(default=False)),
                ('error_message', models.TextField(blank=True)),
                ('config', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='logs', to='daily_reports.dailyreportconfig')),
            ],
            options={
                'verbose_name': 'Report Log',
                'ordering': ['-sent_at'],
            },
        ),
    ]
