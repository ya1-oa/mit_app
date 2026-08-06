from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mit_audit', '0002_hydroxyl_category_mitreferncephoto'),
    ]

    operations = [
        migrations.AddField(
            model_name='mitday3audit',
            name='is_test_run',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='mitday3audit',
            name='archived',
            field=models.BooleanField(default=False),
        ),
    ]
