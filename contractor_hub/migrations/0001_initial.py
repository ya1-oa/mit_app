import uuid
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('docsAppR', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── PriceListVersion ────────────────────────────────────────────────
        migrations.CreateModel(
            name='PriceListVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=50, unique=True, help_text='e.g. OHCL8X_MAR26')),
                ('market', models.CharField(max_length=100, blank=True)),
                ('effective_date', models.DateField(null=True, blank=True)),
                ('source_file', models.CharField(max_length=500, blank=True)),
                ('total_items',   models.PositiveIntegerField(default=0)),
                ('items_created', models.PositiveIntegerField(default=0)),
                ('items_updated', models.PositiveIntegerField(default=0)),
                ('items_skipped', models.PositiveIntegerField(default=0)),
                ('imported_at', models.DateTimeField(auto_now_add=True)),
                ('imported_by', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='imported_price_lists',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('notes', models.TextField(blank=True)),
            ],
            options={'verbose_name': 'Price List Version', 'ordering': ['-imported_at']},
        ),

        # ── Contractor ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Contractor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name',           models.CharField(max_length=255)),
                ('ein',            models.CharField(max_length=20, blank=True, verbose_name='EIN / TIN')),
                ('role',           models.CharField(max_length=30, default='other', choices=[
                    ('gc', 'General Contractor'),
                    ('estimator', 'Estimator / Project Manager'),
                    ('packing', 'CPS Packing & Evaluation'),
                    ('administrative', 'Administrative Services'),
                    ('storage', 'Storage'),
                    ('cleaning', 'Contents Cleaning'),
                    ('demo', 'Demo & Rubbish Removal'),
                    ('transport', 'Transport'),
                    ('other', 'Other'),
                ])),
                ('address',        models.CharField(max_length=500, blank=True)),
                ('city',           models.CharField(max_length=100, blank=True)),
                ('state',          models.CharField(max_length=50, blank=True)),
                ('zip_code',       models.CharField(max_length=20, blank=True)),
                ('phone',          models.CharField(max_length=50, blank=True)),
                ('phone2',         models.CharField(max_length=50, blank=True)),
                ('email',          models.EmailField(blank=True)),
                ('email2',         models.EmailField(blank=True)),
                ('website',        models.URLField(blank=True)),
                ('contact_person', models.CharField(max_length=255, blank=True)),
                ('certification',  models.CharField(max_length=500, blank=True)),
                ('notes',          models.TextField(blank=True)),
                ('is_active',      models.BooleanField(default=True)),
                ('created_at',     models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddIndex(
            model_name='contractor',
            index=models.Index(fields=['role'], name='ch_contractor_role_idx'),
        ),
        migrations.AddIndex(
            model_name='contractor',
            index=models.Index(fields=['name'], name='ch_contractor_name_idx'),
        ),

        # ── RateItem ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='RateItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('cat',          models.CharField(max_length=10, verbose_name='CAT')),
                ('sel',          models.CharField(max_length=20, verbose_name='SEL')),
                ('description',  models.CharField(max_length=500)),
                ('unit',         models.CharField(max_length=5, default='EA', choices=[
                    ('EA', 'Each (EA)'), ('HR', 'Hour (HR)'), ('LF', 'Linear Foot (LF)'),
                    ('SF', 'Square Foot (SF)'), ('CF', 'Cubic Foot (CF)'),
                    ('MO', 'Month (MO)'), ('LS', 'Lump Sum (LS)'),
                ])),
                ('remove_rate',  models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))),
                ('replace_rate', models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))),
                ('taxable',      models.BooleanField(default=True)),
                ('is_bid_item',  models.BooleanField(default=False)),
                ('section_hint', models.CharField(max_length=30, blank=True)),
                ('price_list_version', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='rate_items',
                    to='contractor_hub.pricelistversion',
                )),
                ('previous_replace_rate', models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                ('previous_remove_rate',  models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)),
                ('last_updated_at', models.DateTimeField(null=True, blank=True)),
            ],
            options={'ordering': ['cat', 'sel'], 'verbose_name': 'Rate Item'},
        ),
        migrations.AlterUniqueTogether(
            name='rateitem',
            unique_together={('cat', 'sel')},
        ),

        # ── GCEstimate ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GCEstimate',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='gc_estimates',
                    to='docsAppR.client',
                )),
                ('gc_contractor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='gc_estimates',
                    limit_choices_to={'role': 'gc'},
                    to='contractor_hub.contractor',
                )),
                ('estimator', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='estimated_jobs',
                    limit_choices_to={'role': 'estimator'},
                    to='contractor_hub.contractor',
                )),
                ('estimate_number',  models.CharField(max_length=100, blank=True)),
                ('price_list',       models.CharField(max_length=50, blank=True)),
                ('type_of_estimate', models.CharField(max_length=50, blank=True, default='Fire')),
                ('date_entered',     models.DateField(null=True, blank=True)),
                ('overhead_pct',     models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))),
                ('profit_pct',       models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))),
                ('tax_rate',         models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8.25'))),
                ('status', models.CharField(max_length=20, default='draft', choices=[
                    ('draft', 'Draft'), ('submitted', 'Submitted to Insurance'),
                    ('approved', 'Approved'), ('billed', 'Billed'),
                    ('paid', 'Paid'), ('cancelled', 'Cancelled'),
                ])),
                ('notes', models.TextField(blank=True)),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_gc_estimates',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='gcestimate',
            constraint=models.UniqueConstraint(
                fields=['client'],
                condition=models.Q(status__in=['draft', 'submitted', 'approved', 'billed']),
                name='one_active_estimate_per_client',
            ),
        ),
        migrations.AddIndex(
            model_name='gcestimate',
            index=models.Index(fields=['status'], name='ch_gcestimate_status_idx'),
        ),
        migrations.AddIndex(
            model_name='gcestimate',
            index=models.Index(fields=['client', 'status'], name='ch_gcestimate_client_idx'),
        ),

        # ── GCSection ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GCSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('estimate', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sections',
                    to='contractor_hub.gcestimate',
                )),
                ('section_type', models.CharField(max_length=20, choices=[
                    ('exhaust', 'Exhaust Per Level'),
                    ('admin', 'Administrative Expenses'),
                    ('packing', 'CPS Packing Handling & Evaluation'),
                    ('transport', 'Transporting Contents'),
                    ('storage', 'Storage Info Contents'),
                    ('cleaning', 'Contents Cleaning'),
                    ('demo', 'DMO & Rubbish Removal'),
                    ('porches', 'Porches Exterior'),
                ])),
                ('order',          models.PositiveIntegerField(default=0)),
                ('subcontractor',  models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_sections',
                    to='contractor_hub.contractor',
                )),
                ('bid_status', models.CharField(max_length=20, default='pending', choices=[
                    ('pending', 'Pending'), ('sent', 'Sent to Sub'),
                    ('accepted', 'Accepted'), ('rejected', 'Rejected'),
                ])),
                ('bid_accepted_at', models.DateTimeField(null=True, blank=True)),
                ('notes',          models.TextField(blank=True)),
            ],
            options={'ordering': ['order']},
        ),
        migrations.AlterUniqueTogether(
            name='gcsection',
            unique_together={('estimate', 'section_type')},
        ),

        # ── GCLineItem ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GCLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('section', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='line_items',
                    to='contractor_hub.gcsection',
                )),
                ('rate_item', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='used_in_lines',
                    to='contractor_hub.rateitem',
                )),
                ('cat',          models.CharField(max_length=10)),
                ('sel',          models.CharField(max_length=20)),
                ('description',  models.CharField(max_length=500)),
                ('calc_formula', models.CharField(max_length=100, blank=True)),
                ('quantity',     models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))),
                ('unit',         models.CharField(max_length=5, default='EA')),
                ('remove_rate',  models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))),
                ('replace_rate', models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))),
                ('taxable',         models.BooleanField(default=True)),
                ('is_bid_item',     models.BooleanField(default=False)),
                ('is_memo',         models.BooleanField(default=False)),
                ('order',           models.PositiveIntegerField(default=0)),
                ('notes',           models.TextField(blank=True)),
                ('auto_calculated', models.BooleanField(default=False)),
            ],
            options={'ordering': ['order']},
        ),
    ]
