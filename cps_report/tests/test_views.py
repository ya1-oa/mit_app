"""
Tests for cps_report views — home page, status polling, item editing, and exports.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient
from cps_report.models import CPSReportSession, CPSReportRoom, CPSReportItem

User = get_user_model()


class CPSReportAuthTests(TestCase):
    """All CPS report views require authentication."""

    def test_home_redirects_anonymous(self):
        response = Client().get(reverse('cps_home'))
        self.assertEqual(response.status_code, 302)

    def test_session_status_redirects_anonymous(self):
        response = Client().get('/cps-report/api/session/1/status/')
        self.assertEqual(response.status_code, 302)


class CPSReportHomeTests(TestCase):
    """cps_home groups sessions by claim and renders them."""

    def setUp(self):
        self.user = User.objects.create_user(email='cps@example.com', password='pass')
        self.http_client = Client()
        self.http_client.login(email='cps@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Johnson, Mark', claimNumber='CLM-100')

    def test_home_returns_200(self):
        response = self.http_client.get(reverse('cps_home'))
        self.assertEqual(response.status_code, 200)

    def test_home_context_has_grouped_sessions(self):
        response = self.http_client.get(reverse('cps_home'))
        self.assertIn('grouped_sessions', response.context)

    def test_home_groups_sessions_by_encircle_claim_id(self):
        CPSReportSession.objects.create(
            client=self.claim, encircle_claim_id='ENC-100', insured_name='Johnson, Mark',
        )
        CPSReportSession.objects.create(
            client=self.claim, encircle_claim_id='ENC-100', insured_name='Johnson, Mark',
        )
        CPSReportSession.objects.create(
            client=self.claim, encircle_claim_id='ENC-200', insured_name='Smith, Jane',
        )
        response = self.http_client.get(reverse('cps_home'))
        grouped = response.context['grouped_sessions']
        self.assertIn('ENC-100', grouped)
        self.assertIn('ENC-200', grouped)
        self.assertEqual(len(grouped['ENC-100']['sessions']), 2)
        self.assertEqual(len(grouped['ENC-200']['sessions']), 1)


class CPSSessionStatusTests(TestCase):
    """Session status polling endpoint returns correct JSON structure."""

    def setUp(self):
        self.user = User.objects.create_user(email='status@example.com', password='pass')
        self.http_client = Client()
        self.http_client.login(email='status@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Test Claim')
        self.session = CPSReportSession.objects.create(
            client=self.claim,
            encircle_claim_id='ENC-STATUS',
        )

    def test_status_returns_session_state(self):
        response = self.http_client.get(
            reverse('cps_session_status', args=[self.session.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('status', data)

    def test_status_404_for_nonexistent_session(self):
        response = self.http_client.get(
            reverse('cps_session_status', args=[99999])
        )
        self.assertEqual(response.status_code, 404)

    def test_complete_session_returns_room_progress(self):
        self.session.status = 'complete'
        self.session.save()
        room = CPSReportRoom.objects.create(
            session=self.session,
            room_name='Master Bedroom',
            room_number='301',
            status='complete',
        )
        CPSReportItem.objects.create(
            room=room,
            description='TV',
            qty=1,
            replacement_value_each=699,
        )
        response = self.http_client.get(
            reverse('cps_session_status', args=[self.session.id])
        )
        data = response.json()
        self.assertEqual(data['status'], 'complete')
        self.assertIn('rooms', data)


class CPSItemEditTests(TestCase):
    """Inline item editing via AJAX updates the DB correctly."""

    def setUp(self):
        self.user = User.objects.create_user(email='edit@example.com', password='pass')
        self.http_client = Client()
        self.http_client.login(email='edit@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Edit Client')
        self.session = CPSReportSession.objects.create(
            client=self.claim,
            encircle_claim_id='ENC-EDIT',
            status='complete',
        )
        self.room = CPSReportRoom.objects.create(
            session=self.session,
            room_name='Living Room',
            room_number='303',
        )
        self.item = CPSReportItem.objects.create(
            room=self.room,
            description='Original Description',
            qty=1,
            replacement_value_each=500,
        )

    def test_update_item_description(self):
        response = self.http_client.post(
            reverse('cps_update_item', args=[self.item.id]),
            data=json.dumps({'field': 'description', 'value': 'Updated Description'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.description, 'Updated Description')

    def test_update_item_returns_updated_values(self):
        response = self.http_client.post(
            reverse('cps_update_item', args=[self.item.id]),
            data=json.dumps({'field': 'qty', 'value': 3}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)

    def test_delete_item_removes_from_db(self):
        item_id = self.item.id
        response = self.http_client.post(
            reverse('cps_delete_item', args=[item_id]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CPSReportItem.objects.filter(id=item_id).exists())
