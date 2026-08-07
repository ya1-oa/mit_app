"""
Add unique constraint to Client.encircle_claim_id.

Root cause of the duplicate-client bug:
  The sync looked up clients by encircle_claim_id, but that field was never
  constrained to be unique — so if two rows ended up with the same ID (e.g.
  sync ran before the push task wrote the ID back, so sync created a second
  Client for the same Encircle claim), the lookup would arbitrarily pick one
  and the other would remain a ghost.

This migration:
  1. Deduplicates: for each non-null encircle_claim_id that appears on more
     than one Client, keeps the oldest row (lowest pk — typically the
     manually-created Claimet record) and NULLs the field on all others
     (the sync-created duplicates).  The duplicates are NOT deleted; an admin
     can review and merge them manually.
  2. Adds unique=True so the DB enforces one-to-one mapping going forward.

NULL safety: PostgreSQL treats each NULL as distinct, so clients that have
never been linked to Encircle (encircle_claim_id IS NULL) are unaffected.
"""
from django.db import migrations, models


def deduplicate_encircle_ids(apps, schema_editor):
    """
    For every non-null encircle_claim_id value that appears more than once,
    keep the record with the lowest pk and clear the others.
    """
    Client = apps.get_model('docsAppR', 'Client')

    # Collect ids that appear on 2+ rows
    seen = {}
    for row in Client.objects.filter(
        encircle_claim_id__isnull=False,
    ).exclude(encircle_claim_id='').values('pk', 'encircle_claim_id').order_by('pk'):
        enc_id = row['encircle_claim_id']
        if enc_id not in seen:
            seen[enc_id] = row['pk']   # first (oldest) pk — keeper
        else:
            # Duplicate — NULL out the field so the unique constraint can be added
            Client.objects.filter(pk=row['pk']).update(encircle_claim_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('docsAppR', '0050_taskitem_app_module'),
    ]

    operations = [
        # Step 1: clean existing duplicates before adding the constraint
        migrations.RunPython(
            deduplicate_encircle_ids,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 2: add unique constraint
        migrations.AlterField(
            model_name='client',
            name='encircle_claim_id',
            field=models.CharField(
                max_length=100,
                blank=True,
                null=True,
                unique=True,
                db_index=True,
                help_text="Encircle property claim ID (set after push to Encircle)",
            ),
        ),
    ]
