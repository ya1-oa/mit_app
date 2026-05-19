"""
Tests for box_calculator views — calculator home and room/session API endpoints.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient, Room
from box_calculator.models import BoxCalcSession, BoxCalcRoom, BoxCalcItem

User = get_user_model()


class BoxCalculatorAuthTests(TestCase):

    def test_home_redirects_anonymous(self):
        response = Client().get(reverse('calculator_home'))
        self.assertEqual(response.status_code, 302)


class BoxCalculatorHomeTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='boxcalc@example.com', password='pass')
        self.http = Client()
        self.http.login(email='boxcalc@example.com', password='pass')

    def test_home_returns_200(self):
        response = self.http.get(reverse('calculator_home'))
        self.assertEqual(response.status_code, 200)

    def test_home_context_has_clients(self):
        response = self.http.get(reverse('calculator_home'))
        self.assertIn('clients', response.context)

    def test_home_context_has_category_choices(self):
        response = self.http.get(reverse('calculator_home'))
        self.assertIn('category_choices', response.context)
        self.assertGreater(len(response.context['category_choices']), 0)

    def test_home_context_has_category_groups(self):
        response = self.http.get(reverse('calculator_home'))
        self.assertIn('category_groups', response.context)


class BoxCalculatorClientRoomsTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='boxrooms@example.com', password='pass')
        self.http = Client()
        self.http.login(email='boxrooms@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Box Rooms Client')
        self.room1 = Room.objects.create(client=self.claim, room_name='Living Room', sequence=0)
        self.room2 = Room.objects.create(client=self.claim, room_name='Kitchen', sequence=1)

    def test_client_rooms_returns_json(self):
        response = self.http.get(reverse('api_client_rooms', args=[self.claim.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_client_rooms_returns_all_rooms(self):
        response = self.http.get(reverse('api_client_rooms', args=[self.claim.id]))
        data = response.json()
        self.assertIn('rooms', data)
        self.assertEqual(len(data['rooms']), 2)

    def test_client_rooms_404_for_nonexistent_client(self):
        response = self.http.get(reverse('api_client_rooms', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_client_rooms_returns_saved_session_data(self):
        session = BoxCalcSession.objects.create(client=self.claim)
        bc_room = BoxCalcRoom.objects.create(session=session, room_name='Living Room', room=self.room1)
        BoxCalcItem.objects.create(room=bc_room, category='electronics', quantity=2, compartments=0)

        response = self.http.get(reverse('api_client_rooms', args=[self.claim.id]))
        data = response.json()
        # The saved session data should come back so the UI can restore state
        self.assertIn('saved_rooms', data)


class BoxCalculatorSaveTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='boxsave@example.com', password='pass')
        self.http = Client()
        self.http.login(email='boxsave@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Save Client')

    def test_save_session_creates_database_records(self):
        payload = {
            'client_id': self.claim.id,
            'rooms': [
                {
                    'room_name': 'Living Room',
                    'items': [
                        {'category': 'electronics', 'quantity': 2, 'compartments': 0, 'note': ''},
                    ],
                }
            ],
        }
        response = self.http.post(
            reverse('api_save_session'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertIn(response.status_code, [200, 201])
        self.assertTrue(BoxCalcSession.objects.filter(client=self.claim).exists())
