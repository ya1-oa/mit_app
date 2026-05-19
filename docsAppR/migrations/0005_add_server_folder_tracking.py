# Generated manually to add server folder tracking fields
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0004_merge_20251208_0302'),
    ]

    operations = [
        # Add server folder tracking fields to Client
        migrations.AddField(
            model_name='client',
            name='server_folder_path',
            field=models.CharField(blank=True, help_text='Path to claim folder on server', max_length=500),
        ),
        migrations.AddField(
            model_name='client',
            name='folder_created_at',
            field=models.DateTimeField(blank=True, help_text='When folder structure was created', null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='last_file_modified',
            field=models.DateTimeField(blank=True, help_text='Last time any file was changed', null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='last_modified_by',
            field=models.ForeignKey(
                blank=True,
                help_text='User who last modified files',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='last_modified_claims',
                to=settings.AUTH_USER_MODEL
            ),
        ),

        # Add modified_by field to Room
        migrations.AddField(
            model_name='room',
            name='modified_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Last user to modify this room',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL
            ),
        ),
    ]
