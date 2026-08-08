"""
mit_audit/photo_service.py

Two responsibilities:
  1. fetch_encircle_photos()   — pull all media for a claim from Encircle API
  2. review_photos_with_ai()   — send photos to Claude; get back per-equipment
                                  observation dicts + stabilization findings

Claude prompt design:
  We send up to MAX_IMAGES photos (base64 encoded) and the required-equipment
  list, asking for a structured JSON array back.  Each array element maps to
  one required equipment item with visible_quantity, confidence, notes, and
  supporting_photo_ids.

  For stabilization items (dehumidifiers, air cleaners, zipper walls) the
  prompt also asks for a separate stabilization_check key.
"""
import base64
import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CLAIM_PHOTOS_PER_CALL = 30  # claim-side slots per per-category AI call
                                # reference photos fill the rest (no cap — all approved ones sent)
AI_MODEL      = 'claude-sonnet-4-6'
AI_MAX_TOKENS = 4096

# ---------------------------------------------------------------------------
# Room classification
# ---------------------------------------------------------------------------
# The tech creates rooms in Encircle following naming conventions that tell us
# what type of documentation is in that room:
#
#   full_equip    — "600" or "HOW2 PICS … MITIGATION EQUIPMENT" rooms.
#                   Contains photos of ALL equipment deployed for the job.
#                   Use for general equipment quantity audit.
#
#   stabilization — "STABILIZATION" rooms.
#                   Contains dedicated stabilization photos showing equipment
#                   connected and actively running.
#
#   drying_chamber— "DRYING CHAMBER" rooms.
#                   Photos confirming chamber setup — treated like stabilization.
#
#   other         — All other rooms (living room, bathroom, etc.).
#                   Job-site condition photos; used when no full_equip room exists.
# ---------------------------------------------------------------------------

_ROOM_FULL_EQUIP    = ['600', 'how2 pics', 'mitigation equipment',
                       'wtr mitigation equip', 'water mitigation equip',
                       'water equip', 'equip pics', 'full equip']
_ROOM_STABILIZATION = ['stabiliz', 'stab room', 'stab photo', 'stab docs']
_ROOM_DRYING_CHAMBER= ['drying chamber', 'dry chamber', 'drying room']


def classify_room(room_name: str) -> str:
    """
    Classify an Encircle room name into a photo-purpose bucket.
    Returns one of: 'full_equip' | 'stabilization' | 'drying_chamber' | 'other'
    """
    lower = (room_name or '').lower()
    if any(p in lower for p in _ROOM_FULL_EQUIP):
        return 'full_equip'
    if any(p in lower for p in _ROOM_STABILIZATION):
        return 'stabilization'
    if any(p in lower for p in _ROOM_DRYING_CHAMBER):
        return 'drying_chamber'
    return 'other'


# ---------------------------------------------------------------------------
# Encircle photo retrieval
# ---------------------------------------------------------------------------

def fetch_encircle_photos(encircle_claim_id: str) -> list[dict]:
    """
    Fetch all media items for an Encircle claim.
    Returns a list of dicts:
      [{ 'id', 'url', 'room', 'room_type', 'media_type', ... }, ...]

    room_type is one of: full_equip | stabilization | drying_chamber | other
    """
    try:
        from docsAppR.encircle_client import EncircleAPIClient
        api = EncircleAPIClient()
        raw = api.get_all_claim_media(encircle_claim_id)
        media_list = raw if isinstance(raw, list) else raw.get('list', [])
        # Encircle API media item fields (confirmed from ZipMediaDownloader):
        #   content_type  — 'image/jpeg', 'video/mp4', 'application/pdf', …
        #   download_uri  — signed download URL
        #   labels        — list of strings; first label = room name
        #   id            — numeric media ID
        _IMAGE_TYPES = {
            'image/jpeg', 'image/jpg', 'image/png',
            'image/gif',  'image/webp','image/heic',
            'image/heif', 'image/tiff',
        }
        photos = []
        for item in media_list:
            content_type = (item.get('content_type') or '').lower()
            # Skip non-images (PDFs, videos, audio)
            if content_type and content_type not in _IMAGE_TYPES:
                continue
            url = item.get('download_uri') or item.get('url') or item.get('download_url') or ''
            if not url:
                continue
            labels    = item.get('labels') or []
            room_name = labels[0] if labels else ''
            photos.append({
                'id':         str(item.get('id', '')),
                'url':        url,
                'room':       room_name,
                'room_type':  classify_room(room_name),
                'media_type': content_type or 'image/jpeg',
                'thumbnail':  item.get('thumbnail_url') or '',
            })
        # Log breakdown by room type so we know what we're working with
        by_type: dict[str, int] = {}
        for p in photos:
            by_type[p['room_type']] = by_type.get(p['room_type'], 0) + 1
        logger.info(
            '[MIT] Fetched %d photos from Encircle claim %s — by room type: %s',
            len(photos), encircle_claim_id, by_type,
        )
        return photos
    except Exception as exc:
        logger.error('[MIT] fetch_encircle_photos failed for %s: %s', encircle_claim_id, exc)
        return []


