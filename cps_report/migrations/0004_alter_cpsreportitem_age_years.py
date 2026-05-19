from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0003_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cpsreportitem',
            name='age_years',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
