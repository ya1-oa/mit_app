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

MAX_IMAGES          = 40   # Claude Vision limit per request (practical limit)
MAX_REFERENCE_PHOTOS = 3   # approved reference photos to include per equipment category
                           # 3 gives Claude multiple angles per type without crowding claim slots
AI_MODEL             = 'claude-sonnet-4-6'
AI_MAX_TOKENS        = 4096

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
        photos = []
        for item in media_list:
            media_type = (item.get('media_type') or item.get('type') or '').lower()
            # Include photos and video thumbnails; skip PDFs / audio
            if 'photo' in media_type or 'image' in media_type or not media_type:
                room_name = item.get('room_name') or item.get('room') or ''
                photos.append({
                    'id':         str(item.get('id', '')),
                    'url':        item.get('url') or item.get('download_url') or '',
                    'room':       room_name,
                    'room_type':  classify_room(room_name),
                    'media_type': media_type,
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
# AI photo review
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Reference photo library
# ---------------------------------------------------------------------------

def load_reference_photos(categories: list[str]) -> list[dict]:
    """
    Return up to MAX_REFERENCE_PHOTOS approved reference photos per category
    as a list of dicts: [{ 'category', 'display_name', 'description', 'b64', 'media_type' }]

    Returns an empty list if the model table doesn't exist yet (pre-migration).
    """
    try:
        from mit_audit.models import MITReferencePhoto
    except ImportError:
        return []

    refs = []
    for cat in categories:
        photos = (
            MITReferencePhoto.objects
            .filter(category=cat, approved=True, is_active=True)
            # approved_at nulls-last so auto-approved photos (approved_at=now()) sort first
            .order_by('-approved_at', '-created_at')[:MAX_REFERENCE_PHOTOS]
        )
        for photo in photos:
            try:
                data = Path(photo.file_path).read_bytes()
                b64  = base64.standard_b64encode(data).decode()
                # Guess media type from extension
                ext  = Path(photo.file_path).suffix.lower()
                mt   = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                        'png': 'image/png',  'webp': 'image/webp'}.get(ext.lstrip('.'), 'image/jpeg')
                refs.append({
                    'category':     cat,
                    'display_name': photo.display_name or photo.get_category_display(),
                    'description':  photo.description,
                    'b64':          b64,
                    'media_type':   mt,
                })
            except Exception as exc:
                logger.warning('[MIT] Could not load reference photo %s: %s', photo.pk, exc)
    return refs


_REVIEW_PROMPT = """You are a licensed water mitigation specialist and insurance documentation expert.
You are reviewing job-site photos from an Encircle claim to audit whether all required mitigation equipment is present and documented.

{reference_section}REQUIRED EQUIPMENT LIST:
{items_list}

PHOTO ROOM TYPES:
Each photo below is tagged with its Encircle room type:
  [EQUIP]  — "600" / mitigation-equipment room: contains photos of ALL deployed equipment.
              Use these for counting equipment quantities.
  [STAB]   — Stabilization room: dedicated stabilization documentation photos.
              Use these to verify STABILIZATION_REQUIRED items are properly running.
  [DCHAMB] — Drying Chamber room: photos of chamber setup (same rules as STAB).
  [ROOM]   — Regular job-site room. Use for secondary evidence only if EQUIP photos
              are unavailable or inconclusive.

STABILIZATION PHOTO STANDARD:
For every item marked STABILIZATION_REQUIRED, check whether a valid stabilization photo exists.
The standard is as follows — a photo FAILS if it does not meet these requirements:
  • Dehumidifier    — 1 photo: drain/condensate hose connected, power indicator lit or running
  • Air Cleaner     — 1 photo: unit powered on, intake/exhaust visible, indicator light on
  • Zipper Wall     — MINIMUM 2 photos: (1) full wall visible, (2) support poles tensioned
                      OR 1 single photo that clearly shows BOTH the wall AND the poles together
  • Double Zipper   — MINIMUM 2 photos showing: the double zipper wall AND at least 2 support poles
                      (both poles must be clearly visible; 1 pole is not sufficient)
  • Hydroxyl        — 1 photo: brand/model identifiable, power/UV indicator light visible

Claim photo IDs available in this review:
{photo_ids}

IMPORTANT RULES:
- Use the REFERENCE PHOTOS above (if provided) as your benchmark for what a good documentation photo looks like
- Prioritize [EQUIP] and [STAB] room photos for their respective checks
- Only mark as confirmed when you can clearly count the equipment units in the photos
- If a photo is blurry, distant, or the equipment is partially obstructed, note this but do NOT count it
- Count each physical unit separately — do not count the same unit twice from different angles
- Return ONLY a raw JSON array, no markdown fences, no explanation

JSON format:
[
  {{
    "equipment_type": "dehumidifier",
    "display_name": "LGR Dehumidifier",
    "required_quantity": 3,
    "visible_quantity": 2,
    "missing_quantity": 1,
    "status": "partial",
    "supporting_photo_ids": ["photo_001", "photo_004"],
    "ai_confidence": "high",
    "ai_notes": "Two dehumidifiers clearly visible in photos 001 and 004. Third unit not documented.",
    "stabilization_check": {{
      "required": true,
      "found": true,
      "photo_count": 1,
      "notes": "Photo 001 (STAB room) shows dehumidifier with condensate hose connected and running."
    }},
    "recommended_action": "Photograph the third dehumidifier with unit ID tag visible."
  }}
]

Include one entry for EVERY item in the required equipment list, even if visible_quantity is 0."""


def review_photos_with_ai(
    required_items: list[dict],
    photos: list[dict],
    anthropic_api_key: str,
    model: str = AI_MODEL,
    task_self=None,
) -> list[dict]:
    """
    Send Encircle photos to Claude and get back per-equipment observations.

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
    if not photos:
        logger.warning('[MIT] No photos available for review')
        return [{
            **item,
            'visible_quantity':    0,
            'missing_quantity':    item['required_quantity'],
            'status':              'missing',
            'supporting_photo_ids': [],
            'ai_confidence':       'high',
            'ai_notes':            'No Encircle photos available for this job.',
            'stabilization_check': {'required': item.get('requires_stabilization_photo'),
                                     'found': False, 'notes': 'No photos to review.'},
            'recommended_action':  'Photograph all equipment before leaving the job site.',
        } for item in required_items]

    # Build the items list for the prompt
    items_lines = []
    for it in required_items:
        stab_flag = 'STABILIZATION_REQUIRED' if it.get('requires_stabilization_photo') else ''
        items_lines.append(
            f"- {it['display_name']} | required: {it['required_quantity']} | "
            f"type: {it['equipment_type']} {stab_flag}"
        )
    items_list = '\n'.join(items_lines)

    # ── Load reference photos ──────────────────────────────────────
    # Get unique categories from required_items, then load 1 approved
    # reference photo per category.  These are prepended to the request
    # so Claude has a visual benchmark before it sees the claim photos.
    categories = list(dict.fromkeys(
        it.get('category', 'other') for it in required_items
    ))
    refs = load_reference_photos(categories)

    # Reserve slots for reference photos, leaving at least 10 for claim photos
    ref_slots  = min(len(refs), MAX_IMAGES - 10)
    refs       = refs[:ref_slots]
    claim_slots = MAX_IMAGES - len(refs)

    # ── Prioritise photos by room type ─────────────────────────────────────────
    # Send full_equip first (equipment quantity photos), then stab/drying_chamber
    # (stabilization docs), then other room photos to fill remaining slots.
    has_stab_items = any(it.get('requires_stabilization_photo') for it in required_items)

    ordered_photos: list[dict] = []
    for room_type in ('full_equip', 'stabilization', 'drying_chamber', 'other'):
        ordered_photos.extend(p for p in photos if p.get('room_type') == room_type)

    selected_photos = ordered_photos[:claim_slots]
    photo_ids_str   = ', '.join(p['id'] for p in selected_photos)

    # Log what we're actually sending
    type_counts = {}
    for p in selected_photos:
        type_counts[p.get('room_type', 'other')] = type_counts.get(p.get('room_type', 'other'), 0) + 1
    logger.info('[MIT] Sending %d photos to Claude — room breakdown: %s',
                len(selected_photos), type_counts)

    # Fetch API key for Encircle photo downloads
    encircle_key = getattr(EncircleAPIClient, 'API_KEY', '') or \
                   __import__('os').environ.get('ENCIRCLE_API_KEY', '')

    # ── Build content list ─────────────────────────────────────────
    # Order: reference photos → separator → claim photos → prompt
    content = []

    # 1. Reference photos (if any)
    if refs:
        content.append({'type': 'text', 'text': (
            '=== REFERENCE PHOTOS ===\n'
            'The following photos show correctly documented mitigation equipment '
            'from previous jobs. Use these as your benchmark when reviewing the '
            'claim photos below.\n'
        )})
        for ref in refs:
            content.append({'type': 'text', 'text': (
                f'REFERENCE [{ref["display_name"]}]: {ref["description"]}'
            )})
            content.append({
                'type': 'image',
                'source': {'type': 'base64', 'media_type': ref['media_type'], 'data': ref['b64']},
            })
        content.append({'type': 'text', 'text': '=== END REFERENCE PHOTOS ==='})
        logger.info('[MIT] Included %d reference photos in review', len(refs))

    # 2. Claim photos
    loaded = 0
    total  = len(selected_photos)

    for i, photo in enumerate(selected_photos):
        if task_self and i % 5 == 0:
            task_self.update_state(
                state='PROGRESS',
                meta={'step': f'Downloading photos {i}/{total}…', 'percent': 20 + int(i / total * 30)},
            )
        b64, mt = download_photo_b64(photo['url'], encircle_key)
        if not b64:
            continue
        content.append({
            'type': 'image',
            'source': {'type': 'base64', 'media_type': mt, 'data': b64},
        })
        # Annotate with photo ID, room, and room-type tag so Claude knows
        # which check to use each photo for.
        room_type_tag = {
            'full_equip':    'EQUIP',
            'stabilization': 'STAB',
            'drying_chamber':'DCHAMB',
        }.get(photo.get('room_type', 'other'), 'ROOM')
        content.append({
            'type': 'text',
            'text': (
                f'[Photo ID: {photo["id"]} | '
                f'Room: {photo.get("room", "unknown")} | '
                f'Type: {room_type_tag}]'
            ),
        })
        loaded += 1

    if loaded == 0:
        logger.error('[MIT] Could not download any photos — all returned empty')
        return [{
            **item,
            'visible_quantity':    0,
            'missing_quantity':    item['required_quantity'],
            'status':              'manual',
            'supporting_photo_ids': [],
            'ai_confidence':       'low',
            'ai_notes':            'Photos could not be downloaded for AI review.',
            'recommended_action':  'Manually review Encircle photos.',
        } for item in required_items]

    # 3. Prompt text
    reference_section = (
        f'(You have been given {len(refs)} reference photo(s) above as examples.)\n\n'
        if refs else ''
    )
    prompt = _REVIEW_PROMPT.format(
        reference_section=reference_section,
        items_list=items_list,
        photo_ids=photo_ids_str,
    )
    content.append({'type': 'text', 'text': prompt})

    if task_self:
        task_self.update_state(
            state='PROGRESS',
            meta={'step': f'Sending {loaded} photos to Claude for equipment review…', 'percent': 55},
        )

    client = _anthropic.Anthropic(api_key=anthropic_api_key)
    raw_response = None

    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=AI_MAX_TOKENS,
                messages=[{'role': 'user', 'content': content}],
            )
            raw_response = resp.content[0].text
            break
        except _anthropic.RateLimitError:
            wait = min(60, 2 ** attempt * 5)
            logger.warning('[MIT] Rate limit — waiting %ds (attempt %d)', wait, attempt)
            time.sleep(wait)
        except _anthropic.APIError as exc:
            logger.error('[MIT] Claude API error (attempt %d): %s', attempt, exc)
            if attempt == 3:
                raise
            time.sleep(3)

    if not raw_response:
        raise RuntimeError('No response from Claude after 3 attempts')

    return _parse_ai_response(raw_response, required_items)


def _parse_ai_response(raw: str, required_items: list[dict]) -> list[dict]:
    """
    Parse Claude's JSON response.  If parsing fails, build a manual-review
    result for every item so the pipeline doesn't block.
    """
    text = re.sub(r'^```[a-z]*\n?', '', raw.strip())
    text = re.sub(r'\n?```$', '', text).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            logger.info('[MIT] AI response parsed: %d observations', len(data))
            return data
    except json.JSONDecodeError:
        pass

    # Try to extract the JSON array from a larger blob
    m = re.search(r'\[[\s\S]+\]', text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    logger.error('[MIT] Could not parse AI response — marking all as manual review')
    return [{
        **item,
        'visible_quantity':    0,
        'missing_quantity':    item['required_quantity'],
        'status':              'manual',
        'supporting_photo_ids': [],
        'ai_confidence':       'low',
        'ai_notes':            'AI response could not be parsed. Manual review required.',
        'recommended_action':  'Review Encircle photos manually.',
    } for item in required_items]