def download_photo_b64(url: str, api_key: str = '') -> tuple[str, str]:
    """
    Download a photo URL and return (base64_data, media_type).
    Returns ('', '') on failure.
    """
    import requests
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        ct = r.headers.get('content-type', 'image/jpeg').split(';')[0].strip()
        return base64.standard_b64encode(r.content).decode(), ct
    except Exception as exc:
        logger.warning('[MIT] Could not download photo %s: %s', url, exc)
        return '', ''


# ---------------------------------------------------------------------------
# Reference photo library — load ALL approved photos for one category
# ---------------------------------------------------------------------------

# Category slug → Xactimate line-item code (for labeling Claude's prompt)
_CATEGORY_XACT = {
    'dehumidifier':   'DH',
    'air_cleaner':    'NA / NAFAN',
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
}

# Stabilization requirements per category (plain-English, injected into prompt)
_STAB_REQUIREMENT = {
    'dehumidifier': (
        '1 photo — drain/condensate hose connected AND power indicator lit or unit audibly running.'
    ),
    'air_cleaner': (
        '1 photo — unit powered ON, intake and exhaust visible, indicator light on.'
    ),
    'zipper_wall': (
        'MINIMUM 2 photos: ① full zipper wall visible, ② support poles tensioned. '
        'OR 1 photo that clearly shows BOTH the wall AND poles together.'
    ),
    'double_zipper': (
        'MINIMUM 2 photos showing: the double zipper wall AND at least 2 support poles. '
        'Both poles MUST be clearly visible — 1 pole is NOT sufficient.'
    ),
    'hydroxyl': (
        '1 photo — brand/model clearly identifiable AND power or UV indicator light visible.'
    ),
}


def load_reference_photos_for_category(category: str) -> list[dict]:
    """
    Load ALL approved reference photos for a single equipment category.
    Returns list of dicts: [{ category, display_name, description, b64, media_type }]
    No cap — every variation matters.
    """
    try:
        from mit_audit.models import MITReferencePhoto
    except ImportError:
        return []

    refs = []
    qs = (
        MITReferencePhoto.objects
        .filter(category=category, approved=True, is_active=True)
        .order_by('-approved_at', '-created_at')
    )
    for photo in qs:
        try:
            data = Path(photo.file_path).read_bytes()
            b64  = base64.standard_b64encode(data).decode()
            ext  = Path(photo.file_path).suffix.lower().lstrip('.')
            mt   = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'png': 'image/png',  'webp': 'image/webp'}.get(ext, 'image/jpeg')
            refs.append({
                'category':     category,
                'display_name': photo.display_name or photo.get_category_display(),
                'description':  photo.description or '',
                'b64':          b64,
                'media_type':   mt,
            })
        except Exception as exc:
            logger.warning('[MIT] Could not load reference photo pk=%s: %s', photo.pk, exc)
    logger.debug('[MIT] Loaded %d reference photos for category %r', len(refs), category)
    return refs


# ---------------------------------------------------------------------------
# Per-category focused prompt
# ---------------------------------------------------------------------------

