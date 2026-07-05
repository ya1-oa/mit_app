"""
AI-powered room content analysis using Claude vision + Encircle images,
and PDF box count report analysis.
"""
from __future__ import annotations

import base64
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

# ── PDF report analysis ───────────────────────────────────────────────────────

_PDF_SYSTEM_PROMPT = """You are a master moving company estimator with decades of experience \
packing out homes for insurance mitigation claims. You know exactly how many boxes every type \
of household item requires, and you can spot what less-experienced estimators miss.

Box specifications you MUST follow:
- SMALL  (1.5 cu ft)  — books, tools, small dense items (≤20 lbs/box)
- MEDIUM (3.0 cu ft, 20"L×16"W×15"D, ≤65 lbs) — DEFAULT for most household items
  (clothes, toys, pantry, small electronics, general household)
- LARGE  (4.5 cu ft)  — pillows, lampshades, lightweight bulky decor, linens
- DISH_PACK (5.2 cu ft) — china, crystal, glassware, fragile kitchenware
- WARDROBE (10 cu ft)  — hanging clothes: 1 wardrobe box per 2–3 linear feet of rod
- XL_WRAP  (furniture pad-wrap, NO box) — sofas, bed frames, dressers, large appliances,
  TVs>50", artwork>24"

You respond ONLY with valid JSON — no markdown, no explanation."""

_PDF_USER_PROMPT = """Analyze this box count report / contents document and estimate the \
complete box count needed for a full pack-out.

{context}

{step_instruction}

Return JSON in this EXACT format:
{{
  "rooms": [
    {{
      "name": "Room Name",
      "small": 0,
      "medium": 0,
      "large": 0,
      "dish_pack": 0,
      "wardrobe": 0,
      "xl_wrap": 0,
      "notes": "brief estimator notes for any unusual items or caveats"
    }}
  ],
  "summary": {{
    "total_small": 0,
    "total_medium": 0,
    "total_large": 0,
    "total_dish_pack": 0,
    "total_wardrobe": 0,
    "total_xl_wrap": 0,
    "estimator_notes": "overall notes, items that may require rebuttal from insurer, \
anything the adjuster might challenge"
  }}
}}"""

_STEP1_INSTRUCTION = """STEP 1 — Base estimate:
Based on the contents listed in this report, estimate how many boxes of each type are needed \
per room. Use MEDIUM boxes as your default. Only use SMALL for genuinely heavy/dense items."""

_STEP2_INSTRUCTION = """STEP 2 — Review for missed items:
Also look at the overall context (overview photos / room totals) and add any additional \
boxes for items that may have been missed or underestimated in the per-room breakdown."""


def analyze_pdf_report(pdf_bytes: bytes, client_context: str = '') -> dict:
    """
    Analyze an uploaded box count report PDF using Claude.

    Returns:
        {
          "success": bool,
          "rooms": [...],
          "summary": {...},
          "error": str | None,
        }
    """
    import anthropic

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {"success": False, "rooms": [], "summary": {}, "error": "ANTHROPIC_API_KEY not configured"}

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')

    context_str = f"\nClient/claim context: {client_context}" if client_context else ""

    content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        },
        {
            "type": "text",
            "text": _PDF_USER_PROMPT.format(
                context=context_str,
                step_instruction=_STEP1_INSTRUCTION + "\n\n" + _STEP2_INSTRUCTION,
            ),
        },
    ]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_PDF_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        rooms = parsed.get("rooms", [])
        summary = parsed.get("summary", {})

        # Compute totals if Claude didn't supply them
        if rooms and not summary.get("total_medium"):
            for key in ["small", "medium", "large", "dish_pack", "wardrobe", "xl_wrap"]:
                summary[f"total_{key}"] = sum(r.get(key, 0) for r in rooms)

        return {"success": True, "rooms": rooms, "summary": summary, "error": None}

    except json.JSONDecodeError as e:
        logger.error(f"PDF analysis JSON parse error: {e}")
        return {"success": False, "rooms": [], "summary": {}, "error": "AI returned invalid JSON — try again"}
    except Exception as e:
        logger.error(f"PDF analysis error: {e}", exc_info=True)
        return {"success": False, "rooms": [], "summary": {}, "error": str(e)}

VALID_CATEGORIES = [
    "books", "kitchen", "fragile_kitchen", "general", "linens",
    "hanging_clothes", "folded_clothes", "toys", "decor", "electronics",
    "dresser", "nightstand", "filing_cabinet", "desk", "bed_frame",
    "headboard", "mattress", "sofa", "chair", "dining_table",
    "entertainment_center", "bookshelf", "china_cabinet",
    "appliance_large", "artwork_large",
]

_SYSTEM_PROMPT = """You are an expert home contents estimator for insurance mitigation pack-outs.
You analyze room photos and identify items that need to be packed out.
Respond ONLY with valid JSON — no markdown, no explanation."""

