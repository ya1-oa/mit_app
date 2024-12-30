# Generated by Django 5.1.4 on 2024-12-30 01:45

import django.contrib.auth.validators
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pOwner', models.CharField(blank=True, max_length=255)),
                ('pAddress', models.CharField(blank=True, max_length=255)),
                ('pCityStateZip', models.CharField(blank=True, max_length=255)),
                ('cEmail', models.CharField(blank=True, max_length=255)),
                ('cPhone', models.CharField(blank=True, max_length=255)),
                ('coOwner2', models.CharField(blank=True, max_length=255)),
                ('cPhone2', models.CharField(blank=True, max_length=255)),
                ('cAddress2', models.CharField(blank=True, max_length=255)),
                ('cCityStateZip2', models.CharField(blank=True, max_length=255)),
                ('cEmail2', models.CharField(blank=True, max_length=255)),
                ('rebuildType1', models.CharField(blank=True, max_length=255)),
                ('rebuildType2', models.CharField(blank=True, max_length=255)),
                ('rebuildType3', models.CharField(blank=True, max_length=255)),
                ('demo', models.BooleanField(default=False)),
                ('mitigation', models.BooleanField(default=False)),
                ('otherStructures', models.BooleanField(default=False)),
                ('replacement', models.BooleanField(default=False)),
                ('CPSCLNCONCGN', models.BooleanField(default=False)),
                ('yearBuilt', models.CharField(blank=True, max_length=255)),
                ('lossOfUse', models.CharField(blank=True, max_length=255)),
                ('breathingIssue', models.CharField(blank=True, max_length=255)),
                ('hazardMaterialRemediation', models.CharField(blank=True, max_length=255)),
                ('insuranceCo_Name', models.CharField(blank=True, max_length=255)),
                ('insAddressOvernightMail', models.CharField(blank=True, max_length=255)),
                ('insCityStateZip', models.CharField(blank=True, max_length=255)),
                ('insuranceCoPhone', models.CharField(blank=True, max_length=255)),
                ('insWebsite', models.CharField(blank=True, max_length=255)),
                ('insMailingAddress', models.CharField(blank=True, max_length=255)),
                ('insMailCityStateZip', models.CharField(blank=True, max_length=255)),
                ('policyNumber', models.CharField(blank=True, max_length=255)),
                ('DAPhExt', models.CharField(blank=True, max_length=255)),
                ('fieldAdjusterName', models.CharField(blank=True, max_length=255)),
                ('phoneFieldAdj', models.CharField(blank=True, max_length=255)),
                ('fieldAdjEmail', models.CharField(blank=True, max_length=255)),
                ('adjContents', models.CharField(blank=True, max_length=255)),
                ('adjCpsPhone', models.CharField(blank=True, max_length=255)),
                ('adjCpsEmail', models.CharField(blank=True, max_length=255)),
                ('emsAdj', models.CharField(blank=True, max_length=255)),
                ('emsAdjPhone', models.CharField(blank=True, max_length=255)),
                ('emsTmpEmail', models.CharField(blank=True, max_length=255)),
                ('attLossDraftDept', models.CharField(blank=True, max_length=255)),
                ('newCustomerID', models.CharField(blank=True, max_length=255)),
                ('roomID', models.CharField(blank=True, max_length=255)),
                ('roomArea1', models.CharField(blank=True, max_length=255)),
                ('roomArea2', models.CharField(blank=True, max_length=255)),
                ('roomArea3', models.CharField(blank=True, max_length=255)),
                ('roomArea4', models.CharField(blank=True, max_length=255)),
                ('roomArea5', models.CharField(blank=True, max_length=255)),
                ('roomArea6', models.CharField(blank=True, max_length=255)),
                ('roomArea7', models.CharField(blank=True, max_length=255)),
                ('roomArea8', models.CharField(blank=True, max_length=255)),
                ('roomArea9', models.CharField(blank=True, max_length=255)),
                ('roomArea10', models.CharField(blank=True, max_length=255)),
                ('roomArea11', models.CharField(blank=True, max_length=255)),
                ('roomArea12', models.CharField(blank=True, max_length=255)),
                ('roomArea13', models.CharField(blank=True, max_length=255)),
                ('roomArea14', models.CharField(blank=True, max_length=255)),
                ('roomArea15', models.CharField(blank=True, max_length=255)),
                ('roomArea16', models.CharField(blank=True, max_length=255)),
                ('roomArea17', models.CharField(blank=True, max_length=255)),
                ('roomArea18', models.CharField(blank=True, max_length=255)),
                ('roomArea19', models.CharField(blank=True, max_length=255)),
                ('roomArea20', models.CharField(blank=True, max_length=255)),
                ('roomArea21', models.CharField(blank=True, max_length=255)),
                ('roomArea22', models.CharField(blank=True, max_length=255)),
                ('roomArea23', models.CharField(blank=True, max_length=255)),
                ('roomArea24', models.CharField(blank=True, max_length=255)),
                ('roomArea25', models.CharField(blank=True, max_length=255)),
                ('mortgageCo', models.CharField(blank=True, max_length=255)),
                ('mortgageAccountCo', models.CharField(blank=True, max_length=255)),
                ('mortgageContactPerson', models.CharField(blank=True, max_length=255)),
                ('mortgagePhoneContact', models.CharField(blank=True, max_length=255)),
                ('mortgagePhoneExtContact', models.CharField(blank=True, max_length=255)),
                ('mortgageAttnLossDraftDept', models.CharField(blank=True, max_length=255)),
                ('mortgageOverNightMail', models.CharField(blank=True, max_length=255)),
                ('mortgageCityStZipOVN', models.CharField(blank=True, max_length=255)),
                ('mortgageEmail', models.CharField(blank=True, max_length=255)),
                ('mortgageWebsite', models.CharField(blank=True, max_length=255)),
                ('mortgageCoFax', models.CharField(blank=True, max_length=255)),
                ('mortgageMailingAddress', models.CharField(blank=True, max_length=255)),
                ('mortgageInitialOfferPhase1ContractAmount', models.CharField(blank=True, max_length=255)),
                ('drawRequest', models.CharField(blank=True, max_length=255)),
                ('coName', models.CharField(blank=True, max_length=255)),
                ('coWebsite', models.CharField(blank=True, max_length=255)),
                ('coEmailstatus', models.CharField(blank=True, max_length=255)),
                ('coAddress', models.CharField(blank=True, max_length=255)),
                ('coCityState', models.CharField(blank=True, max_length=255)),
                ('coAddress2', models.CharField(blank=True, max_length=255)),
                ('coCityState2', models.CharField(blank=True, max_length=255)),
                ('coCityState3', models.CharField(blank=True, max_length=255)),
                ('coLogo1', models.CharField(blank=True, max_length=255)),
                ('coLogo2', models.CharField(blank=True, max_length=255)),
                ('coLogo3', models.CharField(blank=True, max_length=255)),
                ('coRepPH', models.CharField(blank=True, max_length=255)),
                ('coREPEmail', models.CharField(blank=True, max_length=255)),
                ('coPhone2', models.CharField(blank=True, max_length=255)),
                ('TinW9', models.CharField(blank=True, max_length=255)),
                ('fedExAccount', models.CharField(blank=True, max_length=255)),
                ('claimReportDate', models.DateField(null=True)),
                ('insuranceCustomerServiceRep', models.CharField(blank=True, max_length=255)),
                ('timeOfClaimReport', models.CharField(blank=True, max_length=255)),
                ('phoneExt', models.CharField(blank=True, max_length=255)),
                ('tarpExtTMPOk', models.BooleanField(default=False)),
                ('IntTMPOk', models.BooleanField(default=False)),
                ('DRYPLACUTOUTMOLDSPRAYOK', models.BooleanField(default=False)),
                ('lossOfUseALE', models.CharField(blank=True, max_length=255)),
                ('tenantLesee', models.CharField(blank=True, max_length=255)),
                ('causeOfLoss', models.CharField(blank=True, max_length=255)),
                ('dateOfLoss', models.DateField(null=True)),
                ('contractDate', models.DateField(null=True)),
                ('insuranceCoName', models.CharField(blank=True, max_length=255)),
                ('claimNumber', models.CharField(blank=True, max_length=255)),
                ('policyClaimNumber', models.CharField(blank=True, max_length=255)),
                ('emailInsCo', models.CharField(blank=True, max_length=255)),
                ('deskAdjusterDA', models.CharField(blank=True, max_length=255)),
                ('DAPhone', models.CharField(blank=True, max_length=255)),
                ('DAPhExtNumber', models.CharField(blank=True, max_length=255)),
                ('DAEmail', models.CharField(blank=True, max_length=255)),
                ('startDate', models.DateField(null=True)),
                ('lessor', models.CharField(blank=True, max_length=255)),
                ('propertyAddressStreet', models.CharField(blank=True, max_length=255)),
                ('propertyCityStateZip', models.CharField(blank=True, max_length=255)),
                ('customerEmail', models.CharField(blank=True, max_length=255)),
                ('cstOwnerPhoneNumber', models.CharField(blank=True, max_length=255)),
                ('bedrooms', models.CharField(blank=True, max_length=255)),
                ('termsAmount', models.CharField(blank=True, max_length=255)),
                ('endDate', models.DateField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name='File',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(max_length=255)),
                ('size', models.IntegerField()),
                ('file', models.FileField(upload_to='templates')),
            ],
        ),
        migrations.CreateModel(
            name='CustomUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('email', models.EmailField(max_length=254, unique=True, verbose_name='email')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to.', related_name='customuser_set', related_query_name='customuser', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='customuser_set', related_query_name='customuser', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
        ),
    ]