_SINGLE_ITEM_PROMPT = """\
You are a licensed water mitigation specialist reviewing Encircle job-site photos.
Your task is to audit ONE specific piece of equipment.

══ EQUIPMENT TO FIND ══════════════════════════════════════════════════════════
{display_name}  |  Xactimate: {xact_code}  |  Required qty: {required_quantity}
{stab_block}
══ REFERENCE PHOTOS ({ref_count} from our equipment library) ══════════════════
The [REF] photos above show this equipment in various models, brands, and
configurations used by our company. ALL variations count as the same line item.
Use them to recognise the equipment in the claim photos below.

══ CLAIM PHOTOS ═══════════════════════════════════════════════════════════════
Photo room tags:
  [EQUIP]  — equipment documentation room (primary source for quantity count)
  [STAB]   — stabilization room (primary source for stabilization check)
  [DCHAMB] — drying chamber room (same as STAB)
  [ROOM]   — general job-site room (secondary evidence only)

Claim photo IDs in this batch: {photo_ids}

══ COUNTING RULES ══════════════════════════════════════════════════════════════
• Count physical units — the same unit in two photos = 1 unit, not 2
• Do not count blurry, distant, or heavily obstructed units
• Prefer [EQUIP] photos for the quantity count
• Prefer [STAB] / [DCHAMB] photos for the stabilization check

══ RETURN FORMAT ═══════════════════════════════════════════════════════════════
Return a SINGLE JSON object (not an array), no markdown fences:
{{
  "equipment_type": "{equipment_type}",
  "display_name": "{display_name}",
  "required_quantity": {required_quantity},
  "visible_quantity": <int>,
  "missing_quantity": <int>,
  "status": "confirmed|partial|missing|manual",
  "supporting_photo_ids": ["<id>", ...],
  "ai_confidence": "high|medium|low",
  "ai_notes": "<what you saw, where, any caveats>",
  "stabilization_check": {{
    "required": {stab_required},
    "found": <true|false|null>,
    "photo_count": <int>,
    "notes": "<which photos satisfy the standard, or what is missing>"
  }},
  "recommended_action": "<one sentence for the tech>"
}}
"""


# ---------------------------------------------------------------------------
# AI photo review — one Claude call per line item
# ---------------------------------------------------------------------------

def review_photos_with_ai(
    required_items: list[dict],
    photos: list[dict],
    anthropic_api_key: str,
    model: str = AI_MODEL,
    task_self=None,
) -> list[dict]:
    """
    Review Encircle claim photos against the required equipment list.

    Strategy: one focused Claude Vision call PER equipment line item.
      • Each call receives ALL approved reference photos for that category
        (every variation from the equipment library — no cap)
      • Each call receives up to MAX_CLAIM_PHOTOS_PER_CALL claim photos,
        prioritised by room type (EQUIP → STAB → DCHAMB → ROOM)
      • The prompt is scoped to a single equipment type so Claude cannot
        confuse similar-looking items
      • Results are collected and returned as a flat list (same shape as before)

    Args:
        required_items:    List of required equipment dicts (from workbook_service).
        photos:            List of photo dicts from fetch_encircle_photos().
        anthropic_api_key: Anthropic API key.
        model:             Claude model ID.
        task_self:         Celery task instance (for update_state progress).

    Returns:
        List of observation dicts, one per required item.
    """
    import anthropic as _anthropic
    from docsAppR.encircle_client import EncircleAPIClient

    if not required_items:
        logger.warning('[MIT] No required items to review')
        return []

    # No-photos fast path
    if not photos:
        logger.warning('[MIT] No photos available for review')
        return [_missing_obs(item, 'No Encircle photos available for this job.',
                             'Photograph all equipment before leaving the job site.')
                for item in required_items]

    encircle_key = (
        getattr(EncircleAPIClient, 'API_KEY', '')
        or __import__('os').environ.get('ENCIRCLE_API_KEY', '')
    )
    client = _anthropic.Anthropic(api_key=anthropic_api_key)

    # Pre-prioritise claim photos by room type (done once, reused per item)
    ordered_photos: list[dict] = []
    for room_type in ('full_equip', 'stabilization', 'drying_chamber', 'other'):
        ordered_photos.extend(p for p in photos if p.get('room_type') == room_type)

    total_items = len(required_items)
    results: list[dict] = []

    for idx, item in enumerate(required_items):
        if task_self:
            pct = 20 + int(idx / total_items * 60)
            task_self.update_state(
                state='PROGRESS',
                meta={
                    'step':    f'Reviewing {item["display_name"]} ({idx + 1}/{total_items})…',
                    'percent': pct,
                },
            )

        obs = _review_single_item(
            item           = item,
            ordered_photos = ordered_photos,
            encircle_key   = encircle_key,
            client         = client,
            model          = model,
        )
        results.append(obs)
        # Brief pause so we don't hammer the rate limit between items
        if idx < total_items - 1:
            time.sleep(1)

    return results


