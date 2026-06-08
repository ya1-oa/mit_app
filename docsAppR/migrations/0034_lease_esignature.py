import uuid
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0033_aiusagelog'),
    ]

    operations = [
        # ── New lessee fields on Lease ─────────────────────────────────────
        migrations.AddField(
            model_name='lease',
            name='lessee_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='Tenant Name'),
        ),
        migrations.AddField(
            model_name='lease',
            name='lessee_email',
            field=models.EmailField(blank=True, verbose_name='Tenant Email'),
        ),
        migrations.AddField(
            model_name='lease',
            name='lessee_phone',
            field=models.CharField(blank=True, max_length=50, verbose_name='Tenant Phone'),
        ),
        migrations.AddField(
            model_name='lease',
            name='lessee_address',
            field=models.CharField(blank=True, max_length=500, verbose_name='Tenant Home Address'),
        ),

        # ── New LeaseSignatureRequest table ───────────────────────────────
        migrations.CreateModel(
            name='LeaseSignatureRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('lease', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='signature_requests',
                    to='docsAppR.lease',
                )),
                ('signer_role', models.CharField(
                    choices=[
                        ('tenant', 'Tenant / Lessee'),
                        ('landlord', 'Landlord / Lessor'),
                        ('re_company', 'Real Estate Company'),
                    ],
                    max_length=20,
                )),
                ('signer_name', models.CharField(max_length=255)),
                ('signer_email', models.EmailField()),
                ('token', models.UUIDField(default=uuid.uuid4, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('viewed', 'Viewed'),
                        ('signed', 'Signed'),
                        ('declined', 'Declined'),
                        ('expired', 'Expired'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('signature_image', models.TextField(blank=True)),
                ('typed_name', models.CharField(blank=True, max_length=255)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('document_hash', models.CharField(blank=True, max_length=64)),
                ('agreed_to_esign', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('viewed_at', models.DateTimeField(blank=True, null=True)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('declined_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField()),
            ],
            options={
                'verbose_name': 'Lease Signature Request',
                'verbose_name_plural': 'Lease Signature Requests',
                'ordering': ['signer_role', '-sent_at'],
            },
        ),
        migrations.AddIndex(
            model_name='leasesignaturerequest',
            index=models.Index(fields=['token'], name='leasesig_token_idx'),
        ),
        migrations.AddIndex(
            model_name='leasesignaturerequest',
            index=models.Index(fields=['lease', 'status'], name='leasesig_lease_status_idx'),
        ),
    ]
