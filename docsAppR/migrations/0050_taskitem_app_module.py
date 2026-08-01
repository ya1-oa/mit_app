from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0049_client_archived'),
        ('dev_hub', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskitem',
            name='app_module',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='board_tasks',
                to='dev_hub.appmodule',
                verbose_name='Dev Hub Module',
                help_text='Link this task to a Claimet app so it counts toward module completion %',
            ),
        ),
    ]
