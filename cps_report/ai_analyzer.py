"""
AI-powered room content analysis for PPR Schedule of Loss reports.
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

_SYSTEM_PROMPT_PREMIUM = """DIRECTIVE: You are a professional mitigation claim inspector specializing in upper-mid-tier property claims. You review images and determine replacement values for items in a client's home for insurance purposes.

Pricing standard: upper-mid retail — quality brands at their mid-to-upper price range. Target 20–40% above standard retail. Do NOT price at absolute luxury/top-tier unless the item is explicitly identifiable as a luxury brand (visible logo, label, or hallmark confirming it). Do not reference or use budget or discount retailers.
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
- notes: any relevant insurance notes (brand visible, serial noted, heavy wear, etc.)
- source_image_indices: list of 1-based positions of the images you were shown that contain or best support this item (e.g. [1, 3] means the 1st and 3rd images you received). List every image where the item is clearly visible. This is required for insurance documentation.

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
      "notes": "Samsung logo visible",
      "source_image_indices": [1, 3]
    }}
  ],
  "confidence": "high|medium|low",
  "room_summary": "brief description of room and notable contents"
}}"""

_USER_PROMPT_PREMIUM = """ACTION: Review the following photos of room "{room_name}" and give me the UPPER-MID-TIER replacement value of each item shown.

PRICING STANDARD:
- Target: 20–40% above standard mid-market retail. This is NOT absolute luxury pricing.
- Only price at high-end / luxury tier if the item has a clearly visible brand logo, label, or hallmark confirming it (e.g. visible Apple logo, visible Breville logo, visible KitchenAid label).
- Do NOT default to top-of-line for every item. Unknown-brand or store-brand items should be priced at quality-equivalent replacements in the mid-premium range.
- DO NOT reference or cite budget or discount retailers: Walmart, Target, Amazon Basics, Dollar General, Costco house brands, or any discount/off-brand source.
- Use upper-mid-tier sources: Crate & Barrel, West Elm, Pottery Barn (mid-range lines), Best Buy (standard tier), Williams-Sonoma (mid-range), Macy's, Nordstrom Rack, Bed Bath & Beyond premium lines, or equivalent.
- For clearly identified luxury brands (visible hallmark), reference the appropriate premium retailer.

