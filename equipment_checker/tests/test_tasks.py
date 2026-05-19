"""
Tests for equipment_checker.tasks — pure parsing helpers.

The Celery task itself hits Claude API + filesystem, so those paths
are tested via integration tests. This module covers the parsing and
data-transformation logic that can be unit-tested in isolation.
"""
from django.test import TestCase

from equipment_checker.tasks import _parse_items, _parse_response


class ParseItemsTests(TestCase):
    """_parse_items normalises raw line-item text from the upload form."""

    def test_simple_description_no_room(self):
        items = _parse_items(['Dehumidifier - LGR'])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['description'], 'Dehumidifier - LGR')
        self.assertEqual(items[0]['room'], '')

    def test_room_pipe_description_format(self):
        items = _parse_items(['BATH DN | Vinyl tile removal'])
        self.assertEqual(items[0]['room'], 'BATH DN')
        self.assertEqual(items[0]['description'], 'Vinyl tile removal')

    def test_multiple_items(self):
        raw = [
            'BATH DN | Vinyl tile removal',
            'HALL | Baseboard tearout',
            'Emergency service call',
        ]
        items = _parse_items(raw)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[2]['room'], '')
        self.assertEqual(items[2]['description'], 'Emergency service call')

    def test_skips_blank_lines(self):
        raw = ['Item A', '', '   ', 'Item B']
        items = _parse_items(raw)
        self.assertEqual(len(items), 2)

    def test_strips_whitespace_from_room_and_description(self):
        items = _parse_items(['  ROOM A  |  Some description  '])
        self.assertEqual(items[0]['room'], 'ROOM A')
        self.assertEqual(items[0]['description'], 'Some description')

    def test_pipe_in_description_keeps_first_split_only(self):
        items = _parse_items(['ROOM | Desc with | extra pipe'])
        self.assertEqual(items[0]['room'], 'ROOM')
        self.assertEqual(items[0]['description'], 'Desc with | extra pipe')

    def test_empty_list_returns_empty(self):
        self.assertEqual(_parse_items([]), [])


class ParseResponseTests(TestCase):
    """_parse_response converts raw Claude JSON text into a verified result list."""

    def test_parses_valid_json_array(self):
        text = '''[
            {"room": "BATH", "description": "Vinyl tile", "status": "FOUND", "note": "Visible"},
            {"room": "HALL", "description": "Baseboard", "status": "NOT FOUND", "note": "No photo"}
        ]'''
        results = _parse_response(text)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['status'], 'FOUND')
        self.assertEqual(results[1]['status'], 'NOT FOUND')

    def test_strips_markdown_fences(self):
        text = '```json\n[{"room": "A", "description": "B", "status": "FOUND", "note": ""}]\n```'
        results = _parse_response(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'FOUND')

    def test_extracts_array_from_noisy_text(self):
        text = 'Sure! Here is the result:\n[{"room": "X", "description": "Y", "status": "PARTIAL", "note": "Z"}]'
        results = _parse_response(text)
        self.assertEqual(len(results), 1)

    def test_invalid_json_returns_empty_list(self):
        results = _parse_response('This is not JSON.')
        self.assertEqual(results, [])

    def test_partial_status_preserved(self):
        text = '[{"room": "BATH", "description": "Vinyl", "status": "PARTIAL", "note": "Only 1 photo"}]'
        results = _parse_response(text)
        self.assertEqual(results[0]['status'], 'PARTIAL')

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(_parse_response(''), [])


class TaskConstantsTests(TestCase):
    """Verify module-level constants used in prompt templates."""

    def test_reference_pdf_path_attribute_exists(self):
        from equipment_checker.tasks import REFERENCE_PDF_PATH
        from pathlib import Path
        self.assertIsInstance(REFERENCE_PDF_PATH, Path)

    def test_supported_exts_includes_image_formats(self):
        from equipment_checker.tasks import SUPPORTED_EXTS
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            self.assertIn(ext, SUPPORTED_EXTS)

    def test_supported_exts_excludes_pdf(self):
        from equipment_checker.tasks import SUPPORTED_EXTS
        # PDFs are handled separately via job_pdf_path, not SUPPORTED_EXTS
        self.assertNotIn('.pdf', SUPPORTED_EXTS)
