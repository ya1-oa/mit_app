"""
Tests for sensor_renamer.tasks — pure helper functions and Celery task logic.

These tests cover the business-critical parsing and filename-building logic
without hitting the Claude API or the filesystem.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import tempfile

from django.test import TestCase

from sensor_renamer.tasks import (
    _rf,
    _parse_response,
    _fv,
    result_has_na,
    build_filenames,
    safe_dest,
    SUB_RH, SUB_T, SUB_GPP, SUB_MC, SUB_NA,
    ALL_SUBFOLDERS,
    SUPPORTED_EXTS,
)


class ParseResponseTests(TestCase):
    """_parse_response converts raw Claude text into a structured dict."""

    def test_parses_mc_device(self):
        text = '{"type": "MC", "MC": 19.5}'
        result = _parse_response(text)
        self.assertEqual(result['device_type'], 'MC')
        self.assertEqual(result['MC'], 19.5)
        self.assertIsNone(result['RH'])

    def test_parses_rh_t_gpp_device(self):
        text = '{"type": "RH_T_GPP", "RH": 65.3, "T": 22.1, "GPP": 450.7}'
        result = _parse_response(text)
        self.assertEqual(result['device_type'], 'RH_T_GPP')
        self.assertEqual(result['RH'], 65.3)
        self.assertEqual(result['T'], 22.1)
        self.assertEqual(result['GPP'], 450.7)

    def test_strips_markdown_fences(self):
        text = '```json\n{"type": "MC", "MC": 8.3}\n```'
        result = _parse_response(text)
        self.assertEqual(result['device_type'], 'MC')
        self.assertEqual(result['MC'], 8.3)

    def test_mc_with_null_value(self):
        text = '{"type": "MC", "MC": null}'
        result = _parse_response(text)
        self.assertEqual(result['device_type'], 'MC')
        self.assertIsNone(result['MC'])

    def test_rh_t_gpp_with_partial_nulls(self):
        text = '{"type": "RH_T_GPP", "RH": 72.0, "T": null, "GPP": 310.5}'
        result = _parse_response(text)
        self.assertEqual(result['device_type'], 'RH_T_GPP')
        self.assertEqual(result['RH'], 72.0)
        self.assertIsNone(result['T'])
        self.assertEqual(result['GPP'], 310.5)

    def test_invalid_json_returns_unknown(self):
        result = _parse_response('not json at all')
        self.assertEqual(result['device_type'], 'unknown')
        self.assertIsNone(result['MC'])
        self.assertIsNone(result['RH'])

    def test_unknown_type_returns_unknown(self):
        text = '{"type": "THERMOSTAT", "value": 72}'
        result = _parse_response(text)
        self.assertEqual(result['device_type'], 'unknown')

    def test_rounds_to_one_decimal(self):
        text = '{"type": "MC", "MC": 19.567}'
        result = _parse_response(text)
        self.assertEqual(result['MC'], 19.6)


class ResultHasNaTests(TestCase):
    """result_has_na identifies incomplete readings that need manual review."""

    def test_mc_complete(self):
        result = {'device_type': 'MC', 'MC': 19.5, 'RH': None, 'T': None, 'GPP': None}
        self.assertFalse(result_has_na(result))

    def test_mc_null_value(self):
        result = {'device_type': 'MC', 'MC': None, 'RH': None, 'T': None, 'GPP': None}
        self.assertTrue(result_has_na(result))

    def test_rh_t_gpp_complete(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': 65.3, 'T': 22.1, 'GPP': 450.7}
        self.assertFalse(result_has_na(result))

    def test_rh_t_gpp_partial_null(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': 65.3, 'T': None, 'GPP': 450.7}
        self.assertTrue(result_has_na(result))

    def test_rh_t_gpp_all_null(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': None, 'T': None, 'GPP': None}
        self.assertTrue(result_has_na(result))

    def test_unknown_type_always_na(self):
        result = {'device_type': 'unknown', 'MC': None, 'RH': None, 'T': None, 'GPP': None}
        self.assertTrue(result_has_na(result))


class BuildFilenamesTests(TestCase):
    """build_filenames routes processed readings to the correct output sub-folders."""

    def test_complete_rh_t_gpp_creates_three_subfolders(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': 65.3, 'T': 22.1, 'GPP': 450.7}
        file_map = build_filenames(result, '.jpg')
        self.assertIn(SUB_RH, file_map)
        self.assertIn(SUB_T, file_map)
        self.assertIn(SUB_GPP, file_map)
        self.assertNotIn(SUB_NA, file_map)

    def test_rh_subfolder_filename_format(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': 65.3, 'T': 22.1, 'GPP': 450.7}
        file_map = build_filenames(result, '.jpg')
        self.assertEqual(file_map[SUB_RH], 'RH65.3_T22.1_GPP450.7.jpg')

    def test_t_subfolder_filename_format(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': 65.3, 'T': 22.1, 'GPP': 450.7}
        file_map = build_filenames(result, '.jpg')
        self.assertEqual(file_map[SUB_T], 'T22.1_RH65.3_GPP450.7.jpg')

    def test_gpp_subfolder_filename_format(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': 65.3, 'T': 22.1, 'GPP': 450.7}
        file_map = build_filenames(result, '.jpg')
        self.assertEqual(file_map[SUB_GPP], 'GPP450.7_RH65.3_T22.1.jpg')

    def test_complete_mc_creates_mc_subfolder(self):
        result = {'device_type': 'MC', 'MC': 19.5, 'RH': None, 'T': None, 'GPP': None}
        file_map = build_filenames(result, '.jpg')
        self.assertIn(SUB_MC, file_map)
        self.assertEqual(file_map[SUB_MC], 'MC19.5.jpg')

    def test_na_rh_t_gpp_routes_to_na_review(self):
        result = {'device_type': 'RH_T_GPP', 'MC': None, 'RH': None, 'T': 22.1, 'GPP': 450.7}
        file_map = build_filenames(result, '.jpg')
        self.assertIn(SUB_NA, file_map)
        self.assertNotIn(SUB_RH, file_map)

    def test_na_mc_routes_to_na_review(self):
        result = {'device_type': 'MC', 'MC': None, 'RH': None, 'T': None, 'GPP': None}
        file_map = build_filenames(result, '.jpg')
        self.assertIn(SUB_NA, file_map)
        self.assertNotIn(SUB_MC, file_map)

    def test_unknown_device_routes_to_na_review(self):
        result = {'device_type': 'unknown', 'MC': None, 'RH': None, 'T': None, 'GPP': None}
        file_map = build_filenames(result, '.png')
        self.assertIn(SUB_NA, file_map)
        self.assertIn('UNKNOWN', file_map[SUB_NA])

    def test_preserves_file_extension(self):
        result = {'device_type': 'MC', 'MC': 19.5, 'RH': None, 'T': None, 'GPP': None}
        file_map = build_filenames(result, '.png')
        self.assertTrue(file_map[SUB_MC].endswith('.png'))


class SafeDestTests(TestCase):
    """safe_dest avoids overwriting existing files with a numeric suffix."""

    def test_returns_original_when_no_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = safe_dest(Path(tmpdir), 'reading.jpg')
            self.assertEqual(dest.name, 'reading.jpg')

    def test_appends_suffix_when_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'reading.jpg').touch()
            dest = safe_dest(tmp, 'reading.jpg')
            self.assertEqual(dest.name, 'reading_2.jpg')

    def test_increments_suffix_for_multiple_conflicts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'reading.jpg').touch()
            (tmp / 'reading_2.jpg').touch()
            dest = safe_dest(tmp, 'reading.jpg')
            self.assertEqual(dest.name, 'reading_3.jpg')


class ConstantsTests(TestCase):
    """Verify module-level constants that templates and views depend on."""

    def test_all_subfolders_contains_expected_names(self):
        self.assertIn(SUB_RH, ALL_SUBFOLDERS)
        self.assertIn(SUB_T, ALL_SUBFOLDERS)
        self.assertIn(SUB_GPP, ALL_SUBFOLDERS)
        self.assertIn(SUB_MC, ALL_SUBFOLDERS)
        self.assertIn(SUB_NA, ALL_SUBFOLDERS)
        self.assertEqual(len(ALL_SUBFOLDERS), 5)

    def test_supported_exts_includes_common_formats(self):
        for ext in ('.jpg', '.jpeg', '.png'):
            self.assertIn(ext, SUPPORTED_EXTS)
