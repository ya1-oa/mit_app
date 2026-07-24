from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0015_remove_ppr_box_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportsession',
            name='ai_model',
            field=models.CharField(
                default='claude-haiku-4-5-20251001',
                max_length=60,
                choices=[
                    ('claude-haiku-4-5-20251001', 'Haiku 4.5 — faster / cheaper'),
                    ('claude-sonnet-5', 'Sonnet 5 — higher accuracy'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='search_query',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='price_options',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='price_source_url',
            field=models.CharField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='price_source_vendor',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='price_selection_reason',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='price_method',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='cpsreportitem',
            name='price_needs_review',
            field=models.BooleanField(default=False),
        ),
    ]
