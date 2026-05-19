"""
Tests for dashboard app — home/app-grid view and stats endpoints.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import Client as ClaimClient

User = get_user_model()


class DashboardAuthTests(TestCase):

    def test_home_redirects_anonymous(self):
        response = Client().get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/', response['Location'])


class DashboardHomeTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='dash@example.com', password='pass')
        self.http = Client()
        self.http.login(email='dash@example.com', password='pass')

    def test_home_returns_200(self):
        response = self.http.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_home_uses_correct_template(self):
        response = self.http.get(reverse('home'))
        self.assertTemplateUsed(response, 'account/home.html')

    def test_home_context_has_apps_grid(self):
        response = self.http.get(reverse('home'))
        self.assertIn('apps', response.context)
        apps = response.context['apps']
        self.assertGreater(len(apps), 0)

    def test_home_apps_have_required_keys(self):
        response = self.http.get(reverse('home'))
        for app in response.context['apps']:
            self.assertIn('name', app)
            self.assertIn('url', app)
            self.assertIn('description', app)

    def test_home_includes_core_apps_in_grid(self):
        response = self.http.get(reverse('home'))
        app_names = [a['name'] for a in response.context['apps']]
        self.assertIn('Claims Manager', app_names)
        self.assertIn('CPS Schedule of Loss', app_names)
        self.assertIn('Equipment Checker', app_names)
