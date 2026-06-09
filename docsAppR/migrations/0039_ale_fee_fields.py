from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0038_ale_agreement_date_inspection_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='ale_late_fee',
            field=models.DecimalField(
                blank=True, null=True, max_digits=10, decimal_places=2,
                help_text='Late Fee Amount (default $50)',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_late_fee_start_day',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Day of month late fee kicks in (default 5)',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_nsf_fee',
            field=models.DecimalField(
                blank=True, null=True, max_digits=10, decimal_places=2,
                help_text='NSF / Returned Check Fee (default $35)',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_rent_due_day',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Day of month rent is due (default 1)',
            ),
        ),
    ]
