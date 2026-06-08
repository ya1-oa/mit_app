"""
AI-powered room content analysis for CPS Schedule of Loss reports.
Uses Claude vision to identify items, estimate replacement values, and assign ages.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import time

import requests

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """DIRECTIVE: You are a professional mitigation claim inspector. You review images and determine the replacement value of items in a client's home for insurance purposes.

You produce insurance-standard schedule of loss line items suitable for invoicing insurance companies.
Respond ONLY with valid JSON — no markdown, no explanation."""

_USER_PROMPT = """ACTION: Review the following photos of room "{room_name}" and give me the replacement value of each item shown.

CONTEXT:
- Base pricing on typical insurance claim replacement costs.
- Replacement price = what it would cost to buy the item new today at retail.
- Do NOT price any structural or permanently fixed building components. This explicitly includes: windows, window frames, window sills, stairs, railings, floorboards, hardwood/tile/carpet flooring, beams, support pillars, columns, walls, ceilings, roofing, baseboards, crown molding, built-in shelving, and any item that would remain in the property when a tenant moves out. If it stays with the building, exclude it entirely.
- This is for a mitigation claim — provide replacement cost of ALL items photographed. If there are multiple items, price them seperately. If its a flower pot we would price the pot and flour seperately.
- Use industry-standard format suitable for invoicing insurance companies.
- Avoid duplicates: if the same item appears in multiple photos, list it once.
- Estimate the age of each item based on visible wear, style, and condition.

For each item provide:
- description: clear insurance-standard item description (e.g. "Queen Size Bed Frame - Dark Wood - Upholstered")
- brand: brand/manufacturer if visible, otherwise ""
- condition: "Good", "Fair", or "Poor"
- qty: quantity (integer)
- model_number: if visible on item, otherwise ""
- serial_number: if visible on item, otherwise ""
- retailer: where this item would typically be purchased (e.g. "Home Depot", "Best Buy", "IKEA", "Walmart", "Amazon")
- replacement_source: "Online" or "Retail"
- purchase_price_each: estimated original purchase price in USD (number only)
- age_years: estimated age in years — inspect wear, style, technology generation (0–5 maximum per policy, vary between items)
- age_months: additional months beyond age_years (0–11)
- replacement_value_each: today's retail replacement cost in USD (number only)
- depreciation_category: one of — Clothing, Electronics, Furniture, Appliances, Bedding/Linens, Books/Media, Decor/Art, Toys/Games, Tools/Hardware, Kitchen/Cookware, Jewelry/Accessories, Sporting Goods, Musical Instruments, Other
- depreciation_pct: depreciation percentage based on age and condition (0–80, proportional — 5 yr old furniture ~30%, 10 yr old electronics ~70%)
- notes: any relevant insurance notes (brand visible, serial noted, heavy wear, etc.)

