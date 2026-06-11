from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0008_cpsreportitem_structural'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportsession',
            name='pricing_mode',
            field=models.CharField(
                choices=[('normal', 'Normal Pricing'), ('premium', 'Premium / High-End Pricing')],
                default='normal',
                max_length=16,
            ),
        ),
    ]
