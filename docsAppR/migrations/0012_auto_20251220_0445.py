from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0011_auto_20251220_0445'),  # replace with the last migration file
    ]

    operations = [
        migrations.RemoveField(model_name='client', name='onedrive_folder_id'),
        migrations.RemoveField(model_name='client', name='last_onedrive_sync'),
        migrations.RemoveField(model_name='client', name='lossOfUse'),  # old non-ALE
        migrations.RemoveField(model_name='client', name='insuranceCoName'),  # duplicate of insuranceCo_Name
        migrations.RemoveField(model_name='client', name='policyClaimNumber'),  # duplicate of policyNumber
        migrations.RemoveField(model_name='client', name='DAPhExtNumber'),  # duplicate of DAPhExt
        migrations.RemoveField(model_name='client', name='startDate'),
        migrations.RemoveField(model_name='client', name='endDate'),
        migrations.RemoveField(model_name='client', name='lessor'),
        migrations.RemoveField(model_name='client', name='propertyAddressStreet'),
        migrations.RemoveField(model_name='client', name='propertyCityStateZip'),
        migrations.RemoveField(model_name='client', name='customerEmail'),
        migrations.RemoveField(model_name='client', name='cstOwnerPhoneNumber'),
        migrations.RemoveField(model_name='client', name='bedrooms'),
        migrations.RemoveField(model_name='client', name='termsAmount'),
        migrations.RemoveField(model_name='client', name='aleDailyLimit'),
    ]
