"""
contractor_hub tenant FK wave:
  Wave 2 (direct Client FK): GCEstimate, BoxCountReport
  Wave 3 (FK to GCEstimate): GCSection
  Wave 4 (FK to GCSection):  GCLineItem
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_contractor_hub_tenants(apps, schema_editor):
    Tenant        = apps.get_model('docsAppR', 'Tenant')
    Client        = apps.get_model('docsAppR', 'Client')
    GCEstimate    = apps.get_model('contractor_hub', 'GCEstimate')
    BoxCountReport= apps.get_model('contractor_hub', 'BoxCountReport')
    GCSection     = apps.get_model('contractor_hub', 'GCSection')
    GCLineItem    = apps.get_model('contractor_hub', 'GCLineItem')

    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    dt_id = dt.id

    # Build client → tenant map
    client_tenant = {
        cid: (tid if tid else dt_id)
        for cid, tid in Client.objects.values_list('id', 'tenant_id')
    }

    def _wave2(ModelClass, fk_field):
        objs = []
        for obj in ModelClass.objects.filter(tenant__isnull=True):
            pid = getattr(obj, fk_field + '_id')
            obj.tenant_id = client_tenant.get(pid, dt_id) if pid else dt_id
            objs.append(obj)
        if objs:
            ModelClass.objects.bulk_update(objs, ['tenant'], batch_size=500)

    _wave2(GCEstimate,     'client')
    _wave2(BoxCountReport, 'client')

    # Wave 3: GCSection → GCEstimate
    estimate_tenant = {
        eid: (tid if tid else dt_id)
        for eid, tid in GCEstimate.objects.values_list('id', 'tenant_id')
    }
    objs = []
    for obj in GCSection.objects.filter(tenant__isnull=True):
        obj.tenant_id = estimate_tenant.get(obj.estimate_id, dt_id)
        objs.append(obj)
    if objs:
        GCSection.objects.bulk_update(objs, ['tenant'], batch_size=500)

    # Wave 4: GCLineItem → GCSection
    section_tenant = {
        sid: (tid if tid else dt_id)
        for sid, tid in GCSection.objects.values_list('id', 'tenant_id')
    }
    objs = []
    for obj in GCLineItem.objects.filter(tenant__isnull=True):
        obj.tenant_id = section_tenant.get(obj.section_id, dt_id)
        objs.append(obj)
    if objs:
        GCLineItem.objects.bulk_update(objs, ['tenant'], batch_size=500)


_FK = dict(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
           to='docsAppR.tenant', db_index=True)


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0007_estimate_delayed_status'),
        ('docsAppR', '0042_tenant_wave1_client'),
    ]

    operations = [
        # Wave 2
        migrations.AddField(model_name='gcestimate', name='tenant',
            field=models.ForeignKey(related_name='gc_estimates_by_tenant', **_FK)),
        migrations.AddField(model_name='boxcountreport', name='tenant',
            field=models.ForeignKey(related_name='box_count_reports_by_tenant', **_FK)),
        # Wave 3
        migrations.AddField(model_name='gcsection', name='tenant',
            field=models.ForeignKey(related_name='gc_sections_by_tenant', **_FK)),
        # Wave 4
        migrations.AddField(model_name='gclineitem', name='tenant',
            field=models.ForeignKey(related_name='gc_line_items_by_tenant', **_FK)),
        migrations.RunPython(backfill_contractor_hub_tenants, migrations.RunPython.noop),
    ]
