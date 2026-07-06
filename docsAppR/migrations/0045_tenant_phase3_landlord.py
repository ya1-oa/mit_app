"""Phase 3 — Landlord is a standalone model (no Client FK); assign default tenant."""
from django.db import migrations, models
import django.db.models.deletion


def backfill_landlord_tenant(apps, schema_editor):
    Tenant   = apps.get_model('docsAppR', 'Tenant')
    Landlord = apps.get_model('docsAppR', 'Landlord')
    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    Landlord.objects.filter(tenant__isnull=True).update(tenant=dt)


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0044_tenant_wave3'),
    ]

    operations = [
        migrations.AddField(
            model_name='landlord',
            name='tenant',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='landlords_by_tenant',
                to='docsAppR.tenant',
                db_index=True,
            ),
        ),
        migrations.RunPython(backfill_landlord_tenant, migrations.RunPython.noop),
    ]
