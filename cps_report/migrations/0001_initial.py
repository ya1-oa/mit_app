from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('docsAppR', '0023_add_damaged_value_choice'),
    ]

    operations = [
        migrations.CreateModel(
            name='CPSReportSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('encircle_claim_id', models.CharField(max_length=100)),
                ('claim_number', models.CharField(blank=True, max_length=100)),
                ('insured_name', models.CharField(blank=True, max_length=255)),
                ('loss_type', models.CharField(blank=True, max_length=100)),
                ('loss_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('processing', 'Processing'),
                             ('complete', 'Complete'), ('error', 'Error')],
                    default='pending', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cps_report_sessions', to='docsAppR.client')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='CPSReportRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=200)),
                ('room_number', models.CharField(blank=True, max_length=20)),
                ('encircle_room_id', models.CharField(blank=True, max_length=100)),
                ('order', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('processing', 'Processing'),
                             ('complete', 'Complete'), ('error', 'Error')],
                    default='pending', max_length=20)),
                ('images_used', models.PositiveIntegerField(default=0)),
                ('ai_confidence', models.CharField(blank=True, max_length=20)),
                ('ai_notes', models.TextField(blank=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='cps_report.cpsreportsession')),
            ],
            options={
                'ordering': ['order', 'room_number'],
            },
        ),
        migrations.CreateModel(
            name='CPSReportItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('description', models.CharField(max_length=500)),
                ('brand', models.CharField(blank=True, max_length=200)),
                ('disposition', models.CharField(default='Replacement', max_length=100)),
                ('condition', models.CharField(blank=True, max_length=50)),
                ('qty', models.PositiveIntegerField(default=1)),
                ('model_number', models.CharField(blank=True, max_length=200)),
                ('serial_number', models.CharField(blank=True, max_length=200)),
                ('retailer', models.CharField(blank=True, max_length=200)),
                ('replacement_source', models.CharField(blank=True, max_length=200)),
                ('purchase_price_each', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('age_years', models.PositiveIntegerField(blank=True, null=True)),
                ('age_months', models.PositiveIntegerField(blank=True, null=True)),
                ('replacement_value_each', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('depreciation_category', models.CharField(blank=True, max_length=100)),
                ('depreciation_pct', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('notes', models.TextField(blank=True)),
                ('ai_suggested', models.BooleanField(default=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='cps_report.cpsreportroom')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
    ]
