"""
Tests for encircle app — dashboard, webhook endpoint, and API proxy views.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class EncircleAuthTests(TestCase):

    def test_dashboard_redirects_anonymous(self):
        response = Client().get(reverse('encircle_dashboard'))
        self.assertEqual(response.status_code, 302)


class EncircleDashboardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='encircle@example.com', password='pass')
        self.http = Client()
        self.http.login(email='encircle@example.com', password='pass')

    @patch('encircle.views.EncircleAPIClient')
    def test_dashboard_returns_200_with_api_mock(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_all_claims.return_value = []
        mock_api_class.return_value = mock_api

        response = self.http.get(reverse('encircle_dashboard'))
        self.assertEqual(response.status_code, 200)

    @patch('encircle.views.EncircleAPIClient')
    @patch('encircle.views.EncircleDataProcessor')
    def test_claims_api_returns_json(self, mock_processor_class, mock_api_class):
        mock_api = MagicMock()
        mock_api.get_all_claims.return_value = []
        mock_api_class.return_value = mock_api

        mock_processor = MagicMock()
        mock_processor.process_claims_list.return_value = []
        mock_processor_class.return_value = mock_processor

        response = self.http.get(reverse('fetch_all_claims_api'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')


class EncircleWebhookTests(TestCase):
    """Webhook endpoint must accept unsigned POST requests from Encircle."""

    def setUp(self):
        self.http = Client()

    def test_webhook_accepts_post_without_auth(self):
        payload = json.dumps({'event': 'claim.updated', 'claim_id': 12345})
        response = self.http.post(
            reverse('encircle_webhook'),
            data=payload,
            content_type='application/json',
        )
        # Should acknowledge without requiring login
        self.assertIn(response.status_code, [200, 202])

    def test_webhook_test_endpoint_returns_200(self):
        response = self.http.post(
            reverse('encircle_webhook_test'),
            data=json.dumps({'test': True}),
            content_type='application/json',
        )
        self.assertIn(response.status_code, [200, 202])
