from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('daily_reports', '0001_initial'),
        ('dev_hub', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyreportconfig',
            name='include_priority_tasks',
            field=models.BooleanField(default=True, verbose_name='Priority Tasks (L1/L2/L3)'),
        ),
        migrations.CreateModel(
            name='PriorityTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=300)),
                ('description', models.TextField(blank=True)),
                ('level', models.CharField(
                    choices=[
                        ('level_1', 'Level 1 — Critical'),
                        ('level_2', 'Level 2 — High'),
                        ('level_3', 'Level 3 — Standard'),
                    ],
                    db_index=True, default='level_2', max_length=20,
                )),
                ('status', models.CharField(
                    choices=[
                        ('open',        'Open'),
                        ('in_progress', 'In Progress'),
                        ('done',        'Done'),
                    ],
                    db_index=True, default='open', max_length=20,
                )),
                ('due_date', models.DateField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('config', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='priority_tasks',
                    to='daily_reports.dailyreportconfig',
                )),
                ('app_module', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='priority_tasks',
                    to='dev_hub.appmodule',
                    verbose_name='Dev Hub Module',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_priority_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Priority Task',
                'ordering': ['level', 'created_at'],
            },
        ),
    ]
