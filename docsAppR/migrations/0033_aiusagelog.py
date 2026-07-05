from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0032_email_batch_scheduling'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIUsageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('operation', models.CharField(
                    choices=[
                        ('cps_room',  'CPS – Room Analysis'),
                        ('equipment', 'Equipment Checker'),
                        ('sensor',    'Sensor Renamer'),
                        ('encircle',  'Encircle Sync'),
                        ('other',     'Other'),
                    ],
                    default='other', max_length=50, db_index=True,
                )),
                ('cps_session_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('cps_room_id',    models.IntegerField(blank=True, null=True)),
                ('model',          models.CharField(default='claude-haiku-4-5-20251001', max_length=100)),
                ('input_tokens',   models.PositiveIntegerField(default=0)),
                ('output_tokens',  models.PositiveIntegerField(default=0)),
                ('images_count',   models.PositiveSmallIntegerField(default=0)),
                ('cost_usd',       models.DecimalField(decimal_places=8, default=0, max_digits=12)),
                ('success',        models.BooleanField(default=True)),
                ('error_message',  models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'AI Usage Log',
                'verbose_name_plural': 'AI Usage Logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
