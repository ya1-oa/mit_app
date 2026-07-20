from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0012_cpsreportitem_source_image_urls'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportsession',
            name='room_sources',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='cpsreportroom',
            name='room_source',
            field=models.CharField(
                choices=[
                    ('primary', 'Primary (400s PPR / 300s CPS)'),
                    ('overview', 'Overview (100s)'),
                    ('bu', 'Backup Photos (BU)'),
                ],
                default='primary',
                max_length=20,
            ),
        ),
    ]