Return JSON in this exact format:
{{
  "items": [
    {{
      "description": "55-inch LED Smart TV",
      "brand": "Samsung",
      "condition": "Good",
      "qty": 1,
      "model_number": "",
      "serial_number": "",
      "retailer": "Best Buy",
      "replacement_source": "Retail",
      "purchase_price_each": 650,
      "age_years": 3,
      "age_months": 0,
      "replacement_value_each": 699,
      "depreciation_category": "Electronics",
      "depreciation_pct": 45,
      "notes": "Samsung logo visible"
    }}
  ],
  "confidence": "high|medium|low",
  "room_summary": "brief description of room and notable contents"
}}"""


_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/jpg', 'image/png'}

_IMAGES_PER_BATCH = 20

# ─────────────────────────────────────────────────────────────────────────────
# Structural item filter
# Items whose description matches any of these terms are flagged structural=True.
# They are NOT personal property and should not appear in a PPR claim line — but
# we auto-collapse them so an adjuster can still review before deleting.
# Keep lowercase; matching is case-insensitive substring.
# ─────────────────────────────────────────────────────────────────────────────
STRUCTURAL_TERMS: frozenset[str] = frozenset({
    # Walls & ceilings
    'wall', 'ceiling', 'drywall', 'sheetrock', 'plaster', 'stucco', 'crown molding',
    'baseboard', 'trim', 'wainscoting', 'chair rail',
    # Floors
    'floor', 'flooring', 'hardwood floor', 'laminate floor', 'tile floor',
    'carpet', 'subfloor', 'underlayment',
    # Doors & windows
    'door', 'window', 'window frame', 'window sill', 'window pane', 'windowsill',
    'sliding door', 'french door', 'exterior door', 'garage door', 'garage door opener',
    'door frame', 'door casing', 'door knob', 'door handle', 'deadbolt',
    # Stairs & structural elements
    'stair', 'staircase', 'stairway', 'railing', 'banister', 'baluster',
    'beam', 'support beam', 'column', 'pillar', 'post', 'support pillar',
    # Plumbing fixtures
    'toilet', 'bathtub', 'tub', 'shower', 'shower pan', 'shower surround',
    'sink', 'vanity sink', 'pedestal sink', 'kitchen sink', 'utility sink',
    'faucet', 'showerhead', 'shower head', 'drain',
    # Built-in cabinetry & shelving
    'cabinet', 'kitchen cabinet', 'bathroom cabinet', 'built-in cabinet',
    'built-in shelf', 'built-in shelving', 'closet shelf', 'closet rod',
    'linen closet', 'medicine cabinet',
    # Roofing & exterior
    'roof', 'roofing', 'shingle', 'gutter', 'downspout', 'soffit', 'fascia',
    'siding', 'brick', 'insulation',
    # HVAC & fixed systems
    'thermostat', 'hvac', 'furnace', 'ductwork', 'vent', 'register',
    'ceiling fan', 'exhaust fan', 'attic fan', 'whole house fan',
    # Electrical fixtures
    'light fixture', 'light switch', 'outlet', 'electrical outlet',
    'recessed light', 'recessed lighting', 'chandelier base',
    # Countertops (attached to house)
    'countertop', 'granite countertop', 'quartz countertop', 'counter',
    # Misc attached
    'fireplace', 'mantle', 'mantel', 'hearth', 'chimney',
    'garage', 'driveway', 'fence', 'deck', 'porch', 'patio',
})


def fetch_all_claim_media(encircle_claim_id: str) -> list[dict]:
    """Fetch all media for a claim once. Pass the result to filter_room_images for each room."""
    from docsAppR.encircle_client import EncircleAPIClient
    api = EncircleAPIClient()
    all_media: list[dict] = []
    after_cursor = None
    while True:
        params: dict = {'limit': 100}
        if after_cursor:
            params['after'] = after_cursor
        response = api._make_request(f"property_claims/{encircle_claim_id}/media", params=params)
        if not response or 'list' not in response:
            break
        all_media.extend(response['list'])
        after_cursor = response.get('cursor', {}).get('after')
        if not after_cursor:
            break
    logger.info(f"Fetched {len(all_media)} total media items for claim {encircle_claim_id}")
    return all_media


def filter_room_images(all_media: list[dict], room_number: str) -> list[str]:
    """
    Filter pre-fetched claim media to images belonging to a specific room.
    Matches by room number prefix: Encircle labels every photo with the room label
    which starts with the room number (e.g. "406 …. BR1 DN ….. PPR …..").
    Matching "406 " catches that room and nothing else.
    """
    prefix_lower = (room_number.strip() + " ").lower()
    exact_lower = room_number.strip().lower()

    # Log a sample of labels from the first few image items so we can verify field name/format
    sample_labels_logged = False

    urls: list[str] = []
    for item in all_media:
        ct = (item.get('content_type') or '').lower().split(';')[0].strip()
        if ct not in _IMAGE_CONTENT_TYPES:
            continue

        raw_labels = item.get('labels') or item.get('label') or item.get('tags') or []
        if not sample_labels_logged:
            logger.info(
                f"Room {room_number}: sample media item keys={list(item.keys())[:15]}, "
                f"labels field={repr(item.get('labels'))}, source={item.get('source')}"
            )
            sample_labels_logged = True

        labels = [str(l).lower() for l in (raw_labels if isinstance(raw_labels, list) else [raw_labels])]
        matched = any(l == exact_lower or l.startswith(prefix_lower) for l in labels)
        if not matched:
            continue

        url = (item.get('download_uri') or item.get('url') or
               item.get('download_url') or item.get('image_url'))
        if url:
            urls.append(url)

    logger.info(f"Room {room_number}: {len(urls)} images matched from {len(all_media)} claim media")
    return urls


def _image_url_to_base64(url: str) -> tuple[str, str] | None:
    """Download an image URL and return (base64_data, media_type)."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        ct = resp.headers.get('content-type', 'image/jpeg').split(';')[0].strip()
        if not ct.startswith('image/'):
            ct = 'image/jpeg'
        b64 = base64.standard_b64encode(resp.content).decode('utf-8')
        return b64, ct
    except Exception as e:
        logger.warning(f"Failed to download image {url}: {e}")
        return None


