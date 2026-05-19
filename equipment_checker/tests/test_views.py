"""
Tests for equipment_checker views — HTTP layer, auth guards, and JSON contracts.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class EquipmentCheckerAuthTests(TestCase):
    """All equipment checker views require authentication."""

    def setUp(self):
        self.client = Client()

    def test_index_redirects_anonymous(self):
        response = self.client.get(reverse('equipment_checker'))
        self.assertEqual(response.status_code, 302)

    def test_upload_redirects_anonymous(self):
        response = self.client.post(reverse('equipment_upload'))
        self.assertEqual(response.status_code, 302)

    def test_status_redirects_anonymous(self):
        response = self.client.get(reverse('equipment_task_status'))
        self.assertEqual(response.status_code, 302)


class EquipmentCheckerViewTests(TestCase):
    """Authenticated request tests for the equipment checker."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='checker@example.com',
            password='testpass123',
        )
        self.client = Client()
        self.client.login(email='checker@example.com', password='testpass123')

    def test_index_returns_200(self):
        response = self.client.get(reverse('equipment_checker'))
        self.assertEqual(response.status_code, 200)

    def test_guide_returns_200(self):
        response = self.client.get(reverse('guide_equipment_checker'))
        self.assertEqual(response.status_code, 200)

    def test_status_missing_task_id_returns_400(self):
        response = self.client.get(reverse('equipment_task_status'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_upload_missing_line_items_returns_400(self):
        image = SimpleUploadedFile('photo.jpg', b'\xff\xd8\xff', content_type='image/jpeg')
        response = self.client.post(
            reverse('equipment_upload'),
            {'images': image},  # missing line_items
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_upload_missing_files_returns_400(self):
        response = self.client.post(
            reverse('equipment_upload'),
            {'line_items': 'Dehumidifier - LGR'},  # missing images and job_pdf
        )
        self.assertEqual(response.status_code, 400)

    @patch('equipment_checker.views.process_equipment_check_task')
    def test_upload_dispatches_task_with_image(self, mock_task):
        mock_async = MagicMock()
        mock_async.id = 'eq-task-id-123'
        mock_task.delay.return_value = mock_async

        image = SimpleUploadedFile('jobsite.jpg', b'\xff\xd8\xff', content_type='image/jpeg')
        response = self.client.post(
            reverse('equipment_upload'),
            {
                'images': image,
                'line_items': 'BATH DN | Vinyl tile\nHALL | Baseboard',
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('task_id', data)
        self.assertIn('session_id', data)
        self.assertEqual(data['item_count'], 2)
        mock_task.delay.assert_called_once()

    @patch('equipment_checker.views.process_equipment_check_task')
    def test_upload_skips_unsupported_image_formats(self, mock_task):
        mock_async = MagicMock()
        mock_async.id = 'eq-task-id'
        mock_task.delay.return_value = mock_async

        good = SimpleUploadedFile('photo.jpg', b'\xff\xd8\xff', content_type='image/jpeg')
        bad = SimpleUploadedFile('doc.docx', b'content', content_type='application/msword')
        response = self.client.post(
            reverse('equipment_upload'),
            {
                'images': [good, bad],
                'line_items': 'Some item',
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['skipped']), 1)
        self.assertEqual(data['skipped'][0], 'doc.docx')

    @patch('equipment_checker.views.AsyncResult')
    def test_status_pending_state(self, mock_async_result):
        mock_result = MagicMock()
        mock_result.state = 'PENDING'
        mock_async_result.return_value = mock_result

        response = self.client.get(reverse('equipment_task_status'), {'task_id': 'abc'})
        data = response.json()
        self.assertEqual(data['state'], 'PENDING')
        self.assertEqual(data['percent'], 0)

    @patch('equipment_checker.views.AsyncResult')
    def test_status_success_includes_result(self, mock_async_result):
        mock_result = MagicMock()
        mock_result.state = 'SUCCESS'
        mock_result.result = {
            'success': True,
            'found': 3,
            'partial': 1,
            'not_found': 0,
            'results': [],
        }
        mock_async_result.return_value = mock_result

        response = self.client.get(reverse('equipment_task_status'), {'task_id': 'abc'})
        data = response.json()
        self.assertEqual(data['state'], 'SUCCESS')
        self.assertIn('result', data)


class EquipmentExportCsvTests(TestCase):
    """CSV export produces correct headers and row data."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='csvuser@example.com',
            password='testpass123',
        )
        self.client = Client()
        self.client.login(email='csvuser@example.com', password='testpass123')

    def test_export_returns_csv_content_type(self):
        payload = {
            'results': [
                {'room': 'BATH', 'description': 'Vinyl', 'status': 'FOUND', 'note': 'Clear'},
            ]
        }
        response = self.client.post(
            reverse('equipment_export_csv'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('equipment_check.csv', response['Content-Disposition'])

    def test_export_csv_contains_header_row(self):
        payload = {'results': []}
        response = self.client.post(
            reverse('equipment_export_csv'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        content = response.content.decode('utf-8')
        self.assertIn('Room', content)
        self.assertIn('Status', content)
        self.assertIn('Verification Note', content)

    def test_export_csv_contains_data_rows(self):
        payload = {
            'results': [
                {'room': 'BATH DN', 'description': 'Vinyl tile', 'status': 'FOUND', 'note': 'Visible'},
                {'room': 'HALL', 'description': 'Baseboard', 'status': 'NOT FOUND', 'note': 'No photo'},
            ]
        }
        response = self.client.post(
            reverse('equipment_export_csv'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        content = response.content.decode('utf-8')
        self.assertIn('BATH DN', content)
        self.assertIn('NOT FOUND', content)

    def test_export_invalid_json_returns_400(self):
        response = self.client.post(
            reverse('equipment_export_csv'),
            data='not json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
