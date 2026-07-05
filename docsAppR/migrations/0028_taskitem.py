import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0027_systemactivity'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('backlog', 'Backlog'), ('todo', 'To Do'), ('in_progress', 'In Progress'),
                        ('review', 'Needs Review'), ('done', 'Done'), ('cancelled', 'Cancelled'),
                    ],
                    db_index=True, default='todo', max_length=20,
                )),
                ('priority', models.CharField(
                    choices=[
                        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent'),
                    ],
                    db_index=True, default='medium', max_length=10,
                )),
                ('category', models.CharField(
                    choices=[
                        ('general', 'General'), ('claim', 'Claim'), ('lease', 'Lease / ALE'),
                        ('email', 'Email'), ('follow_up', 'Follow Up'), ('admin', 'Admin'),
                        ('billing', 'Billing'), ('legal', 'Legal'),
                    ],
                    db_index=True, default='general', max_length=20,
                )),
                ('due_date', models.DateField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_to', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('related_client', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tasks',
                    to='docsAppR.client',
                )),
                ('related_lease', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tasks',
                    to='docsAppR.lease',
                )),
            ],
            options={
                'verbose_name': 'Task',
                'verbose_name_plural': 'Tasks',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='taskitem',
            index=models.Index(fields=['status', '-created_at'], name='task_status_idx'),
        ),
        migrations.AddIndex(
            model_name='taskitem',
            index=models.Index(fields=['assigned_to', 'status'], name='task_assign_idx'),
        ),
        migrations.AddIndex(
            model_name='taskitem',
            index=models.Index(fields=['due_date'], name='task_due_idx'),
        ),
    ]
