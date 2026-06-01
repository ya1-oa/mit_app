import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0025_generatedfile_uploadedattachment_sentemail_extensions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Fix EmailSchedule: add last_sent + send_count ─────────────────────
        migrations.AddField(
            model_name='emailschedule',
            name='last_sent',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='emailschedule',
            name='send_count',
            field=models.IntegerField(default=0),
        ),

        # ── EmailCampaign ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='EmailCampaign',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('subject', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('recipients', models.JSONField(default=list)),
                ('cc', models.JSONField(blank=True, default=list)),
                ('bcc', models.JSONField(blank=True, default=list)),
                ('total_sends', models.PositiveIntegerField()),
                ('interval_value', models.PositiveIntegerField()),
                ('interval_unit', models.CharField(
                    choices=[('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks')],
                    default='days', max_length=10,
                )),
                ('start_at', models.DateTimeField()),
                ('status', models.CharField(
                    choices=[
                        ('draft',     'Draft'),
                        ('scheduled', 'Scheduled'),
                        ('running',   'Running'),
                        ('complete',  'Complete'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='draft', max_length=20,
                )),
                ('sends_completed', models.PositiveIntegerField(default=0)),
                ('beat_task_ids', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to=settings.AUTH_USER_MODEL,
                )),
                ('sent_emails', models.ManyToManyField(
                    blank=True,
                    related_name='campaigns',
                    to='docsAppR.sentemail',
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
