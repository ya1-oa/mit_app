from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0003_remove_limit_choices_to'),
    ]

    operations = [
        migrations.CreateModel(
            name='BoxCountReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('small_boxes',    models.PositiveIntegerField(default=0, verbose_name='Small Boxes')),
                ('medium_boxes',   models.PositiveIntegerField(default=0, verbose_name='Medium Boxes')),
                ('large_boxes',    models.PositiveIntegerField(default=0, verbose_name='Large Boxes')),
                ('xl_items',       models.PositiveIntegerField(default=0, verbose_name='XL / Unboxed Items')),
                ('mirror_boxes',   models.PositiveIntegerField(default=0, verbose_name='Mirror / Picture Boxes')),
                ('lamp_boxes',     models.PositiveIntegerField(default=0, verbose_name='Lamp / Plant / Vase Boxes')),
                ('tv_boxes',       models.PositiveIntegerField(default=0, verbose_name='TV Boxes')),
                ('wardrobe_boxes', models.PositiveIntegerField(default=0, verbose_name='Wardrobe Boxes')),
                ('mattress_boxes', models.PositiveIntegerField(default=0, verbose_name='Mattress Boxes')),
                ('dishpack_boxes', models.PositiveIntegerField(default=0, verbose_name='Dish Pack Boxes')),
                ('glasspack_boxes',models.PositiveIntegerField(default=0, verbose_name='Glass Pack Boxes')),
                ('pots_boxes',     models.PositiveIntegerField(default=0, verbose_name='Pots & Pans Boxes')),
                ('source_file',    models.CharField(blank=True, max_length=500)),
                ('uploaded_at',    models.DateTimeField(auto_now_add=True)),
                ('updated_at',     models.DateTimeField(auto_now=True)),
                ('notes',          models.TextField(blank=True)),
                ('estimate', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='box_count_report',
                    to='contractor_hub.gcestimate',
                )),
            ],
            options={'verbose_name': 'Box Count Report'},
        ),
        migrations.CreateModel(
            name='LineItemTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_code',   models.CharField(db_index=True, max_length=20,
                                                  help_text='Xactimate group code, e.g. SMALL_TOTAL2')),
                ('section_type', models.CharField(max_length=20, choices=[
                    ('exhaust',   'Exhaust Per Level'),
                    ('admin',     'Administrative Expenses'),
                    ('packing',   'CPS Packing Handling & Evaluation'),
                    ('transport', 'Transporting Contents'),
                    ('storage',   'Storage Info Contents'),
                    ('cleaning',  'Contents Cleaning'),
                    ('demo',      'DMO & Rubbish Removal'),
                    ('porches',   'Porches Exterior'),
                ])),
                ('box_type', models.CharField(
                    max_length=20, default='fixed',
                    choices=[
                        ('small',     'Small Box'),
                        ('medium',    'Medium Box'),
                        ('large',     'Large Box'),
                        ('xl',        'XL / Unboxed Item'),
                        ('mirror',    'Mirror / Picture Box'),
                        ('lamp',      'Lamp / Plant / Vase Box'),
                        ('tv',        'TV Box'),
                        ('wardrobe',  'Wardrobe Box'),
                        ('mattress',  'Mattress Box'),
                        ('dishpack',  'Dish Pack Box'),
                        ('glasspack', 'Glass Pack Box'),
                        ('pots',      'Pots & Pans Box'),
                        ('fixed',     'Fixed Quantity (not box-dependent)'),
                    ],
                    help_text='Which box count field drives QTY. FIXED = qty_factor is the literal qty.',
                )),
                ('cat',         models.CharField(max_length=10)),
                ('sel',         models.CharField(max_length=20)),
                ('description', models.CharField(max_length=500)),
                ('unit',        models.CharField(max_length=5, default='EA')),
                ('qty_factor',  models.DecimalField(
                    max_digits=8, decimal_places=4, default=Decimal('1.0000'),
                    help_text='Multiplier × box count = qty. For FIXED, this IS the qty.',
                )),
                ('taxable',     models.BooleanField(default=True)),
                ('order',       models.PositiveIntegerField(default=0)),
                ('notes',       models.TextField(blank=True,
                                                 help_text='Printed beneath the line item in the PDF')),
            ],
            options={
                'verbose_name': 'Line Item Template',
                'ordering': ['section_type', 'group_code', 'order'],
            },
        ),
    ]
