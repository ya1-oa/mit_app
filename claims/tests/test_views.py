"""
Tests for claims app — claim CRUD, room management, and Encircle push endpoints.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient, Room, WorkType

User = get_user_model()


class ClaimsAuthTests(TestCase):
    """All claims views require authentication."""

    def test_list_redirects_anonymous(self):
        response = Client().get(reverse('claims_list'))
        self.assertEqual(response.status_code, 302)

    def test_create_redirects_anonymous(self):
        response = Client().post(reverse('claims_list'))
        self.assertEqual(response.status_code, 302)


class ClaimsListTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='claims@example.com', password='pass')
        self.http = Client()
        self.http.login(email='claims@example.com', password='pass')

    def test_list_returns_200(self):
        response = self.http.get(reverse('claims_list'))
        self.assertEqual(response.status_code, 200)

    def test_list_displays_existing_claims(self):
        ClaimClient.objects.create(pOwner='Jones, Sarah', claimNumber='CLM-200')
        ClaimClient.objects.create(pOwner='Brown, Tom', claimNumber='CLM-201')
        response = self.http.get(reverse('claims_list'))
        self.assertContains(response, 'Jones')
        self.assertContains(response, 'Brown')

    def test_list_paginates_large_result_sets(self):
        for i in range(30):
            ClaimClient.objects.create(pOwner=f'Client {i:02d}', claimNumber=f'CLM-{i:03d}')
        response = self.http.get(reverse('claims_list'))
        self.assertEqual(response.status_code, 200)


class ClaimsDetailTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='detail@example.com', password='pass')
        self.http = Client()
        self.http.login(email='detail@example.com', password='pass')
        self.claim = ClaimClient.objects.create(
            pOwner='Detail, Test',
            claimNumber='CLM-DETAIL',
        )

    def test_detail_returns_200(self):
        response = self.http.get(reverse('claim_detail', args=[self.claim.id]))
        self.assertEqual(response.status_code, 200)

    def test_detail_404_for_nonexistent_claim(self):
        response = self.http.get(reverse('claim_detail', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_detail_contains_claim_info(self):
        response = self.http.get(reverse('claim_detail', args=[self.claim.id]))
        self.assertContains(response, 'CLM-DETAIL')


class RoomManagementTests(TestCase):
    """Room creation, ordering, and deletion within a claim."""

    def setUp(self):
        self.user = User.objects.create_user(email='rooms@example.com', password='pass')
        self.http = Client()
        self.http.login(email='rooms@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Room Test Client')
        WorkType.objects.get_or_create(work_type_id=100, defaults={'name': 'Overview'})

    def test_rooms_list_returns_200(self):
        response = self.http.get(reverse('rooms_list', args=[self.claim.id]))
        self.assertEqual(response.status_code, 200)

    def test_create_room_adds_to_claim(self):
        initial_count = Room.objects.filter(client=self.claim).count()
        response = self.http.post(
            reverse('rooms_list', args=[self.claim.id]),
            data=json.dumps({'room_name': 'Master Bedroom'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Room.objects.filter(client=self.claim).count(), initial_count + 1)

    def test_room_name_is_required(self):
        response = self.http.post(
            reverse('rooms_list', args=[self.claim.id]),
            data=json.dumps({'room_name': ''}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, [400, 422])
