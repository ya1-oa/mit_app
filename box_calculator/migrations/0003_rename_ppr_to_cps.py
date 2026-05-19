from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('box_calculator', '0002_ppr_models'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='BoxCalcPPRSession',
            new_name='BoxCalcCPSSession',
        ),
        migrations.RenameModel(
            old_name='BoxCalcPPRRoom',
            new_name='BoxCalcCPSRoom',
        ),
        migrations.AlterField(
            model_name='boxcalccpssession',
            name='client',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='cps_sessions',
                to='docsAppR.client',
            ),
        ),
    ]
