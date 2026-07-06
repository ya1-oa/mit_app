from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('box_calculator', '0005_tenant_fks'),
    ]

    operations = [
        migrations.AddField(
            model_name='boxcalccpsroom',
            name='picture_mirror',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
