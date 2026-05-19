# Generated manually to remove sync_status field from Room model
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0005_add_server_folder_tracking'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='room',
            name='sync_status',
        ),
    ]
