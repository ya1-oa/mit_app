from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0022_update_worktype_6000s_to_8000s'),
    ]

    operations = [
        migrations.AlterField(
            model_name='roomworktypevalue',
            name='value_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'No Value'),
                    ('TBD', 'To Be Determined'),
                    ('NA', 'Not Applicable'),
                    ('LOS', 'Line Of Sight'),
                    ('TRAVEL', 'Travel Area'),
                    ('DAMAGED', 'Damaged Room'),
                ],
                default='',
                max_length=10,
            ),
        ),
    ]
