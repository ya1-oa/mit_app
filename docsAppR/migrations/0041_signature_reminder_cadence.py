from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0040_signature_otp'),
    ]

    operations = [
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='reminder_24h_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='reminder_48h_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='reminder_72h_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
