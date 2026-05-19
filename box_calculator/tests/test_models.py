"""
Tests for box_calculator models and the pure calculator engine.
"""
from decimal import Decimal

from django.test import TestCase

from docsAppR.models import Client as ClaimClient
from box_calculator.models import BoxCalcSession, BoxCalcRoom, BoxCalcItem
from box_calculator.calculator import (
    ItemCategory,
    Item,
    Room,
    BoxTotals,
    RoomReport,
    JobReport,
    calculate_room,
    calculate_job,
    items_from_dicts,
)


class BoxCalcSessionTests(TestCase):

    def setUp(self):
        self.claim = ClaimClient.objects.create(pOwner='Box Test Client')

    def test_session_str_includes_client_name(self):
        session = BoxCalcSession.objects.create(client=self.claim)
        self.assertIn('Box Test Client', str(session))

    def test_sessions_ordered_by_updated_at_descending(self):
        s1 = BoxCalcSession.objects.create(client=self.claim)
        s2 = BoxCalcSession.objects.create(client=self.claim)
        sessions = list(BoxCalcSession.objects.all())
        self.assertEqual(sessions[0], s2)

    def test_get_job_report_empty_session(self):
        session = BoxCalcSession.objects.create(client=self.claim)
        report = session.get_job_report()
        self.assertIsInstance(report, JobReport)
        self.assertEqual(report.totals.total_boxes, 0)


class BoxCalcRoomTests(TestCase):

    def setUp(self):
        self.claim = ClaimClient.objects.create(pOwner='Room Test Client')
        self.session = BoxCalcSession.objects.create(client=self.claim)

    def test_room_creation(self):
        room = BoxCalcRoom.objects.create(
            session=self.session,
            room_name='Living Room',
        )
        self.assertEqual(room.room_name, 'Living Room')
        self.assertEqual(room.session, self.session)

    def test_room_items_cascade_on_delete(self):
        room = BoxCalcRoom.objects.create(session=self.session, room_name='Test Room')
        BoxCalcItem.objects.create(room=room, category='electronics', quantity=2, compartments=0)
        room_id = room.id
        room.delete()
        self.assertFalse(BoxCalcItem.objects.filter(room_id=room_id).exists())


class BoxCalcItemTests(TestCase):

    def setUp(self):
        self.claim = ClaimClient.objects.create(pOwner='Item Test Client')
        self.session = BoxCalcSession.objects.create(client=self.claim)
        self.room = BoxCalcRoom.objects.create(session=self.session, room_name='Kitchen')

    def test_item_stores_category_and_quantity(self):
        item = BoxCalcItem.objects.create(
            room=self.room,
            category='fragile_kitchen',
            quantity=3,
            compartments=0,
            note='Glassware set',
        )
        self.assertEqual(item.category, 'fragile_kitchen')
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.note, 'Glassware set')


# ── Pure calculator logic tests ───────────────────────────────────────────────

class CalculatorItemTests(TestCase):
    """Item dataclass validates its inputs."""

    def test_valid_item_creation(self):
        item = Item(category=ItemCategory.ELECTRONICS, quantity=2, compartments=0)
        self.assertEqual(item.quantity, 2)

    def test_quantity_below_one_raises(self):
        with self.assertRaises(ValueError):
            Item(category=ItemCategory.BOOKS, quantity=0)

    def test_negative_compartments_raises(self):
        with self.assertRaises(ValueError):
            Item(category=ItemCategory.DRESSER, quantity=1, compartments=-1)


class CalculateRoomTests(TestCase):
    """calculate_room converts items to box counts using IICRC rules."""

    def test_electronics_use_medium_boxes(self):
        room = Room(
            name='Living Room',
            items=(Item(category=ItemCategory.ELECTRONICS, quantity=3),),
        )
        report = calculate_room(room)
        self.assertEqual(report.totals.medium, 3)
        self.assertEqual(report.totals.xl, 0)

    def test_hanging_clothes_use_wardrobe_boxes(self):
        room = Room(
            name='Master Bedroom',
            items=(Item(category=ItemCategory.HANGING_CLOTHES, quantity=10),),
        )
        report = calculate_room(room)
        self.assertGreater(report.totals.wardrobe, 0)

    def test_fragile_kitchen_uses_dish_packs(self):
        room = Room(
            name='Kitchen',
            items=(Item(category=ItemCategory.FRAGILE_KITCHEN, quantity=5),),
        )
        report = calculate_room(room)
        self.assertEqual(report.totals.dish_pack, 5)

    def test_furniture_goes_to_xl(self):
        room = Room(
            name='Bedroom',
            items=(Item(category=ItemCategory.SOFA, quantity=1),),
        )
        report = calculate_room(room)
        self.assertEqual(report.totals.xl, 1)

    def test_dresser_with_drawers_adds_medium_boxes(self):
        room = Room(
            name='Bedroom',
            items=(Item(category=ItemCategory.DRESSER, quantity=1, compartments=6),),
        )
        report = calculate_room(room)
        self.assertEqual(report.totals.xl, 1)
        self.assertEqual(report.totals.medium, 6)

    def test_empty_room_returns_zero_totals(self):
        room = Room(name='Empty Room', items=())
        report = calculate_room(room)
        self.assertEqual(report.totals.total_boxes, 0)
        self.assertEqual(report.totals.total_units, 0)

    def test_report_room_name_is_preserved(self):
        room = Room(name='Guest Bedroom', items=(Item(category=ItemCategory.GENERAL, quantity=1),))
        report = calculate_room(room)
        self.assertEqual(report.room, 'Guest Bedroom')


class CalculateJobTests(TestCase):
    """calculate_job aggregates multiple room reports correctly."""

    def test_job_totals_sum_across_rooms(self):
        rooms = [
            Room(name='Living Room', items=(Item(category=ItemCategory.ELECTRONICS, quantity=2),)),
            Room(name='Kitchen', items=(Item(category=ItemCategory.FRAGILE_KITCHEN, quantity=10),)),
        ]
        report = calculate_job(rooms)
        self.assertEqual(report.totals.medium, 2)
        self.assertEqual(report.totals.dish_pack, 10)

    def test_job_report_contains_all_rooms(self):
        rooms = [
            Room(name='Room A', items=(Item(category=ItemCategory.BOOKS, quantity=1),)),
            Room(name='Room B', items=(Item(category=ItemCategory.BOOKS, quantity=1),)),
        ]
        report = calculate_job(rooms)
        self.assertEqual(len(report.rooms), 2)

    def test_empty_job_returns_zero_totals(self):
        report = calculate_job([])
        self.assertEqual(report.totals.total_boxes, 0)


class ItemsFromDictsTests(TestCase):
    """items_from_dicts converts JSON payloads from the front-end to Item objects."""

    def test_converts_valid_dicts(self):
        dicts = [{'category': 'books', 'quantity': 5, 'compartments': 0}]
        items = items_from_dicts(dicts)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].category, ItemCategory.BOOKS)
        self.assertEqual(items[0].quantity, 5)

    def test_skips_invalid_category(self):
        dicts = [{'category': 'INVALID_CAT', 'quantity': 1}]
        items = items_from_dicts(dicts)
        self.assertEqual(len(items), 0)

    def test_defaults_quantity_to_one(self):
        dicts = [{'category': 'general'}]
        items = items_from_dicts(dicts)
        self.assertEqual(items[0].quantity, 1)
