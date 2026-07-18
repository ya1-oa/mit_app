from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('box_calculator', '0007_cps_saved_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='boxcalccpsroom',
            name='image_urls',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='boxcalccpsreport',
            name='format',
            field=models.CharField(
                choices=[('pdf', 'PDF'), ('excel', 'Excel'), ('photo_pdf', 'Photo PDF')],
                max_length=10,
            ),
        ),
    ]
