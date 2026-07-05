import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('dev_hub', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WeeklyReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(default='Software Development Progress Report', max_length=200)),
                ('week_of', models.DateField(help_text='Monday of the report week')),
                ('overall_status', models.CharField(default='In Progress', max_length=100)),
                ('weekly_objectives', models.JSONField(blank=True, default=list)),
                ('next_week_priorities', models.JSONField(blank=True, default=list)),
                ('completed_deliverables', models.JSONField(blank=True, default=list)),
                ('days', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='weekly_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-week_of', '-created_at'],
            },
        ),
    ]
