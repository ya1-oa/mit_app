# Generated manually to make lease date fields nullable

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0017_fix_leaseactivity_lease_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lease',
            name='lease_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='lease',
            name='lease_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='lease',
            name='monthly_rent',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
