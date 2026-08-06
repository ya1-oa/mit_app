"""
management/commands/import_reference_photos.py

Download photos from Encircle claims and store them locally as reference
photos for the MIT AI review system.

Usage:
    # Auto-discover the latest N claims (default 6) that have Encircle IDs:
    python manage.py import_reference_photos

    # Import specific claim IDs:
    python manage.py import_reference_photos abc123 def456

    # Options:
    --latest N          Pull the N most-recent claims (default 6, ignored if IDs given)
    --room-series 6     Only import rooms whose number starts with this digit (default: 6)
    --all-rooms         Ignore room numbering, import every room
    --overwrite         Re-download even if source_media_id already exists
    --dry-run           Print what would be imported, don't write anything

Examples:
    python manage.py import_reference_photos
    python manage.py import_reference_photos --latest 10
    python manage.py import_reference_photos abc123 def456 --room-series 6
    python manage.py import_reference_photos --all-rooms --dry-run
"""
import re
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mit_audit.models import MITReferencePhoto


# Xactimate code → category slug
XACT_TO_CATEGORY = {
    'DHMAC':   'dehumidifier',
    'DRY':     'blower',
    'NAFAN':   'air_cleaner',
    'FHEPA':   'air_cleaner',
    'BARRZ+':  'zipper_wall',
    'BARRP':   'zipper_wall',
    'BARR':    'zipper_wall',
    'WALL':    'wall_cavity',
    'WALLH':   'wall_cavity',
    'WFI':     'floor_drying',
    'HTBL':    'floor_drying',
    'DUCTLF':  'other',
    'DODHY>':  'hydroxyl',
}


