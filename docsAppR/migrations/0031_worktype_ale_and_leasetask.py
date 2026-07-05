import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0030_taskitem_completion_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # WorkType choices can't be altered via migrations (they're in-code)
        # so we just need to ensure the ALE work type record exists

        migrations.CreateModel(
            name='LeaseTask',
            fields=[
                ('id', models.UUIDField(default=None, editable=False, primary_key=True, serialize=False)),
                ('task_type', models.CharField(
                    choices=[
                        ('draft', 'Draft Lease Created'),
                        ('send_for_signature', 'Send for Signature'),
                        ('re_company_signed', 'Signed by Real Estate Company'),
                        ('tenant_signed', 'Signed by Tenant'),
                        ('landlord_signed', 'Signed by Landlord'),
                        ('completed', 'All Signatures Received'),
                    ],
                    max_length=30,
                )),
                ('is_completed', models.BooleanField(default=False)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, help_text='Field notes on completion')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='completed_lease_tasks',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('lease', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='workflow_tasks',
                    to='docsAppR.lease',
                )),
            ],
            options={
                'ordering': ['lease', 'created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='leasetask',
            constraint=models.UniqueConstraint(fields=['lease', 'task_type'], name='unique_lease_task_type'),
        ),
        migrations.AddIndex(
            model_name='leasetask',
            index=models.Index(fields=['lease', 'is_completed'], name='docsAppR_le_lease_i_idx'),
        ),
        migrations.AddIndex(
            model_name='leasetask',
            index=models.Index(fields=['lease', 'task_type'], name='docsAppR_le_lease_t_idx'),
        ),
    ]
