from django.db import migrations, models
import django.db.models.deletion


def backfill_client_tenant(apps, schema_editor):
    Client = apps.get_model('docsAppR', 'Client')
    Tenant = apps.get_model('docsAppR', 'Tenant')
    dt = Tenant.objects.filter(slug='default').first() or Tenant.objects.first()
    if not dt:
        return
    Client.objects.filter(tenant__isnull=True).update(tenant=dt)


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0041_tenant'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='clients',
                to='docsAppR.tenant',
                db_index=True,
            ),
        ),
        migrations.RunPython(backfill_client_tenant, migrations.RunPython.noop),
    ]
