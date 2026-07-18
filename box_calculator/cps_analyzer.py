"""
CPS (Contents Processing Sheet) AI box count estimator.

Uses Claude Vision to analyze room photos and return direct box count estimates
using the 11 CPS column types used by pack-out crews, based on standard
Home Depot box dimensions.

Box sizes (Home Depot standard):
    Small     1.5 cu ft  16×12×12   — books, tools, dense items
    Medium    3.0 cu ft  18×18×16   — general household, clothes, toys
    Large     4.5 cu ft  18×18×24   — linens, lampshades, pillows
    Wardrobe  ~10 cu ft  24×24×48   — hanging clothes, 1 per ~5 linear ft
    Mattress  flat box              — 1 per mattress/box spring
    TV        flat box              — 1 per flat-screen TV
    Dish Pack 5.2 cu ft  18×18×28   — china, fragile kitchenware
    Glass Pack smaller cushioned    — drinking glasses, vases, stemware
    Box/Wrapped furniture wrap + small box — mirrors, artwork, lamps
    Plant/Vase tall open-top        — plants, floor vases, tall décor
    Boots & Pans corrugated wrap    — cast iron, baking sheets, boot sets
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os

import requests

logger = logging.getLogger(__name__)

CPS_COLUMNS = [
    "small",
    "medium",
    "large",
    "box_wrapped",    # XL Tagged/Wrapped
    "picture_mirror", # PICTURE/MIRROR
    "plant_vase",     # LAMP/PLANT/VASE
    "tv",             # TV BOX
    "wardrobe",       # Wardrobe BOX
    "mattress",       # MATTRESS BOX
    "dish_pack",      # DISH PACK BOX
    "glass_pack",     # GLASS PACK BOX
    "boots_pans",     # POTS & PANS BOX
]

CPS_COLUMN_LABELS = {
    "small":          "Small Box",
    "medium":         "Medium Box",
    "large":          "Large Box",
    "box_wrapped":    "XL Tagged/Wrapped",
    "picture_mirror": "Picture/Mirror",
    "plant_vase":     "Lamp/Plant/Vase",
    "tv":             "TV Box",
    "wardrobe":       "Wardrobe Box",
    "mattress":       "Mattress Box",
    "dish_pack":      "Dish Pack Box",
    "glass_pack":     "Glass Pack Box",
    "boots_pans":     "Pots & Pans Box",
}

_SYSTEM_PROMPT = """\
You are a master moving company estimator with 30+ years of experience packing out \
residential homes for insurance mitigation claims. You specialize in producing \
insurance-grade CPS (Contents Processing Sheet) box count estimates that can \
withstand adjuster scrutiny.

Box type definitions — use MEDIUM as the default for anything that does not clearly \
fit another type:
  small          — 1.5 cu ft, 16×12×12  (books, tools, dense items, files, canned goods)
  medium         — 3.0 cu ft, 18×18×16  (DEFAULT — general household, folded clothes, toys, office, pantry)
  large          — 4.5 cu ft, 18×18×24  (pillows, lampshades, light bulky items, linens, bedding)
  box_wrapped    — XL tagged/wrapped item (sofas, chairs, tables, large furniture, appliances unless disassembled)
  picture_mirror — picture/mirror carton (framed artwork, mirrors, wall art, photos, glass pictures)
  plant_vase     — tall open-top box (floor lamps, table lamps, floor plants, floor vases, tall decorative items)
  tv             — flat TV box (one per flat-screen TV regardless of size)
  wardrobe       — 10 cu ft hanging box (1 per ~4 linear feet of visible hanging rod)
  mattress       — flat mattress/box-spring box (one per mattress or box spring)
  dish_pack      — 5.2 cu ft, 18×18×28 (china, crystal, ceramic kitchenware, fragile items)
  glass_pack     — cushioned glass box (drinking glasses, stemware, glass sets, crystal)
  boots_pans     — POTS & PANS BOX (cast iron, baking sheets, boots/shoes grouped, heavy cookware)

