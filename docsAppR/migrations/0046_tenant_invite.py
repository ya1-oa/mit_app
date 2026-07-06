from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0045_tenant_phase3_landlord'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantInvite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=32, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('max_uses', models.PositiveIntegerField(default=0, help_text='0 = unlimited')),
                ('use_count', models.PositiveIntegerField(default=0)),
                ('label', models.CharField(blank=True, help_text="Optional note (e.g. 'For John S.')", max_length=100)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_invites',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='invites',
                    to='docsAppR.tenant',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
