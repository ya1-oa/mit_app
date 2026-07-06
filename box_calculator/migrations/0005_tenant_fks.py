"""
box_calculator tenant FK wave:
  Wave 2 (direct Client FK): BoxCalcSession, BoxCalcCPSSession
  Wave 3 (FK to session):    BoxCalcRoom, BoxCalcCPSRoom
  Wave 4 (FK to room):       BoxCalcItem
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_box_calculator_tenants(apps, schema_editor):
    Tenant          = apps.get_model('docsAppR', 'Tenant')
    Client          = apps.get_model('docsAppR', 'Client')
    BoxCalcSession  = apps.get_model('box_calculator', 'BoxCalcSession')
    BoxCalcCPSSession = apps.get_model('box_calculator', 'BoxCalcCPSSession')
    BoxCalcRoom     = apps.get_model('box_calculator', 'BoxCalcRoom')
    BoxCalcCPSRoom  = apps.get_model('box_calculator', 'BoxCalcCPSRoom')
    BoxCalcItem     = apps.get_model('box_calculator', 'BoxCalcItem')

    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    dt_id = dt.id

    client_tenant = {
        cid: (tid if tid else dt_id)
        for cid, tid in Client.objects.values_list('id', 'tenant_id')
    }

    def _from_client(ModelClass):
        objs = []
        for obj in ModelClass.objects.filter(tenant__isnull=True):
            obj.tenant_id = client_tenant.get(obj.client_id, dt_id)
            objs.append(obj)
        if objs:
            ModelClass.objects.bulk_update(objs, ['tenant'], batch_size=500)

    _from_client(BoxCalcSession)
    _from_client(BoxCalcCPSSession)

    # Wave 3: rooms inherit from their session
    session_tenant = {
        sid: (tid if tid else dt_id)
        for sid, tid in BoxCalcSession.objects.values_list('id', 'tenant_id')
    }
    cps_session_tenant = {
        sid: (tid if tid else dt_id)
        for sid, tid in BoxCalcCPSSession.objects.values_list('id', 'tenant_id')
    }

    objs = []
    for obj in BoxCalcRoom.objects.filter(tenant__isnull=True):
        obj.tenant_id = session_tenant.get(obj.session_id, dt_id)
        objs.append(obj)
    if objs:
        BoxCalcRoom.objects.bulk_update(objs, ['tenant'], batch_size=500)

    objs = []
    for obj in BoxCalcCPSRoom.objects.filter(tenant__isnull=True):
        obj.tenant_id = cps_session_tenant.get(obj.session_id, dt_id)
        objs.append(obj)
    if objs:
        BoxCalcCPSRoom.objects.bulk_update(objs, ['tenant'], batch_size=500)

    # Wave 4: items inherit from their room
    room_tenant = {
        rid: (tid if tid else dt_id)
        for rid, tid in BoxCalcRoom.objects.values_list('id', 'tenant_id')
    }
    objs = []
    for obj in BoxCalcItem.objects.filter(tenant__isnull=True):
        obj.tenant_id = room_tenant.get(obj.room_id, dt_id)
        objs.append(obj)
    if objs:
        BoxCalcItem.objects.bulk_update(objs, ['tenant'], batch_size=500)


_FK = dict(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
           to='docsAppR.tenant', db_index=True)


class Migration(migrations.Migration):

    dependencies = [
        ('box_calculator', '0004_merge_20260524_2117'),
        ('docsAppR', '0042_tenant_wave1_client'),
    ]

    operations = [
        # Wave 2
        migrations.AddField(model_name='boxcalcsession', name='tenant',
            field=models.ForeignKey(related_name='box_calc_sessions_by_tenant', **_FK)),
        migrations.AddField(model_name='boxcalccpssession', name='tenant',
            field=models.ForeignKey(related_name='box_calc_cps_sessions_by_tenant', **_FK)),
        # Wave 3
        migrations.AddField(model_name='boxcalcroom', name='tenant',
            field=models.ForeignKey(related_name='box_calc_rooms_by_tenant', **_FK)),
        migrations.AddField(model_name='boxcalccpsroom', name='tenant',
            field=models.ForeignKey(related_name='box_calc_cps_rooms_by_tenant', **_FK)),
        # Wave 4
        migrations.AddField(model_name='boxcalcitem', name='tenant',
            field=models.ForeignKey(related_name='box_calc_items_by_tenant', **_FK)),
        migrations.RunPython(backfill_box_calculator_tenants, migrations.RunPython.noop),
    ]
