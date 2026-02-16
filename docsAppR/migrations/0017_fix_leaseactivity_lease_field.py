# Generated manually to fix migration order issue
# Migration 0016 had AddIndex before AddField - this fixes it

from django.db import migrations, models
import django.db.models.deletion


def add_lease_columns_if_missing(apps, schema_editor):
    """Add lease_id columns if they don't exist (handles partial migration state)"""
    from django.db import connection

    with connection.cursor() as cursor:
        # Check LeaseActivity table
        cursor.execute("PRAGMA table_info(docsAppR_leaseactivity)")
        activity_columns = [row[1] for row in cursor.fetchall()]

        if 'lease_id' not in activity_columns:
            cursor.execute(
                "ALTER TABLE docsAppR_leaseactivity ADD COLUMN lease_id char(32) NULL REFERENCES docsAppR_lease(id)"
            )

        # Check LeaseDocument table
        cursor.execute("PRAGMA table_info(docsAppR_leasedocument)")
        document_columns = [row[1] for row in cursor.fetchall()]

        if 'lease_id' not in document_columns:
            cursor.execute(
                "ALTER TABLE docsAppR_leasedocument ADD COLUMN lease_id char(32) NULL REFERENCES docsAppR_lease(id)"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0016_lease_remove_leasepackage_client_and_more'),
    ]

    operations = [
        # Remove the index that was incorrectly added (it will fail silently if not exists)
        migrations.RunSQL(
            "DROP INDEX IF EXISTS docsAppR_le_lease_i_5e649b_idx;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Add lease_id columns using Python function (handles "column already exists" gracefully)
        migrations.RunPython(add_lease_columns_if_missing, migrations.RunPython.noop),
        # Now create the index
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS docsAppR_le_lease_i_5e649b_idx ON docsAppR_leaseactivity(lease_id, created_at DESC);",
            reverse_sql="DROP INDEX IF EXISTS docsAppR_le_lease_i_5e649b_idx;",
        ),
    ]
