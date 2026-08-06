"""
management/commands/run_mit_pipeline.py

Run the full MIT Day 3 audit pipeline synchronously against a single claim.
No Celery required — everything runs in the current process.
Useful for testing before the workbook is configured, or for debugging a claim.

Usage:
    # Test with preset equipment list (no workbook needed):
    python manage.py run_mit_pipeline 4808069 --skip-workbook

    # Override equipment quantities:
    python manage.py run_mit_pipeline 4808069 --skip-workbook \\
        --equipment "dehumidifier:4,blower:12,air_cleaner:2,hydroxyl:1,zipper_wall:2"

    # Once workbook is configured at /mit/config/, run the full pipeline:
    python manage.py run_mit_pipeline 4808069

Output: prints AI observations per equipment item, then saves two PDFs.
View the audit at /mit/<audit_id>/ or download reports from the audit detail page.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Run the MIT audit pipeline synchronously for a given Encircle claim.'

    # Default equipment when --skip-workbook is used without --equipment
    DEFAULT_EQUIPMENT = [
        ('dehumidifier',  3,  True),
        ('blower',       10, False),
        ('air_cleaner',   1,  True),
        ('hydroxyl',      1,  True),
    ]

    CATEGORY_META = {
        'dehumidifier': ('LGR Dehumidifier',             True),
        'blower':       ('Air Mover / Blower',            False),
        'air_cleaner':  ('HEPA Air Scrubber',             True),
        'zipper_wall':  ('Zipper Wall (containment)',     True),
        'hydroxyl':     ('Hydroxyl Generator',            True),
        'wall_cavity':  ('Wall Cavity Drying System',    False),
        'floor_drying': ('Floor Drying Mat',             False),
        'heater':       ('Heater',                        False),
        'other':        ('Other Equipment',               False),
    }

    def add_arguments(self, parser):
        parser.add_argument(
            'claim_id', type=str,
            help='Encircle claim ID to audit.',
        )
        parser.add_argument(
            '--skip-workbook', action='store_true',
            help=(
                'Skip the workbook steps (dims extraction, cell mapping). '
                'Uses --equipment to define required items. '
                'Lets you test AI review + reports without a configured template.'
            ),
        )
        parser.add_argument(
            '--equipment', type=str, default='',
            help=(
                'Comma-separated category:quantity pairs used with --skip-workbook. '
                'Example: "dehumidifier:3,blower:10,air_cleaner:2,hydroxyl:1". '
                'Defaults: dehumidifier:3, blower:10, air_cleaner:1, hydroxyl:1.'
            ),
        )
        parser.add_argument(
            '--reuse-audit', action='store_true',
            help=(
                'If an audit for this claim already exists, reuse it and '
                'clear its previous results. Default: create a fresh audit.'
            ),
        )

    # ── Entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        from docsAppR.models import Client
        from mit_audit.models import (
            MITDay3Audit, MITRequiredEquipment,
            MITPhotoObservation, MITReport,
        )
        from mit_audit import photo_service as ps, report_builder as rb

        claim_id   = options['claim_id']
        skip_wb    = options['skip_workbook']
        equip_spec = options['equipment']
        reuse      = options['reuse_audit']

        # ── Find client ──────────────────────────────────────────────────────
        client = (
            Client.objects
            .filter(encircle_claim_id=claim_id, archived=False)
            .first()
        )
        if not client:
            raise CommandError(
                f'No active client found with encircle_claim_id={claim_id!r}.\n'
                'Make sure the claim exists in the database (check /admin/ or '
                'run the Encircle sync first).'
            )
        self.stdout.write(f'Client : {client} (pk={client.pk})')

        # ── Create or reuse audit ────────────────────────────────────────────
        if reuse:
            audit = (
                MITDay3Audit.objects
                .filter(client=client, encircle_claim_id=claim_id)
                .order_by('-created_at')
                .first()
            )
            if audit:
                self.stdout.write(f'Reusing MITDay3Audit #{audit.pk} (clearing previous results)')
                MITRequiredEquipment.objects.filter(audit=audit).delete()
                MITPhotoObservation.objects.filter(required_item__audit=audit).delete()
                MITReport.objects.filter(audit=audit).delete()
            else:
                audit = MITDay3Audit.objects.create(
                    client=client,
                    encircle_claim_id=claim_id,
                    triggered_by=None,
                )
                self.stdout.write(self.style.SUCCESS(f'Created MITDay3Audit #{audit.pk}'))
        else:
            audit = MITDay3Audit.objects.create(
                client=client,
                encircle_claim_id=claim_id,
                triggered_by=None,
            )
            self.stdout.write(self.style.SUCCESS(f'Created MITDay3Audit #{audit.pk}'))

        self.stdout.write(f'Audit  : /mit/{audit.pk}/')

        # ── Required equipment ────────────────────────────────────────────────
        if skip_wb:
            items = self._parse_equipment_spec(equip_spec)
            self.stdout.write(f'\n[skip-workbook] Using {len(items)} equipment types:')
            for it in items:
                stab = '  ★ stabilization required' if it['requires_stabilization_photo'] else ''
                self.stdout.write(
                    f'  • {it["display_name"]:35s} × {it["required_quantity"]}{stab}'
                )
            for it in items:
                MITRequiredEquipment.objects.create(audit=audit, **it)
        else:
            self._run_workbook_steps(audit)

        # ── Fetch Encircle photos ─────────────────────────────────────────────
        self.stdout.write(f'\nFetching photos from Encircle claim {claim_id}…')
        photos = ps.fetch_encircle_photos(claim_id)
        if not photos:
            self.stdout.write(self.style.WARNING(
                '  No photos found. The AI will flag all equipment as missing.'
            ))
        else:
            self.stdout.write(f'  {len(photos)} photos found')

        # ── AI review ────────────────────────────────────────────────────────
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
        if not api_key:
            raise CommandError(
                'ANTHROPIC_API_KEY is not set in settings — cannot run AI review.'
            )

        required_items = list(
            MITRequiredEquipment.objects
            .filter(audit=audit)
            .values('id', 'equipment_type', 'display_name', 'category',
                    'required_quantity', 'requires_stabilization_photo')
        )

        self.stdout.write(
            f'Sending {len(photos)} photos + {len(required_items)} equipment '
            f'types to Claude… (may take 30–90 s)'
        )
        observations = ps.review_photos_with_ai(required_items, photos, api_key)
        self.stdout.write(f'  Claude returned {len(observations)} observations')

        # ── Persist observations ──────────────────────────────────────────────
        id_map   = {it['equipment_type']: it['id'] for it in required_items}
        name_map = {it['display_name'].lower(): it['id'] for it in required_items}

        for obs in observations:
            req_id = (
                id_map.get(obs.get('equipment_type')) or
                name_map.get((obs.get('display_name') or '').lower())
            )
            if not req_id:
                self.stderr.write(
                    f'  [warn] No match for: type={obs.get("equipment_type")!r} '
                    f'name={obs.get("display_name")!r}'
                )
                continue
            stab = obs.get('stabilization_check') or {}
            MITPhotoObservation.objects.update_or_create(
                required_item_id=req_id,
                defaults={
                    'visible_quantity':          int(obs.get('visible_quantity', 0)),
                    'ai_confidence':             obs.get('ai_confidence', 'low'),
                    'ai_notes':                  obs.get('ai_notes', ''),
                    'supporting_photo_ids':      obs.get('supporting_photo_ids', []),
                    'stabilization_photo_found': stab.get('found'),
                    'recommended_action':        obs.get('recommended_action', ''),
                    'ai_model':                  'claude-sonnet-4-6',
                },
            )

        # ── Print summary ─────────────────────────────────────────────────────
        self.stdout.write('\n── AI Review Results ──')
        confirmed = missing = partial = 0
        for obs in observations:
            vis  = int(obs.get('visible_quantity', 0))
            req  = int(obs.get('required_quantity', 0))
            conf = obs.get('ai_confidence', '')
            name = obs.get('display_name') or obs.get('equipment_type', '?')
            if vis >= req:
                marker = '✓'
                confirmed += 1
            elif vis > 0:
                marker = '~'
                partial += 1
            else:
                marker = '✗'
                missing += 1
            self.stdout.write(
                f'  {marker} {name:40s} {vis}/{req} confirmed  [{conf}]'
            )
            if obs.get('ai_notes'):
                self.stdout.write(f'    → {obs["ai_notes"][:120]}')

        self.stdout.write(
            f'\n  Confirmed: {confirmed}  |  Partial: {partial}  |  Missing: {missing}'
        )

        # ── Generate PDF reports ──────────────────────────────────────────────
        self.stdout.write('\nGenerating PDF reports…')
        for report_type, builder_fn, label in [
            ('required_equipment', rb.build_required_equipment_report, 'Required Equipment Report'),
            ('missing_equipment',  rb.build_missing_equipment_report,  'Outstanding Photo Requirements'),
        ]:
            try:
                pdf_path = builder_fn(audit)
                size = Path(pdf_path).stat().st_size
                MITReport.objects.update_or_create(
                    audit=audit, report_type=report_type,
                    defaults={'file_path': pdf_path, 'file_size_bytes': size},
                )
                self.stdout.write(
                    self.style.SUCCESS(f'  ✓ {label}')
                )
                self.stdout.write(f'    {pdf_path}  ({size:,} bytes)')
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'  ✗ {label}: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone. View at: /mit/{audit.pk}/'
            )
        )

    # ── Workbook steps (when not skipping) ───────────────────────────────────

    def _run_workbook_steps(self, audit):
        from mit_audit import workbook_service as ws
        from mit_audit.models import MITRequiredEquipment, MITRoomDimension

        config = ws.get_config()
        if not config or not getattr(config, 'template_path', None):
            raise CommandError(
                'No MIT workbook template is configured.\n'
                'Upload one at /mit/config/ then try again.\n'
                'Or use --skip-workbook to test with a preset equipment list.'
            )

        self.stdout.write('\nPopulating workbook…')
        path = ws.copy_template_for_job(audit.pk)
        audit.workbook_path = path
        audit.save(update_fields=['workbook_path'])

        dims = MITRoomDimension.objects.filter(audit=audit, approved=True)
        written = ws.write_dimensions(path, dims)
        self.stdout.write(f'  Wrote {len(written)} room dimensions')

        ws.recalculate_via_subprocess(path)

        self.stdout.write('Reading required equipment from Total Equipment tab…')
        items = ws.read_total_equipment(path)
        if not items:
            raise CommandError(
                'No equipment with qty > 0 found in the workbook.\n'
                'Check that the template recalculated correctly and '
                'that the cell mapping at /mit/config/ is correct.'
            )
        MITRequiredEquipment.objects.filter(audit=audit).delete()
        for it in items:
            MITRequiredEquipment.objects.create(audit=audit, **it)
        self.stdout.write(f'  {len(items)} required equipment types loaded from workbook')

    # ── Equipment spec parser ─────────────────────────────────────────────────

    def _parse_equipment_spec(self, spec: str) -> list[dict]:
        """Parse 'dehumidifier:3,blower:10' → list of MITRequiredEquipment field dicts."""
        if not spec.strip():
            pairs = [(cat, qty) for cat, qty, _ in self.DEFAULT_EQUIPMENT]
        else:
            pairs = []
            for part in spec.split(','):
                part = part.strip()
                if ':' not in part:
                    continue
                cat, qty = part.rsplit(':', 1)
                try:
                    pairs.append((cat.strip(), int(qty.strip())))
                except ValueError:
                    self.stderr.write(f'Ignoring bad spec: {part!r}')

        items = []
        for cat, qty in pairs:
            meta = self.CATEGORY_META.get(cat)
            if not meta:
                self.stderr.write(
                    f'Unknown category {cat!r}. '
                    f'Valid: {", ".join(self.CATEGORY_META)}'
                )
                continue
            display_name, requires_stab = meta
            items.append({
                'display_name':              display_name,
                'equipment_type':            cat,
                'category':                  cat,
                'required_quantity':         qty,
                'source_sheet':              'test',
                'workbook_row':              None,
                'workbook_cell':             '',
                'requires_stabilization_photo': requires_stab,
            })
        return items
