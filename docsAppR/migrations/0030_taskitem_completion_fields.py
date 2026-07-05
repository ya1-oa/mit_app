import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0029_client_contractor_fk'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='taskitem',
            name='completed_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='task_completions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='taskitem',
            name='completion_notes',
            field=models.TextField(blank=True,
                help_text='Notes added by the person who completed this task'),
        ),
        migrations.AddField(
            model_name='taskitem',
            name='unit_tests_passed',
            field=models.BooleanField(blank=True, null=True,
                help_text='None=N/A, True=passed, False=failed'),
        ),
        migrations.AddField(
            model_name='taskitem',
            name='beta_tested',
            field=models.BooleanField(blank=True, null=True,
                help_text='None=N/A, True=yes, False=no'),
        ),
        migrations.AddField(
            model_name='taskitem',
            name='test_notes',
            field=models.TextField(blank=True,
                help_text='Unit test / beta test details for development tasks'),
        ),
        # No schema change needed for category choices (CharField stores raw value)
    ]
