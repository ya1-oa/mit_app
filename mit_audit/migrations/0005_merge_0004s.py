"""
Merge migration — resolves the conflict between:
  0004_alter_mitreferencephoto_description_and_more  (pre-existing on server)
  0004_mitreport_four_types                          (added in this session)

Both depend on 0003_audit_is_test_run_archived.
This empty merge makes Django see a single leaf node again.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mit_audit', '0004_alter_mitreferencephoto_description_and_more'),
        ('mit_audit', '0004_mitreport_four_types'),
    ]

    operations = []
