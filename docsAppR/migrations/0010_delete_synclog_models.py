from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0009_remove_synclog_fields'),
    ]

    operations = [
        migrations.DeleteModel(name='SyncLog'),
        migrations.DeleteModel(name='OneDriveFile'),
        migrations.DeleteModel(name='OneDriveFolder'),
    ]
