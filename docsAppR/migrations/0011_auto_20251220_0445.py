from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0010_delete_synclog_models'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='client',
            name='tenantLesee',
        ),
    ]
