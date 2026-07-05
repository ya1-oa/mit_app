import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0024_room_is_encircle_entry'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── GeneratedFile ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GeneratedFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('file_path', models.CharField(
                    help_text='Absolute server path to the file', max_length=1000)),
                ('mime_type', models.CharField(
                    default='application/octet-stream', max_length=100)),
                ('category', models.CharField(
                    choices=[
                        ('pdf',     'PDF Report'),
                        ('excel',   'Excel Spreadsheet'),
                        ('invoice', 'Invoice'),
                        ('other',   'Other'),
                    ],
                    default='other', max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='generated_files',
                    to='docsAppR.client',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='generated_files',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ── UploadedAttachment ────────────────────────────────────────────────
        migrations.CreateModel(
            name='UploadedAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='email_attachments/%Y/%m/')),
                ('original_name', models.CharField(max_length=255)),
                ('mime_type', models.CharField(
                    default='application/octet-stream', max_length=100)),
                ('size', models.PositiveIntegerField(
                    default=0, help_text='File size in bytes')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='uploaded_attachments',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-uploaded_at']},
        ),

        # ── SentEmail: CC / BCC ───────────────────────────────────────────────
        migrations.AddField(
            model_name='sentemail',
            name='cc',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='sentemail',
            name='bcc',
            field=models.JSONField(blank=True, default=list),
        ),

        # ── SentEmail: claim FK ───────────────────────────────────────────────
        migrations.AddField(
            model_name='sentemail',
            name='claim',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sent_emails',
                to='docsAppR.client',
            ),
        ),

        # ── SentEmail: new attachment M2Ms ────────────────────────────────────
        migrations.AddField(
            model_name='sentemail',
            name='generated_files',
            field=models.ManyToManyField(
                blank=True,
                related_name='sent_in_emails',
                to='docsAppR.generatedfile',
            ),
        ),
        migrations.AddField(
            model_name='sentemail',
            name='uploaded_attachments',
            field=models.ManyToManyField(
                blank=True,
                related_name='sent_in_emails',
                to='docsAppR.uploadedattachment',
            ),
        ),
    ]
