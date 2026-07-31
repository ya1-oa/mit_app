from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0016_live_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportsession',
            name='archived',
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
