from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0034_lease_esignature'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='ale_rental_security_deposit',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                null=True,
                blank=True,
                help_text='Security Deposit',
            ),
        ),
    ]
