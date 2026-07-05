import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0031_worktype_ale_and_leasetask'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailLinkClick',
            fields=[
                ('id', models.UUIDField(default=None, editable=False, primary_key=True, serialize=False)),
                ('url', models.URLField()),
                ('clicked_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('sent_email', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='link_clicks', to='docsAppR.sentemail')),
            ],
            options={'ordering': ['-clicked_at']},
        ),
        migrations.CreateModel(
            name='EmailBatch',
            fields=[
                ('id', models.UUIDField(default=None, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='e.g. "July Follow-up Campaign"', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('claim', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='email_batches', to='docsAppR.client')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ScheduledEmail',
            fields=[
                ('id', models.UUIDField(default=None, editable=False, primary_key=True, serialize=False)),
                ('subject', models.TextField()),
                ('body', models.TextField()),
                ('recipients', models.JSONField(help_text='List of email addresses')),
                ('cc', models.JSONField(blank=True, default=list)),
                ('bcc', models.JSONField(blank=True, default=list)),
                ('scheduled_send_time', models.DateTimeField(help_text='When this email should be sent')),
                ('is_sent', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('has_followup', models.BooleanField(default=False)),
                ('followup_trigger', models.CharField(
                    blank=True,
                    choices=[('time', 'After X days'), ('unopened', 'If not opened after X days'), ('opened', 'When opened')],
                    help_text='How to trigger the follow-up',
                    max_length=20,
                )),
                ('followup_days', models.PositiveIntegerField(blank=True, help_text='Days to wait before follow-up', null=True)),
                ('followup_subject', models.TextField(blank=True, help_text='Subject of follow-up email')),
                ('followup_body', models.TextField(blank=True, help_text='Body of follow-up email')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scheduled_emails', to='docsAppR.emailbatch')),
                ('generated_files', models.ManyToManyField(blank=True, to='docsAppR.generatedfile')),
                ('uploaded_attachments', models.ManyToManyField(blank=True, to='docsAppR.uploadedattachment')),
            ],
            options={'ordering': ['scheduled_send_time']},
        ),
        migrations.AddIndex(
            model_name='emaillinkclick',
            index=models.Index(fields=['sent_email', 'clicked_at'], name='docsAppR_em_sent_em_idx'),
        ),
        migrations.AddIndex(
            model_name='scheduledemail',
            index=models.Index(fields=['batch', 'is_sent'], name='docsAppR_sc_batch_i_idx'),
        ),
        migrations.AddIndex(
            model_name='scheduledemail',
            index=models.Index(fields=['scheduled_send_time', 'is_sent'], name='docsAppR_sc_schedul_idx'),
        ),
    ]
