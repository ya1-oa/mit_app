# Generated manually to remove onedrive_sync_status field

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='client',
            name='onedrive_sync_status',
        ),
    ]
