"""
dev_hub/tests.py

Unit tests for:
  1. Completion percentage calculation
  2. Task toggle view (status change, response shape)
  3. Notification routing (secretarial → redirect URL, non-secretarial → task queued)
  4. Weekly report task (only queued tasks included, flags cleared after send)
  5. ProgressReport model
"""
import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.utils import timezone

from dev_hub.models import AppModule, DevTask, TestCoverage, ProgressReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email='dev@example.com'):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u, _ = User.objects.get_or_create(
        email=email, defaults={'username': email.split('@')[0]},
    )
    u.set_password('pw')
    u.save()
    return u


def _make_module(name='Email Manager', status='in_dev'):
    return AppModule.objects.create(name=name, status=status, order=1)


def _make_task(module, title='Fix bug', task_type='bug', status='todo',
               notify=False, queue=False):
    return DevTask.objects.create(
        module=module, title=title, task_type=task_type,
        status=status, notify_on_complete=notify,
        queue_for_weekly_report=queue,
    )


# ---------------------------------------------------------------------------
# 1. Completion percentage
# ---------------------------------------------------------------------------

class CompletionPctTest(TestCase):

    def test_zero_when_no_tasks(self):
        m = _make_module('Empty Module')
        self.assertEqual(m.completion_pct, 0)

    def test_100_when_all_done(self):
        m = _make_module('All Done')
        _make_task(m, status='done')
        _make_task(m, status='done')
        self.assertEqual(m.completion_pct, 100)

    def test_50_when_half_done(self):
        m = _make_module('Half Done')
        _make_task(m, status='done')
        _make_task(m, status='todo')
        self.assertEqual(m.completion_pct, 50)

    def test_rounds_to_nearest_integer(self):
        m = _make_module('Rounding')
        # 2 done, 1 todo = 66.66... → 67
        _make_task(m, status='done')
        _make_task(m, status='done')
        _make_task(m, status='todo')
        self.assertEqual(m.completion_pct, 67)

    def test_task_counts(self):
        m = _make_module('Counts')
        _make_task(m, status='done')
        _make_task(m, status='in_progress')
        _make_task(m, status='todo')
        counts = m.task_counts
        self.assertEqual(counts['done'],        1)
        self.assertEqual(counts['in_progress'], 1)
        self.assertEqual(counts['todo'],        1)
        self.assertEqual(counts['total'],       3)

    def test_only_done_counts_toward_completion(self):
        m = _make_module('Only Done Counts')
        _make_task(m, status='in_progress')
        _make_task(m, status='in_progress')
        _make_task(m, status='done')
        # 1/3 = 33%
        self.assertEqual(m.completion_pct, 33)


# ---------------------------------------------------------------------------
# 2. Task toggle view
# ---------------------------------------------------------------------------

class TaskToggleViewTest(TestCase):

    def setUp(self):
        self.user   = _make_user()
        self.client = TestClient()
        self.client.force_login(self.user)
        self.module = _make_module()

    def test_toggle_todo_to_done(self):
        task = _make_task(self.module, status='todo')
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'done')
        self.assertEqual(data['action'], 'completed')

        task.refresh_from_db()
        self.assertEqual(task.status, 'done')
        self.assertIsNotNone(task.completed_at)

    def test_toggle_done_to_todo(self):
        task = _make_task(self.module, status='done')
        task.completed_at = timezone.now()
        task.save()

        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        resp = self.client.post(url)
        data = resp.json()
        self.assertEqual(data['status'], 'todo')
        self.assertEqual(data['action'], 'reverted')

        task.refresh_from_db()
        self.assertIsNone(task.completed_at)

    def test_toggle_updates_completion_pct(self):
        t1 = _make_task(self.module, status='done')
        t2 = _make_task(self.module, status='todo')
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': t2.id})
        resp = self.client.post(url)
        data = resp.json()
        self.assertEqual(data['completion_pct'], 100)

    def test_requires_login(self):
        c    = TestClient()  # not logged in
        task = _make_task(self.module)
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        resp = c.post(url)
        self.assertIn(resp.status_code, [302, 403])

    def test_returns_task_counts(self):
        t1 = _make_task(self.module, status='todo')
        _make_task(self.module, status='done')
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': t1.id})
        resp = self.client.post(url)
        data = resp.json()
        self.assertIn('task_counts', data)
        self.assertEqual(data['task_counts']['done'], 2)


# ---------------------------------------------------------------------------
# 3. Notification routing
# ---------------------------------------------------------------------------

