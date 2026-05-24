# This migration was a SQLite-specific workaround for a field ordering bug in 0016.
# Migration 0016 has been fixed directly (AddField before AddIndex), making this a no-op.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0016_lease_remove_leasepackage_client_and_more'),
    ]

    operations = [
        # No-op: the original fix used SQLite PRAGMA syntax which is incompatible
        # with PostgreSQL. Migration 0016 was corrected at source instead.
    ]
