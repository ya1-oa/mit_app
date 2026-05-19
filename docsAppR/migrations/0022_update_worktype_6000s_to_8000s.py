from django.db import migrations, models


def rename_6000s_to_8000s(apps, schema_editor):
    """Update WorkType records from 6100-6400 to 8100-8400."""
    WorkType = apps.get_model('docsAppR', 'WorkType')
    mapping = {6100: 8100, 6200: 8200, 6300: 8300, 6400: 8400}
    for old_id, new_id in mapping.items():
        WorkType.objects.filter(work_type_id=old_id).update(work_type_id=new_id)


def revert_8000s_to_6000s(apps, schema_editor):
    """Revert WorkType records from 8100-8400 back to 6100-6400."""
    WorkType = apps.get_model('docsAppR', 'WorkType')
    mapping = {8100: 6100, 8200: 6200, 8300: 6300, 8400: 6400}
    for old_id, new_id in mapping.items():
        WorkType.objects.filter(work_type_id=old_id).update(work_type_id=new_id)


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0021_client_encircle_claim_id_client_encircle_synced_at'),
    ]

    operations = [
        # Update the choices on the field (cosmetic — Django doesn't enforce choices at DB level)
        migrations.AlterField(
            model_name='worktype',
            name='work_type_id',
            field=models.IntegerField(
                choices=[
                    (100, 'Work Type 100'),
                    (200, 'Work Type 200'),
                    (300, 'Work Type 300'),
                    (400, 'Work Type 400'),
                    (500, 'Work Type 500'),
                    (800, 'Work Type 800'),
                    (900, 'Work Type 900 - HMR'),
                    (8100, 'MC DAY 1'),
                    (8200, 'MC DAY 2'),
                    (8300, 'MC DAY 3'),
                    (8400, 'MC DAY 4'),
                ],
                db_index=True,
                unique=True,
            ),
        ),
        # Migrate existing data
        migrations.RunPython(rename_6000s_to_8000s, revert_8000s_to_6000s),
    ]
