from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0037_encircle_sync'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='ale_lease_agreement_date',
            field=models.DateField(
                blank=True, null=True,
                help_text='Lease Agreement Date (date lease is signed/effective)',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_inspection_fee',
            field=models.DecimalField(
                blank=True, null=True,
                max_digits=10, decimal_places=2,
                help_text='Final Inspection & Cleanup Fee',
            ),
        ),
    ]
