"""
Migration 0037: Encircle sync infrastructure

1. Add new encircle_* metadata fields to Client:
   - encircle_permalink_url  — link to the claim in the Encircle web app
   - encircle_date_created   — when the claim was created in Encircle
   - encircle_project_manager
   - encircle_loss_details
   - encircle_cat_code
   - encircle_assignment_id
   - encircle_last_synced_at — last inbound sync timestamp

2. Add db_index=True to encircle_claim_id for fast lookup during sync.

3. Create EncircleSyncLog model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0036_clear_autofilled_special_notes'),
    ]

    operations = [
        # ── Client: new Encircle metadata fields ─────────────────────────────
        migrations.AddField(
            model_name='client',
            name='encircle_permalink_url',
            field=models.URLField(
                max_length=500, blank=True,
                help_text='Direct link to this claim in the Encircle web app',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='encircle_date_created',
            field=models.DateTimeField(
                null=True, blank=True,
                help_text='When this claim was first created in Encircle',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='encircle_project_manager',
            field=models.CharField(
                max_length=255, blank=True,
                help_text='Project manager name as set in Encircle',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='encircle_loss_details',
            field=models.TextField(
                blank=True,
                help_text='Free-text loss description from Encircle',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='encircle_cat_code',
            field=models.CharField(
                max_length=100, blank=True,
                help_text='Catastrophe code from Encircle',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='encircle_assignment_id',
            field=models.CharField(
                max_length=255, blank=True,
                help_text='Assignment identifier from Encircle',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='encircle_last_synced_at',
            field=models.DateTimeField(
                null=True, blank=True,
                help_text='Last time this claim was pulled FROM Encircle (inbound sync)',
            ),
        ),
        # ── Client: add index to encircle_claim_id ────────────────────────────
        migrations.AlterField(
            model_name='client',
            name='encircle_claim_id',
            field=models.CharField(
                max_length=100, blank=True, null=True,
                help_text='Encircle property claim ID (set after push to Encircle)',
                db_index=True,
            ),
        ),
        # ── EncircleSyncLog model ─────────────────────────────────────────────
        migrations.CreateModel(
            name='EncircleSyncLog',
            fields=[
                ('id',              models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('started_at',      models.DateTimeField(auto_now_add=True, db_index=True)),
                ('completed_at',    models.DateTimeField(null=True, blank=True)),
                ('status',          models.CharField(
                    max_length=20,
                    choices=[
                        ('running', 'Running'),
                        ('success', 'Success'),
                        ('failed',  'Failed'),
                        ('partial', 'Partial (some errors)'),
                    ],
                    default='running',
                )),
                ('triggered_by',    models.CharField(max_length=50, default='schedule')),
                ('claims_processed', models.IntegerField(default=0)),
                ('claims_created',   models.IntegerField(default=0)),
                ('claims_updated',   models.IntegerField(default=0)),
                ('error_count',      models.IntegerField(default=0)),
                ('error_details',    models.JSONField(default=list, blank=True)),
            ],
            options={
                'verbose_name':        'Encircle Sync Log',
                'verbose_name_plural': 'Encircle Sync Logs',
                'ordering':            ['-started_at'],
            },
        ),
    ]
