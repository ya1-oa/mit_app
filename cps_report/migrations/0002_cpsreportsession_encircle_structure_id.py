from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cps_report', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cpsreportsession',
            name='encircle_structure_id',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
