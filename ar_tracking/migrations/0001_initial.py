import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('docsAppR', '0041_tenant'),
        ('contractor_hub', '0007_estimate_delayed_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommunicationActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activity_type', models.CharField(choices=[
                    ('email_sent', 'Email Sent'),
                    ('manual_note', 'Manual Note'),
                    ('reply_logged', 'Reply Logged'),
                    ('status_changed', 'Status Changed'),
                    ('followup_scheduled', 'Follow-up Scheduled'),
                ], max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.PROTECT, to='docsAppR.tenant',
                )),
                ('estimate', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ar_activities', to='contractor_hub.gcestimate',
                )),
                ('sent_email', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ar_activities', to='docsAppR.sentemail',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name_plural': 'Communication activities',
            },
        ),
    ]
