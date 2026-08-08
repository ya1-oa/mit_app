"""
management/commands/import_reference_photos.py

Download photos from Encircle claims and store them locally as reference
photos for the MIT AI review system.

Usage:
    # Auto-discover the N most-documented recent claims (scans Encircle, default 6):
    python manage.py import_reference_photos

    # Import specific claim IDs:
    python manage.py import_reference_photos abc123 def456

Options:
    --latest N          How many claims to collect in auto-discover mode (default: 6)
    --pool N            How many recent clients to scan when auto-discovering (default: 30)
    --room-series 6     Only import rooms whose number starts with this digit.
                        NOTE: if Encircle rooms aren't numerically named (e.g. "Living Room"
                        rather than "601 Living Room"), use --all-rooms instead.
    --all-rooms         Import every room regardless of name (default in auto-discover mode)
    --overwrite         Re-download even if source_media_id already exists
    --dry-run           Print what would be imported without writing anything
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
    'BARRP':   'tension_poles',
    'BARR':    'zipper_wall',
    'WALL':    'wall_cavity',
    'WALLH':   'wall_cavity',
    'WFI':     'floor_drying',
    'HTBL':    'drying_blanket',
    'DUCTLF':  'other',
    'DODHY>':  'hydroxyl',
    'BWCDU':   'bound_water',
    'CCDU':    'ceiling_cavity',
    'CABDU':   'cabinet_drying',
    'CLSTDU':  'closet_drying',
    'HTAM':    'heat_air_mover',
}

# ---------------------------------------------------------------------------
# Claim 1021079 — "HOW2 PICS 600 WTR MITIGATION EQUIPMENT"
# Each room in this claim is named after an equipment type, making it the
# canonical reference photo library.  Room name → category slug mapping.
# ---------------------------------------------------------------------------
_REFERENCE_CLAIM_ROOM_MAP: dict[str, str] = {
    'afd nafan hepa air cleaners':              'air_cleaner',
    'hydroxyl machines':                        'hydroxyl',
    'dh dehumidifiers':                         'dehumidifier',
    'zip walls & support poles':                'zipper_wall',
    'zip walls and support poles':              'zipper_wall',
    'am air movers':                            'blower',
    'wcdu wall cavity drying unit':             'wall_cavity',
    'ccdu cavity drying unit':                  'ceiling_cavity',
    'cabdu cabinet drying unit':                'cabinet_drying',
    'bwcdu bound water cavity drying unit':     'bound_water',
    'wfi wood floor drying injection units':    'floor_drying',
    'htbl heated blanket floor drying units':   'drying_blanket',
    'grm sprayers anti microbial':              'antimicrobial',
    'exhaust system':                           'other',
    'backpack hepa vacuum':                     'other',
    'ppe personal protection equipment suits':  'other',
    'multi pics equipment':                     'other',
    'trailer atl #1 black beauty':              'other',
}

# Claims whose rooms ARE the equipment categories — photos get auto-approved
# when imported with --auto-approve.
REFERENCE_CLAIM_IDS = {'1021079'}


# Category slug → Xactimate billing code (stamped on auto-approved photos)
_CATEGORY_XACT_CODE: dict[str, str] = {
    'dehumidifier':   'DH',
    'air_cleaner':    'NA',
    'zipper_wall':    'BARRZ',
    'double_zipper':  'BARRZ+',
    'blower':         'DRY',
    'heat_air_mover': 'HTAM',
    'hydroxyl':       'DODHY',
    'ceiling_cavity': 'CCDU',
    'wall_cavity':    'WCDU',
    'cabinet_drying': 'CABDU',
    'closet_drying':  'CLSTDU',
    'floor_drying':   'WFI',
    'drying_blanket': 'HTBL',
    'bound_water':    'BWCDU',
    'tension_poles':  'BARRP',
    'antimicrobial':  'GRM',
}


def _room_to_category(room_name: str, claim_id: str) -> str:
    """
    Return the category slug for a room in a known reference claim.
    Falls back to '' (untagged) if the room isn't in the map.
    """
    if claim_id not in REFERENCE_CLAIM_IDS:
        return ''
    key = room_name.strip().lower()
    return _REFERENCE_CLAIM_ROOM_MAP.get(key, '')


class Command(BaseCommand):
    help = (
        'Import Encircle photos as MIT reference photos for AI-assisted review. '
        'When no claim IDs are given, auto-discovers recent well-documented claims.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'claim_ids', nargs='*', type=str,
            help='Encircle claim ID(s). Omit to auto-discover.',
        )
        parser.add_argument(
            '--latest', type=int, default=6,
            help='Number of claims to collect in auto-discover mode (default: 6).',
        )
        parser.add_argument(
            '--pool', type=int, default=30,
            help='Number of recent clients to scan when auto-discovering (default: 30).',
        )
        parser.add_argument(
            '--room-series', type=str, default='',
            help=(
                'Only import rooms whose name starts with this digit '
                '(e.g. "6" for 601, 602 …). '
                'Leave blank (default) to import all rooms.'
            ),
        )
        parser.add_argument(
            '--all-rooms', action='store_true',
            help='Import every room. This is the default in auto-discover mode.',
        )
        parser.add_argument(
            '--overwrite', action='store_true',
            help='Re-download even if the Encircle media ID is already stored.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be imported without writing anything.',
        )
        parser.add_argument(
            '--auto-approve', action='store_true',
            help=(
                'Automatically approve and categorise photos from known reference '
                'claims (currently: 1021079 — HOW2 PICS equipment library). '
                'Rooms in those claims are named after equipment types, so no '
                'manual review is needed. Photos for "other" rooms are still '
                'imported as untagged/unapproved.'
            ),
        )

    # ── Entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        from docsAppR.encircle_client import EncircleAPIClient

        claim_ids   = options['claim_ids']
        latest_n    = options['latest']
        pool_size   = options['pool']
        room_series = options['room_series']
        all_rooms   = options['all_rooms'] or not room_series  # default: all rooms
        overwrite   = options['overwrite']
        dry_run     = options['dry_run']
        auto_approve= options['auto_approve']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be written.'))

        try:
            api = EncircleAPIClient()
        except Exception as exc:
            raise CommandError(f'Could not initialise Encircle API client: {exc}')

        # ── Resolve claim IDs ────────────────────────────────────────────────
        if not claim_ids:
            self.stdout.write(
                f'Scanning up to {pool_size} recent claims for ones with photos…'
            )
            claim_ids, media_cache = self._discover_claims(latest_n, pool_size, api)
            if not claim_ids:
                raise CommandError(
                    'No claims with photo content found in the last '
                    f'{pool_size} clients. '
                    'Supply claim IDs manually or increase --pool.'
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Selected {len(claim_ids)} claim(s): {", ".join(claim_ids)}'
                )
            )
        else:
            media_cache = {}   # no pre-fetch for manual runs
            self.stdout.write(f'Using {len(claim_ids)} explicit claim ID(s).')

        dest_base = Path(settings.MEDIA_ROOT) / 'mit_reference_photos' / 'pending'
        if not dry_run:
            dest_base.mkdir(parents=True, exist_ok=True)

        total_imported = 0
        total_skipped  = 0

        for claim_id in claim_ids:
            self.stdout.write(f'\n── Claim {claim_id} ──')

            # Use cached media if available (from discovery pass)
            if claim_id in media_cache:
                media_items = media_cache[claim_id]
                self.stdout.write(f'  {len(media_items)} media items (cached from scan)')
            else:
                try:
                    raw         = api.get_all_claim_media(claim_id)
                    media_items = raw if isinstance(raw, list) else raw.get('list', [])
                    self.stdout.write(f'  {len(media_items)} total media items')
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f'  Failed to fetch media: {exc}'))
                    continue

            # Encircle API media fields:
            #   content_type  → 'image/jpeg', 'video/mp4', 'application/pdf' …
            #   download_uri  → signed download URL
            #   labels        → hierarchy list: labels[0] = building, labels[1] = room name
            _IMAGE_TYPES = {
                'image/jpeg', 'image/jpg', 'image/png',
                'image/gif',  'image/webp','image/heic',
                'image/heif', 'image/tiff',
            }
            for item in media_items:
                content_type = (item.get('content_type') or '').lower()

                # Skip non-images (PDFs, videos, audio)
                # If content_type is blank, allow it (old API fallback)
                if content_type and content_type not in _IMAGE_TYPES:
                    continue

                labels    = item.get('labels') or []
                # labels hierarchy: [building, room, ...] — room is at index 1
                room_name = labels[1] if len(labels) >= 2 else (labels[0] if labels else '')
                url       = (item.get('download_uri')
                             or item.get('url')
                             or item.get('download_url')
                             or '')

                # Prefer explicit id field; fall back to UUID embedded in the
                # Azure Blob URL path: .../pictures/{UUID}?se=...&sig=...
                # This is always present and unique per photo.
                _uuid_pat = re.compile(r'/pictures/([0-9a-f\-]{36})', re.I)
                media_id  = (str(item.get('id') or '')
                             or str(item.get('primary_id') or ''))
                if not media_id and url:
                    _m = _uuid_pat.search(url)
                    media_id = _m.group(1) if _m else ''

                if not url:
                    self.stderr.write(f'  [SKIP] {media_id}: no download_uri — skipping')
                    total_skipped += 1
                    continue

                # Room series filter (skipped if all_rooms)
                if not all_rooms and not self._is_target_room(room_name, room_series):
                    continue

                # Duplicate check
                if not overwrite and media_id:
                    if MITReferencePhoto.objects.filter(source_media_id=media_id).exists():
                        total_skipped += 1
                        continue

                if dry_run:
                    self.stdout.write(f'  [DRY] Would import: {room_name or "(no room)"} / {media_id}')
                    total_imported += 1
                    continue

                # Download
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

                # Auto-categorise + approve photos from known reference claims
                from django.utils import timezone as _tz
                category     = ''
                approved     = False
                approved_at  = None
                display_name = ''
                if auto_approve:
                    category = _room_to_category(room_name, claim_id)
                    if category and category != 'other':
                        approved     = True
                        approved_at  = _tz.now()
                        # e.g. "DH Dehumidifiers" → "Dh Dehumidifiers" (readable label)
                        display_name = room_name.title()

                xact_code = _CATEGORY_XACT_CODE.get(category, '') if category else ''

                _, created = MITReferencePhoto.objects.update_or_create(
                    source_media_id=media_id,
                    defaults={
                        'file_path':                str(dest_path),
                        'file_size_bytes':          len(file_bytes),
                        'source_encircle_claim_id': claim_id,
                        'source_room_name':         room_name,
                        'category':                 category,
                        'display_name':             display_name,
                        'xact_code':                xact_code,
                        'approved':                 approved,
                        'approved_at':              approved_at,
                        'is_active':                True,
                    },
                )
                action = 'Created' if created else 'Updated'
                tag = f' → {category} [AUTO-APPROVED]' if approved else (' → untagged' if not category else f' → {category} (needs approval)')
                self.stdout.write(
                    f'  [{action}] {room_name or "(no room)"} / {media_id}{tag}'
                )
                total_imported += 1
                time.sleep(0.05)

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone — {total_imported} photo(s) imported, {total_skipped} already present.'
            )
        )
        if total_imported == 0 and not dry_run:
            self.stdout.write(self.style.WARNING(
                'Tip: if Encircle rooms are named "Living Room" rather than '
                '"601 Living Room", run without --room-series (the default '
                'now imports all rooms).'
            ))
        elif total_imported > 0 and not dry_run:
            self.stdout.write(
                'Next step: visit /mit/reference-photos/ to tag and approve each photo.'
            )

    # ── Discovery ────────────────────────────────────────────────────────────

    def _discover_claims(
        self,
        n: int,
        pool_size: int,
        api,
    ) -> tuple[list[str], dict]:
        """
        Scan up to pool_size recent clients with Encircle IDs.
        Fetch media counts for each, then return the n claims with the
        most photos (best-documented jobs → most useful reference material).

        Returns (selected_claim_ids, media_cache) where media_cache maps
        claim_id → media_items list so we don't re-fetch during import.
        """
        from docsAppR.models import Client

        candidates = list(
            Client.objects
            .filter(archived=False, encircle_claim_id__isnull=False)
            .exclude(encircle_claim_id='')
            .order_by('-created_at')
            .values_list('encircle_claim_id', flat=True)[:pool_size]
        )

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for cid in candidates:
            if cid not in seen:
                seen.add(cid)
                unique.append(cid)

        # Fetch media count for each candidate
        results = []   # (photo_count, claim_id, media_items)
        for cid in unique:
            try:
                raw   = api.get_all_claim_media(cid)
                items = raw if isinstance(raw, list) else raw.get('list', [])
                photos = [
                    it for it in items
                    if not (it.get('media_type') or it.get('type') or '').lower() or
                       any(t in (it.get('media_type') or it.get('type') or '').lower()
                           for t in ('photo', 'image'))
                ]
                count = len(photos)
                self.stdout.write(f'  {cid}: {count} photos')
                if count > 0:
                    results.append((count, cid, items))
            except Exception as exc:
                self.stdout.write(f'  {cid}: API error — {exc}')

        # Pick the n most-documented claims
        results.sort(key=lambda r: r[0], reverse=True)
        top = results[:n]

        selected = [cid for _, cid, _ in top]
        cache    = {cid: items for _, cid, items in top}
        return selected, cache

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _is_target_room(room_name: str, series_prefix: str) -> bool:
        if not room_name:
            return False
        m = re.match(r'^(\d+)', room_name.strip())
        if not m:
            return False
        return m.group(1).startswith(series_prefix)

    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r'[^\w\-]', '_', name.strip())[:60]

    @staticmethod
    def _download(url: str, api) -> tuple[str, bytes]:
        # Azure Blob Storage SAS URLs (encircleuserdata.blob.core.windows.net)
        # already carry auth in query params (se/sp/sig).  Sending an
        # Authorization header alongside a SAS URL causes a 400:
        # "Authentication information is not given in the correct format."
        # So: use API headers only for non-SAS hosts.
        if 'blob.core.windows.net' in url or ('sig=' in url and 'se=' in url):
            headers = {}
        else:
            headers = getattr(api, 'headers', {})
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        ct  = r.headers.get('content-type', '').split(';')[0].strip()
        ext = {'image/jpeg': '.jpg', 'image/png': '.png',
               'image/webp': '.webp', 'image/heic': '.heic'}.get(ct, '.jpg')
        return ext, r.content
