"""
Remove limit_choices_to from GCEstimate.gc_contractor and GCEstimate.estimator
so any active contractor can be assigned as GC or estimator regardless of role.

This is a schema-level no-op (limit_choices_to only enforces choices in forms,
not at the DB level), but Django's migration framework still records the state change.
"""
from django.db import migrations
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0002_pricelistversion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gcestimate',
            name='gc_contractor',
            field=__import__('django.db.models', fromlist=['ForeignKey']).ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='gc_estimates',
                to='contractor_hub.contractor',
            ),
        ),
        migrations.AlterField(
            model_name='gcestimate',
            name='estimator',
            field=__import__('django.db.models', fromlist=['ForeignKey']).ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='estimated_jobs',
                to='contractor_hub.contractor',
            ),
        ),
    ]
