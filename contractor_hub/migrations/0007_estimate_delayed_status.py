from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0006_boxcountreport_use_client'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gcestimate',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('submitted', 'Submitted to Insurance'),
                    ('approved', 'Approved'),
                    ('billed', 'Billed'),
                    ('delayed', 'Delayed'),
                    ('paid', 'Paid'),
                    ('cancelled', 'Cancelled'),
                ],
                default='draft', max_length=20,
            ),
        ),
        migrations.RemoveConstraint(
            model_name='gcestimate',
            name='one_active_estimate_per_client',
        ),
        migrations.AddConstraint(
            model_name='gcestimate',
            constraint=models.UniqueConstraint(
                condition=models.Q(('status__in', ['draft', 'submitted', 'approved', 'billed', 'delayed'])),
                fields=('client',),
                name='one_active_estimate_per_client',
            ),
        ),
    ]