def _review_single_item(
    item: dict,
    ordered_photos: list[dict],
    encircle_key: str,
    client,
    model: str,
) -> dict:
    """
    Run one Claude Vision call for a single required equipment item.
    Returns an observation dict.
    """
    category   = item.get('category', 'other')
    xact_code  = _CATEGORY_XACT.get(category, category.upper())
    requires_stab = bool(item.get('requires_stabilization_photo'))

    # ── 1. Load ALL reference photos for this category (no cap) ──────────────
    refs = load_reference_photos_for_category(category)

    # ── 2. Select claim photos (up to MAX_CLAIM_PHOTOS_PER_CALL) ─────────────
    selected_claim = ordered_photos[:MAX_CLAIM_PHOTOS_PER_CALL]

    # ── 3. Build message content ─────────────────────────────────────────────
    content: list[dict] = []

    # Reference photos first — labeled so Claude knows what it's seeing
    if refs:
        content.append({'type': 'text', 'text': (
            f'=== REFERENCE PHOTOS FOR: {item["display_name"].upper()} ===\n'
            f'The following {len(refs)} photo(s) show this exact equipment type '
            f'in different models, brands, and configurations. '
            f'All variations count as the same Xactimate line item ({xact_code}).\n'
        )})
        for i, ref in enumerate(refs, 1):
            desc = f' — {ref["description"]}' if ref.get('description') else ''
            content.append({
                'type': 'text',
                'text': f'[REF {i}/{len(refs)}: {ref["display_name"]}{desc}]',
            })
            content.append({
                'type':   'image',
                'source': {
                    'type':       'base64',
                    'media_type': ref['media_type'],
                    'data':       ref['b64'],
                },
            })
        content.append({'type': 'text', 'text': '=== END REFERENCE PHOTOS ==='})

    # Claim photos
    loaded_ids: list[str] = []
    for photo in selected_claim:
        b64, mt = download_photo_b64(photo['url'], encircle_key)
        if not b64:
            continue
        content.append({
            'type':   'image',
            'source': {'type': 'base64', 'media_type': mt, 'data': b64},
        })
        tag = {
            'full_equip':    'EQUIP',
            'stabilization': 'STAB',
            'drying_chamber':'DCHAMB',
        }.get(photo.get('room_type', 'other'), 'ROOM')
        content.append({
            'type': 'text',
            'text': f'[Photo ID: {photo["id"]} | Room: {photo.get("room","?")} | {tag}]',
        })
        loaded_ids.append(photo['id'])

    if not loaded_ids:
        logger.warning('[MIT] No photos downloaded for %r — marking manual', category)
        return _missing_obs(item,
                            'Photos could not be downloaded for AI review.',
                            'Manually review Encircle photos.',
                            status='manual', confidence='low')

    # ── 4. Build focused prompt ──────────────────────────────────────────────
    stab_block = ''
    if requires_stab:
        req_text = _STAB_REQUIREMENT.get(category, '1 photo showing equipment running.')
        stab_block = (
            f'\nSTABILIZATION REQUIRED — standard for this item:\n'
            f'  {req_text}\n'
        )

    prompt = _SINGLE_ITEM_PROMPT.format(
        display_name      = item['display_name'],
        xact_code         = xact_code,
        required_quantity = item['required_quantity'],
        equipment_type    = item['equipment_type'],
        stab_block        = stab_block,
        ref_count         = len(refs),
        photo_ids         = ', '.join(loaded_ids),
        stab_required     = 'true' if requires_stab else 'false',
    )
    content.append({'type': 'text', 'text': prompt})

    logger.info(
        '[MIT] Reviewing %r — %d ref photos, %d claim photos',
        item['display_name'], len(refs), len(loaded_ids),
    )

    # ── 5. Call Claude ───────────────────────────────────────────────────────
    raw = _call_claude(client, model, content)
    if raw is None:
        return _missing_obs(item,
                            'Claude API did not respond after 3 attempts.',
                            'Retry the audit or review manually.',
                            status='manual', confidence='low')

    return _parse_single_obs(raw, item)


