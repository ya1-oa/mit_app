import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('docsAppR', '0050_taskitem_app_module'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MITDay3Config',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_path', models.CharField(blank=True, help_text='Path to the MIT Day 3 .xlsx template, relative to MEDIA_ROOT.', max_length=512)),
                ('job_info_sheet', models.CharField(default='Job Information', max_length=100)),
                ('total_equipment_sheet', models.CharField(default='Total Equipment', max_length=100)),
                ('dimension_cell_map', models.JSONField(blank=True, default=dict, help_text='JSON describing where room dimensions live on the Job Info sheet.')),
                ('equipment_cell_map', models.JSONField(blank=True, default=list, help_text='JSON array mapping Total Equipment rows to equipment types.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'MIT Day 3 Config',
            },
        ),
        migrations.CreateModel(
            name='MITDay3Audit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('encircle_claim_id', models.CharField(blank=True, db_index=True, max_length=100)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('extracting_dims', 'Extracting Dimensions'),
                        ('dims_review', 'Awaiting Dimension Review'),
                        ('populating_wb', 'Populating Workbook'),
                        ('calculating', 'Calculating Equipment'),
                        ('reviewing_photos', 'Reviewing Photos'),
                        ('generating_reports', 'Generating Reports'),
                        ('complete', 'Complete'),
                        ('error', 'Error'),
                    ],
                    db_index=True, default='pending', max_length=30,
                )),
                ('error_message', models.TextField(blank=True)),
                ('workbook_path', models.CharField(blank=True, max_length=512)),
                ('celery_task_id', models.CharField(blank=True, max_length=200)),
                ('triggered_by_webhook', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mit_audits',
                    to='docsAppR.client',
                )),
                ('triggered_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='mit_audits_triggered',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'MIT Day 3 Audit',
                'verbose_name_plural': 'MIT Day 3 Audits',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MITRoomDimension',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=200)),
                ('length', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('width', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('height', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('square_feet', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('cubic_feet', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('source_floorplan_id', models.CharField(blank=True, max_length=100)),
                ('confidence_score', models.FloatField(default=1.0)),
                ('needs_review', models.BooleanField(db_index=True, default=False)),
                ('approved', models.BooleanField(default=False)),
                ('workbook_row', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('audit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='room_dimensions',
                    to='mit_audit.mitday3audit',
                )),
            ],
            options={
                'verbose_name': 'MIT Room Dimension',
                'ordering': ['room_name'],
            },
        ),
        migrations.CreateModel(
            name='MITRequiredEquipment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('equipment_type', models.CharField(max_length=100)),
                ('display_name', models.CharField(max_length=200)),
                ('category', models.CharField(
                    choices=[
                        ('dehumidifier', 'Dehumidifier'),
                        ('air_cleaner', 'Air Cleaner / Scrubber'),
                        ('zipper_wall', 'Zipper Wall & Poles'),
                        ('double_zipper', 'Double Zipper Wall & Poles'),
                        ('blower', 'Blower / Air Mover'),
                        ('wall_cavity', 'Wall Cavity Drying'),
                        ('floor_drying', 'Floor Drying Equipment'),
                        ('heater', 'Heater'),
                        ('other', 'Other'),
                    ],
                    db_index=True, default='other', max_length=30,
                )),
                ('required_quantity', models.PositiveIntegerField()),
                ('source_sheet', models.CharField(default='Total Equipment', max_length=100)),
                ('workbook_row', models.PositiveIntegerField(blank=True, null=True)),
                ('workbook_cell', models.CharField(blank=True, max_length=20)),
                ('requires_stabilization_photo', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('audit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='required_equipment',
                    to='mit_audit.mitday3audit',
                )),
            ],
            options={
                'verbose_name': 'MIT Required Equipment',
                'verbose_name_plural': 'MIT Required Equipment',
                'ordering': ['category', 'display_name'],
            },
        ),
        migrations.CreateModel(
            name='MITPhotoObservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('visible_quantity', models.PositiveIntegerField(default=0)),
                ('missing_quantity', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(
                    choices=[
                        ('confirmed', 'Confirmed'),
                        ('partial', 'Partial'),
                        ('missing', 'Missing'),
                        ('manual', 'Needs Manual Review'),
                    ],
                    db_index=True, default='missing', max_length=20,
                )),
                ('supporting_photo_ids', models.JSONField(default=list)),
                ('ai_confidence', models.CharField(default='medium', max_length=20)),
                ('ai_notes', models.TextField(blank=True)),
                ('stabilization_photo_found', models.BooleanField(blank=True, null=True)),
                ('recommended_action', models.TextField(blank=True)),
                ('ai_model', models.CharField(blank=True, max_length=100)),
                ('reviewed_at', models.DateTimeField(auto_now_add=True)),
                ('required_item', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='photo_observation',
                    to='mit_audit.mitrequiredequipment',
                )),
            ],
            options={
                'verbose_name': 'MIT Photo Observation',
            },
        ),
        migrations.CreateModel(
            name='MITReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_type', models.CharField(
                    choices=[
                        ('required_equipment', 'Required Equipment Report'),
                        ('missing_equipment', 'Missing Equipment & Photos Report'),
                    ],
                    db_index=True, max_length=30,
                )),
                ('file_path', models.CharField(blank=True, max_length=512)),
                ('file_size_bytes', models.PositiveIntegerField(default=0)),
                ('download_token', models.CharField(blank=True, max_length=64, unique=True)),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('audit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reports',
                    to='mit_audit.mitday3audit',
                )),
            ],
            options={
                'verbose_name': 'MIT Report',
                'ordering': ['-generated_at'],
            },
        ),
    ]
