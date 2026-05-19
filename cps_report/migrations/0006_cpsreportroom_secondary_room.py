from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0005_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportroom',
            name='encircle_room_id_secondary',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='cpsreportroom',
            name='encircle_room_label_secondary',
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