def _call_claude(client, model: str, content: list[dict]) -> str | None:
    """Call Claude with retry on rate-limit. Returns raw text or None."""
    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=AI_MAX_TOKENS,
                messages=[{'role': 'user', 'content': content}],
            )
            return resp.content[0].text
        except Exception as exc:
            # Lazy import to avoid hard dependency at module load time
            try:
                import anthropic as _a
                if isinstance(exc, _a.RateLimitError):
                    wait = min(60, 2 ** attempt * 5)
                    logger.warning('[MIT] Rate limit — waiting %ds (attempt %d)', wait, attempt)
                    time.sleep(wait)
                    continue
            except ImportError:
                pass
            logger.error('[MIT] Claude API error (attempt %d): %s', attempt, exc)
            if attempt == 3:
                return None
            time.sleep(3)
    return None


def _parse_single_obs(raw: str, item: dict) -> dict:
    """
    Parse a single-item JSON object from Claude's response.
    Falls back to a manual-review placeholder if parsing fails.
    """
    text = re.sub(r'^```[a-z]*\n?', '', raw.strip())
    text = re.sub(r'\n?```$', '', text).strip()

    # Try direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            _coerce_obs(obj, item)
            return obj
        if isinstance(obj, list) and obj:
            _coerce_obs(obj[0], item)
            return obj[0]
    except json.JSONDecodeError:
        pass

    # Try to extract a JSON object from a larger blob
    m = re.search(r'\{[\s\S]+\}', text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                _coerce_obs(obj, item)
                return obj
        except json.JSONDecodeError:
            pass

    logger.error('[MIT] Could not parse single-item response for %r — raw: %.200s',
                 item.get('display_name'), raw)
    return _missing_obs(item,
                        'AI response could not be parsed. Manual review required.',
                        'Review Encircle photos manually.',
                        status='manual', confidence='low')


def _coerce_obs(obs: dict, item: dict) -> None:
    """Ensure required fields are present with sane types (mutates obs in-place)."""
    obs.setdefault('equipment_type',      item.get('equipment_type', ''))
    obs.setdefault('display_name',        item.get('display_name', ''))
    obs.setdefault('required_quantity',   item.get('required_quantity', 0))
    obs.setdefault('visible_quantity',    0)
    obs.setdefault('missing_quantity',    0)
    obs.setdefault('supporting_photo_ids', [])
    obs.setdefault('ai_confidence',       'low')
    obs.setdefault('ai_notes',            '')
    obs.setdefault('recommended_action',  '')
    obs.setdefault('stabilization_check', {
        'required': item.get('requires_stabilization_photo', False),
        'found':    None,
        'photo_count': 0,
        'notes':    '',
    })
    # Ensure integer types
    try:
        obs['visible_quantity']  = int(obs['visible_quantity'])
        obs['required_quantity'] = int(obs['required_quantity'])
    except (TypeError, ValueError):
        pass
    obs['missing_quantity'] = max(
        obs.get('required_quantity', 0) - obs.get('visible_quantity', 0), 0
    )


def _missing_obs(
    item: dict,
    ai_notes: str,
    recommended_action: str,
    status: str = 'missing',
    confidence: str = 'high',
) -> dict:
    """Build a placeholder observation for an item that could not be reviewed."""
    return {
        'equipment_type':       item.get('equipment_type', ''),
        'display_name':         item.get('display_name', ''),
        'required_quantity':    item.get('required_quantity', 0),
        'visible_quantity':     0,
        'missing_quantity':     item.get('required_quantity', 0),
        'status':               status,
        'supporting_photo_ids': [],
        'ai_confidence':        confidence,
        'ai_notes':             ai_notes,
        'stabilization_check':  {
            'required':    item.get('requires_stabilization_photo', False),
            'found':       False,
            'photo_count': 0,
            'notes':       ai_notes,
        },
        'recommended_action':   recommended_action,
    }
