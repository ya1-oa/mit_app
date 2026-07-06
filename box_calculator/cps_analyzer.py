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
import os

import requests

logger = logging.getLogger(__name__)

CPS_COLUMNS = [
    "small",
    "medium",
    "large",
    "box_wrapped",
    "plant_vase",
    "tv",
    "wardrobe",
    "mattress",
    "dish_pack",
    "glass_pack",
    "boots_pans",
]

CPS_COLUMN_LABELS = {
    "small":       "Small",
    "medium":      "Medium",
    "large":       "Large",
    "box_wrapped":  "Box/Wrapped",
    "plant_vase":  "Plant/Vase",
    "tv":          "TV",
    "wardrobe":    "Wardrobe",
    "mattress":    "Mattress",
    "dish_pack":   "Dish Pack",
    "glass_pack":  "Glass Pack",
    "boots_pans":  "Boots & Pans",
}

_SYSTEM_PROMPT = """\
You are a master moving company estimator with 30+ years of experience packing out \
residential homes for insurance mitigation claims. You specialize in producing \
insurance-grade CPS (Contents Processing Sheet) box count estimates that can \
withstand adjuster scrutiny.

Box type definitions — use MEDIUM as the default for anything that does not clearly \
fit another type:
  small       — 1.5 cu ft, 16×12×12  (books, tools, dense items, files, canned goods)
  medium      — 3.0 cu ft, 18×18×16  (DEFAULT — general household, folded clothes, toys, office, pantry)
  large       — 4.5 cu ft, 18×18×24  (pillows, lampshades, light bulky items, linens, bedding)
  box_wrapped — furniture wrap + small box (mirrors, framed artwork, lamps, fragile décor)
  plant_vase  — tall open-top box (floor plants, floor vases, tall decorative items)
  tv          — flat TV box (one per flat-screen TV regardless of size)
  wardrobe    — 10 cu ft hanging box (1 per ~4 linear feet of visible hanging rod)
  mattress    — flat mattress/box-spring box (one per mattress or box spring)
  dish_pack   — 5.2 cu ft, 18×18×28 (china, crystal, ceramic kitchenware, fragile items)
  glass_pack  — cushioned glass box (drinking glasses, stemware, vases, glass jars)
  boots_pans  — corrugated wrap bundle (cast iron, baking sheets, boots/shoes, heavy cookware)

You respond ONLY with valid JSON — no markdown, no explanation outside the JSON."""

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


def analyze_room_ppr(
    room_name: str,
    image_paths: list[str],
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Analyze room images and return PPR box count estimates.

    Args:
        room_name:    e.g. "301 Living Room DN"
        image_paths:  list of filesystem paths or URLs (up to 5 used)
        model:        Claude model ID

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

    content = []
    images_used = 0
    for path in image_paths[:5]:
        result = _image_to_base64(path)
        if result:
            b64, media_type = result
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })
            images_used += 1

    if not content:
        return _error_result("Could not load any images", 0)

    content.append({
        "type": "text",
        "text": _USER_PROMPT.format(room_name=room_name),
    })

    try:
        client = anthropic.Anthropic(api_key=api_key)
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
        raw = raw.strip()

        parsed = json.loads(raw)
        counts = {col: max(0, int(parsed.get(col, 0) or 0)) for col in CPS_COLUMNS}
        total = sum(counts.values())

        return {
            "success": True,
            "counts": counts,
            "total": total,
            "confidence": str(parsed.get("confidence", "medium")),
            "notes": str(parsed.get("notes", ""))[:500],
            "images_used": images_used,
            "error": None,
        }

    except json.JSONDecodeError as e:
        logger.error("PPR analysis JSON parse error for %s: %s", room_name, e)
        return _error_result("AI returned invalid JSON — try again", images_used)
    except Exception as e:
        logger.error("PPR analysis error for %s: %s", room_name, e, exc_info=True)
        return _error_result(str(e), images_used)


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