_USER_PROMPT = """These photos are of a {room_name} in a home that needs pack-out for mitigation.

Identify all visible items and categorize them using ONLY these categories:
{categories}

Rules:
- "hanging_clothes": use quantity = estimated linear feet of hanging rod
- "general": for miscellaneous items that don't fit other categories
- For furniture with drawers/shelves (dresser, nightstand, desk, bookshelf, etc.), estimate compartments
- Only include items you can see or reasonably infer from the room type

Return JSON in this exact format:
{{
  "items": [
    {{"category": "dresser", "quantity": 1, "compartments": 4, "note": "4-drawer dresser"}},
    {{"category": "general", "quantity": 2, "compartments": 0, "note": "misc bedside items"}}
  ],
  "confidence": "high|medium|low",
  "notes": "brief summary of what was identified"
}}"""


def _fetch_encircle_room_images(encircle_claim_id: str, room_name: str, max_images: int = 4) -> list[str]:
    """
    Fetch image URLs for a specific room from the Encircle API.
    Returns a list of download URLs (up to max_images).
    """
    from docsAppR.encircle_client import EncircleAPIClient
    try:
        api = EncircleAPIClient()
        # Get claim structures
        structures = api.get_claim_structures(encircle_claim_id)
        if not structures or not structures.get('list'):
            return []
        structure_id = structures['list'][0]['id']

        # Get rooms for this structure
        rooms_data = api.get_claim_rooms(encircle_claim_id, structure_id)
        rooms = rooms_data.get('list', []) if rooms_data else []

        # Find the matching room (fuzzy match on name)
        room_name_lower = room_name.lower().strip()
        target_room_id = None
        for room in rooms:
            r_name = (room.get('label') or room.get('name') or '').lower().strip()
            if r_name == room_name_lower or room_name_lower in r_name or r_name in room_name_lower:
                target_room_id = room.get('id')
                break

        if not target_room_id:
            return []

        # Get media for that room
        media = api.get_room_media(encircle_claim_id, structure_id, target_room_id)
        if not media:
            return []

        urls = []
        for item in media.get('list', [])[:max_images]:
            url = item.get('url') or item.get('download_url') or item.get('image_url')
            if url:
                urls.append(url)
        return urls

    except Exception as e:
        logger.warning(f"Could not fetch Encircle images for room '{room_name}': {e}")
        return []


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


def analyze_room_with_ai(
    room_name: str,
    encircle_claim_id: str | None = None,
    image_urls: list[str] | None = None,
) -> dict:
    """
    Analyze a room using Claude vision and return suggested items.

    Returns:
        {
          "success": bool,
          "items": [...],         # list of item dicts
          "confidence": str,
          "notes": str,
          "images_used": int,
          "error": str | None,
        }
    """
    import anthropic

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {
            "success": False, "items": [], "confidence": "none",
            "notes": "", "images_used": 0,
            "error": "ANTHROPIC_API_KEY not configured",
        }

    # Gather images
    urls = list(image_urls or [])
    if not urls and encircle_claim_id:
        urls = _fetch_encircle_room_images(encircle_claim_id, room_name)

    if not urls:
        return {
            "success": False, "items": [], "confidence": "none",
            "notes": "", "images_used": 0,
            "error": "No images available for this room",
        }

    # Build message content with images
    content = []
    images_used = 0
    for url in urls[:4]:
        result = _image_url_to_base64(url)
        if result:
            b64, media_type = result
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })
            images_used += 1

    if not content:
        return {
            "success": False, "items": [], "confidence": "none",
            "notes": "", "images_used": 0,
            "error": "Could not download any images",
        }

    content.append({
        "type": "text",
        "text": _USER_PROMPT.format(
            room_name=room_name,
            categories=", ".join(VALID_CATEGORIES),
        ),
    })

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()

        # Strip any markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        items = parsed.get("items", [])

        # Validate and sanitise items
        clean_items = []
        for item in items:
            cat = item.get("category", "")
            if cat not in VALID_CATEGORIES:
                continue
            clean_items.append({
                "category": cat,
                "quantity": max(1, int(item.get("quantity", 1))),
                "compartments": max(0, int(item.get("compartments", 0))),
                "note": str(item.get("note", ""))[:120],
                "ai_suggested": True,
            })

        return {
            "success": True,
            "items": clean_items,
            "confidence": parsed.get("confidence", "medium"),
            "notes": parsed.get("notes", ""),
            "images_used": images_used,
            "error": None,
        }

    except json.JSONDecodeError as e:
        logger.error(f"AI analysis JSON parse error: {e}")
        return {
            "success": False, "items": [], "confidence": "none",
            "notes": "", "images_used": images_used,
            "error": "AI returned invalid JSON — try again",
        }
    except Exception as e:
        logger.error(f"AI analysis error: {e}", exc_info=True)
        return {
            "success": False, "items": [], "confidence": "none",
            "notes": "", "images_used": images_used,
            "error": str(e),
        }
