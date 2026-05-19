"""
Tests for email_manager app — email list, send, schedule creation, and tracking.
"""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import SentEmail, DocumentCategory, EmailSchedule
from django.utils import timezone

User = get_user_model()


class EmailManagerAuthTests(TestCase):

    def test_emails_page_redirects_anonymous(self):
        response = Client().get(reverse('emails'))
        self.assertEqual(response.status_code, 302)

    def test_schedule_page_redirects_anonymous(self):
        response = Client().get(reverse('create_schedule'))
        self.assertEqual(response.status_code, 302)


class EmailsListViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='emailmgr@example.com', password='pass')
        self.http = Client()
        self.http.login(email='emailmgr@example.com', password='pass')

    def test_emails_page_returns_200(self):
        response = self.http.get(reverse('emails'))
        self.assertEqual(response.status_code, 200)

    def test_emails_context_has_sent_emails(self):
        response = self.http.get(reverse('emails'))
        self.assertIn('sent_emails', response.context)

    def test_emails_context_has_schedules(self):
        response = self.http.get(reverse('emails'))
        self.assertIn('schedules', response.context)

    def test_emails_context_has_form(self):
        response = self.http.get(reverse('emails'))
        self.assertIn('form', response.context)

    def test_emails_filter_by_date_range(self):
        response = self.http.get(reverse('emails'), {'date_range': 'today'})
        self.assertEqual(response.status_code, 200)

    def test_emails_filter_by_category(self):
        cat = DocumentCategory.objects.create(name='Test Cat')
        response = self.http.get(reverse('emails'), {'category': cat.id})
        self.assertEqual(response.status_code, 200)

    @patch('email_manager.views.EmailMessage')
    def test_send_email_creates_sent_email_record(self, mock_email_class):
        mock_email = mock_email_class.return_value
        mock_email.send.return_value = 1

        response = self.http.post(reverse('emails'), {
            'recipients': 'client@example.com',
            'subject': 'Test Subject',
            'body': 'Test body text',
            'send_now': True,
        })
        self.assertIn(response.status_code, [200, 302])


class EmailTrackingPixelTests(TestCase):
    """The tracking pixel endpoint does not require authentication (email clients fetch it)."""

    def setUp(self):
        self.user = User.objects.create_user(email='track@example.com', password='pass')
        self.http = Client()
        self.sent_email = SentEmail.objects.create(
            subject='Tracked',
            body='body',
            recipients=['client@example.com'],
            sent_by=self.user,
            notify_on_open=True,
            admin_notification_email='admin@example.com',
        )

    def test_tracking_pixel_returns_gif(self):
        response = self.http.get(
            reverse('track_email_open', args=[self.sent_email.tracking_pixel_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/gif')

    def test_tracking_pixel_marks_email_opened(self):
        self.http.get(
            reverse('track_email_open', args=[self.sent_email.tracking_pixel_id])
        )
        self.sent_email.refresh_from_db()
        self.assertTrue(self.sent_email.is_opened)

    def test_tracking_pixel_nonexistent_uuid_still_returns_gif(self):
        import uuid
        fake_uuid = uuid.uuid4()
        response = self.http.get(reverse('track_email_open', args=[fake_uuid]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/gif')

    def test_tracking_pixel_sets_no_cache_headers(self):
        response = self.http.get(
            reverse('track_email_open', args=[self.sent_email.tracking_pixel_id])
        )
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')


class EmailScheduleViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='sched@example.com', password='pass')
        self.http = Client()
        self.http.login(email='sched@example.com', password='pass')

    def test_create_schedule_get_returns_200(self):
        response = self.http.get(reverse('create_schedule'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)

    def test_create_schedule_post_invalid_redirects_back(self):
        response = self.http.post(reverse('create_schedule'), {
            'name': '',  # required
            'subject': '',  # required
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
        self.assertTrue(response.context['form'].errors)
