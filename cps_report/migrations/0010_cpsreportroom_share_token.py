import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0009_cpssession_pricing_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportroom',
            name='share_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True),
        ),
    ]
