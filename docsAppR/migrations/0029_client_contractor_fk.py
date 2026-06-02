import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0028_taskitem'),
        ('contractor_hub', '0006_boxcountreport_use_client'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='contractor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='claims',
                to='contractor_hub.contractor',
            ),
        ),
    ]
