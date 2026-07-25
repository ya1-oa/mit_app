from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0048_client_claimid'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='archived',
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
