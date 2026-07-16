from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0011_cpsreportroom_analyzed_image_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportitem',
            name='source_image_urls',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