You respond ONLY with valid JSON — no markdown, no explanation outside the JSON."""

_OVERVIEW_PROMPT = """\
These are OVERVIEW / WIDE-ANGLE photos of the space labeled {room_name}.

You are cross-checking a detailed per-room CPS (Contents Processing Sheet) estimate. \
Your job is to CATCH ITEMS THAT ARE EASILY MISSED when field agents photograph individual \
corners or closets: large furniture visible from across the room, items stacked near \
doorways, décor on high shelves, pieces partially hidden behind other items, and anything \
a photographer focusing on one area at a time might skip.

Focus on:
- Large furniture pieces visible in the wide shot that are often under-counted
- High-shelf items only visible from a distance
- Transition-space items (hallways, doorway areas, landing piles)
- Background items partially occluded in individual close-up shots

Count what you can confidently see. Return 0 for any category where nothing is clearly visible.

Return ONLY this JSON (all fields required, integers only, 0 for none):
{{
  "small": <int>,
  "medium": <int>,
  "large": <int>,
  "box_wrapped": <int>,
  "picture_mirror": <int>,
  "plant_vase": <int>,
  "tv": <int>,
  "wardrobe": <int>,
  "mattress": <int>,
  "dish_pack": <int>,
  "glass_pack": <int>,
  "boots_pans": <int>,
  "confidence": "high" | "medium" | "low",
  "notes": "<focus on items likely missed in individual close-up shots>"
}}"""

_USER_PROMPT = """\
These photos show a {room_name} that needs to be fully packed out for an insurance claim.

STEP 1 — Systematic room scan:
Visually divide the room into zones (left wall, center, right wall, closets, \
upper shelving, floor). Count every visible item and assign it to the correct box type.

STEP 2 — Reality check:
Review your count. Would a crew of two be able to pack this room with what you estimated? \
If a closet is visible, ensure wardrobe boxes are counted. If a TV is on screen, count it. \
If a kitchen or dining area, check for dish_pack and glass_pack.

BOX ASSIGNMENT RULES:
- Use MEDIUM as the default for anything that does not fit another type
- Only count items you can see or confidently infer from the room type
- Visible closet rod = wardrobe boxes (1 per ~4 linear feet)
- Each flat-screen TV = 1 tv box
- Each mattress or box spring = 1 mattress box
- Round up to nearest whole box
- Empty or bare spaces = 0, do not speculate

