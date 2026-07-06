"""
Wave 3 — models whose first-order parent is a Wave-2 model (Room, Lease, ClaimFile).
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_wave3(apps, schema_editor):
    Tenant = apps.get_model('docsAppR', 'Tenant')
    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    dt_id = dt.id

    Room      = apps.get_model('docsAppR', 'Room')
    Lease     = apps.get_model('docsAppR', 'Lease')
    ClaimFile = apps.get_model('docsAppR', 'ClaimFile')

    room_tenant      = {i: (t or dt_id) for i, t in Room.objects.values_list('id', 'tenant_id')}
    lease_tenant     = {i: (t or dt_id) for i, t in Lease.objects.values_list('id', 'tenant_id')}
    claimfile_tenant = {i: (t or dt_id) for i, t in ClaimFile.objects.values_list('id', 'tenant_id')}

    def _backfill(ModelClass, fk_field, parent_map):
        objs = []
        for obj in ModelClass.objects.filter(tenant__isnull=True):
            pid = getattr(obj, fk_field + '_id')
            obj.tenant_id = parent_map.get(pid, dt_id) if pid else dt_id
            objs.append(obj)
        if objs:
            ModelClass.objects.bulk_update(objs, ['tenant'], batch_size=500)

    _backfill(apps.get_model('docsAppR', 'RoomWorkTypeValue'),      'room',       room_tenant)
    _backfill(apps.get_model('docsAppR', 'LeaseTask'),              'lease',      lease_tenant)
    _backfill(apps.get_model('docsAppR', 'LeaseActivity'),          'lease',      lease_tenant)
    _backfill(apps.get_model('docsAppR', 'LeaseSignatureRequest'),  'lease',      lease_tenant)
    _backfill(apps.get_model('docsAppR', 'LeaseStageCompletion'),   'lease',      lease_tenant)
    _backfill(apps.get_model('docsAppR', 'LeaseDocument'),          'lease',      lease_tenant)
    _backfill(apps.get_model('docsAppR', 'FileChangeLog'),          'claim_file', claimfile_tenant)


_FK = dict(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
           to='docsAppR.tenant', db_index=True)


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0043_tenant_wave2'),
    ]

    operations = [
        migrations.AddField(model_name='roomworktypevalue',
            name='tenant', field=models.ForeignKey(related_name='room_work_type_values_by_tenant', **_FK)),
        migrations.AddField(model_name='leasetask',
            name='tenant', field=models.ForeignKey(related_name='lease_tasks_by_tenant', **_FK)),
        migrations.AddField(model_name='leaseactivity',
            name='tenant', field=models.ForeignKey(related_name='lease_activities_by_tenant', **_FK)),
        migrations.AddField(model_name='leasesignaturerequest',
            name='tenant', field=models.ForeignKey(related_name='lease_sig_requests_by_tenant', **_FK)),
        migrations.AddField(model_name='leasestagecompletion',
            name='tenant', field=models.ForeignKey(related_name='lease_stage_completions_by_tenant', **_FK)),
        migrations.AddField(model_name='leasedocument',
            name='tenant', field=models.ForeignKey(related_name='lease_documents_by_tenant', **_FK)),
        migrations.AddField(model_name='filechangelog',
            name='tenant', field=models.ForeignKey(related_name='file_change_logs_by_tenant', **_FK)),
        migrations.RunPython(backfill_wave3, migrations.RunPython.noop),
    ]
