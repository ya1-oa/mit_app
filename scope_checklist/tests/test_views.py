"""
Tests for scope_checklist app — checklist page, room data API, and PDF generation.
"""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient, Room

User = get_user_model()


class ScopeChecklistAuthTests(TestCase):

    def test_checklist_redirects_anonymous(self):
        response = Client().get(reverse('scope_checklist'))
        self.assertEqual(response.status_code, 302)

    def test_rooms_api_redirects_anonymous(self):
        response = Client().get(reverse('scope_checklist_get_rooms', args=[1]))
        self.assertEqual(response.status_code, 302)


class ScopeChecklistPageTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='scope@example.com', password='pass')
        self.http = Client()
        self.http.login(email='scope@example.com', password='pass')

    def test_checklist_returns_200(self):
        response = self.http.get(reverse('scope_checklist'))
        self.assertEqual(response.status_code, 200)

    def test_checklist_context_has_claims(self):
        response = self.http.get(reverse('scope_checklist'))
        self.assertIn('claims', response.context)

    def test_checklist_lists_all_claims(self):
        ClaimClient.objects.create(pOwner='Scope Client A')
        ClaimClient.objects.create(pOwner='Scope Client B')
        response = self.http.get(reverse('scope_checklist'))
        claims_in_context = list(response.context['claims'])
        self.assertGreaterEqual(len(claims_in_context), 2)


class ScopeChecklistRoomsApiTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='scoperooms@example.com', password='pass')
        self.http = Client()
        self.http.login(email='scoperooms@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Rooms API Client')
        Room.objects.create(client=self.claim, room_name='Master Bedroom', sequence=1)
        Room.objects.create(client=self.claim, room_name='Living Room', sequence=2)

    def test_rooms_api_returns_json(self):
        response = self.http.get(reverse('scope_checklist_get_rooms', args=[self.claim.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_rooms_api_returns_all_rooms_for_claim(self):
        response = self.http.get(reverse('scope_checklist_get_rooms', args=[self.claim.id]))
        data = response.json()
        self.assertIn('rooms', data)
        self.assertEqual(len(data['rooms']), 2)

    def test_rooms_api_404_for_nonexistent_claim(self):
        response = self.http.get(reverse('scope_checklist_get_rooms', args=[99999]))
        self.assertEqual(response.status_code, 404)


class ScopeChecklistSaveTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='scopesave@example.com', password='pass')
        self.http = Client()
        self.http.login(email='scopesave@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Save Client')
        self.room = Room.objects.create(client=self.claim, room_name='Kitchen', sequence=1)

    def test_save_checklist_requires_post(self):
        response = self.http.get(reverse('scope_checklist_save'))
        self.assertNotEqual(response.status_code, 200)

    def test_save_checklist_accepts_valid_payload(self):
        payload = {
            'claim_id': self.claim.id,
            'room_id': str(self.room.id),
            'items': [
                {'code': 'WTR MITIGATION', 'checked': True, 'notes': ''},
            ],
        }
        response = self.http.post(
            reverse('scope_checklist_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(response.status_code, [200, 201])
