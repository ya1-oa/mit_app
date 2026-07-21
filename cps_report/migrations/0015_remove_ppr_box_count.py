"""Drop the unused manual PPR box count tables.

The NON SALVAGEABLE / PPR Box Count is now a direct PDF export of the
client's existing CPS box count (BoxCalcCPSSession) — no separate
manual-entry models needed.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0014_ppr_box_count'),
    ]

    operations = [
        migrations.DeleteModel(name='PPRBoxCountRoom'),
        migrations.DeleteModel(name='PPRBoxCount'),
    ]
