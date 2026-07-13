from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0047_customuser_is_tenant_admin'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='claimID',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
    ]