CATEGORY PRICE ANCHORS — use these as your target range, not the ceiling:
- Furniture (sofa, bed, table, chair): $500–$1,200 per piece for unbranded; up to $2,000 for confirmed premium brand
- Electronics (TV 55"): $500–$900; laptop: $900–$1,400; tablet: $400–$700
- Appliances (washer/dryer): $700–$1,200; refrigerator: $900–$1,800
- Kitchen/Cookware (pots, pans, small appliances): $60–$250 per item
- Bedding/Linens (sheet set, comforter): $80–$250
- Decor/Art (lamps, mirrors, artwork): $80–$400

OTHER RULES:
- Do NOT price any structural or permanently fixed building components (windows, stairs, flooring, walls, ceilings, built-in cabinets, etc.). Exclude entirely.
- This is for a mitigation claim — price ALL items photographed separately. Each item on its own line.
- Avoid duplicates: if the same item appears in multiple photos, list it once.
- Estimate age based on visible wear, style, and technology generation.

For each item provide:
- description: clear insurance-standard item description (e.g. "Queen Size Upholstered Platform Bed - Fabric - Upper-Mid Tier")
- brand: brand/manufacturer if VISIBLY confirmed on item, otherwise ""
- condition: "Good", "Fair", or "Poor"
- qty: quantity (integer)
- model_number: if visible on item, otherwise ""
- serial_number: if visible on item, otherwise ""
- retailer: upper-mid-tier retailer appropriate for the item (e.g. "Crate & Barrel", "Best Buy", "Pottery Barn", "Williams-Sonoma")
- replacement_source: "Online" or "Retail"
- purchase_price_each: estimated original purchase price in USD (number only)
- age_years: estimated age in years (0–5 maximum per policy, vary between items)
- age_months: additional months beyond age_years (0–11)
- replacement_value_each: today's upper-mid-tier retail replacement cost in USD (number only)
- depreciation_category: one of — Clothing, Electronics, Furniture, Appliances, Bedding/Linens, Books/Media, Decor/Art, Toys/Games, Tools/Hardware, Kitchen/Cookware, Jewelry/Accessories, Sporting Goods, Musical Instruments, Other
- notes: any relevant insurance notes (brand visible, serial noted, heavy wear, premium grade confirmed, cap applied, etc.)
- source_image_indices: list of 1-based positions of the images you were shown that contain or best support this item (e.g. [1, 3] means the 1st and 3rd images you received). List every image where the item is clearly visible. This is required for insurance documentation.

Return JSON in this exact format:
{{
  "items": [
    {{
      "description": "65-inch LED 4K Smart TV - Upper-Mid Tier",
      "brand": "",
      "condition": "Good",
      "qty": 1,
      "model_number": "",
      "serial_number": "",
      "retailer": "Best Buy",
      "replacement_source": "Retail",
      "purchase_price_each": 650,
      "age_years": 2,
      "age_months": 0,
      "replacement_value_each": 849,
      "depreciation_category": "Electronics",
      "notes": "No brand visible — priced at upper-mid Best Buy tier",
      "source_image_indices": [2]
    }}
  ],
  "confidence": "high|medium|low",
  "room_summary": "brief description of room and notable contents"
}}"""


_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'}

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


# ─────────────────────────────────────────────────────────────────────────────
# Premium pricing calibration
#
# Problem: unconstrained "premium" prompting produces 2.5–3× category-median
# prices, yielding ~900k total variance on real claims. Target is ~300k.
#
# Mathematical approach — two-phase logarithmic soft cap:
#
#   Phase 1  (ratio ≤ SOFT_THRESHOLD):  price accepted as-is.
#   Phase 2  (ratio >  SOFT_THRESHOLD):
#       compressed = SOFT_THRESHOLD
#                    + LOG_SCALE_FACTOR × log10((ratio − SOFT_THRESHOLD)×3 + 1)
#       capped_price = baseline × min(compressed, HARD_CEILING)
#
# Ratio → effective multiplier after cap:
#   1.30×  →  1.30×  (under threshold, no change)
#   2.00×  →  1.45×  (compressed)
#   3.00×  →  1.54×  (compressed)
#   4.00×  →  1.59×  (compressed)
#   10.0×  →  1.73×  (compressed)
#   ∞       →  1.80×  (hard ceiling)
#
# Net effect on a claim where AI averages 2.5× category baseline (900k variance):
#   After cap, effective average ≈ 1.50×  →  variance ≈ 300k  ✓
# ─────────────────────────────────────────────────────────────────────────────

# Per-category approximate US mid-market retail medians (USD, per unit).
# Used as the reference baseline for per-item ratio calculation.
CATEGORY_BASELINES: dict[str, float] = {
    'Furniture':          650.0,
    'Electronics':        450.0,
    'Appliances':         750.0,
    'Kitchen/Cookware':    80.0,
    'Bedding/Linens':     120.0,
    'Clothing':            75.0,
    'Books/Media':         25.0,
    'Decor/Art':          200.0,
    'Toys/Games':          60.0,
    'Tools/Hardware':     150.0,
    'Jewelry/Accessories': 300.0,
    'Sporting Goods':     200.0,
    'Musical Instruments': 400.0,
    'Other':              200.0,
}

# Calibration constants — tune these to shift the variance target.
# SOFT_THRESHOLD: ratio above which logarithmic compression begins.
#   Lower value = more aggressive cap = lower variance.
PREMIUM_SOFT_THRESHOLD   = 1.30   # items up to 1.30× baseline pass through unchanged
PREMIUM_LOG_SCALE_FACTOR = 0.30   # log10 dampening weight above threshold
PREMIUM_HARD_CEILING     = 1.80   # absolute maximum multiplier vs category baseline

# Expected premium lift factor displayed on the audit page.
# 1.33 = targeting ~33% above normal (≈300k on a 900k baseline claim).
PREMIUM_EXPECTED_LIFT    = 1.33


def _apply_premium_calibration(items: list[dict]) -> list[dict]:
    """
    Post-process premium-mode items through a logarithmic soft cap so that
    per-item prices stay within the calibrated range defined by
    PREMIUM_SOFT_THRESHOLD / PREMIUM_LOG_SCALE_FACTOR / PREMIUM_HARD_CEILING.

    Only items priced above their category median baseline are affected.
    The original AI price is preserved in the notes field for audit traceability.
    Items without a replacement_value_each are skipped silently.
    """
    for item in items:
        rv = float(item.get('replacement_value_each') or 0)
        if rv <= 0:
            continue

        cat      = item.get('depreciation_category', 'Other')
        baseline = CATEGORY_BASELINES.get(cat, 200.0)
        ratio    = rv / baseline

        if ratio <= PREMIUM_SOFT_THRESHOLD:
            continue  # within calibrated range — no change

        # Two-phase log compression
        compressed = (
            PREMIUM_SOFT_THRESHOLD
            + PREMIUM_LOG_SCALE_FACTOR
            * math.log10((ratio - PREMIUM_SOFT_THRESHOLD) * 3 + 1)
        )
        effective_multiplier = min(compressed, PREMIUM_HARD_CEILING)
        capped_rv = round(baseline * effective_multiplier, 2)

        if capped_rv < rv:
            notes = (item.get('notes') or '').strip()
            item['notes'] = (
                f"{notes} | ai-raw=${rv:,.0f} cap-applied=${capped_rv:,.0f}"
            ).lstrip(' |')
            item['replacement_value_each'] = capped_rv

            # Scale purchase_price proportionally so it doesn't exceed replacement value
            pp = float(item.get('purchase_price_each') or 0)
            if pp > 0 and pp > capped_rv:
                item['purchase_price_each'] = round(pp * (capped_rv / rv), 2)

    return items


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


def _detect_image_media_type(data: bytes) -> str:
    """Detect true image media type from magic bytes — never trust the HTTP header."""
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'


def _image_url_to_base64(url: str) -> tuple[str, str] | None:
    """Download an image URL and return (base64_data, media_type).
    Uses magic-byte detection — Encircle CDN sometimes serves GIF/WebP bytes
    with content-type: image/jpeg, which Claude rejects with a 400 error.
    """
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.content
        ct = _detect_image_media_type(data)
        b64 = base64.standard_b64encode(data).decode('utf-8')
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
            "notes": "Manual entry required — no images available",
        }
    ]


_CPS_MODEL = "claude-haiku-4-5-20251001"


def _call_claude_with_images(
    client,
    image_content_blocks: list,
    room_name: str,
    pricing_mode: str = 'normal',
) -> tuple[dict, dict]:
    """
    Send one batch of image blocks to Claude and return (parsed_result, usage).
    usage = {'input_tokens': int, 'output_tokens': int}
    pricing_mode: 'normal' or 'premium'
    """
    if pricing_mode == 'premium':
        system_prompt = _SYSTEM_PROMPT_PREMIUM
        user_prompt = _USER_PROMPT_PREMIUM
    else:
        system_prompt = _SYSTEM_PROMPT
        user_prompt = _USER_PROMPT

    content = list(image_content_blocks) + [{
        "type": "text",
        "text": user_prompt.format(room_name=room_name),
    }]
    response = client.messages.create(
        model=_CPS_MODEL,
        max_tokens=8192,
        system=system_prompt,
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
        raw_indices = item.get("source_image_indices") or []
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
            "notes": str(item.get("notes", ""))[:500],
            "ai_suggested": True,
            "order": start_order + i,
            # Raw 1-based indices into this batch; converted to URLs in analyze_room_for_ppr
            "_source_image_indices": [int(x) for x in raw_indices if str(x).isdigit()],
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


def analyze_room_for_ppr(
    room_name: str,
    room_number: str,
    prefetched_media: list[dict],
    image_urls: list[str] | None = None,
    pricing_mode: str = 'normal',
    log_fn=None,
) -> dict:
    """
    Analyze a room using Claude vision and return structured PPR schedule of loss items.
    Pass prefetched_media (from fetch_all_claim_media) and the room_number (e.g. "406")
    to filter images for this room.

    pricing_mode: 'normal' (default) or 'premium' (high-end retailers, no budget pricing)

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

    def _log(msg):
        if log_fn:
            log_fn(msg)

    urls = list(image_urls or [])
    if not urls:
        urls = filter_room_images(prefetched_media, room_number)

    # Deduplicate while preserving order — Encircle sometimes returns the same
    # image with slightly different metadata, causing duplicate downloads.
    urls = list(dict.fromkeys(urls))

    if not urls:
        _log(f"No images found for room {room_number} — using placeholder")
        return {
            "success": False,
            "items": _make_fallback_items(room_name),
            "confidence": "none",
            "room_summary": "No images available",
            "images_used": 0,
            "error": "No images available for this room",
        }

    _log(f"Found {len(urls)} images for room {room_number} — downloading…")
    image_blocks = []
    downloaded_urls = []  # parallel to image_blocks — only successfully downloaded URLs
    for url in urls:
        result = _image_url_to_base64(url)
        if result:
            b64, media_type = result
            image_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })
            downloaded_urls.append(url)

    if not image_blocks:
        _log(f"Could not download any images for room {room_number}")
        return {
            "success": False,
            "items": _make_fallback_items(room_name),
            "confidence": "none",
            "room_summary": "Could not download images",
            "images_used": 0,
            "error": "Could not download any images",
        }

    _log(f"Downloaded {len(image_blocks)}/{len(urls)} images for room {room_number}")

    mode_label = "PREMIUM" if pricing_mode == 'premium' else "normal"
    logger.info(
        f"PPR AI analyzing {len(image_blocks)} images for '{room_name}' "
        f"[{mode_label}] in {math.ceil(len(image_blocks) / _IMAGES_PER_BATCH)} batch(es)"
    )

    client = anthropic.Anthropic(api_key=api_key, timeout=180.0)
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
        logger.info(f"PPR AI batch {batch_num}/{total_batches} for '{room_name}' ({len(batch)} images)")
        if batch_num > 1:
            time.sleep(2)

        try:
            print(f"[PPR-AI] CALLING CLAUDE — room='{room_name}' batch={batch_num}/{total_batches} images={len(batch)} mode={pricing_mode}", flush=True)
            _log(f"Sending batch {batch_num}/{total_batches} to Claude AI ({len(batch)} images)…")
            parsed, usage = _call_claude_with_images(client, batch, room_name, pricing_mode=pricing_mode)
            total_input_tokens  += usage.get('input_tokens', 0)
            total_output_tokens += usage.get('output_tokens', 0)
            batch_items = _clean_items(parsed.get("items", []), start_order=len(all_items))
            # Map each item's batch-local 1-based indices → actual download URLs.
            # downloaded_urls is parallel to image_blocks; batch slice tells us
            # which URLs correspond to this batch's image positions.
            batch_urls = downloaded_urls[batch_start:batch_start + _IMAGES_PER_BATCH]
            for it in batch_items:
                raw_idx = it.pop("_source_image_indices", [])
                it["source_image_urls"] = [
                    batch_urls[i - 1]
                    for i in raw_idx
                    if isinstance(i, int) and 1 <= i <= len(batch_urls)
                ]
            all_items.extend(batch_items)
            confidences.append(parsed.get("confidence", "medium"))
            if parsed.get("room_summary"):
                summaries.append(parsed["room_summary"])
            images_used += len(batch)
            print(f"[PPR-AI] DONE — room='{room_name}' batch={batch_num}/{total_batches} items_so_far={len(all_items)} tokens_in={total_input_tokens}", flush=True)
            _log(f"Batch {batch_num}/{total_batches} done — {len(batch_items)} items found (running total: {len(all_items)})")

        except json.JSONDecodeError as e:
            logger.error(f"PPR AI JSON parse error for '{room_name}' batch {batch_num}: {e}")
            last_error = "AI returned invalid JSON on one batch"
        except Exception as e:
            logger.error(f"PPR AI error for '{room_name}' batch {batch_num}: {e}", exc_info=True)
            last_error = str(e)

    # Flag structural items (walls, floors, fixtures, etc.)
    flag_structural_items(all_items)

    # Apply logarithmic soft cap in premium mode to anchor variance near target
    if pricing_mode == 'premium' and all_items:
        all_items = _apply_premium_calibration(all_items)

    if not all_items and last_error:
        return {
            "success": False,
            "items": _make_fallback_items(room_name),
            "confidence": "none",
            "room_summary": "",
            "images_used": images_used,
            "analyzed_urls": urls,
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
        "analyzed_urls": urls,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "error": last_error,
    }


# Backward-compat alias
analyze_room_for_cps = analyze_room_for_ppr
