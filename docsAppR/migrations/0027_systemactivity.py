import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0026_emailcampaign_emailschedule_tracking'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemActivity',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action_type', models.CharField(
                    choices=[
                        ('email_sent', 'Email Sent'),
                        ('package_sent', 'Package Sent'),
                        ('demand_letter', 'Demand Letter Generated'),
                        ('lease_created', 'Lease Created'),
                        ('lease_status_changed', 'Lease Status Changed'),
                        ('document_generated', 'Document Generated'),
                        ('pdf_generated', 'PDF Generated'),
                        ('note_added', 'Note Added'),
                        ('claim_created', 'Claim Created'),
                        ('file_uploaded', 'File Uploaded'),
                        ('login', 'User Login'),
                        ('ale_sync', 'ALE Data Synced'),
                        ('other', 'Other'),
                    ],
                    db_index=True, default='other', max_length=50,
                )),
                ('description', models.TextField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('performed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='system_activities',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('related_client', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='system_activities',
                    to='docsAppR.client',
                )),
                ('related_lease', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='system_activities',
                    to='docsAppR.lease',
                )),
            ],
            options={
                'verbose_name': 'System Activity',
                'verbose_name_plural': 'System Activities',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='systemactivity',
            index=models.Index(fields=['-created_at'], name='sysact_created_idx'),
        ),
        migrations.AddIndex(
            model_name='systemactivity',
            index=models.Index(fields=['performed_by', '-created_at'], name='sysact_user_idx'),
        ),
        migrations.AddIndex(
            model_name='systemactivity',
            index=models.Index(fields=['action_type', '-created_at'], name='sysact_type_idx'),
        ),
    ]
