"""
Add MITAuditLog — live progress log for MIT pipeline tasks.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mit_audit', '0006_config_correct_sheet_names'),
    ]

    operations = [
        migrations.CreateModel(
            name='MITAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('message',    models.CharField(max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('audit', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='log_entries',
                    to='mit_audit.mitday3audit',
                )),
            ],
            options={
                'verbose_name': 'MIT Audit Log Entry',
                'ordering': ['created_at'],
            },
        ),
    ]
