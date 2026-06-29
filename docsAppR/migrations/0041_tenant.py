import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0040_signature_otp'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tenant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(max_length=64, unique=True)),
                ('status', models.CharField(
                    choices=[('active', 'Active'), ('suspended', 'Suspended'), ('trial', 'Trial')],
                    db_index=True, default='active', max_length=20,
                )),
                ('plan', models.CharField(blank=True, default='', max_length=50)),
                ('primary_contact_email', models.EmailField(blank=True, max_length=254)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='customuser',
            name='tenant',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='users', to='docsAppR.tenant',
            ),
        ),
    ]
