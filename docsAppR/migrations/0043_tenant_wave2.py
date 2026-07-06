"""
Wave 2 — add nullable tenant FK to every docsAppR model whose first-order
parent is Client.  RunPython backfills each record from its client.tenant_id.
"""
from django.db import migrations, models
import django.db.models.deletion


def backfill_wave2(apps, schema_editor):
    Tenant = apps.get_model('docsAppR', 'Tenant')
    Client = apps.get_model('docsAppR', 'Client')

    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    dt_id = dt.id

    # Build client_id → tenant_id map (single-tenant: all map to dt_id)
    client_tenant = {
        cid: (tid if tid else dt_id)
        for cid, tid in Client.objects.values_list('id', 'tenant_id')
    }

    def _backfill(ModelClass, fk_field):
        """Set tenant_id on all NULL-tenant rows from the given FK field."""
        objs = []
        for obj in ModelClass.objects.filter(tenant__isnull=True):
            parent_id = getattr(obj, fk_field + '_id')
            obj.tenant_id = client_tenant.get(parent_id, dt_id) if parent_id else dt_id
            objs.append(obj)
        if objs:
            ModelClass.objects.bulk_update(objs, ['tenant'], batch_size=500)

    _backfill(apps.get_model('docsAppR', 'Room'),               'client')
    _backfill(apps.get_model('docsAppR', 'Lease'),              'client')
    _backfill(apps.get_model('docsAppR', 'ChecklistItem'),      'client')
    _backfill(apps.get_model('docsAppR', 'ClaimFile'),          'client')
    _backfill(apps.get_model('docsAppR', 'GeneratedFile'),      'client')
    _backfill(apps.get_model('docsAppR', 'EmailBatch'),         'claim')
    _backfill(apps.get_model('docsAppR', 'Document'),           'claim')
    _backfill(apps.get_model('docsAppR', 'RoomScopeChecklist'), 'client')
    _backfill(apps.get_model('docsAppR', 'TaskItem'),           'related_client')
    _backfill(apps.get_model('docsAppR', 'SentEmail'),          'claim')


_FK = dict(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
           to='docsAppR.tenant', db_index=True)


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0042_tenant_wave1_client'),
    ]

    operations = [
        migrations.AddField(model_name='room',
            name='tenant', field=models.ForeignKey(related_name='rooms_by_tenant', **_FK)),
        migrations.AddField(model_name='lease',
            name='tenant', field=models.ForeignKey(related_name='leases_by_tenant', **_FK)),
        migrations.AddField(model_name='checklistitem',
            name='tenant', field=models.ForeignKey(related_name='checklist_items_by_tenant', **_FK)),
        migrations.AddField(model_name='claimfile',
            name='tenant', field=models.ForeignKey(related_name='claim_files_by_tenant', **_FK)),
        migrations.AddField(model_name='generatedfile',
            name='tenant', field=models.ForeignKey(related_name='generated_files_by_tenant', **_FK)),
        migrations.AddField(model_name='emailbatch',
            name='tenant', field=models.ForeignKey(related_name='email_batches_by_tenant', **_FK)),
        migrations.AddField(model_name='document',
            name='tenant', field=models.ForeignKey(related_name='documents_by_tenant', **_FK)),
        migrations.AddField(model_name='roomscopechecklist',
            name='tenant', field=models.ForeignKey(related_name='room_scope_checklists_by_tenant', **_FK)),
        migrations.AddField(model_name='taskitem',
            name='tenant', field=models.ForeignKey(related_name='task_items_by_tenant', **_FK)),
        migrations.AddField(model_name='sentemail',
            name='tenant', field=models.ForeignKey(related_name='sent_emails_by_tenant', **_FK)),
        migrations.RunPython(backfill_wave2, migrations.RunPython.noop),
    ]
