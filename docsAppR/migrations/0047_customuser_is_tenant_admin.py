from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0046_tenant_invite'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_tenant_admin',
            field=models.BooleanField(default=False),
        ),
    ]
