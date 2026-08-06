from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Update MITReport.report_type choices to the four-report split:
      required_equipment / required_stab / missing_equipment / missing_stab
    No schema change — CharField stays VARCHAR(30).
    """

    dependencies = [
        ('mit_audit', '0003_audit_is_test_run_archived'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mitreport',
            name='report_type',
            field=models.CharField(
                max_length=30,
                db_index=True,
                choices=[
                    ('required_equipment', 'Required Water Mitigation Equipment'),
                    ('required_stab',      'Required Stabilization Photos'),
                    ('missing_equipment',  'Missing Water Mitigation Photos'),
                    ('missing_stab',       'Missing Stabilization Photos'),
                ],
            ),
        ),
    ]
