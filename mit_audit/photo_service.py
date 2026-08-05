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

MAX_IMAGES      = 40     # Claude Vision limit per request (practical limit)
AI_MODEL        = 'claude-sonnet-4-6'
AI_MAX_TOKENS   = 4096

# ---------------------------------------------------------------------------
# Encircle photo retrieval
# ---------------------------------------------------------------------------

def fetch_encircle_photos(encircle_claim_id: str) -> list[dict]:
    """
    Fetch all media items for an Encircle claim.
    Returns a list of dicts: [{ 'id', 'url', 'room', 'media_type', ... }, ...]
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
                photos.append({
                    'id':         str(item.get('id', '')),
                    'url':        item.get('url') or item.get('download_url') or '',
                    'room':       item.get('room_name') or item.get('room') or '',
                    'media_type': media_type,
                    'thumbnail':  item.get('thumbnail_url') or '',
                })
        logger.info('[MIT] Fetched %d photos from Encircle claim %s',
                    len(photos), encircle_claim_id)
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

_REVIEW_PROMPT = """You are a licensed water mitigation specialist and insurance documentation expert.
You are reviewing job-site photos from an Encircle claim to audit whether all required mitigation equipment is present and documented.

REQUIRED EQUIPMENT LIST:
{items_list}

For each item in the required equipment list, examine all provided photos and determine:
  - How many units of that equipment are CLEARLY visible (do not count partially obscured equipment unless you are confident)
  - Which photo IDs (from the list below) support your finding
  - Your confidence level: "high", "medium", or "low"

For items marked as STABILIZATION_REQUIRED, also determine whether there is a photo that clearly shows the equipment properly set up (e.g. dehumidifier with hose connected, zipper wall with both poles visible, double zipper wall with at least TWO poles visible).

Photo IDs available in this review:
{photo_ids}

IMPORTANT RULES:
- Only mark as confirmed when you can clearly count the equipment units in the photos
- If a photo is blurry, distant, or the equipment is partially obstructed, note this but do NOT count it
- For double zipper walls: a photo only passes if BOTH the wall AND at least 2 poles are clearly visible
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
      "notes": "Dehumidifier in photo 001 shows condensate hose connected and running."
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

    # Select photos to send (cap at MAX_IMAGES)
    selected_photos = photos[:MAX_IMAGES]
    photo_ids_str   = ', '.join(p['id'] for p in selected_photos)

    # Fetch API key for Encircle photo downloads
    encircle_key = getattr(EncircleAPIClient, 'API_KEY', '') or \
                   __import__('os').environ.get('ENCIRCLE_API_KEY', '')

    # Build content list: images first, then the prompt text
    content = []
    loaded  = 0
    total   = len(selected_photos)

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
        # Annotate with photo ID so Claude can reference it
        content.append({
            'type': 'text',
            'text': f'[Photo ID: {photo["id"]} | Room: {photo.get("room", "unknown")}]',
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

    prompt = _REVIEW_PROMPT.format(items_list=items_list, photo_ids=photo_ids_str)
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
