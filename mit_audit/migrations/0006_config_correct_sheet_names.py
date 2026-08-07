"""
Fix MITDay3Config sheet name defaults to match the actual 82-MIT-3DAY.xlsm
workbook structure discovered from the template file:

  job_info_sheet:        'Job Information'  →  'jobinfo(2)'
  total_equipment_sheet: 'Total Equipment'  →  'TOTAL-EQPT'

Also updates any existing singleton row (id=1) so the pipeline uses the
correct sheet names immediately without requiring an admin to edit the config.
"""
from django.db import migrations, models


def fix_singleton_sheet_names(apps, schema_editor):
    MITDay3Config = apps.get_model('mit_audit', 'MITDay3Config')
    MITDay3Config.objects.filter(id=1).update(
        job_info_sheet='jobinfo(2)',
        total_equipment_sheet='TOTAL-EQPT',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('mit_audit', '0005_merge_0004s'),
    ]

    operations = [
        # Update field defaults
        migrations.AlterField(
            model_name='mitday3config',
            name='job_info_sheet',
            field=models.CharField(default='jobinfo(2)', max_length=100),
        ),
        migrations.AlterField(
            model_name='mitday3config',
            name='total_equipment_sheet',
            field=models.CharField(default='TOTAL-EQPT', max_length=100),
        ),
        # Fix the existing singleton row
        migrations.RunPython(
            fix_singleton_sheet_names,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
