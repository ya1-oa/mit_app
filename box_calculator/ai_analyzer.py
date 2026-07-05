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

# ── PDF report → CPS session analysis ────────────────────────────────────────
# Output columns match BoxCalcCPSRoom exactly so results can be stored
# directly in the CPS session and rendered/edited/exported via the CPS report.

_PDF_SYSTEM_PROMPT = """\
You are a master moving company estimator with 30+ years of experience packing out homes \
for insurance mitigation claims. You read box count reports, contents lists, and scope of \
work documents, then produce a complete, room-by-room box count estimate.

Box type definitions you MUST use:
  small       — 1.5 cu ft  (books, tools, dense items ≤20 lbs)
  medium      — 3.0 cu ft  (DEFAULT — general household, clothes, toys, pantry)
  large       — 4.5 cu ft  (pillows, lampshades, lightweight bulky items, linens)
  box_wrapped — furniture wrap + small box (mirrors, artwork, lamps, fragile décor)
  plant_vase  — tall open-top box (floor plants, vases, tall décor)
  tv          — flat TV box (one per flat-screen TV)
  wardrobe    — 10 cu ft hanging box (1 per ~4 linear feet of hanging rod)
  mattress    — flat mattress/box-spring box (one per mattress or box spring)
  dish_pack   — 5.2 cu ft dish-pack box (china, crystal, glassware, fragile kitchenware)
  glass_pack  — cushioned glass box (drinking glasses, stemware, vases)
  boots_pans  — corrugated wrap bundle (cast iron, baking sheets, boots)

Use MEDIUM as the default for anything that does not clearly fit another type.
You respond ONLY with valid JSON — no markdown, no explanation."""

_PDF_USER_PROMPT = """\
{context}

STEP 1 — Per-room base estimate:
Read every room and its contents in the attached report. For each room estimate how many \
boxes of each type are needed. Prefer MEDIUM as your default.

STEP 2 — Overview review:
Review the document holistically for any rooms or items that may have been missed or \
underestimated. Add those to the appropriate rooms.

Return JSON in this EXACT format (use integer values, never null):
{{
  "rooms": [
    {{
      "name": "Room Name",
      "small": 0,
      "medium": 0,
      "large": 0,
      "box_wrapped": 0,
      "plant_vase": 0,
      "tv": 0,
      "wardrobe": 0,
      "mattress": 0,
      "dish_pack": 0,
      "glass_pack": 0,
      "boots_pans": 0,
      "ai_notes": "brief room-level notes, unusual items, rebuttal points"
    }}
  ],
  "estimator_notes": "overall notes — items the adjuster may challenge and how to defend them"
}}"""

_CPS_COLS = [
    "small", "medium", "large", "box_wrapped", "plant_vase",
    "tv", "wardrobe", "mattress", "dish_pack", "glass_pack", "boots_pans",
]


def analyze_pdf_report(pdf_bytes: bytes, client_context: str = '') -> dict:
    """
    Analyze an uploaded box count report PDF using Claude.

    Output columns match BoxCalcCPSRoom exactly so the caller can create
    CPS session records directly from the result.

    Returns:
        {
          "success": bool,
          "rooms": [{"name": str, "small": int, "medium": int, ...11 cols...,
                     "ai_notes": str}],
          "estimator_notes": str,
          "error": str | None,
        }
    """
    import anthropic

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {"success": False, "rooms": [], "estimator_notes": "",
                "error": "ANTHROPIC_API_KEY not configured"}

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')
    context_str = (f"Client/claim context: {client_context}\n\n") if client_context else ""

    content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
        },
        {"type": "text", "text": _PDF_USER_PROMPT.format(context=context_str)},
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
        rooms = []
        for r in parsed.get("rooms", []):
            rooms.append({
                "name": str(r.get("name", "Unknown Room")),
                **{col: max(0, int(r.get(col, 0) or 0)) for col in _CPS_COLS},
                "ai_notes": str(r.get("ai_notes", "")),
            })

        return {
            "success": True,
            "rooms": rooms,
            "estimator_notes": str(parsed.get("estimator_notes", "")),
            "error": None,
        }

    except json.JSONDecodeError as e:
        logger.error(f"PDF analysis JSON parse error: {e}")
        return {"success": False, "rooms": [], "estimator_notes": "",
                "error": "AI returned invalid JSON — try again"}
    except Exception as e:
        logger.error(f"PDF analysis error: {e}", exc_info=True)
        return {"success": False, "rooms": [], "estimator_notes": "", "error": str(e)}

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
