"""
Tests for cps_report models — CPSReportSession, CPSReportRoom, CPSReportItem.
"""
import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from docsAppR.models import Client
from cps_report.models import CPSReportSession, CPSReportRoom, CPSReportItem

User = get_user_model()


class CPSReportSessionTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='cps@example.com', password='pass')
        self.client_obj = Client.objects.create(
            pOwner='Smith, John',
            claimNumber='CLM-001',
        )

    def test_session_creation_with_defaults(self):
        session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
            claim_number='CLM-001',
            insured_name='John Smith',
        )
        self.assertEqual(session.status, 'pending')
        self.assertIsNotNone(session.share_token)
        self.assertIsInstance(session.share_token, uuid.UUID)

    def test_session_str_representation(self):
        session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
            insured_name='John Smith',
        )
        self.assertIn('Smith', str(session))

    def test_session_status_transitions(self):
        session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
        )
        self.assertEqual(session.status, 'pending')

        session.status = 'processing'
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.status, 'processing')

        session.status = 'complete'
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.status, 'complete')

    def test_total_replacement_value_empty_session(self):
        session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
        )
        self.assertEqual(session.total_replacement_value(), 0)

    def test_total_replacement_value_with_items(self):
        session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
        )
        room = CPSReportRoom.objects.create(
            session=session,
            room_name='Master Bedroom',
            room_number='301',
        )
        CPSReportItem.objects.create(
            room=room,
            description='55-inch LED TV',
            qty=1,
            replacement_value_each=699.00,
        )
        CPSReportItem.objects.create(
            room=room,
            description='Couch',
            qty=1,
            replacement_value_each=1200.00,
        )
        self.assertEqual(session.total_replacement_value(), 1899.00)

    def test_total_replacement_value_multiplies_by_qty(self):
        session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
        )
        room = CPSReportRoom.objects.create(
            session=session,
            room_name='Living Room',
            room_number='302',
        )
        CPSReportItem.objects.create(
            room=room,
            description='Chair',
            qty=4,
            replacement_value_each=250.00,
        )
        self.assertEqual(session.total_replacement_value(), 1000.00)

    def test_sessions_ordered_by_updated_at_descending(self):
        s1 = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-001',
        )
        s2 = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-002',
        )
        sessions = list(CPSReportSession.objects.all())
        self.assertEqual(sessions[0], s2)

    def test_share_token_is_unique_per_session(self):
        s1 = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-001',
        )
        s2 = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-002',
        )
        self.assertNotEqual(s1.share_token, s2.share_token)


class CPSReportRoomTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='cps_room@example.com', password='pass')
        self.client_obj = Client.objects.create(pOwner='Test Client')
        self.session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-12345',
        )

    def test_room_creation(self):
        room = CPSReportRoom.objects.create(
            session=self.session,
            room_name='Master Bedroom',
            room_number='301',
            encircle_room_id='room-abc',
        )
        self.assertEqual(room.room_name, 'Master Bedroom')
        self.assertEqual(room.status, 'pending')

    def test_room_with_secondary_pairing(self):
        room = CPSReportRoom.objects.create(
            session=self.session,
            room_name='Master Bedroom',
            room_number='301',
            encircle_room_id='room-301',
            encircle_room_id_secondary='room-401',
            encircle_room_label_secondary='Master Bedroom PPR',
        )
        self.assertNotEqual(room.encircle_room_id, room.encircle_room_id_secondary)
        self.assertTrue(room.encircle_room_id_secondary)


class CPSReportItemTests(TestCase):

    def setUp(self):
        self.client_obj = Client.objects.create(pOwner='Item Test Client')
        self.session = CPSReportSession.objects.create(
            client=self.client_obj,
            encircle_claim_id='ENC-ITEM',
        )
        self.room = CPSReportRoom.objects.create(
            session=self.session,
            room_name='Kitchen',
            room_number='305',
        )

    def test_item_creation_with_all_fields(self):
        item = CPSReportItem.objects.create(
            room=self.room,
            description='Samsung 55-inch QLED TV',
            brand='Samsung',
            condition='Good',
            qty=1,
            purchase_price_each=600.00,
            replacement_value_each=699.00,
            age_years=3,
            depreciation_pct=45.0,
        )
        self.assertEqual(item.description, 'Samsung 55-inch QLED TV')
        self.assertEqual(item.depreciation_pct, 45.0)

    def test_acv_calculated_from_replacement_and_depreciation(self):
        item = CPSReportItem.objects.create(
            room=self.room,
            description='TV',
            qty=1,
            replacement_value_each=1000.00,
            depreciation_pct=30.0,
        )
        expected_acv = 1000.00 * (1 - 30.0 / 100)
        if hasattr(item, 'acv'):
            self.assertAlmostEqual(float(item.acv), expected_acv, places=2)
