from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0003_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportsession',
            name='celery_task_id',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
