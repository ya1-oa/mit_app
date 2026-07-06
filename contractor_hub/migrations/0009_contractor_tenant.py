"""Contractor is a standalone model — assign to default tenant directly."""
from django.db import migrations, models
import django.db.models.deletion


def backfill_contractor_tenant(apps, schema_editor):
    Tenant     = apps.get_model('docsAppR', 'Tenant')
    Contractor = apps.get_model('contractor_hub', 'Contractor')
    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    Contractor.objects.filter(tenant__isnull=True).update(tenant=dt)


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0008_tenant_fks'),
    ]

    operations = [
        migrations.AddField(
            model_name='contractor',
            name='tenant',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='contractors_by_tenant',
                to='docsAppR.tenant',
                db_index=True,
            ),
        ),
        migrations.RunPython(backfill_contractor_tenant, migrations.RunPython.noop),
    ]