Return ONLY this JSON (all fields required, integers only, 0 for none):
{{
  "small": <int>,
  "medium": <int>,
  "large": <int>,
  "box_wrapped": <int>,
  "picture_mirror": <int>,
  "plant_vase": <int>,
  "tv": <int>,
  "wardrobe": <int>,
  "mattress": <int>,
  "dish_pack": <int>,
  "glass_pack": <int>,
  "boots_pans": <int>,
  "confidence": "high" | "medium" | "low",
  "notes": "<brief summary of major items identified and any items an adjuster may question>"
}}"""


def _image_to_base64(path_or_url: str) -> tuple[str, str] | None:
    """Read an image from a filesystem path or URL; return (base64, media_type)."""
    try:
        if path_or_url.startswith(("http://", "https://")):
            resp = requests.get(path_or_url, timeout=20)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            data = resp.content
        else:
            with open(path_or_url, "rb") as f:
                data = f.read()
            ext = path_or_url.rsplit(".", 1)[-1].lower()
            ct = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "bmp": "image/bmp",
                "webp": "image/webp", "gif": "image/gif",
            }.get(ext, "image/jpeg")
        if not ct.startswith("image/"):
            ct = "image/jpeg"
        return base64.standard_b64encode(data).decode("utf-8"), ct
    except Exception as e:
        logger.warning("Could not load image %s: %s", path_or_url, e)
        return None


_IMAGES_PER_BATCH = 20
_CONF_RANK = {"high": 2, "medium": 1, "low": 0, "none": -1}


def _call_claude_batch(client, model, image_blocks, room_name, is_overview):
    """Send one batch of image blocks to Claude; return (counts_dict, confidence, notes)."""
    prompt_template = _OVERVIEW_PROMPT if is_overview else _USER_PROMPT
    content = list(image_blocks) + [{
        "type": "text",
        "text": prompt_template.format(room_name=room_name),
    }]
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw.strip())
    counts = {col: max(0, int(parsed.get(col, 0) or 0)) for col in CPS_COLUMNS}
    return counts, str(parsed.get("confidence", "medium")), str(parsed.get("notes", ""))[:300]


def analyze_room_ppr(
    room_name: str,
    image_paths: list[str],
    model: str = "claude-haiku-4-5-20251001",
    is_overview: bool = False,
) -> dict:
    """
    Analyze ALL room images in batches of 20 and return merged PPR box count estimates.

    Batches are merged by taking the MAX per box type so boxes visible from
    different angles across batches are not double-counted.

    Returns:
        {
            "success": bool,
            "counts": {small, medium, large, box_wrapped, plant_vase, tv,
                       wardrobe, mattress, dish_pack, glass_pack, boots_pans},
            "total": int,
            "confidence": str,
            "notes": str,
            "images_used": int,
            "error": str | None,
        }
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _error_result("ANTHROPIC_API_KEY not configured", 0)
    if not image_paths:
        return _error_result("No images provided", 0)

    # Build image content blocks from ALL paths — no artificial cap
    all_blocks = []
    for path in image_paths:
        result = _image_to_base64(path)
        if result:
            b64, media_type = result
            all_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })

    if not all_blocks:
        return _error_result("Could not load any images", 0)

    client = anthropic.Anthropic(api_key=api_key)
    total_batches = math.ceil(len(all_blocks) / _IMAGES_PER_BATCH)

    logger.info("CPS AI start — room=%r model=%s images=%d batches=%d overview=%s",
                room_name, model, len(all_blocks), total_batches, is_overview)

    batch_counts = []
    batch_confidences = []
    batch_notes = []
    images_used = 0
    last_error = None

    for batch_num in range(total_batches):
        batch_start = batch_num * _IMAGES_PER_BATCH
        batch = all_blocks[batch_start:batch_start + _IMAGES_PER_BATCH]
        logger.info("CPS AI batch %d/%d — room=%r images=%d",
                    batch_num + 1, total_batches, room_name, len(batch))
        try:
            counts, confidence, notes = _call_claude_batch(
                client, model, batch, room_name, is_overview
            )
            batch_counts.append(counts)
            batch_confidences.append(confidence)
            if notes:
                batch_notes.append(notes)
            images_used += len(batch)
            logger.info("CPS batch %d/%d done — room=%r total=%d confidence=%s",
                        batch_num + 1, total_batches, room_name, sum(counts.values()), confidence)
        except json.JSONDecodeError as e:
            logger.error("CPS JSON error batch %d/%d — room=%r: %s",
                         batch_num + 1, total_batches, room_name, e)
            last_error = "AI returned invalid JSON on one batch"
        except Exception as e:
            logger.error("CPS API error batch %d/%d — room=%r: %s",
                         batch_num + 1, total_batches, room_name, e, exc_info=True)
            last_error = str(e)

    if not batch_counts:
        return _error_result(last_error or "All batches failed", images_used)

    # Merge: MAX per box type — same box visible from different angles
    # across batches should not be summed.
    merged = {col: max(c.get(col, 0) for c in batch_counts) for col in CPS_COLUMNS}
    total = sum(merged.values())

    # Worst confidence wins across batches
    confidence = min(batch_confidences, key=lambda c: _CONF_RANK.get(c, 0))
    notes_str = (" | ".join(batch_notes) if batch_notes else "")[:500]

    logger.info("CPS merged — room=%r total=%d batches=%d images_used=%d",
                room_name, total, total_batches, images_used)

    return {
        "success": True,
        "counts": merged,
        "total": total,
        "confidence": confidence,
        "notes": notes_str,
        "images_used": images_used,
        "error": None,
    }


def _error_result(error: str, images_used: int) -> dict:
    return {
        "success": False,
        "counts": {col: 0 for col in CPS_COLUMNS},
        "total": 0,
        "confidence": "none",
        "notes": "",
        "images_used": images_used,
        "error": error,
    }
