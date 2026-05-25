# Migration: add PriceListVersion model + price_list_version FK on RateItem

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceListVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('code', models.CharField(
                    max_length=50, unique=True,
                    help_text='e.g. OHCL8X_MAR26  (market_month_year)',
                )),
                ('market', models.CharField(
                    max_length=100, blank=True,
                    help_text='e.g. Ohio - Cleveland',
                )),
                ('effective_date', models.DateField(
                    null=True, blank=True,
                    help_text='Month this price list took effect',
                )),
                ('source_file', models.CharField(
                    max_length=500, blank=True,
                    help_text='Original filename that was imported',
                )),
                ('total_items',    models.PositiveIntegerField(default=0)),
                ('items_created',  models.PositiveIntegerField(default=0)),
                ('items_updated',  models.PositiveIntegerField(default=0)),
                ('items_skipped',  models.PositiveIntegerField(default=0)),
                ('imported_at',    models.DateTimeField(default=django.utils.timezone.now)),
                ('imported_by',    models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='imported_price_lists',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['-imported_at'],
                'verbose_name': 'Price List Version',
            },
        ),

        migrations.AddField(
            model_name='rateitem',
            name='price_list_version',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rate_items',
                to='contractor_hub.pricelistversion',
                help_text='Which price list import set this rate',
            ),
        ),

        migrations.AddField(
            model_name='rateitem',
            name='previous_replace_rate',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
                help_text='Rate before last import update (for change tracking)',
            ),
        ),

        migrations.AddField(
            model_name='rateitem',
            name='previous_remove_rate',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, null=True, blank=True,
            ),
        ),

        migrations.AddField(
            model_name='rateitem',
            name='last_updated_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
