from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportroom',
            name='encircle_room_label',
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
