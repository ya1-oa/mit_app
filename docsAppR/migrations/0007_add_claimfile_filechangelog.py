# Generated manually - Add ClaimFile and FileChangeLog models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0006_remove_room_sync_status'),
    ]

    operations = [
        # Create ClaimFile model
        migrations.CreateModel(
            name='ClaimFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file_type', models.CharField(choices=[('01-INFO', '01-INFO - General Information'), ('01-ROOMS', '01-ROOMS - Room Data'), ('02-INS-CO', '02-INS-CO - Insurance Company'), ('30-MASTER', '30-MASTER - Master Lists'), ('50-CONTRACT', '50-CONTRACT - Contracts'), ('60-SCOPE', '60-SCOPE - Scope Documents'), ('82-MIT', '82-MIT - Mitigation'), ('92-CPS', '92-CPS - Contents Processing'), ('94-INVOICE', '94-INVOICE - Invoices'), ('OTHER', 'Other')], max_length=20)),
                ('file_name', models.CharField(max_length=255)),
                ('file_path', models.CharField(help_text='Relative path from claim folder root', max_length=500)),
                ('file_size', models.PositiveIntegerField(help_text='File size in bytes')),
                ('file_hash', models.CharField(blank=True, help_text='MD5 hash for change detection', max_length=64)),
                ('mime_type', models.CharField(blank=True, max_length=100)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('is_active', models.BooleanField(default=True, help_text='False if file is deleted')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='claim_files', to='docsAppR.client')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_claim_files', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='modified_claim_files', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['client', 'file_type', 'file_name'],
            },
        ),

        # Create FileChangeLog model
        migrations.CreateModel(
            name='FileChangeLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('created', 'Created'), ('modified', 'Modified'), ('deleted', 'Deleted'), ('renamed', 'Renamed'), ('moved', 'Moved')], max_length=20)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('old_hash', models.CharField(blank=True, help_text='File hash before change', max_length=64)),
                ('new_hash', models.CharField(blank=True, help_text='File hash after change', max_length=64)),
                ('old_filename', models.CharField(blank=True, max_length=255)),
                ('new_filename', models.CharField(blank=True, max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('changed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('claim_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='change_logs', to='docsAppR.claimfile')),
            ],
            options={
                'ordering': ['-changed_at'],
            },
        ),

        # Add indexes
        migrations.AddIndex(
            model_name='filechangelog',
            index=models.Index(fields=['claim_file', '-changed_at'], name='docsAppR_fi_claim_f_cd2336_idx'),
        ),
        migrations.AddIndex(
            model_name='filechangelog',
            index=models.Index(fields=['changed_by'], name='docsAppR_fi_changed_90fde8_idx'),
        ),
        migrations.AddIndex(
            model_name='filechangelog',
            index=models.Index(fields=['-changed_at'], name='docsAppR_fi_changed_e76f45_idx'),
        ),
        migrations.AddIndex(
            model_name='claimfile',
            index=models.Index(fields=['client', 'file_type'], name='docsAppR_cl_client__8d2a07_idx'),
        ),
        migrations.AddIndex(
            model_name='claimfile',
            index=models.Index(fields=['file_hash'], name='docsAppR_cl_file_ha_21f046_idx'),
        ),
        migrations.AddIndex(
            model_name='claimfile',
            index=models.Index(fields=['is_active'], name='docsAppR_cl_is_acti_0004d0_idx'),
        ),
    ]