def _make_fallback_items(room_name: str) -> list[dict]:
    """Return generic items when no images are available."""
    return [
        {
            "description": f"Room Contents - {room_name}",
            "brand": "",
            "condition": "Fair",
            "qty": 1,
            "model_number": "",
            "serial_number": "",
            "retailer": "",
            "replacement_source": "Retail",
            "purchase_price_each": 0,
            "age_years": 2,
            "age_months": 0,
            "replacement_value_each": 0,
            "depreciation_category": "Other",
            "depreciation_pct": 20,
            "notes": "Manual entry required — no images available",
        }
    ]


_CPS_MODEL = "claude-haiku-4-5-20251001"


def _call_claude_with_images(client, image_content_blocks: list, room_name: str) -> tuple[dict, dict]:
    """
    Send one batch of image blocks to Claude and return (parsed_result, usage).
    usage = {'input_tokens': int, 'output_tokens': int}
    """
    content = list(image_content_blocks) + [{
        "type": "text",
        "text": _USER_PROMPT.format(room_name=room_name),
    }]
    response = client.messages.create(
        model=_CPS_MODEL,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    usage = {
        'input_tokens':  getattr(response.usage, 'input_tokens', 0),
        'output_tokens': getattr(response.usage, 'output_tokens', 0),
    }
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip()), usage


def _clean_items(items: list, start_order: int = 0) -> list:
    clean = []
    for i, item in enumerate(items):
        age_years = max(0, min(5, int(item.get("age_years", 0) or 0)))
        age_months = max(0, min(11, int(item.get("age_months", 0) or 0)))
        if age_years >= 5:
            age_months = 0
        clean.append({
            "description": str(item.get("description", ""))[:500],
            "brand": str(item.get("brand", ""))[:200],
            "condition": str(item.get("condition", "Good")),
            "qty": max(1, int(item.get("qty", 1) or 1)),
            "model_number": str(item.get("model_number", ""))[:200],
            "serial_number": str(item.get("serial_number", ""))[:200],
            "retailer": str(item.get("retailer", ""))[:200],
            "replacement_source": str(item.get("replacement_source", "Retail")),
            "purchase_price_each": float(item.get("purchase_price_each", 0) or 0),
            "age_years": age_years,
            "age_months": age_months,
            "replacement_value_each": float(item.get("replacement_value_each", 0) or 0),
            "depreciation_category": str(item.get("depreciation_category", "Other"))[:100],
            "depreciation_pct": max(0, min(80, float(item.get("depreciation_pct", 0) or 0))),
            "notes": str(item.get("notes", ""))[:500],
            "ai_suggested": True,
            "order": start_order + i,
        })
    return clean


def flag_structural_items(items: list[dict]) -> list[dict]:
    """
    Walk a cleaned item list and set structural=True on any item whose
    description contains a known structural/building term.
    Mutates the dicts in-place and returns the same list.
    """
    for item in items:
        desc_lower = item.get('description', '').lower()
        item['structural'] = any(term in desc_lower for term in STRUCTURAL_TERMS)
    return items


