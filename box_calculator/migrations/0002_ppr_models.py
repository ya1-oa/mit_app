from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('box_calculator', '0001_initial'),
        ('docsAppR', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BoxCalcPPRSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ppr_sessions', to='docsAppR.client')),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='BoxCalcPPRRoom',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=120)),
                ('order', models.PositiveIntegerField(default=0)),
                ('small', models.PositiveIntegerField(default=0)),
                ('medium', models.PositiveIntegerField(default=0)),
                ('large', models.PositiveIntegerField(default=0)),
                ('box_wrapped', models.PositiveIntegerField(default=0)),
                ('plant_vase', models.PositiveIntegerField(default=0)),
                ('tv', models.PositiveIntegerField(default=0)),
                ('wardrobe', models.PositiveIntegerField(default=0)),
                ('mattress', models.PositiveIntegerField(default=0)),
                ('dish_pack', models.PositiveIntegerField(default=0)),
                ('glass_pack', models.PositiveIntegerField(default=0)),
                ('boots_pans', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('processing', 'Processing'),
                        ('complete', 'Complete'),
                        ('error', 'Error'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('celery_task_id', models.CharField(blank=True, max_length=255)),
                ('confidence', models.CharField(blank=True, max_length=20)),
                ('ai_notes', models.TextField(blank=True)),
                ('images_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rooms', to='box_calculator.boxcalcpprsession')),
            ],
            options={
                'ordering': ['order', 'room_name'],
                'unique_together': {('session', 'room_name')},
            },
        ),
    ]
