from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0010_cpsreportroom_share_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportroom',
            name='analyzed_image_urls',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
