"""
Standard room content estimates based on IICRC S500 pack-out conventions.
Used as a starting point when no items have been entered for a room.
"""
from __future__ import annotations
import re

# Each entry: list of dicts compatible with calculator.items_from_dicts()
# quantity for HANGING_CLOTHES = linear feet of rod
_DEFAULTS: dict[str, list[dict]] = {
    "master bedroom": [
        {"category": "dresser",         "quantity": 2, "compartments": 6, "note": ""},
        {"category": "nightstand",      "quantity": 2, "compartments": 2, "note": ""},
        {"category": "bed_frame",       "quantity": 1, "compartments": 0, "note": ""},
        {"category": "mattress",        "quantity": 1, "compartments": 0, "note": ""},
        {"category": "headboard",       "quantity": 1, "compartments": 0, "note": ""},
        {"category": "hanging_clothes", "quantity": 10, "compartments": 0, "note": "~10 linear ft of rod"},
        {"category": "folded_clothes",  "quantity": 2, "compartments": 0, "note": ""},
        {"category": "decor",           "quantity": 3, "compartments": 0, "note": "mirrors, lamps, artwork"},
    ],
    "bedroom": [
        {"category": "dresser",         "quantity": 1, "compartments": 4, "note": ""},
        {"category": "nightstand",      "quantity": 1, "compartments": 2, "note": ""},
        {"category": "bed_frame",       "quantity": 1, "compartments": 0, "note": ""},
        {"category": "mattress",        "quantity": 1, "compartments": 0, "note": ""},
        {"category": "headboard",       "quantity": 1, "compartments": 0, "note": ""},
        {"category": "hanging_clothes", "quantity": 5, "compartments": 0, "note": "~5 linear ft"},
        {"category": "folded_clothes",  "quantity": 1, "compartments": 0, "note": ""},
        {"category": "decor",           "quantity": 2, "compartments": 0, "note": ""},
    ],
    "kids bedroom": [
        {"category": "dresser",         "quantity": 1, "compartments": 4, "note": ""},
        {"category": "bed_frame",       "quantity": 1, "compartments": 0, "note": ""},
        {"category": "mattress",        "quantity": 1, "compartments": 0, "note": ""},
        {"category": "toys",            "quantity": 4, "compartments": 0, "note": ""},
        {"category": "bookshelf",       "quantity": 1, "compartments": 4, "note": ""},
        {"category": "folded_clothes",  "quantity": 1, "compartments": 0, "note": ""},
        {"category": "decor",           "quantity": 2, "compartments": 0, "note": ""},
    ],
    "kitchen": [
        {"category": "fragile_kitchen", "quantity": 3, "compartments": 0, "note": "dishes, glasses, bowls"},
        {"category": "kitchen",         "quantity": 4, "compartments": 0, "note": "pots, pans, small appliances"},
        {"category": "general",         "quantity": 2, "compartments": 0, "note": "pantry, non-perishables"},
    ],
    "living room": [
        {"category": "sofa",                 "quantity": 1, "compartments": 0, "note": ""},
        {"category": "chair",                "quantity": 2, "compartments": 0, "note": ""},
        {"category": "entertainment_center", "quantity": 1, "compartments": 3, "note": ""},
        {"category": "electronics",          "quantity": 2, "compartments": 0, "note": "TV, stereo"},
        {"category": "decor",                "quantity": 3, "compartments": 0, "note": "lamps, artwork, vases"},
        {"category": "books",                "quantity": 2, "compartments": 0, "note": ""},
    ],
    "family room": [
        {"category": "sofa",            "quantity": 2, "compartments": 0, "note": ""},
        {"category": "chair",           "quantity": 2, "compartments": 0, "note": ""},
        {"category": "entertainment_center", "quantity": 1, "compartments": 4, "note": ""},
        {"category": "electronics",     "quantity": 3, "compartments": 0, "note": ""},
        {"category": "toys",            "quantity": 2, "compartments": 0, "note": ""},
        {"category": "decor",           "quantity": 2, "compartments": 0, "note": ""},
    ],
    "dining room": [
        {"category": "dining_table",   "quantity": 1, "compartments": 0, "note": ""},
        {"category": "chair",          "quantity": 6, "compartments": 0, "note": "dining chairs"},
        {"category": "china_cabinet",  "quantity": 1, "compartments": 3, "note": ""},
        {"category": "decor",          "quantity": 2, "compartments": 0, "note": "centerpiece, artwork"},
    ],
    "bathroom": [
        {"category": "general", "quantity": 1, "compartments": 0, "note": "toiletries, medicine cabinet"},
        {"category": "linens",  "quantity": 1, "compartments": 0, "note": "towels, bath mats"},
    ],
    "master bathroom": [
        {"category": "general", "quantity": 2, "compartments": 0, "note": "toiletries, medicine, cosmetics"},
        {"category": "linens",  "quantity": 2, "compartments": 0, "note": "towels, robes, bath mats"},
        {"category": "decor",   "quantity": 1, "compartments": 0, "note": "artwork, accessories"},
    ],
    "office": [
        {"category": "desk",           "quantity": 1, "compartments": 3, "note": ""},
        {"category": "filing_cabinet", "quantity": 1, "compartments": 4, "note": ""},
        {"category": "bookshelf",      "quantity": 2, "compartments": 5, "note": ""},
        {"category": "electronics",    "quantity": 2, "compartments": 0, "note": "computer, printer"},
        {"category": "books",          "quantity": 3, "compartments": 0, "note": ""},
        {"category": "general",        "quantity": 2, "compartments": 0, "note": "supplies, files"},
    ],
    "laundry": [
        {"category": "appliance_large", "quantity": 2, "compartments": 0, "note": "washer & dryer"},
        {"category": "general",         "quantity": 2, "compartments": 0, "note": "supplies, detergent"},
    ],
    "laundry room": [
        {"category": "appliance_large", "quantity": 2, "compartments": 0, "note": "washer & dryer"},
        {"category": "general",         "quantity": 2, "compartments": 0, "note": "supplies"},
    ],
    "garage": [
        {"category": "appliance_large", "quantity": 1, "compartments": 0, "note": "e.g. chest freezer"},
        {"category": "general",         "quantity": 6, "compartments": 0, "note": "tools, bins, misc"},
        {"category": "books",           "quantity": 1, "compartments": 0, "note": "manuals, magazines"},
    ],
    "basement": [
        {"category": "general",         "quantity": 8, "compartments": 0, "note": "storage bins, misc"},
        {"category": "books",           "quantity": 3, "compartments": 0, "note": ""},
        {"category": "decor",           "quantity": 3, "compartments": 0, "note": "seasonal items"},
        {"category": "electronics",     "quantity": 2, "compartments": 0, "note": ""},
        {"category": "appliance_large", "quantity": 1, "compartments": 0, "note": ""},
    ],
    "sunroom": [
        {"category": "chair",    "quantity": 4, "compartments": 0, "note": "patio/sun chairs"},
        {"category": "decor",    "quantity": 3, "compartments": 0, "note": "plants, artwork"},
        {"category": "general",  "quantity": 2, "compartments": 0, "note": ""},
    ],
    "mudroom": [
        {"category": "general",  "quantity": 2, "compartments": 0, "note": "coats, boots, bags"},
    ],
    "closet": [
        {"category": "hanging_clothes", "quantity": 6, "compartments": 0, "note": "~6 linear ft"},
        {"category": "linens",          "quantity": 2, "compartments": 0, "note": "linens, blankets"},
        {"category": "general",         "quantity": 2, "compartments": 0, "note": "misc stored items"},
    ],
    "hallway": [
        {"category": "decor",   "quantity": 2, "compartments": 0, "note": "artwork, console table"},
        {"category": "general", "quantity": 1, "compartments": 0, "note": ""},
    ],
}