class NotificationRoutingTest(TestCase):

    def setUp(self):
        self.user   = _make_user('notif@example.com')
        self.client = TestClient()
        self.client.force_login(self.user)
        self.module = _make_module()

    @patch('dev_hub.tasks.send_task_completion_email.delay')
    def test_non_secretarial_notify_queues_celery_task(self, mock_delay):
        task = _make_task(self.module, task_type='feature', notify=True, status='todo')
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        self.client.post(url)
        mock_delay.assert_called_once_with(str(task.id))

    @patch('dev_hub.tasks.send_task_completion_email.delay')
    def test_secretarial_task_returns_redirect_url(self, mock_delay):
        task = _make_task(self.module, task_type='secretarial', notify=True, status='todo')
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        resp = self.client.post(url)
        data = resp.json()
        # Should give redirect, NOT queue Celery
        self.assertIsNotNone(data['notify_redirect'])
        self.assertIn('/emails/', data['notify_redirect'])
        mock_delay.assert_not_called()

    @patch('dev_hub.tasks.send_task_completion_email.delay')
    def test_no_notify_flag_means_no_email(self, mock_delay):
        task = _make_task(self.module, task_type='feature', notify=False, status='todo')
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        self.client.post(url)
        mock_delay.assert_not_called()

    @patch('dev_hub.tasks.send_task_completion_email.delay')
    def test_reverting_done_task_does_not_send_email(self, mock_delay):
        task = _make_task(self.module, task_type='feature', notify=True, status='done')
        task.completed_at = timezone.now()
        task.save()
        url  = reverse('dev_hub:task_toggle', kwargs={'task_id': task.id})
        self.client.post(url)
        mock_delay.assert_not_called()

    def test_bug_and_test_types_are_non_secretarial(self):
        for t_type in ('bug', 'test', 'feature'):
            task = _make_task(self.module, task_type=t_type, notify=True, status='todo')
            self.assertFalse(task.is_secretarial)

    def test_secretarial_type_is_secretarial(self):
        task = _make_task(self.module, task_type='secretarial', notify=True)
        self.assertTrue(task.is_secretarial)


# ---------------------------------------------------------------------------
# 4. Weekly report Beat task
# ---------------------------------------------------------------------------

class WeeklyReportTaskTest(TestCase):

    def setUp(self):
        self.module = _make_module()

    @patch('dev_hub.tasks._create_sent_email')
    def test_skips_send_when_no_queued_tasks(self, mock_send):
        _make_task(self.module, queue=False)
        from dev_hub.tasks import send_weekly_progress_report
        result = send_weekly_progress_report.apply().get()
        self.assertEqual(result, 0)
        mock_send.assert_not_called()

    @patch('dev_hub.tasks._create_sent_email')
    def test_sends_when_queued_tasks_exist(self, mock_send):
        mock_sent = MagicMock()
        mock_sent.id = 'fake-id'
        mock_send.return_value = mock_sent

        t1 = _make_task(self.module, queue=True, status='done')
        t2 = _make_task(self.module, queue=True, status='done')

        from dev_hub.tasks import send_weekly_progress_report
        result = send_weekly_progress_report.apply().get()
        self.assertEqual(result, 2)
        mock_send.assert_called_once()

    @patch('dev_hub.tasks._create_sent_email')
    def test_clears_queue_flag_after_send(self, mock_send):
        mock_sent = MagicMock()
        mock_sent.id = 'fake-id'
        mock_send.return_value = mock_sent

        task = _make_task(self.module, queue=True, status='done')
        self.assertTrue(task.queue_for_weekly_report)

        from dev_hub.tasks import send_weekly_progress_report
        send_weekly_progress_report.apply().get()

        task.refresh_from_db()
        self.assertFalse(task.queue_for_weekly_report)

    @patch('dev_hub.tasks._create_sent_email')
    def test_creates_progress_report_record(self, mock_send):
        mock_sent = MagicMock()
        mock_sent.id = 'fake-id'
        mock_send.return_value = mock_sent

        _make_task(self.module, queue=True, status='done')

        from dev_hub.tasks import send_weekly_progress_report
        send_weekly_progress_report.apply().get()

        self.assertEqual(ProgressReport.objects.count(), 1)
        report = ProgressReport.objects.first()
        self.assertEqual(report.report_type, 'weekly')
        self.assertIsNotNone(report.modules_snapshot)

    @patch('dev_hub.tasks._create_sent_email')
    def test_snapshot_contains_all_modules(self, mock_send):
        mock_sent = MagicMock()
        mock_sent.id = 'fake-id'
        mock_send.return_value = mock_sent

        m2 = _make_module('Another Module')
        _make_task(self.module, queue=True, status='done')

        from dev_hub.tasks import send_weekly_progress_report
        send_weekly_progress_report.apply().get()

        report   = ProgressReport.objects.first()
        snapshot = report.modules_snapshot
        names    = [entry['name'] for entry in snapshot]
        self.assertIn(self.module.name, names)
        self.assertIn(m2.name, names)


# ---------------------------------------------------------------------------
# 5. AppModule model helpers
# ---------------------------------------------------------------------------

class AppModuleModelTest(TestCase):

    def test_slug_auto_generated(self):
        m = AppModule.objects.create(name='Email Manager Test')
        self.assertNotEqual(m.slug, '')
        self.assertIn('email', m.slug)

    def test_str(self):
        m = _make_module('Claims App')
        self.assertEqual(str(m), 'Claims App')

    def test_status_color(self):
        m = _make_module()
        m.status = 'stable'
        self.assertEqual(m.status_color, 'success')
        m.status = 'in_dev'
        self.assertEqual(m.status_color, 'secondary')

    def test_last_report_none_when_no_reports(self):
        m = _make_module()
        self.assertIsNone(m.last_report)
