"""
Migration 0006 — Move BoxCountReport from GCEstimate → docsAppR.Client.

Why: box counts belong to the homeowner's claim, not a specific GC estimate.
     Every client will get a BoxCountReport (manually or via AI in future).
"""
import django.db.models.deletion
from django.db import migrations, models


def migrate_estimate_to_client(apps, schema_editor):
    """Carry forward existing data: bcr.client = bcr.estimate.client."""
    BoxCountReport = apps.get_model('contractor_hub', 'BoxCountReport')
    for bcr in BoxCountReport.objects.select_related('estimate__client').all():
        if bcr.estimate_id and bcr.estimate:
            try:
                bcr.client_id = bcr.estimate.client_id
                bcr.save(update_fields=['client_id'])
            except Exception:
                pass  # skip if estimate or client is gone


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0005_rename_ch_contractor_role_idx_contractor__role_c6a7e0_idx_and_more'),
        ('docsAppR', '0001_initial'),
    ]

    operations = [
        # 1. Add new client FK (nullable so existing rows survive)
        migrations.AddField(
            model_name='boxcountreport',
            name='client',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='box_count_report',
                to='docsAppR.client',
            ),
        ),
        # 2. Populate client from existing estimate→client relationship
        migrations.RunPython(migrate_estimate_to_client, migrations.RunPython.noop),
        # 3. Drop the old estimate FK
        migrations.RemoveField(
            model_name='boxcountreport',
            name='estimate',
        ),
        # 4. Make client non-nullable now that old FK is gone
        migrations.AlterField(
            model_name='boxcountreport',
            name='client',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='box_count_report',
                to='docsAppR.client',
            ),
        ),
    ]
