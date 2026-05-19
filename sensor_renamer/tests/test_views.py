"""
Tests for sensor_renamer views — HTTP layer, auth guards, and response contracts.
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class SensorRenamerAuthTests(TestCase):
    """All sensor renamer views require authentication."""

    def setUp(self):
        self.client = Client()

    def test_index_redirects_anonymous(self):
        response = self.client.get(reverse('sensor_image_renamer'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/', response['Location'])

    def test_upload_redirects_anonymous(self):
        response = self.client.post(reverse('sensor_upload'))
        self.assertEqual(response.status_code, 302)

    def test_status_redirects_anonymous(self):
        response = self.client.get(reverse('sensor_task_status'))
        self.assertEqual(response.status_code, 302)


class SensorRenamerViewTests(TestCase):
    """Authenticated request tests for the sensor renamer pages."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='sensor@example.com',
            password='testpass123',
        )
        self.client = Client()
        self.client.login(email='sensor@example.com', password='testpass123')

    def test_index_returns_200(self):
        response = self.client.get(reverse('sensor_image_renamer'))
        self.assertEqual(response.status_code, 200)

    def test_index_passes_subfolders_context(self):
        response = self.client.get(reverse('sensor_image_renamer'))
        self.assertIn('subfolders', response.context)
        self.assertIn('sub_na', response.context)

    def test_guide_returns_200(self):
        response = self.client.get(reverse('guide_sensor_renamer'))
        self.assertEqual(response.status_code, 200)

    def test_status_missing_task_id_returns_400(self):
        response = self.client.get(reverse('sensor_task_status'))
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    @patch('sensor_renamer.views.process_sensor_images_task')
    def test_upload_accepts_valid_image(self, mock_task):
        mock_async = MagicMock()
        mock_async.id = 'fake-task-id-123'
        mock_task.delay.return_value = mock_async

        image = SimpleUploadedFile('sensor.jpg', b'\xff\xd8\xff', content_type='image/jpeg')
        response = self.client.post(
            reverse('sensor_upload'),
            {'images': image, 'model': 'claude-sonnet-4-6'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('task_id', data)
        self.assertIn('session_id', data)
        self.assertEqual(data['count'], 1)

    @patch('sensor_renamer.views.process_sensor_images_task')
    def test_upload_rejects_unsupported_extension(self, mock_task):
        mock_async = MagicMock()
        mock_async.id = 'fake-task-id'
        mock_task.delay.return_value = mock_async

        bad_file = SimpleUploadedFile('document.pdf', b'pdf content', content_type='application/pdf')
        response = self.client.post(reverse('sensor_upload'), {'images': bad_file})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    def test_upload_no_files_returns_400(self):
        response = self.client.post(reverse('sensor_upload'), {})
        self.assertEqual(response.status_code, 400)

    @patch('sensor_renamer.views.AsyncResult')
    def test_status_pending_task(self, mock_async_result):
        mock_result = MagicMock()
        mock_result.state = 'PENDING'
        mock_async_result.return_value = mock_result

        response = self.client.get(reverse('sensor_task_status'), {'task_id': 'abc123'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['state'], 'PENDING')

    @patch('sensor_renamer.views.AsyncResult')
    def test_status_success_task(self, mock_async_result):
        mock_result = MagicMock()
        mock_result.state = 'SUCCESS'
        mock_result.result = {'success': True, 'total': 5, 'results': []}
        mock_async_result.return_value = mock_result

        response = self.client.get(reverse('sensor_task_status'), {'task_id': 'abc123'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['state'], 'SUCCESS')
        self.assertIn('result', data)

    @patch('sensor_renamer.views.AsyncResult')
    def test_status_progress_includes_percent(self, mock_async_result):
        mock_result = MagicMock()
        mock_result.state = 'PROGRESS'
        mock_result.info = {'done': 3, 'total': 10, 'percent': 30, 'current_file': 'img3.jpg'}
        mock_async_result.return_value = mock_result

        response = self.client.get(reverse('sensor_task_status'), {'task_id': 'abc123'})
        data = response.json()
        self.assertEqual(data['percent'], 30)
        self.assertEqual(data['current_file'], 'img3.jpg')
