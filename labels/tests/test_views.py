"""
Tests for labels app — box labels and wall labels PDF generation.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient, Room

User = get_user_model()


class LabelsAuthTests(TestCase):

    def test_labels_page_redirects_anonymous(self):
        response = Client().get(reverse('labels'))
        self.assertEqual(response.status_code, 302)

    def test_wall_labels_redirects_anonymous(self):
        response = Client().get(reverse('wall_labels'))
        self.assertEqual(response.status_code, 302)


class LabelsPageTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='labels@example.com', password='pass')
        self.http = Client()
        self.http.login(email='labels@example.com', password='pass')

    def test_labels_get_returns_200(self):
        response = self.http.get(reverse('labels'))
        self.assertEqual(response.status_code, 200)

    def test_labels_page_lists_all_claims(self):
        ClaimClient.objects.create(pOwner='Labels Test Client')
        response = self.http.get(reverse('labels'))
        self.assertContains(response, 'Labels Test Client')

    def test_wall_labels_get_returns_200(self):
        response = self.http.get(reverse('wall_labels'))
        self.assertEqual(response.status_code, 200)

    def test_labels_post_missing_claim_returns_400(self):
        response = self.http.post(reverse('labels'), {'claim': ''})
        self.assertEqual(response.status_code, 400)

    def test_wall_labels_post_missing_claim_returns_400(self):
        response = self.http.post(reverse('wall_labels'), {'claim': ''})
        self.assertEqual(response.status_code, 400)


class LabelsWithClaimTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='labelsclaim@example.com', password='pass')
        self.http = Client()
        self.http.login(email='labelsclaim@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Label Claim', pAddress='123 Main St')
        self.room = Room.objects.create(
            client=self.claim,
            room_name='Living Room',
            sequence=1,
        )

    def test_labels_page_shows_rooms_for_selected_claim(self):
        response = self.http.get(reverse('labels'), {'claim': self.claim.pOwner})
        self.assertEqual(response.status_code, 200)
        self.assertIn('rooms', response.context)

    def test_labels_post_no_room_counts_returns_success(self):
        response = self.http.post(
            reverse('labels'),
            data={'claim': self.claim.pOwner},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('status', data)


class LabelHelperFunctionTests(TestCase):
    """Unit tests for pure helper functions in labels/views.py."""

    def test_safe_filename_removes_illegal_chars(self):
        from labels.views import safe_filename
        result = safe_filename('My/File:Name<>?"')
        self.assertNotIn('/', result)
        self.assertNotIn(':', result)
        self.assertNotIn('<', result)

    def test_safe_filename_truncates_to_max_length(self):
        from labels.views import safe_filename
        long_name = 'a' * 200
        result = safe_filename(long_name, max_length=120)
        self.assertLessEqual(len(result), 120)

    def test_calculate_print_area_single_label(self):
        from labels.views import calculate_print_area
        result = calculate_print_area(1)
        self.assertIn('A1', result)

    def test_calculate_print_area_zero_defaults(self):
        from labels.views import calculate_print_area
        result = calculate_print_area(0)
        self.assertEqual(result, 'A1:B4')
