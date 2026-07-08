import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('box_calculator', '0006_add_picture_mirror'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BoxCalcCPSReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('format', models.CharField(choices=[('pdf', 'PDF'), ('excel', 'Excel')], max_length=10)),
                ('filename', models.CharField(max_length=255)),
                ('file_data', models.BinaryField()),
                ('file_size', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='cps_reports',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='saved_reports',
                    to='box_calculator.boxcalccpssession',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