class Command(BaseCommand):
    help = (
        'Import Encircle photos as MIT reference photos for AI-assisted review. '
        'When no claim IDs are given, auto-discovers the latest --latest active claims.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'claim_ids', nargs='*', type=str,
            help='Encircle claim ID(s) to import from. Omit to auto-discover.',
        )
        parser.add_argument(
            '--latest', type=int, default=6,
            help='Number of most-recent Encircle claims to pull when no IDs are given (default: 6).',
        )
        parser.add_argument(
            '--room-series', type=str, default='6',
            help='Only import rooms whose number begins with this digit (default: 6).',
        )
        parser.add_argument(
            '--all-rooms', action='store_true',
            help='Import every room, ignoring the room-series filter.',
        )
        parser.add_argument(
            '--overwrite', action='store_true',
            help='Re-download even if the Encircle media ID is already stored.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be imported without writing anything.',
        )

    # ── Entry point ─────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        from docsAppR.encircle_client import EncircleAPIClient

        claim_ids   = options['claim_ids']
        latest_n    = options['latest']
        room_series = options['room_series']
        all_rooms   = options['all_rooms']
        overwrite   = options['overwrite']
        dry_run     = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be written.'))

        # ── Resolve claim IDs ────────────────────────────────────────────────
        if not claim_ids:
            claim_ids = self._latest_claim_ids(latest_n)
            if not claim_ids:
                raise CommandError(
                    'No active clients with Encircle claim IDs found in the database. '
                    'Push at least one claim to Encircle first, or supply IDs manually.'
                )
            self.stdout.write(
                f'Auto-discovered {len(claim_ids)} claim(s): {", ".join(claim_ids)}'
            )
        else:
            self.stdout.write(f'Using {len(claim_ids)} explicit claim ID(s).')

        # ── Encircle client ──────────────────────────────────────────────────
        try:
            api = EncircleAPIClient()
        except Exception as exc:
            raise CommandError(f'Could not initialise Encircle API client: {exc}')

        dest_base = Path(settings.MEDIA_ROOT) / 'mit_reference_photos' / 'pending'
        if not dry_run:
            dest_base.mkdir(parents=True, exist_ok=True)

        total_imported = 0
        total_skipped  = 0

        for claim_id in claim_ids:
            self.stdout.write(f'\n── Claim {claim_id} ──')

            try:
                raw         = api.get_all_claim_media(claim_id)
                media_items = raw if isinstance(raw, list) else raw.get('list', [])
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'  Failed to fetch media: {exc}'))
                continue

            self.stdout.write(f'  {len(media_items)} total media items')

            for item in media_items:
                media_type = (item.get('media_type') or item.get('type') or '').lower()

                # Skip non-photos (PDFs, audio, video)
                if media_type and not any(t in media_type for t in ('photo', 'image')):
                    continue

                media_id  = str(item.get('id', ''))
                room_name = item.get('room_name') or item.get('room') or ''
                url       = item.get('url') or item.get('download_url') or ''

                if not url:
                    continue

                # Room series filter
                if not all_rooms and not self._is_target_room(room_name, room_series):
                    continue

                # Duplicate check
                if not overwrite and media_id:
                    if MITReferencePhoto.objects.filter(source_media_id=media_id).exists():
                        total_skipped += 1
                        continue

                if dry_run:
                    self.stdout.write(f'  [DRY] Would import: {room_name} / {media_id}')
                    total_imported += 1
                    continue

                # Download the photo
                dest_dir = dest_base / claim_id / self._safe_name(room_name or 'unknown')
                dest_dir.mkdir(parents=True, exist_ok=True)

                try:
                    ext, file_bytes = self._download(url, api)
                except Exception as exc:
                    self.stderr.write(f'  [SKIP] {media_id}: download failed — {exc}')
                    total_skipped += 1
                    continue

                dest_path = dest_dir / f'{media_id}{ext}'
                dest_path.write_bytes(file_bytes)

                obj, created = MITReferencePhoto.objects.update_or_create(
                    source_media_id=media_id,
                    defaults={
                        'file_path':                str(dest_path),
                        'file_size_bytes':          len(file_bytes),
                        'source_encircle_claim_id': claim_id,
                        'source_room_name':         room_name,
                        'category':                 '',   # staff will tag during review
                        'approved':                 False,
                        'is_active':                True,
                    },
                )
                action = 'Created' if created else 'Updated'
                self.stdout.write(f'  [{action}] {room_name} / {media_id} → {dest_path.name}')
                total_imported += 1
                time.sleep(0.05)   # gentle rate-limit

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone — {total_imported} photo(s) imported, {total_skipped} already present.'
            )
        )
        if total_imported > 0 and not dry_run:
            self.stdout.write(
                'Next step: visit /mit/reference-photos/ to tag and approve each photo.'
            )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _latest_claim_ids(n: int) -> list[str]:
        """
        Return the Encircle claim IDs for the N most-recently created active clients
        that have a non-empty encircle_claim_id.
        """
        from docsAppR.models import Client
        qs = (
            Client.objects
            .filter(archived=False, encircle_claim_id__isnull=False)
            .exclude(encircle_claim_id='')
            .order_by('-created_at')
            .values_list('encircle_claim_id', flat=True)[:n]
        )
        # Deduplicate while preserving order (multiple clients can share a claim)
        seen = set()
        ids  = []
        for cid in qs:
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
        return ids

    @staticmethod
    def _is_target_room(room_name: str, series_prefix: str) -> bool:
        """Return True if the room name starts with a number in the target series."""
        if not room_name:
            return False
        m = re.match(r'^(\d+)', room_name.strip())
        if not m:
            return False
        return m.group(1).startswith(series_prefix)

    @staticmethod
    def _safe_name(name: str) -> str:
        """Convert a room name to a filesystem-safe directory name."""
        return re.sub(r'[^\w\-]', '_', name.strip())[:60]

    @staticmethod
    def _download(url: str, api) -> tuple[str, bytes]:
        """Download a photo URL and return (extension, bytes)."""
        headers = getattr(api, 'headers', {})
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        ct  = r.headers.get('content-type', '').split(';')[0].strip()
        ext = {'image/jpeg': '.jpg', 'image/png': '.png',
               'image/webp': '.webp', 'image/heic': '.heic'}.get(ct, '.jpg')
        return ext, r.content
