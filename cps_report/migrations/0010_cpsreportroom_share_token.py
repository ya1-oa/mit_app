import uuid
from django.db import migrations, models


def _populate_room_tokens(apps, schema_editor):
    CPSReportRoom = apps.get_model('cps_report', 'CPSReportRoom')
    for room in CPSReportRoom.objects.all():
        room.share_token = uuid.uuid4()
        room.save(update_fields=['share_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0009_cpssession_pricing_mode'),
    ]

    operations = [
        # Step 1 — add nullable, non-unique so SQLite doesn't need a unique default
        migrations.AddField(
            model_name='cpsreportroom',
            name='share_token',
            field=models.UUIDField(null=True, blank=True),
        ),
        # Step 2 — stamp each existing row with its own UUID
        migrations.RunPython(_populate_room_tokens, migrations.RunPython.noop),
        # Step 3 — now safe to make it required and unique
        migrations.AlterField(
            model_name='cpsreportroom',
            name='share_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
