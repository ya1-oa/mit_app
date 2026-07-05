from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0007_signatures'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportitem',
            name='structural',
            field=models.BooleanField(default=False),
        ),
    ]
