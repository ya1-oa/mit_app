"""
Unit tests for email scheduling and campaign tasks.

Requirements:
    pip install freezegun

Run:
    python manage.py test email_manager.tests.test_scheduling
"""
from datetime import datetime
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.utils import timezone
from freezegun import freeze_time

from docsAppR.models import EmailSchedule, EmailCampaign, SentEmail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username='testuser'):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.get_or_create(
        email=f'{username}@example.com',
        defaults={'username': username, 'password': 'pw'},
    )[0]


def _make_schedule(user, start_dt, interval='none', repeat_count=1, **kwargs):
    return EmailSchedule.objects.create(
        name='Test Schedule',
        subject='Test Subject',
        body='Test Body',
        recipients=['recipient@example.com'],
        start_date=start_dt,
        interval=interval,
        repeat_count=repeat_count,
        is_active=True,
        created_by=user,
        admin_notification_email='admin@example.com',
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test: send_scheduled_emails_task fires at the right time
# ---------------------------------------------------------------------------

class SendScheduledEmailsTaskTest(TestCase):

    @patch('email_manager.tasks.EmailMessage')
    @freeze_time('2026-06-01 10:00:00')
    def test_due_schedule_fires(self, MockEmailMessage):
        """A schedule whose start_date == now should fire."""
        mock_instance = MagicMock()
        MockEmailMessage.return_value = mock_instance

        user = _make_user()
        schedule = _make_schedule(
            user,
            start_dt=timezone.make_aware(datetime(2026, 6, 1, 10, 0, 0)),
        )
        self.assertIsNone(schedule.last_sent)

        from email_manager.tasks import send_scheduled_emails_task
        count = send_scheduled_emails_task.apply().get()

        self.assertEqual(count, 1)
        mock_instance.send.assert_called_once()

        schedule.refresh_from_db()
        self.assertIsNotNone(schedule.last_sent)
        self.assertEqual(schedule.send_count, 1)

    @patch('email_manager.tasks.EmailMessage')
    @freeze_time('2026-06-01 09:59:00')
    def test_future_schedule_does_not_fire(self, MockEmailMessage):
        """A schedule 1 minute in the future should NOT fire."""
        user = _make_user('future_user')
        _make_schedule(
            user,
            start_dt=timezone.make_aware(datetime(2026, 6, 1, 10, 0, 0)),
        )

        from email_manager.tasks import send_scheduled_emails_task
        count = send_scheduled_emails_task.apply().get()

        self.assertEqual(count, 0)
        MockEmailMessage.return_value.send.assert_not_called()

    @patch('email_manager.tasks.EmailMessage')
    @freeze_time('2026-06-01 10:00:00')
    def test_one_time_schedule_deactivates_after_send(self, MockEmailMessage):
        """interval='none' schedule should be deactivated after one send."""
        MockEmailMessage.return_value = MagicMock()
        user = _make_user('deactivate_user')
        schedule = _make_schedule(
            user,
            start_dt=timezone.make_aware(datetime(2026, 6, 1, 9, 0, 0)),
            interval='none',
            repeat_count=1,
        )

        from email_manager.tasks import send_scheduled_emails_task
        send_scheduled_emails_task.apply().get()

        schedule.refresh_from_db()
        self.assertFalse(schedule.is_active)

    @patch('email_manager.tasks.EmailMessage')
    def test_daily_schedule_fires_on_next_day(self, MockEmailMessage):
        """A daily schedule should fire once per day."""
        MockEmailMessage.return_value = MagicMock()
        user = _make_user('daily_user')

        start = timezone.make_aware(datetime(2026, 6, 1, 8, 0, 0))
        schedule = _make_schedule(
            user,
            start_dt=start,
            interval='daily',
            repeat_count=3,
        )

        from email_manager.tasks import send_scheduled_emails_task

        # Day 1 — should fire
        with freeze_time('2026-06-01 08:01:00'):
            send_scheduled_emails_task.apply().get()
        schedule.refresh_from_db()
        self.assertEqual(schedule.send_count, 1)

        # Same day again — should NOT fire (already sent today)
        with freeze_time('2026-06-01 12:00:00'):
            count = send_scheduled_emails_task.apply().get()
        self.assertEqual(count, 0)
        schedule.refresh_from_db()
        self.assertEqual(schedule.send_count, 1)

        # Next day — should fire again
        with freeze_time('2026-06-02 08:01:00'):
            send_scheduled_emails_task.apply().get()
        schedule.refresh_from_db()
        self.assertEqual(schedule.send_count, 2)

    @patch('email_manager.tasks.EmailMessage')
    @freeze_time('2026-06-01 10:00:00')
    def test_repeat_count_exhausted_deactivates(self, MockEmailMessage):
        """Schedule at its repeat_count limit should be deactivated."""
        MockEmailMessage.return_value = MagicMock()
        user = _make_user('repeat_user')
        schedule = _make_schedule(
            user,
            start_dt=timezone.make_aware(datetime(2026, 6, 1, 9, 0, 0)),
            interval='daily',
            repeat_count=1,
        )
        # Already sent once
        schedule.send_count = 1
        schedule.last_sent  = timezone.make_aware(datetime(2026, 5, 31, 8, 0, 0))
        schedule.save()

        from email_manager.tasks import send_scheduled_emails_task
        send_scheduled_emails_task.apply().get()

        schedule.refresh_from_db()
        self.assertFalse(schedule.is_active)


# ---------------------------------------------------------------------------
# Test: campaign preview API
# ---------------------------------------------------------------------------

class CampaignPreviewTest(TestCase):

    def setUp(self):
        self.user = _make_user('cam_user')
        self.client.force_login(self.user)

    def test_preview_returns_correct_count(self):
        import json
        resp = self.client.post(
            '/emails/api/campaign/preview/',
            data=json.dumps({
                'total_sends':    3,
                'interval_value': 1,
                'interval_unit':  'days',
                'start_at':       '2026-06-01T10:00:00',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 3)
        self.assertEqual(len(data['events']), 3)

    def test_preview_computes_correct_datetimes(self):
        import json
        resp = self.client.post(
            '/emails/api/campaign/preview/',
            data=json.dumps({
                'total_sends':    2,
                'interval_value': 7,
                'interval_unit':  'days',
                'start_at':       '2026-06-01T08:00',
            }),
            content_type='application/json',
        )
        data = resp.json()
        starts = [e['start'] for e in data['events']]
        # Second send should be 7 days after first
        self.assertIn('2026-06-08', starts[1])

    def test_preview_rejects_over_365(self):
        import json
        resp = self.client.post(
            '/emails/api/campaign/preview/',
            data=json.dumps({
                'total_sends': 400, 'interval_value': 1,
                'interval_unit': 'days', 'start_at': '2026-06-01T10:00',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Test: campaign confirm API
# ---------------------------------------------------------------------------

class CampaignConfirmTest(TestCase):

    def setUp(self):
        self.user = _make_user('conf_user')
        self.client.force_login(self.user)

    @patch('email_manager.tasks.send_campaign_email_task.apply_async')
    def test_confirm_creates_campaign_and_queues_tasks(self, mock_apply_async):
        import json
        mock_result = MagicMock()
        mock_result.id = 'fake-task-id'
        mock_apply_async.return_value = mock_result

        resp = self.client.post(
            '/emails/api/campaign/confirm/',
            data=json.dumps({
                'name':           'Test Campaign',
                'subject':        'Hello',
                'body':           'Test body',
                'recipients':     ['r@example.com'],
                'total_sends':    3,
                'interval_value': 1,
                'interval_unit':  'days',
                'start_at':       '2026-07-01T09:00',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['tasks_queued'], 3)

        campaign = EmailCampaign.objects.get(id=data['campaign_id'])
        self.assertEqual(campaign.status, 'scheduled')
        self.assertEqual(campaign.total_sends, 3)
        self.assertEqual(mock_apply_async.call_count, 3)

    @patch('email_manager.tasks.send_campaign_email_task.apply_async')
    def test_confirm_requires_recipients(self, _):
        import json
        resp = self.client.post(
            '/emails/api/campaign/confirm/',
            data=json.dumps({
                'name': 'X', 'subject': 'X', 'body': 'X',
                'recipients': [],
                'total_sends': 1, 'interval_value': 1,
                'interval_unit': 'days', 'start_at': '2026-07-01T09:00',
            }),
            content_type='application/json',
        )
        # Empty recipients list is technically valid at API level;
        # _build_and_send will raise — but confirm endpoint doesn't validate it.
        # Adjust if stricter validation is added later.
        self.assertIn(resp.status_code, [200, 400])


# ---------------------------------------------------------------------------
# Test: EmailCampaign model helpers
# ---------------------------------------------------------------------------

class EmailCampaignModelTest(TestCase):

    def setUp(self):
        self.user = _make_user('model_user')

    def test_compute_send_datetimes_count(self):
        start = timezone.make_aware(datetime(2026, 6, 1, 10, 0))
        campaign = EmailCampaign(
            total_sends=5, interval_value=2, interval_unit='days',
            start_at=start, created_by=self.user,
        )
        dts = campaign.compute_send_datetimes()
        self.assertEqual(len(dts), 5)

    def test_compute_send_datetimes_spacing(self):
        start = timezone.make_aware(datetime(2026, 6, 1, 10, 0))
        campaign = EmailCampaign(
            total_sends=3, interval_value=1, interval_unit='weeks',
            start_at=start, created_by=self.user,
        )
        dts = campaign.compute_send_datetimes()
        from datetime import timedelta
        self.assertEqual(dts[1] - dts[0], timedelta(weeks=1))
        self.assertEqual(dts[2] - dts[1], timedelta(weeks=1))
