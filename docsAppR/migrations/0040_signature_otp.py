from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0039_ale_fee_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='signer_phone',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='otp_code',
            field=models.CharField(blank=True, max_length=6),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='otp_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='otp_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='otp_contact',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='otp_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='leasesignaturerequest',
            name='is_otp_verified',
            field=models.BooleanField(default=False),
        ),
    ]
