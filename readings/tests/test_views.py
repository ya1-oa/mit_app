"""
Tests for readings app — reading browser and image upload.
"""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from docsAppR.models import ReadingImage

User = get_user_model()


class ReadingBrowserTests(TestCase):
    """Reading browser is public (no login required per original implementation)."""

    def setUp(self):
        self.http = Client()

    def test_browser_returns_200(self):
        response = self.http.get(reverse('reading_browser'))
        self.assertEqual(response.status_code, 200)

    def test_browser_context_has_images(self):
        response = self.http.get(reverse('reading_browser'))
        self.assertIn('images', response.context)

    def test_browser_shows_uploaded_images(self):
        ReadingImage.objects.create(
            filename='moisture_reading_001.jpg',
            claim='CLM-001',
            room='Master Bedroom',
        )
        response = self.http.get(reverse('reading_browser'))
        self.assertEqual(response.status_code, 200)
        # Should have 1 image in context
        self.assertEqual(len(response.context['images']), 1)


class ReadingUploadTests(TestCase):

    def setUp(self):
        self.http = Client()

    def test_upload_requires_post(self):
        response = self.http.get(reverse('upload_readings'))
        self.assertNotEqual(response.status_code, 200)

    def test_upload_valid_images(self):
        image = SimpleUploadedFile(
            'reading.jpg',
            b'\xff\xd8\xff\xe0',
            content_type='image/jpeg',
        )
        response = self.http.post(
            reverse('upload_readings'),
            {'images': image},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)

    def test_upload_no_files_returns_400_or_empty(self):
        response = self.http.post(reverse('upload_readings'), {})
        # Should handle gracefully — either 400 or empty success list
        self.assertIn(response.status_code, [200, 400])
