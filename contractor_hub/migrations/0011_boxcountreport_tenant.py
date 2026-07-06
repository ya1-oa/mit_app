"""
BoxCountReport tenant FK — idempotent.

The BoxCountReport table may or may not exist in the database depending on
whether migration 0004 was applied or faked during the multi-tenant retrofit.
This migration uses SeparateDatabaseAndState so:
  - State side:    adds the tenant FK to Django's migration graph (required so
                   makemigrations stops regenerating this migration).
  - Database side: CREATE TABLE IF NOT EXISTS (creates if faked) +
                   ALTER TABLE ADD COLUMN IF NOT EXISTS (adds column if table
                   existed but column was removed in 0008 fix).

Safe to apply regardless of DB state.
"""
from django.db import migrations, models
import django.db.models.deletion

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS contractor_hub_boxcountreport (
    id              BIGSERIAL PRIMARY KEY,
    client_id       BIGINT NOT NULL UNIQUE
                    REFERENCES "docsAppR_client"(id) ON DELETE CASCADE
                    DEFERRABLE INITIALLY DEFERRED,
    small_boxes     INTEGER NOT NULL DEFAULT 0,
    medium_boxes    INTEGER NOT NULL DEFAULT 0,
    large_boxes     INTEGER NOT NULL DEFAULT 0,
    xl_items        INTEGER NOT NULL DEFAULT 0,
    mirror_boxes    INTEGER NOT NULL DEFAULT 0,
    lamp_boxes      INTEGER NOT NULL DEFAULT 0,
    tv_boxes        INTEGER NOT NULL DEFAULT 0,
    wardrobe_boxes  INTEGER NOT NULL DEFAULT 0,
    mattress_boxes  INTEGER NOT NULL DEFAULT 0,
    dishpack_boxes  INTEGER NOT NULL DEFAULT 0,
    glasspack_boxes INTEGER NOT NULL DEFAULT 0,
    pots_boxes      INTEGER NOT NULL DEFAULT 0,
    source_file     VARCHAR(500) NOT NULL DEFAULT '',
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT NOT NULL DEFAULT ''
);

ALTER TABLE contractor_hub_boxcountreport
    ADD COLUMN IF NOT EXISTS tenant_id BIGINT NULL
    REFERENCES "docsAppR_tenant"(id) ON DELETE RESTRICT
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX IF NOT EXISTS contractor_hub_boxcountreport_tenant_id
    ON contractor_hub_boxcountreport (tenant_id);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('contractor_hub', '0009_contractor_tenant'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='boxcountreport',
                    name='tenant',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        db_index=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='box_count_reports_by_tenant',
                        to='docsAppR.tenant',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(sql=_CREATE_SQL, reverse_sql=migrations.RunSQL.noop),
            ],
        ),
    ]