# Normalize keys once
_NORMALIZED = {k.lower().strip(): v for k, v in _DEFAULTS.items()}


def _normalize(room_name: str) -> str:
    """Lowercase, strip, collapse spaces."""
    return re.sub(r'\s+', ' ', room_name.lower().strip())


def get_defaults_for_room(room_name: str) -> list[dict]:
    """
    Return the default item list for a room by name.
    Tries exact match first, then substring/keyword match.
    Returns [] if no match found.
    """
    norm = _normalize(room_name)

    # Exact match
    if norm in _NORMALIZED:
        return [d.copy() for d in _NORMALIZED[norm]]

    # Keyword match: check if any key is a substring of the room name
    for key, defaults in _NORMALIZED.items():
        if key in norm or norm in key:
            return [d.copy() for d in defaults]

    # Partial word match (e.g. "BR1" → bedroom, "MBR" → master bedroom)
    keyword_map = {
        "mbr": "master bedroom", "master": "master bedroom",
        "br": "bedroom", "bed": "bedroom",
        "kit": "kitchen", "kitch": "kitchen",
        "lr": "living room", "living": "living room",
        "dr": "dining room", "dining": "dining room",
        "fr": "family room", "family": "family room",
        "bath": "bathroom", "ba": "bathroom", "wc": "bathroom",
        "off": "office", "study": "office",
        "laund": "laundry", "util": "laundry",
        "gar": "garage",
        "base": "basement", "bsmt": "basement",
        "hall": "hallway",
        "clos": "closet",
        "mud": "mudroom",
        "sun": "sunroom",
        "kid": "kids bedroom", "child": "kids bedroom",
    }
    for keyword, canonical in keyword_map.items():
        if keyword in norm:
            return [d.copy() for d in _NORMALIZED.get(canonical, [])]

    # Generic fallback
    return [
        {"category": "general", "quantity": 3, "compartments": 0, "note": "estimated"},
    ]
