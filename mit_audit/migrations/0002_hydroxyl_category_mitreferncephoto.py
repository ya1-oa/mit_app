import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mit_audit', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Add 'hydroxyl' choice to MITRequiredEquipment.category
        migrations.AlterField(
            model_name='mitrequiredequipment',
            name='category',
            field=models.CharField(
                choices=[
                    ('dehumidifier',  'Dehumidifier'),
                    ('air_cleaner',   'Air Cleaner / Scrubber'),
                    ('zipper_wall',   'Zipper Wall & Poles'),
                    ('double_zipper', 'Double Zipper Wall & Poles'),
                    ('blower',        'Blower / Air Mover'),
                    ('wall_cavity',   'Wall Cavity Drying'),
                    ('floor_drying',  'Floor Drying Equipment'),
                    ('hydroxyl',      'Hydroxyl Generator'),
                    ('heater',        'Heater'),
                    ('other',         'Other'),
                ],
                db_index=True, default='other', max_length=30,
            ),
        ),

        # 2. Create MITReferencePhoto
        migrations.CreateModel(
            name='MITReferencePhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('category', models.CharField(
                    blank=True, db_index=True, max_length=30,
                    choices=[
                        ('dehumidifier',  'Dehumidifier'),
                        ('air_cleaner',   'Air Cleaner / Scrubber'),
                        ('zipper_wall',   'Zipper Wall & Poles'),
                        ('double_zipper', 'Double Zipper Wall & Poles'),
                        ('blower',        'Blower / Air Mover'),
                        ('wall_cavity',   'Wall Cavity Drying'),
                        ('floor_drying',  'Floor Drying Equipment'),
                        ('hydroxyl',      'Hydroxyl Generator'),
                        ('heater',        'Heater'),
                        ('other',         'Other'),
                    ],
                    help_text='Equipment type shown in this photo.',
                )),
                ('xact_code',   models.CharField(blank=True, max_length=20)),
                ('display_name', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True)),
                ('file_path',   models.CharField(max_length=512)),
                ('file_size_bytes', models.PositiveIntegerField(default=0)),
                ('source_encircle_claim_id', models.CharField(blank=True, max_length=100)),
                ('source_room_name',         models.CharField(blank=True, max_length=200)),
                ('source_media_id',          models.CharField(blank=True, max_length=100)),
                ('is_active',   models.BooleanField(db_index=True, default=True)),
                ('approved',    models.BooleanField(db_index=True, default=False)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='mit_reference_photos_approved',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name':        'MIT Reference Photo',
                'verbose_name_plural': 'MIT Reference Photos',
                'ordering':            ['category', '-approved', '-created_at'],
            },
        ),
    ]
