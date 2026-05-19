import uuid

from django.db import migrations, models


def _populate_share_tokens(apps, schema_editor):
    """Assign a unique UUID to every existing session row."""
    CPSReportSession = apps.get_model('cps_report', 'CPSReportSession')
    for session in CPSReportSession.objects.filter(share_token__isnull=True):
        session.share_token = uuid.uuid4()
        session.save(update_fields=['share_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0006_cpsreportroom_secondary_room'),
    ]

    operations = [
        # ── share_token: 3-step to safely backfill existing rows ──────────────
        # 1. Add as nullable — Django can set NULL for all existing rows safely.
        migrations.AddField(
            model_name='cpsreportsession',
            name='share_token',
            field=models.UUIDField(null=True, blank=True),
        ),
        # 2. Generate a distinct UUID for every existing row.
        migrations.RunPython(_populate_share_tokens, migrations.RunPython.noop),
        # 3. Now enforce non-null + unique (all values already exist and differ).
        migrations.AlterField(
            model_name='cpsreportsession',
            name='share_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),

        # ── Signature fields on CPSReportRoom ─────────────────────────────────
        migrations.AddField(
            model_name='cpsreportroom',
            name='signature_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='cpsreportroom',
            name='signed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cpsreportroom',
            name='signer_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
    ]
