"""
Tests for lease_manager app — lease dashboard, document tracking, and activity feed.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient, Landlord, Lease

User = get_user_model()


class LeaseManagerAuthTests(TestCase):

    def test_dashboard_redirects_anonymous(self):
        response = Client().get(reverse('lease_manager:lease_manager'))
        self.assertEqual(response.status_code, 302)


class LeaseManagerDashboardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='lease@example.com', password='pass')
        self.http = Client()
        self.http.login(email='lease@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Lease Test Client')

    def test_dashboard_returns_200(self):
        response = self.http.get(reverse('lease_manager:lease_manager'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_context_has_leases(self):
        response = self.http.get(reverse('lease_manager:lease_manager'))
        self.assertIn('leases', response.context)

    def test_dashboard_shows_lease_pipeline(self):
        response = self.http.get(reverse('lease_manager:lease_manager'))
        self.assertEqual(response.status_code, 200)
        # Pipeline data should be in context
        context_keys = set(response.context.keys())
        self.assertTrue(
            any('pipeline' in k.lower() or 'stage' in k.lower() for k in context_keys)
            or 'leases' in context_keys
        )

    def test_dashboard_filters_by_status(self):
        response = self.http.get(reverse('lease_manager:lease_manager'), {'status': 'active'})
        self.assertEqual(response.status_code, 200)

    def test_dashboard_filters_by_date_range(self):
        response = self.http.get(reverse('lease_manager:lease_manager'), {'date_range': '7'})
        self.assertEqual(response.status_code, 200)


class LeaseDetailTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='leasedetail@example.com', password='pass')
        self.http = Client()
        self.http.login(email='leasedetail@example.com', password='pass')
        self.claim = ClaimClient.objects.create(pOwner='Detail Lease Client')
        self.landlord = Landlord.objects.create(
            name='Test Landlord',
            address='123 Main St',
        )

    def test_detail_404_for_nonexistent_lease(self):
        import uuid
        response = self.http.get(
            reverse('lease_manager:lease_detail', args=[uuid.uuid4()])
        )
        self.assertEqual(response.status_code, 404)