def analyze_room_for_cps(
    room_name: str,
    room_number: str,
    prefetched_media: list[dict],
    image_urls: list[str] | None = None,
) -> dict:
    """
    Analyze a room using Claude vision and return structured schedule of loss items.
    Pass prefetched_media (from fetch_all_claim_media) and the room_number (e.g. "406")
    to filter images for this room.

    Returns:
        {
          "success": bool,
          "items": [...],
          "confidence": str,
          "room_summary": str,
          "images_used": int,
          "error": str | None,
        }
    """
    import anthropic

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {
            "success": False, "items": [], "confidence": "none",
            "room_summary": "", "images_used": 0,
            "error": "ANTHROPIC_API_KEY not configured",
        }

    urls = list(image_urls or [])
    if not urls:
        urls = filter_room_images(prefetched_media, room_number)

    if not urls:
        return {
            "success": False,
            "items": _make_fallback_items(room_name),
            "confidence": "none",
            "room_summary": "No images available",
            "images_used": 0,
            "error": "No images available for this room",
        }

    image_blocks = []
    for url in urls:
        result = _image_url_to_base64(url)
        if result:
            b64, media_type = result
            image_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })

    if not image_blocks:
        return {
            "success": False,
            "items": _make_fallback_items(room_name),
            "confidence": "none",
            "room_summary": "Could not download images",
            "images_used": 0,
            "error": "Could not download any images",
        }

    logger.info(f"Analyzing {len(image_blocks)} images for '{room_name}' in {math.ceil(len(image_blocks) / _IMAGES_PER_BATCH)} batch(es)")

    client = anthropic.Anthropic(api_key=api_key)
    all_items: list[dict] = []
    confidences: list[str] = []
    summaries: list[str] = []
    images_used = 0
    last_error = None
    total_input_tokens  = 0
    total_output_tokens = 0

    total_batches = math.ceil(len(image_blocks) / _IMAGES_PER_BATCH)

    for batch_start in range(0, len(image_blocks), _IMAGES_PER_BATCH):
        batch = image_blocks[batch_start:batch_start + _IMAGES_PER_BATCH]
        batch_num = batch_start // _IMAGES_PER_BATCH + 1
        logger.info(f"CPS AI batch {batch_num}/{total_batches} for '{room_name}' ({len(batch)} images)")
        if batch_num > 1:
            time.sleep(2)

        try:
            parsed, usage = _call_claude_with_images(client, batch, room_name)
            total_input_tokens  += usage.get('input_tokens', 0)
            total_output_tokens += usage.get('output_tokens', 0)
            batch_items = _clean_items(parsed.get("items", []), start_order=len(all_items))
            all_items.extend(batch_items)
            confidences.append(parsed.get("confidence", "medium"))
            if parsed.get("room_summary"):
                summaries.append(parsed["room_summary"])
            images_used += len(batch)

        except json.JSONDecodeError as e:
            logger.error(f"CPS AI JSON parse error for '{room_name}' batch {batch_num}: {e}")
            last_error = "AI returned invalid JSON on one batch"
        except Exception as e:
            logger.error(f"CPS AI error for '{room_name}' batch {batch_num}: {e}", exc_info=True)
            last_error = str(e)

    # Flag structural items (walls, floors, fixtures, etc.)
    flag_structural_items(all_items)

    if not all_items and last_error:
        return {
            "success": False,
            "items": _make_fallback_items(room_name),
            "confidence": "none",
            "room_summary": "",
            "images_used": images_used,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "error": last_error,
        }

    confidence_rank = {"high": 2, "medium": 1, "low": 0, "none": -1}
    final_confidence = min(confidences, key=lambda c: confidence_rank.get(c, 1)) if confidences else "medium"

    return {
        "success": True,
        "items": all_items,
        "confidence": final_confidence,
        "room_summary": " | ".join(summaries),
        "images_used": images_used,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "error": last_error,
    }
