"""
Box count calculator for home mitigation pack-outs.

Follows standardized industry conventions (IICRC S500 workflows) used by
mitigation contractors for content inventory and pack-out estimation.

Box sizes:
    SMALL     1.5 cu ft  - books, tools, dense heavy items
    MEDIUM    3.0 cu ft  - general household, kitchen, toys
    LARGE     4.5 cu ft  - linens, lampshades, light bulky items
    DISH_PACK 5.2 cu ft  - china, glassware, fragile kitchenware
    WARDROBE  10.0 cu ft - hanging clothes
    XL        furniture wrap (no box; pad-wrapped + inventoried)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Iterable


class BoxSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    DISH_PACK = "dish_pack"
    WARDROBE = "wardrobe"
    XL = "xl"

    @property
    def cubic_feet(self) -> Decimal:
        return {
            BoxSize.SMALL: Decimal("1.5"),
            BoxSize.MEDIUM: Decimal("3.0"),
            BoxSize.LARGE: Decimal("4.5"),
            BoxSize.DISH_PACK: Decimal("5.2"),
            BoxSize.WARDROBE: Decimal("10.0"),
            BoxSize.XL: Decimal("0"),
        }[self]

    @property
    def label(self) -> str:
        return {
            BoxSize.SMALL: "Small (1.5 cu ft)",
            BoxSize.MEDIUM: "Medium (3.0 cu ft)",
            BoxSize.LARGE: "Large (4.5 cu ft)",
            BoxSize.DISH_PACK: "Dish Pack (5.2 cu ft)",
            BoxSize.WARDROBE: "Wardrobe (10.0 cu ft)",
            BoxSize.XL: "XL Wrap (furniture)",
        }[self]


class ItemCategory(str, Enum):
    BOOKS = "books"
    KITCHEN = "kitchen"
    FRAGILE_KITCHEN = "fragile_kitchen"
    GENERAL = "general"
    LINENS = "linens"
    HANGING_CLOTHES = "hanging_clothes"
    FOLDED_CLOTHES = "folded_clothes"
    TOYS = "toys"
    DECOR = "decor"
    ELECTRONICS = "electronics"
    DRESSER = "dresser"
    NIGHTSTAND = "nightstand"
    FILING_CABINET = "filing_cabinet"
    DESK = "desk"
    BED_FRAME = "bed_frame"
    HEADBOARD = "headboard"
    MATTRESS = "mattress"
    SOFA = "sofa"
    CHAIR = "chair"
    DINING_TABLE = "dining_table"
    ENTERTAINMENT_CENTER = "entertainment_center"
    BOOKSHELF = "bookshelf"
    CHINA_CABINET = "china_cabinet"
    APPLIANCE_LARGE = "appliance_large"
    ARTWORK_LARGE = "artwork_large"

    @property
    def label(self) -> str:
        return self.value.replace('_', ' ').title()

    @property
    def is_furniture(self) -> bool:
        return self in {
            ItemCategory.DRESSER, ItemCategory.NIGHTSTAND, ItemCategory.FILING_CABINET,
            ItemCategory.DESK, ItemCategory.BED_FRAME, ItemCategory.HEADBOARD,
            ItemCategory.MATTRESS, ItemCategory.SOFA, ItemCategory.CHAIR,
            ItemCategory.DINING_TABLE, ItemCategory.ENTERTAINMENT_CENTER,
            ItemCategory.BOOKSHELF, ItemCategory.CHINA_CABINET,
            ItemCategory.APPLIANCE_LARGE, ItemCategory.ARTWORK_LARGE,
        }

    @property
    def has_compartments(self) -> bool:
        return self in {
            ItemCategory.DRESSER, ItemCategory.NIGHTSTAND, ItemCategory.FILING_CABINET,
            ItemCategory.DESK, ItemCategory.ENTERTAINMENT_CENTER,
            ItemCategory.BOOKSHELF, ItemCategory.CHINA_CABINET,
        }

    @property
    def compartment_label(self) -> str:
        labels = {
            ItemCategory.DRESSER: "drawers",
            ItemCategory.NIGHTSTAND: "drawers",
            ItemCategory.FILING_CABINET: "drawers",
            ItemCategory.DESK: "drawers",
            ItemCategory.ENTERTAINMENT_CENTER: "shelves",
            ItemCategory.BOOKSHELF: "shelves",
            ItemCategory.CHINA_CABINET: "shelves",
        }
        return labels.get(self, "compartments")


@dataclass(frozen=True)
class Item:
    category: ItemCategory
    quantity: int = 1
    compartments: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("quantity must be >= 1")
        if self.compartments < 0:
            raise ValueError("compartments must be >= 0")


@dataclass(frozen=True)
class Room:
    name: str
    items: tuple[Item, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _Rule:
    primary: BoxSize
    per_unit: Decimal
    compartment: BoxSize | None = None


_RULES: dict[ItemCategory, _Rule] = {
    ItemCategory.BOOKS:           _Rule(BoxSize.SMALL,     Decimal("1")),
    ItemCategory.KITCHEN:         _Rule(BoxSize.MEDIUM,    Decimal("1")),
    ItemCategory.FRAGILE_KITCHEN: _Rule(BoxSize.DISH_PACK, Decimal("1")),
    ItemCategory.GENERAL:         _Rule(BoxSize.MEDIUM,    Decimal("1")),
    ItemCategory.LINENS:          _Rule(BoxSize.LARGE,     Decimal("1")),
    ItemCategory.FOLDED_CLOTHES:  _Rule(BoxSize.MEDIUM,    Decimal("1")),
    ItemCategory.TOYS:            _Rule(BoxSize.MEDIUM,    Decimal("1")),
    ItemCategory.DECOR:           _Rule(BoxSize.MEDIUM,    Decimal("1")),
    ItemCategory.ELECTRONICS:     _Rule(BoxSize.MEDIUM,    Decimal("1")),
    ItemCategory.HANGING_CLOTHES: _Rule(BoxSize.WARDROBE,  Decimal("0.5")),
    ItemCategory.DRESSER:              _Rule(BoxSize.XL, Decimal("1"), BoxSize.MEDIUM),
    ItemCategory.NIGHTSTAND:           _Rule(BoxSize.XL, Decimal("1"), BoxSize.MEDIUM),
    ItemCategory.FILING_CABINET:       _Rule(BoxSize.XL, Decimal("1"), BoxSize.SMALL),
    ItemCategory.DESK:                 _Rule(BoxSize.XL, Decimal("1"), BoxSize.MEDIUM),
    ItemCategory.ENTERTAINMENT_CENTER: _Rule(BoxSize.XL, Decimal("1"), BoxSize.MEDIUM),
    ItemCategory.BOOKSHELF:            _Rule(BoxSize.XL, Decimal("1"), BoxSize.SMALL),
    ItemCategory.CHINA_CABINET:        _Rule(BoxSize.XL, Decimal("1"), BoxSize.DISH_PACK),
    ItemCategory.BED_FRAME:       _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.HEADBOARD:       _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.MATTRESS:        _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.SOFA:            _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.CHAIR:           _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.DINING_TABLE:    _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.APPLIANCE_LARGE: _Rule(BoxSize.XL, Decimal("1")),
    ItemCategory.ARTWORK_LARGE:   _Rule(BoxSize.XL, Decimal("1")),
}


@dataclass(frozen=True)
class BoxTotals:
    small: int = 0
    medium: int = 0
    large: int = 0
    dish_pack: int = 0
    wardrobe: int = 0
    xl: int = 0

    def __add__(self, other: "BoxTotals") -> "BoxTotals":
        return BoxTotals(
            small=self.small + other.small,
            medium=self.medium + other.medium,
            large=self.large + other.large,
            dish_pack=self.dish_pack + other.dish_pack,
            wardrobe=self.wardrobe + other.wardrobe,
            xl=self.xl + other.xl,
        )

    @property
    def total_boxes(self) -> int:
        return self.small + self.medium + self.large + self.dish_pack + self.wardrobe

    @property
    def total_units(self) -> int:
        return self.total_boxes + self.xl

    @property
    def total_cubic_feet(self) -> Decimal:
        return (
            BoxSize.SMALL.cubic_feet * self.small
            + BoxSize.MEDIUM.cubic_feet * self.medium
            + BoxSize.LARGE.cubic_feet * self.large
            + BoxSize.DISH_PACK.cubic_feet * self.dish_pack
            + BoxSize.WARDROBE.cubic_feet * self.wardrobe
        )

    def to_dict(self) -> dict:
        return {
            "small": self.small,
            "medium": self.medium,
            "large": self.large,
            "dish_pack": self.dish_pack,
            "wardrobe": self.wardrobe,
            "xl": self.xl,
            "total_boxes": self.total_boxes,
            "total_units": self.total_units,
            "total_cubic_feet": str(self.total_cubic_feet),
        }


@dataclass(frozen=True)
class RoomReport:
    room: str
    totals: BoxTotals
    line_items: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "room": self.room,
            "totals": self.totals.to_dict(),
            "line_items": list(self.line_items),
        }


@dataclass(frozen=True)
class JobReport:
    rooms: tuple[RoomReport, ...]
    totals: BoxTotals

    def to_dict(self) -> dict:
        return {
            "rooms": [r.to_dict() for r in self.rooms],
            "totals": self.totals.to_dict(),
        }


def _ceil_decimal(value: Decimal) -> int:
    int_part = int(value)
    return int_part + 1 if value > int_part else int_part


def _boxes_for_item(item: Item) -> tuple[BoxTotals, list[dict]]:
    try:
        rule = _RULES[item.category]
    except KeyError:
        raise ValueError(f"No conversion rule for category {item.category!r}")

    breakdown: list[dict] = []
    counts = {size: 0 for size in BoxSize}

    primary_qty = _ceil_decimal(Decimal(item.quantity) * rule.per_unit)
    counts[rule.primary] += primary_qty
    breakdown.append({
        "category": item.category.value,
        "category_label": item.category.label,
        "quantity": item.quantity,
        "box_size": rule.primary.value,
        "box_size_label": rule.primary.label,
        "box_count": primary_qty,
        "reason": f"{item.quantity} {item.category.label} → {primary_qty} {rule.primary.label}",
        "note": item.note,
        "is_furniture": item.category.is_furniture,
    })

    if rule.compartment and item.compartments > 0:
        comp_qty = item.quantity * item.compartments
        counts[rule.compartment] += comp_qty
        breakdown.append({
            "category": item.category.value,
            "category_label": item.category.label,
            "quantity": item.quantity,
            "box_size": rule.compartment.value,
            "box_size_label": rule.compartment.label,
            "box_count": comp_qty,
            "reason": (
                f"{item.quantity}× {item.category.label} with "
                f"{item.compartments} {item.category.compartment_label} "
                f"→ {comp_qty} {rule.compartment.label} (contents)"
            ),
            "note": "",
            "is_furniture": False,
        })

    return BoxTotals(
        small=counts[BoxSize.SMALL],
        medium=counts[BoxSize.MEDIUM],
        large=counts[BoxSize.LARGE],
        dish_pack=counts[BoxSize.DISH_PACK],
        wardrobe=counts[BoxSize.WARDROBE],
        xl=counts[BoxSize.XL],
    ), breakdown


def calculate_room(room: Room) -> RoomReport:
    totals = BoxTotals()
    line_items: list[dict] = []
    for item in room.items:
        item_totals, item_lines = _boxes_for_item(item)
        totals = totals + item_totals
        line_items.extend(item_lines)
    return RoomReport(room=room.name, totals=totals, line_items=tuple(line_items))


def calculate_job(rooms: Iterable[Room]) -> JobReport:
    room_reports = tuple(calculate_room(r) for r in rooms)
    job_totals = BoxTotals()
    for rr in room_reports:
        job_totals = job_totals + rr.totals
    return JobReport(rooms=room_reports, totals=job_totals)


def items_from_dicts(item_dicts: list[dict]) -> list[Item]:
    """Convert a list of plain dicts (from JSON) into Item objects."""
    items = []
    for d in item_dicts:
        try:
            items.append(Item(
                category=ItemCategory(d['category']),
                quantity=int(d.get('quantity', 1)),
                compartments=int(d.get('compartments', 0)),
                note=d.get('note', ''),
            ))
        except (KeyError, ValueError):
            continue
    return items


# Human-readable category choices for forms / templates
CATEGORY_CHOICES = [(c.value, c.label) for c in ItemCategory]
CATEGORY_GROUPS = {
    "Contents (Box Items)": [
        ItemCategory.BOOKS, ItemCategory.KITCHEN, ItemCategory.FRAGILE_KITCHEN,
        ItemCategory.GENERAL, ItemCategory.LINENS, ItemCategory.HANGING_CLOTHES,
        ItemCategory.FOLDED_CLOTHES, ItemCategory.TOYS, ItemCategory.DECOR,
        ItemCategory.ELECTRONICS,
    ],
    "Furniture (XL Wrap)": [
        ItemCategory.DRESSER, ItemCategory.NIGHTSTAND, ItemCategory.DESK,
        ItemCategory.FILING_CABINET, ItemCategory.BED_FRAME, ItemCategory.HEADBOARD,
        ItemCategory.MATTRESS, ItemCategory.SOFA, ItemCategory.CHAIR,
        ItemCategory.DINING_TABLE, ItemCategory.ENTERTAINMENT_CENTER,
        ItemCategory.BOOKSHELF, ItemCategory.CHINA_CABINET,
        ItemCategory.APPLIANCE_LARGE, ItemCategory.ARTWORK_LARGE,
    ],
}
