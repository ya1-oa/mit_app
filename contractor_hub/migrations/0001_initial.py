# Generated manually — 2026-05-25
# contractor_hub initial migration

import django.db.models.deletion
import uuid
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
        # ── Contractor ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Contractor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('ein', models.CharField(blank=True, max_length=20, verbose_name='EIN / TIN')),
                ('role', models.CharField(choices=[
                    ('gc', 'General Contractor'),
                    ('estimator', 'Estimator / Project Manager'),
                    ('packing', 'CPS Packing & Evaluation'),
                    ('administrative', 'Administrative Services'),
                    ('storage', 'Storage'),
                    ('cleaning', 'Contents Cleaning'),
                    ('demo', 'Demo & Rubbish Removal'),
                    ('transport', 'Transport'),
                    ('other', 'Other'),
                ], default='other', max_length=30)),
                ('address', models.CharField(blank=True, max_length=500)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=50)),
                ('zip_code', models.CharField(blank=True, max_length=20)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('phone2', models.CharField(blank=True, max_length=50)),
                ('email', models.EmailField(blank=True)),
                ('email2', models.EmailField(blank=True)),
                ('website', models.URLField(blank=True)),
                ('contact_person', models.CharField(blank=True, max_length=255)),
                ('certification', models.CharField(blank=True, max_length=500)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddIndex(
            model_name='contractor',
            index=models.Index(fields=['role'], name='contractor_hub_contractor_role_idx'),
        ),
        migrations.AddIndex(
            model_name='contractor',
            index=models.Index(fields=['name'], name='contractor_hub_contractor_name_idx'),
        ),

        # ── RateItem ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='RateItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cat', models.CharField(max_length=10, verbose_name='CAT')),
                ('sel', models.CharField(max_length=20, verbose_name='SEL')),
                ('description', models.CharField(max_length=500)),
                ('unit', models.CharField(choices=[
                    ('EA', 'Each (EA)'), ('HR', 'Hour (HR)'), ('LF', 'Linear Foot (LF)'),
                    ('SF', 'Square Foot (SF)'), ('CF', 'Cubic Foot (CF)'),
                    ('MO', 'Month (MO)'), ('LS', 'Lump Sum (LS)'),
                ], default='EA', max_length=5)),
                ('remove_rate', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('replace_rate', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('taxable', models.BooleanField(default=True)),
                ('is_bid_item', models.BooleanField(default=False, help_text='[*] bid item — qty locked to 1, rate is total')),
                ('section_hint', models.CharField(blank=True, max_length=30)),
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
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('estimate_number', models.CharField(blank=True, max_length=100)),
                ('price_list', models.CharField(blank=True, max_length=50)),
                ('type_of_estimate', models.CharField(blank=True, default='Fire', max_length=50)),
                ('date_entered', models.DateField(blank=True, null=True)),
                ('overhead_pct', models.DecimalField(decimal_places=2, default=Decimal('10.00'), max_digits=5)),
                ('profit_pct', models.DecimalField(decimal_places=2, default=Decimal('10.00'), max_digits=5)),
                ('tax_rate', models.DecimalField(decimal_places=2, default=Decimal('8.25'), max_digits=5)),
                ('status', models.CharField(choices=[
                    ('draft', 'Draft'), ('submitted', 'Submitted to Insurance'),
                    ('approved', 'Approved'), ('billed', 'Billed'),
                    ('paid', 'Paid'), ('cancelled', 'Cancelled'),
                ], default='draft', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='gc_estimates',
                    to='docsAppR.client',
                )),
                ('gc_contractor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='gc_estimates',
                    to='contractor_hub.contractor',
                )),
                ('estimator', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='estimated_jobs',
                    to='contractor_hub.contractor',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_gc_estimates',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='gcestimate',
            index=models.Index(fields=['status'], name='contractor_hub_gcestimate_status_idx'),
        ),
        migrations.AddIndex(
            model_name='gcestimate',
            index=models.Index(fields=['client', 'status'], name='contractor_hub_gcestimate_client_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='gcestimate',
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=['draft', 'submitted', 'approved', 'billed']),
                fields=['client'],
                name='one_active_estimate_per_client',
            ),
        ),

        # ── GCSection ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GCSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('section_type', models.CharField(choices=[
                    ('exhaust', 'Exhaust Per Level'),
                    ('admin', 'Administrative Expenses'),
                    ('packing', 'CPS Packing Handling & Evaluation'),
                    ('transport', 'Transporting Contents'),
                    ('storage', 'Storage Info Contents'),
                    ('cleaning', 'Contents Cleaning'),
                    ('demo', 'DMO & Rubbish Removal'),
                    ('porches', 'Porches Exterior'),
                ], max_length=20)),
                ('order', models.PositiveIntegerField(default=0)),
                ('bid_status', models.CharField(choices=[
                    ('pending', 'Pending'), ('sent', 'Sent to Sub'),
                    ('accepted', 'Accepted'), ('rejected', 'Rejected'),
                ], default='pending', max_length=20)),
                ('bid_accepted_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('estimate', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sections',
                    to='contractor_hub.gcestimate',
                )),
                ('subcontractor', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_sections',
                    to='contractor_hub.contractor',
                )),
            ],
            options={'ordering': ['order']},
        ),
        migrations.AlterUniqueTogether(
            name='gcsection',
            unique_together={('estimate', 'section_type')},
        ),

        # ── GCLineItem ────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GCLineItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cat', models.CharField(max_length=10)),
                ('sel', models.CharField(max_length=20)),
                ('description', models.CharField(max_length=500)),
                ('calc_formula', models.CharField(blank=True, max_length=100)),
                ('quantity', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10)),
                ('unit', models.CharField(default='EA', max_length=5)),
                ('remove_rate', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('replace_rate', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('taxable', models.BooleanField(default=True)),
                ('is_bid_item', models.BooleanField(default=False)),
                ('is_memo', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('auto_calculated', models.BooleanField(default=False)),
                ('section', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='line_items',
                    to='contractor_hub.gcsection',
                )),
                ('rate_item', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='used_in_lines',
                    to='contractor_hub.rateitem',
                )),
            ],
            options={'ordering': ['order']},
        ),
    ]
