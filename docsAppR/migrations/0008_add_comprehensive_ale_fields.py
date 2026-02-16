# Generated migration for comprehensive ALE fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0007_add_claimfile_filechangelog'),
    ]

    operations = [
        # Add new ALE Daily Limit field
        migrations.AddField(
            model_name='client',
            name='aleDailyLimit',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='ALE Daily Limit Amount', max_digits=10, null=True),
        ),

        # LESSEE INFO fields
        migrations.AddField(
            model_name='client',
            name='ale_lessee_name',
            field=models.CharField(blank=True, help_text='Lessee/Tenant Name', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessee_home_address',
            field=models.CharField(blank=True, help_text='Lessee Home Address', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessee_city_state_zip',
            field=models.CharField(blank=True, help_text='Lessee City, State, ZIP', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessee_email',
            field=models.CharField(blank=True, help_text='Lessee Email', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessee_phone',
            field=models.CharField(blank=True, help_text='Lessee Phone Number', max_length=255),
        ),

        # RENTAL INFO fields
        migrations.AddField(
            model_name='client',
            name='ale_rental_bedrooms',
            field=models.CharField(blank=True, help_text='Number of Bedrooms', max_length=50),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_rental_months',
            field=models.CharField(blank=True, help_text='Number of Months', max_length=50),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_rental_start_date',
            field=models.DateField(blank=True, help_text='Rental Start Date', null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_rental_end_date',
            field=models.DateField(blank=True, help_text='Rental End Date', null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_rental_amount_per_month',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Amount Per Month', max_digits=10, null=True),
        ),

        # LESSOR INFO fields
        migrations.AddField(
            model_name='client',
            name='ale_lessor_name',
            field=models.CharField(blank=True, help_text='Lessor Legal Name', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_leased_address',
            field=models.CharField(blank=True, help_text='Leased Property Address', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_city_zip',
            field=models.CharField(blank=True, help_text='Lessor City, ZIP', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_phone',
            field=models.CharField(blank=True, help_text='Lessor Phone Number', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_email',
            field=models.CharField(blank=True, help_text='Lessor Email', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_mailing_address',
            field=models.CharField(blank=True, help_text='Lessor Mailing Address', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_mailing_city_zip',
            field=models.CharField(blank=True, help_text='Lessor Mailing City, ZIP', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_lessor_contact_person',
            field=models.CharField(blank=True, help_text='Lessor Contact Person', max_length=255),
        ),

        # REAL ESTATE COMPANY fields
        migrations.AddField(
            model_name='client',
            name='ale_re_company_name',
            field=models.CharField(blank=True, help_text='Real Estate Company Name', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_mailing_address',
            field=models.CharField(blank=True, help_text='RE Company Mailing Address', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_city_zip',
            field=models.CharField(blank=True, help_text='RE Company City, ZIP', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_contact_person',
            field=models.CharField(blank=True, help_text='RE Company Contact Person', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_phone',
            field=models.CharField(blank=True, help_text='RE Company Phone', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_email',
            field=models.CharField(blank=True, help_text='RE Company Email', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_owner_broker_name',
            field=models.CharField(blank=True, help_text='Owner/Broker Name', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_owner_broker_phone',
            field=models.CharField(blank=True, help_text='Owner/Broker Phone', max_length=255),
        ),
        migrations.AddField(
            model_name='client',
            name='ale_re_owner_broker_email',
            field=models.CharField(blank=True, help_text='Owner/Broker Email', max_length=255),
        ),
    ]
