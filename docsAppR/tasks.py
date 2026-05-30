# docsAppR/tasks.py

import glob
import logging
import os
import sys
import tempfile
import shutil
import subprocess
import time
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import Client, ClaimFile
from .claim_folder_utils import (
    copy_templates_to_claim_folder,
    save_rooms_to_json,
    save_client_info_to_json,
    get_templates_folder,
    get_folder_structure,
    get_claims_root
)

logger = logging.getLogger(__name__)

# Platform detection
IS_WINDOWS = sys.platform.startswith('win')
IS_MAC = sys.platform.startswith('darwin')
IS_LINUX = sys.platform.startswith('linux')

# ---------------------------------------------------------------------------
# Population method selector
# Set EXCEL_POPULATE_METHOD in .env (or pass via the API) to override the
# automatic 3-tier fallback.
#   'auto' (default) — try UNO → LO subprocess → XML in order
#   'uno'            — UNO only (raises if unavailable)
#   'xml'            — XML only (fast, no LibreOffice needed)
# ---------------------------------------------------------------------------
EXCEL_POPULATE_METHOD = os.environ.get('EXCEL_POPULATE_METHOD', 'auto').lower()

# ==================== LIBREOFFICE UTILITIES ====================

def can_use_libreoffice():
    """Check if LibreOffice is available."""
    try:
        if IS_WINDOWS:
            possible_paths = [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ]
        elif IS_MAC:
            possible_paths = [
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin",
            ]
        else:  # Linux
            possible_paths = [
                "/usr/bin/libreoffice",
                "/usr/bin/soffice",
                "/usr/local/bin/libreoffice",
                "/opt/libreoffice/program/soffice",
            ]

        for path in possible_paths:
            if os.path.exists(path):
                return True

        # Try which/where command
        cmd = "where" if IS_WINDOWS else "which"
        try:
            result = subprocess.run([cmd, "libreoffice"],
                                  capture_output=True, text=True, shell=IS_WINDOWS)
            if result.returncode == 0:
                return True
            result = subprocess.run([cmd, "soffice"],
                                  capture_output=True, text=True, shell=IS_WINDOWS)
            if result.returncode == 0:
                return True
        except:
            pass

        return False
    except:
        return False

def get_libreoffice_path():
    """Get the path to LibreOffice executable."""
    if IS_WINDOWS:
        possible_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
    elif IS_MAC:
        possible_paths = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin",
        ]
    else:  # Linux
        possible_paths = [
            "/usr/bin/libreoffice",
            "/usr/bin/soffice",
            "/usr/local/bin/libreoffice",
            "/opt/libreoffice/program/soffice",
        ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # Try to find via command line
    try:
        cmd = "where" if IS_WINDOWS else "which"
        for prog in ["libreoffice", "soffice"]:
            result = subprocess.run([cmd, prog],
                                  capture_output=True, text=True, shell=IS_WINDOWS)
            if result.returncode == 0:
                return result.stdout.strip()
    except:
        pass

    return None

def _populate_jobinfo_via_libreoffice(filepaths_and_labels):
    """
    Write claim data into jobinfo(2) Column C using LibreOffice's own bundled
    Python subprocess — which already has 'uno' built in without needing the
    python3-uno system package.

    Zero ZIP surgery: LibreOffice opens the file natively, writes cells via
    UNO API, and saves. No ZIP rewriting = no repair prompts, no VBA corruption.

    Args:
        filepaths_and_labels: list of (filepath, {label: value_or_list, ...}) tuples

    Returns:
        dict: {filepath: cells_updated}  (cells_updated = -1 on per-file error)
    """
    import tempfile
    import json as _json

    # LibreOffice ships its own Python at this path with uno already importable
    lo_python_candidates = [
        '/usr/lib/libreoffice/program/python3',
        '/usr/lib/libreoffice/program/python',
        '/opt/libreoffice/program/python3',
    ]
    lo_python = next((p for p in lo_python_candidates if os.path.exists(p)), None)
    if not lo_python:
        raise RuntimeError("LibreOffice bundled Python not found — cannot populate without XML surgery")

    script_path = os.path.join(os.path.dirname(__file__), 'lo_populate.py')
    if not os.path.exists(script_path):
        raise RuntimeError(f"lo_populate.py not found at {script_path}")

    def _serialize(v):
        """Convert any value to JSON-serializable string or list of strings."""
        if isinstance(v, list):
            return [str(x) for x in v if x is not None]
        return str(v) if v is not None else ''

    payload = {
        'files': [
            {
                'path': fp,
                'labels': {k: _serialize(v) for k, v in lv.items()}
            }
            for fp, lv in filepaths_and_labels
        ]
    }

    # Write input JSON, derive output path
    with tempfile.NamedTemporaryFile(
            mode='w', suffix='_lo_in.json', delete=False, encoding='utf-8') as f:
        _json.dump(payload, f)
        input_path = f.name
    output_path = input_path.replace('_lo_in.json', '_lo_out.json')

    try:
        proc = subprocess.run(
            [lo_python, script_path, input_path, output_path],
            capture_output=True, text=True, timeout=180
        )
        if proc.returncode != 0:
            stderr_snippet = proc.stderr[-500:] if proc.stderr else '(no stderr)'
            raise RuntimeError(f"lo_populate.py exited {proc.returncode}: {stderr_snippet}")

        with open(output_path, encoding='utf-8') as f:
            results_list = _json.load(f)

        results = {}
        for r in results_list:
            fp = r['path']
            if r.get('success'):
                results[fp] = r['cells']
                logger.info(f"LO wrote {r['cells']} cells to {os.path.basename(fp)}")
            else:
                results[fp] = -1
                logger.error(f"LO failed on {os.path.basename(fp)}: {r.get('error', '?')}")
        return results

    finally:
        for p in (input_path, output_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def safe_strftime(date_obj, format_str):
    """Safe date formatting that works on both Windows and Linux."""
    try:
        if IS_WINDOWS:
            # Windows doesn't support %-d or %-m
            format_str = format_str.replace('%-d', '%#d').replace('%-m', '%#m')
        return date_obj.strftime(format_str) if date_obj else ''
    except Exception:
        return str(date_obj) if date_obj else ''

def _repair_workbook_xml(filepath):
    """
    Repair a potentially corrupted Excel file's workbook.xml.
    Previous runs may have inserted r:id attributes without declaring xmlns:r.
    """
    import zipfile, re

    filename = os.path.basename(filepath)

    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            if 'xl/workbook.xml' not in z.namelist():
                return
            wbxml = z.read('xl/workbook.xml').decode('utf-8')
    except Exception:
        return

    r_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    has_r_id = 'r:id=' in wbxml
    has_r_ns = f'xmlns:r="{r_ns}"' in wbxml or f"xmlns:r='{r_ns}'" in wbxml

    if not has_r_id or has_r_ns:
        return

    logger.info(f"Repairing broken xmlns:r in {filename}")
    wbxml_fixed = re.sub(r'(<workbook\b)', rf'\1 xmlns:r="{r_ns}"', wbxml, count=1)

    entries = {}
    with zipfile.ZipFile(filepath, 'r') as z:
        for name in z.namelist():
            entries[name] = z.read(name)
    entries['xl/workbook.xml'] = wbxml_fixed.encode('utf-8')

    temp_path = filepath + '.repair_tmp'
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for name, data in entries.items():
                z_out.writestr(name, data)
        os.replace(temp_path, filepath)
        logger.info(f"Repaired workbook.xml in {filename}")
    except Exception as e:
        logger.error(f"Failed to repair {filename}: {e}")
        try:
            os.unlink(temp_path)
        except OSError:
            pass


# ==================== XML CELL REGEX HELPERS ====================
#
# These helpers build correct regexes for matching OOXML cell elements.
# The key problems they solve:
#
# 1. Self-closing cells: <c r="C5" s="3"/>  (no children, no </c>)
#    vs full cells:      <c r="C5" t="s"><v>12</v></c>
#    The old regex [^/]* before (?:/>) could eat across multiple cells.
#
# 2. Namespace prefixes: When the worksheet uses a default namespace,
#    elements have NO prefix. But some files use x: prefix. The regex
#    must handle both, and we must write new elements with the SAME prefix.
#
# 3. Attribute order: r="C5" can appear anywhere in the <c> tag attributes.
#    We use \b word boundaries to avoid matching "AC5" or "BC5".

def _build_cell_re(ns_prefix, col_letter, row_num):
    """
    Build a compiled regex that matches a cell element for a specific column+row.
    Correctly handles both self-closing <c .../> and full <c ...>...</c> forms.

    Returns a compiled regex with DOTALL flag.
    """
    import re
    p = re.escape(ns_prefix)
    # Match: <(ns:)c ...r="COL_ROW"... /> OR <(ns:)c ...r="COL_ROW"...>...</(ns:)c>
    # Use a non-greedy match for attributes and content.
    # The key fix: for self-closing, [^>]*/> ensures we stop at the first >.
    # For full elements, we use .*? (non-greedy) between > and </c>.
    pattern = (
        r'<' + p + r'c\b(?=[^>]*\br="' + col_letter + str(row_num) + r'")'
        r'[^>]*'
        r'(?:/>|>.*?</' + p + r'c>)'
    )
    return re.compile(pattern, re.DOTALL)


def _build_row_re(ns_prefix):
    """
    Build a compiled regex that matches row elements.
    Handles both full <row ...>...</row> and self-closing <row .../> forms.

    Returns a compiled regex with DOTALL flag. Groups:
      1: row opening tag (including attributes)
      2: row number from r="N"
      3: row inner content (empty string for self-closing)
      4: row closing tag (empty string for self-closing)
    """
    import re
    p = re.escape(ns_prefix)
    # Two alternatives:
    #   Full:         (<row ...r="N"...>)(content)(</row>)
    #   Self-closing: (<row ...r="N".../>)  — groups 3,4 will be empty
    pattern = (
        r'(?:'
        # Full row element
        r'(<' + p + r'row\b[^>]*\br="(\d+)"[^>]*>)(.*?)(</' + p + r'row>)'
        r'|'
        # Self-closing row element (no content)
        r'(<' + p + r'row\b[^>]*\br="(\d+)"[^>]*/>' + r')'
        r')'
    )
    return re.compile(pattern, re.DOTALL)


def _iter_rows(sheet_xml, ns_prefix):
    """
    Iterate over row elements in sheet XML, yielding normalized tuples.

    Yields: (match_start, match_end, row_open, row_num, row_inner, row_close)
        - For full rows:  row_open = '<row ...>', row_inner = content, row_close = '</row>'
        - For self-closing: row_open = '', row_num, row_inner = '', row_close = ''
          (these rows have no cells so we skip them, but yield for completeness)
    """
    row_re = _build_row_re(ns_prefix)
    for m in row_re.finditer(sheet_xml):
        if m.group(1) is not None:
            # Full row: groups 1-4
            yield (m.start(), m.end(), m.group(1), int(m.group(2)), m.group(3), m.group(4))
        else:
            # Self-closing row: group 5,6
            yield (m.start(), m.end(), m.group(5), int(m.group(6)), '', '')


def _build_inline_str_cell(ns_prefix, col_letter, row_num, value_str):
    """
    Build an inline string cell element for Column C.

    CRITICAL: When the worksheet uses the default spreadsheetml namespace
    (ns_prefix == ''), the child elements <is> and <t> must also have NO prefix.
    When ns_prefix is e.g. 'x:', children must also use 'x:'.

    The cell type is t="inlineStr" which tells Excel to read the <is><t>
    child directly instead of looking up sharedStrings.xml.
    """
    escaped = (value_str
               .replace('&', '&amp;')
               .replace('<', '&lt;')
               .replace('>', '&gt;'))
    p = ns_prefix
    return (
        f'<{p}c r="{col_letter}{row_num}" t="inlineStr">'
        f'<{p}is><{p}t>{escaped}</{p}t></{p}is>'
        f'</{p}c>'
    )


def _build_formula_cell(ns_prefix, col_letter, row_num, formula_text, cached_value=''):
    """
    Build a formula cell element.

    For formulas that return strings (like our external references to jobinfo),
    we set t="str" so Excel knows the cached <v> is a string, not a number.
    If there's no cached value, we still include an empty <v></v> to avoid
    Excel complaining about missing value elements.
    """
    p = ns_prefix
    escaped_val = ''
    if cached_value:
        escaped_val = (str(cached_value)
                       .replace('&', '&amp;')
                       .replace('<', '&lt;')
                       .replace('>', '&gt;'))
    return (
        f'<{p}c r="{col_letter}{row_num}" t="str">'
        f'<{p}f>{formula_text}</{p}f>'
        f'<{p}v>{escaped_val}</{p}v>'
        f'</{p}c>'
    )


def _detect_ns_prefix(sheet_xml):
    """Detect the namespace prefix used for spreadsheetml elements."""
    import re
    ns_match = re.search(r'<(\w+:)?worksheet\b', sheet_xml)
    if ns_match and ns_match.group(1):
        return ns_match.group(1)
    return ''


# ==================== SHARED STRINGS AND CELL VALUE PARSING ====================

def _parse_shared_strings(ss_bytes):
    """Parse xl/sharedStrings.xml into a list of strings by index."""
    import re
    if not ss_bytes:
        return []
    text = ss_bytes.decode('utf-8')
    # Each <si> element is one shared string entry
    strings = []
    for si_match in re.finditer(r'<si[^>]*>(.*?)</si>', text, re.DOTALL):
        si_content = si_match.group(1)
        # Concatenate all <t> elements within the <si>
        parts = re.findall(r'<t[^>]*>([^<]*)</t>', si_content)
        strings.append(''.join(parts))
    return strings


def _get_cell_text(cell_xml, shared_strings, ns_prefix):
    """
    Extract the text value of a cell from its XML string.
    Handles shared strings (t="s"), inline strings (t="inlineStr"), and direct values.
    """
    import re
    cell_type = re.search(r'\bt="([^"]*)"', cell_xml)
    cell_type = cell_type.group(1) if cell_type else ''

    p = re.escape(ns_prefix)

    if cell_type == 's':
        # Shared string index
        v_match = re.search(r'<' + p + r'v>(\d+)</' + p + r'v>', cell_xml)
        if v_match:
            idx = int(v_match.group(1))
            return shared_strings[idx] if idx < len(shared_strings) else ''
    elif cell_type == 'inlineStr':
        # Inline string — look for <t> inside <is>
        t_match = re.search(r'<' + p + r't[^>]*>([^<]*)</', cell_xml)
        if t_match:
            return t_match.group(1)
    elif cell_type == 'str':
        # Formula string result — cached in <v>
        v_match = re.search(r'<' + p + r'v>([^<]*)</' + p + r'v>', cell_xml)
        if v_match:
            return v_match.group(1)
    else:
        v_match = re.search(r'<' + p + r'v>([^<]*)</' + p + r'v>', cell_xml)
        if v_match:
            return v_match.group(1)
    return ''


# ==================== WORKBOOK / SHEET NAVIGATION ====================

def _find_jobinfo_sheet_file(entries):
    """
    Given a dict of ZIP entries, find the worksheet file path for jobinfo(2)
    or jobinfo sheet. Returns (sheet_file_path, wbxml, rels_xml) or (None, ...).
    """
    import re

    wbxml = entries.get('xl/workbook.xml', b'').decode('utf-8')
    rels_xml = entries.get('xl/_rels/workbook.xml.rels', b'').decode('utf-8')

    sheet_rids = {}
    for m in re.finditer(r'<sheet\b([^>]*)/?>', wbxml):
        attrs = m.group(1)
        nm = re.search(r'name="([^"]+)"', attrs)
        rid = re.search(r'r:id="(rId\d+)"', attrs)
        if nm and rid:
            sheet_rids[nm.group(1)] = rid.group(1)

    rid_to_file = {}
    for m in re.finditer(r'<Relationship\b([^>]*)/?>', rels_xml):
        attrs = m.group(1)
        id_m = re.search(r'Id="(rId\d+)"', attrs)
        tgt = re.search(r'Target="(worksheets/[^"]+)"', attrs)
        if id_m and tgt:
            rid_to_file[id_m.group(1)] = tgt.group(1)

    for sn in ['jobinfo(2)', 'jobinfo']:
        if sn in sheet_rids and sheet_rids[sn] in rid_to_file:
            return 'xl/' + rid_to_file[sheet_rids[sn]], wbxml, rels_xml

    return None, wbxml, rels_xml


def _read_zip_preserving_compression(filepath):
    """
    Read an entire ZIP into memory, preserving per-entry ZipInfo metadata
    (compression type, extra fields, timestamps, external attributes).
    Returns (entries_dict, zip_infos_dict).
    """
    import zipfile
    entries = {}
    zip_infos = {}
    with zipfile.ZipFile(filepath, 'r') as z:
        for info in z.infolist():
            entries[info.filename] = z.read(info.filename)
            zip_infos[info.filename] = info
    return entries, zip_infos


def _write_zip_preserving_compression(filepath, entries, zip_infos):
    """
    Atomically write entries dict to a ZIP file, preserving per-entry ZipInfo
    metadata (compression, extra fields, timestamps). Uses temp + os.replace.
    """
    import zipfile
    temp_path = filepath + '.write_tmp'
    try:
        with zipfile.ZipFile(temp_path, 'w') as z_out:
            for name, data in entries.items():
                info = zip_infos.get(name)
                if info is not None:
                    # Write with full original metadata; Python recomputes CRC/sizes
                    z_out.writestr(info, data)
                else:
                    z_out.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        os.replace(temp_path, filepath)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


# ==================== CORE XML SURGERY FUNCTIONS ====================

def _read_info_data(info_filepath):
    """
    Read 01-INFO's jobinfo(2) sheet and return everything needed
    to set up references in other templates. PURE XML — no openpyxl.

    Returns:
        (sheet_names, cell_cache, label_to_row)
        - sheet_names: list of sheet names in the 01-INFO workbook
        - cell_cache: {row_num: value_string} for Column C values
        - label_to_row: {normalized_label: row_num} for Column B labels
    """
    import zipfile, re

    entries = {}
    with zipfile.ZipFile(info_filepath, 'r') as z:
        for name in z.namelist():
            entries[name] = z.read(name)

    wbxml = entries.get('xl/workbook.xml', b'').decode('utf-8')

    # Extract sheet names in document order
    sheet_names = re.findall(r'<sheet[^>]*name="([^"]+)"', wbxml)

    jobinfo_file, _, _ = _find_jobinfo_sheet_file(entries)

    cell_cache = {}
    label_to_row = {}

    if not jobinfo_file or jobinfo_file not in entries:
        return sheet_names, cell_cache, label_to_row

    sheet_xml = entries[jobinfo_file].decode('utf-8')
    shared_strings = _parse_shared_strings(entries.get('xl/sharedStrings.xml', b''))
    ns_prefix = _detect_ns_prefix(sheet_xml)

    for start, end, row_open, row_num, row_content, row_close in _iter_rows(sheet_xml, ns_prefix):
        if not row_content:
            continue  # self-closing row, no cells

        # Column B label
        b_re = _build_cell_re(ns_prefix, 'B', row_num)
        b_match = b_re.search(row_content)
        if b_match:
            label = _get_cell_text(b_match.group(0), shared_strings, ns_prefix)
            if label and label.strip():
                label_to_row[label.strip()] = row_num

        # Column C value
        c_re = _build_cell_re(ns_prefix, 'C', row_num)
        c_match = c_re.search(row_content)
        if c_match:
            val = _get_cell_text(c_match.group(0), shared_strings, ns_prefix)
            if val:
                cell_cache[row_num] = val

    return sheet_names, cell_cache, label_to_row


def _populate_jobinfo_via_xml(filepath, client):
    """
    Populate 01-INFO's jobinfo(2) sheet with raw client data.
    PURE ZIP SURGERY — no openpyxl = no corruption.

    Reads Column B labels via shared strings, matches against build_field_mapping(),
    writes values in Column C as inline strings (avoids sharedStrings.xml changes).
    Handles duplicate labels with ordered queues (same logic as old update_jobinfo_tab).

    Args:
        filepath: Path to the 01-INFO .xlsx file
        client: Client model instance

    Returns:
        int: Number of cells updated
    """
    import re
    from collections import deque

    filename = os.path.basename(filepath)

    entries, zip_infos = _read_zip_preserving_compression(filepath)

    jobinfo_file, wbxml, rels_xml = _find_jobinfo_sheet_file(entries)

    if not jobinfo_file or jobinfo_file not in entries:
        logger.warning(f"No jobinfo(2) sheet in {filename}")
        return 0

    sheet_xml = entries[jobinfo_file].decode('utf-8')
    shared_strings = _parse_shared_strings(entries.get('xl/sharedStrings.xml', b''))
    ns_prefix = _detect_ns_prefix(sheet_xml)

    # Build field mapping + duplicate queues
    field_mapping = build_field_mapping(client)
    normalized = {k.strip(): v for k, v in field_mapping.items()}
    dup_queues = {k: deque(v) for k, v in normalized.items() if isinstance(v, list)}

    # Parse merged cells — rows where Column C is an interior cell of a merge
    # must not receive a new <c> element or Excel will repair/clear the sheet.
    def _col_to_num(col_str):
        n = 0
        for ch in col_str.upper():
            n = n * 26 + (ord(ch) - 64)
        return n

    C_NUM = _col_to_num('C')
    merged_interior_rows = set()  # row numbers where writing a C cell would corrupt
    mc_block = re.search(r'<mergeCells[^>]*>(.*?)</mergeCells>', sheet_xml, re.DOTALL)
    if mc_block:
        for mc in re.finditer(r'ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"', mc_block.group(1)):
            sc, sr, ec, er = mc.group(1), int(mc.group(2)), mc.group(3), int(mc.group(4))
            sc_num, ec_num = _col_to_num(sc), _col_to_num(ec)
            if sc_num <= C_NUM <= ec_num:
                # C is inside this merge — interior rows (not the top-left) are off-limits
                first_writable = sr if sc_num == C_NUM else None
                for r in range(sr, er + 1):
                    if r != first_writable:
                        merged_interior_rows.add(r)

    # Pass 1: Scan rows top-to-bottom, determine replacements
    replacements = []  # [(match_start, match_end, new_full_row_xml)]
    cells_updated = 0

    for start, end, row_open, row_num, row_inner, row_close in _iter_rows(sheet_xml, ns_prefix):
        if row_num in merged_interior_rows:
            continue  # never write a C cell into a merged interior row
        if not row_inner:
            continue  # self-closing row, nothing to do

        # Remove any existing Column C cell (clear old data)
        c_re = _build_cell_re(ns_prefix, 'C', row_num)
        # If the existing C cell contains a formula (e.g. external link to 01-INFO),
        # leave this row completely untouched — deleting it causes Excel repair dialogs.
        c_match_existing = c_re.search(row_inner)
        if c_match_existing and re.search(r'<(?:\w+:)?f[\s>/]', c_match_existing.group(0)):
            continue
        new_inner = c_re.sub('', row_inner)

        # Read Column B label
        b_re = _build_cell_re(ns_prefix, 'B', row_num)
        b_match = b_re.search(new_inner)

        if not b_match:
            if new_inner != row_inner:
                replacements.append((start, end, row_open + new_inner + row_close))
            continue

        label = _get_cell_text(b_match.group(0), shared_strings, ns_prefix)
        if not label or not label.strip():
            if new_inner != row_inner:
                replacements.append((start, end, row_open + new_inner + row_close))
            continue

        label_stripped = label.strip()

        # Look up value in field mapping
        data_value = None
        if label_stripped in normalized:
            if label_stripped in dup_queues:
                q = dup_queues[label_stripped]
                if q:
                    data_value = q.popleft()
            else:
                data_value = normalized[label_stripped]

        if data_value is None or data_value == '' or str(data_value) == 'None':
            if new_inner != row_inner:
                replacements.append((start, end, row_open + new_inner + row_close))
            continue

        # Build new Column C cell as inline string
        new_c = _build_inline_str_cell(ns_prefix, 'C', row_num, str(data_value))

        # Insert C cell after B cell in the row
        b_in_new = b_re.search(new_inner)
        if b_in_new:
            pos = b_in_new.end()
            new_inner = new_inner[:pos] + new_c + new_inner[pos:]
        else:
            new_inner = new_inner + new_c

        replacements.append((start, end, row_open + new_inner + row_close))
        cells_updated += 1

    # Pass 2: Apply replacements bottom-to-top (avoids position shifts)
    for rstart, rend, new_text in reversed(replacements):
        sheet_xml = sheet_xml[:rstart] + new_text + sheet_xml[rend:]

    entries[jobinfo_file] = sheet_xml.encode('utf-8')

    # Write final ZIP — preserve original compression type per entry
    try:
        _write_zip_preserving_compression(filepath, entries, zip_infos)
        logger.info(f"Populated {filename}: {cells_updated} cells via XML")
    except Exception as e:
        logger.error(f"Failed to write {filename}: {e}")
        raise

    return cells_updated


def _read_jobinfo_cells(filepath):
    """
    Read all jobinfo(2) cells (Column B labels + Column C values) via pure XML.
    Used by data_check_audit to compare generated values against test inputs.

    Args:
        filepath: Path to an .xlsx or .xlsm file

    Returns:
        list of dicts: [{'row': int, 'label': str, 'value': str}, ...]
    """
    import zipfile

    entries = {}
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            for name in z.namelist():
                entries[name] = z.read(name)
    except Exception as e:
        logger.error(f"Cannot read {os.path.basename(filepath)}: {e}")
        return []

    jobinfo_file, _, _ = _find_jobinfo_sheet_file(entries)

    if not jobinfo_file or jobinfo_file not in entries:
        return []

    sheet_xml = entries[jobinfo_file].decode('utf-8')
    shared_strings = _parse_shared_strings(entries.get('xl/sharedStrings.xml', b''))
    ns_prefix = _detect_ns_prefix(sheet_xml)

    cells = []
    for start, end, row_open, row_num, row_content, row_close in _iter_rows(sheet_xml, ns_prefix):
        if not row_content:
            continue

        # Column B label
        label = ''
        b_re = _build_cell_re(ns_prefix, 'B', row_num)
        b_match = b_re.search(row_content)
        if b_match:
            label = _get_cell_text(b_match.group(0), shared_strings, ns_prefix)

        # Column C value
        value = ''
        c_re = _build_cell_re(ns_prefix, 'C', row_num)
        c_match = c_re.search(row_content)
        if c_match:
            value = _get_cell_text(c_match.group(0), shared_strings, ns_prefix)

        if label or value:
            cells.append({
                'row': row_num,
                'label': label.strip() if label else '',
                'value': value.strip() if value else '',
            })

    return cells


def _setup_template_references(filepath, info_filename, info_sheet_names, info_label_to_row, info_cell_cache):
    """
    Set up a non-01-INFO template with formulas referencing 01-INFO and
    fix external links. PURE ZIP SURGERY — no openpyxl = no corruption.

    This is the core function for the new paradigm:
    1. In jobinfo(2) Column C: writes formulas ='[1]jobinfo(2)'!C{row}
       with cached values so data displays even when 01-INFO isn't open
    2. In all worksheets: normalizes [N]jobinfo(2) → [1]jobinfo(2)
    3. Strips non-jobinfo external formulas (keeps cached <v>)
    4. Replaces external link files to point to correct local 01-INFO
       with full cell value cache for offline viewing
    5. Does NOT touch workbook.xml, workbook.xml.rels, or Content_Types
       (unless creating external link infrastructure from scratch)

    When user extracts ZIP and opens any template, Excel finds 01-INFO in
    same folder → formulas auto-resolve, cached values display immediately.
    """
    import zipfile, re

    filename = os.path.basename(filepath)

    entries = {}
    with zipfile.ZipFile(filepath, 'r') as z:
        for name in z.namelist():
            entries[name] = z.read(name)

    # --- Step 1: Find jobinfo(2) sheet file in this template ---
    jobinfo_file, wbxml, rels_xml = _find_jobinfo_sheet_file(entries)

    # --- Step 2: Clear ALL Column C cells, then write formulas for matched labels ---
    if jobinfo_file and jobinfo_file in entries:
        sheet_xml = entries[jobinfo_file].decode('utf-8')
        ns_prefix = _detect_ns_prefix(sheet_xml)
        shared_strings = _parse_shared_strings(entries.get('xl/sharedStrings.xml', b''))

        replacements = []
        formulas_written = 0

        for start, end, row_open, row_num, row_inner, row_close in _iter_rows(sheet_xml, ns_prefix):
            if not row_inner:
                continue  # self-closing row

            # ALWAYS remove existing Column C cell
            c_re = _build_cell_re(ns_prefix, 'C', row_num)
            new_inner = c_re.sub('', row_inner)

            # Read Column B label
            b_re = _build_cell_re(ns_prefix, 'B', row_num)
            b_match = b_re.search(new_inner)

            if not b_match:
                if new_inner != row_inner:
                    replacements.append((start, end, row_open + new_inner + row_close))
                continue

            label = _get_cell_text(b_match.group(0), shared_strings, ns_prefix)
            if not label or not label.strip():
                if new_inner != row_inner:
                    replacements.append((start, end, row_open + new_inner + row_close))
                continue

            info_row = info_label_to_row.get(label.strip())
            if info_row is None:
                if new_inner != row_inner:
                    replacements.append((start, end, row_open + new_inner + row_close))
                continue

            # Build formula with cached value
            cached_val = info_cell_cache.get(info_row, '')
            cached_str = str(cached_val) if cached_val is not None and str(cached_val).strip() else ''
            formula_text = f"&apos;[1]jobinfo(2)&apos;!C{info_row}"

            new_c = _build_formula_cell(ns_prefix, 'C', row_num, formula_text, cached_str)

            # Insert C cell after B cell
            b_in_new = b_re.search(new_inner)
            if b_in_new:
                pos = b_in_new.end()
                new_inner = new_inner[:pos] + new_c + new_inner[pos:]
            else:
                new_inner = new_inner + new_c

            replacements.append((start, end, row_open + new_inner + row_close))
            formulas_written += 1

        # Apply replacements bottom-to-top
        for rstart, rend, new_text in reversed(replacements):
            sheet_xml = sheet_xml[:rstart] + new_text + sheet_xml[rend:]

        entries[jobinfo_file] = sheet_xml.encode('utf-8')
        logger.info(f"Wrote {formulas_written} formulas in {filename} (cleared all Column C first)")

    # --- Step 3: Normalize [N]jobinfo(2) → [1]jobinfo(2) in ALL worksheets ---
    for name in list(entries.keys()):
        if not name.startswith('xl/worksheets/'):
            continue
        content = entries[name].decode('utf-8')
        original_content = content

        # Normalize external book references to jobinfo
        content = re.sub(r'\[(\d+)\](jobinfo(?:\(2\))?)', r'[1]\2', content)

        # Strip non-jobinfo external formulas (keep cached <v>)
        def strip_non_jobinfo(m):
            formula = m.group(1)
            if re.search(r'\[\d+\](?!jobinfo)', formula):
                return ''
            return m.group(0)
        content = re.sub(r'<f[^>]*>([^<]*\[\d+\][^<]*)</f>', strip_non_jobinfo, content)

        if content != original_content:
            entries[name] = content.encode('utf-8')

    # --- Step 4: Build and replace external link files ---
    # Use the spreadsheetml namespace for external link XML
    _ss_ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    _r_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

    jobinfo_idx = None
    for i, sn in enumerate(info_sheet_names):
        if sn in ('jobinfo(2)', 'jobinfo'):
            jobinfo_idx = i
            break

    sheet_names_xml = ''.join(
        f'<sheetName val="{sn.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}"/>'
        for sn in info_sheet_names
    )

    sheet_data_parts = []
    for i in range(len(info_sheet_names)):
        if i == jobinfo_idx and info_cell_cache:
            rows_xml = ''
            for row_num in sorted(info_cell_cache.keys()):
                val = info_cell_cache[row_num]
                if isinstance(val, str):
                    escaped = val.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                    rows_xml += f'<row r="{row_num}"><cell r="C{row_num}" t="str"><v>{escaped}</v></cell></row>'
                elif isinstance(val, (int, float)):
                    rows_xml += f'<row r="{row_num}"><cell r="C{row_num}"><v>{val}</v></cell></row>'
                else:
                    escaped = str(val).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    rows_xml += f'<row r="{row_num}"><cell r="C{row_num}" t="str"><v>{escaped}</v></cell></row>'
            sheet_data_parts.append(f'<sheetData sheetId="{i}">{rows_xml}</sheetData>')
        else:
            sheet_data_parts.append(f'<sheetData sheetId="{i}" refreshError="1"/>')

    ext_link_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<externalLink xmlns="{_ss_ns}"'
        f' xmlns:r="{_r_ns}">'
        '<externalBook r:id="rId1">'
        f'<sheetNames>{sheet_names_xml}</sheetNames>'
        f'<sheetDataSet>{"".join(sheet_data_parts)}</sheetDataSet>'
        '</externalBook></externalLink>'
    ).encode('utf-8')

    info_fn_escaped = info_filename.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')
    ext_link_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1"'
        f' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLinkPath"'
        f' Target="{info_fn_escaped}" TargetMode="External"/>'
        '</Relationships>'
    ).encode('utf-8')

    # Replace ALL existing external link files
    existing_ext_links = sorted([n for n in entries if re.match(r'^xl/externalLinks/externalLink\d+\.xml$', n)])
    existing_ext_rels = sorted([n for n in entries if re.match(r'^xl/externalLinks/_rels/externalLink\d+\.xml\.rels$', n)])

    if existing_ext_links:
        for link_name in existing_ext_links:
            entries[link_name] = ext_link_xml
        for rels_name in existing_ext_rels:
            entries[rels_name] = ext_link_rels_xml
        for link_name in existing_ext_links:
            rels_name = link_name.replace('xl/externalLinks/', 'xl/externalLinks/_rels/') + '.rels'
            if rels_name not in entries:
                entries[rels_name] = ext_link_rels_xml
    else:
        # --- CREATE external link infrastructure from scratch ---
        logger.info(f"Creating external link infrastructure for {filename}")

        # 1) Add the external link file and its rels
        entries['xl/externalLinks/externalLink1.xml'] = ext_link_xml
        entries['xl/externalLinks/_rels/externalLink1.xml.rels'] = ext_link_rels_xml

        # 2) Add relationship to workbook.xml.rels — find next available rId
        existing_rids = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels_xml)]
        next_rid = max(existing_rids) + 1 if existing_rids else 1
        new_rel = (
            f'<Relationship Id="rId{next_rid}"'
            f' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink"'
            f' Target="externalLinks/externalLink1.xml"/>'
        )
        rels_xml = rels_xml.replace('</Relationships>', new_rel + '</Relationships>')
        entries['xl/_rels/workbook.xml.rels'] = rels_xml.encode('utf-8')

        # 3) Add <externalReference> to workbook.xml
        # Ensure xmlns:r is declared on <workbook> for the r:id attribute
        r_ns_decl = f'xmlns:r="{_r_ns}"'
        if r_ns_decl not in wbxml and "xmlns:r=" not in wbxml:
            wbxml = re.sub(r'(<workbook\b)', rf'\1 {r_ns_decl}', wbxml, count=1)

        ext_ref_tag = f'<externalReference r:id="rId{next_rid}"/>'
        ext_refs_block = '<externalReferences>' + ext_ref_tag + '</externalReferences>'
        if '<externalReferences>' in wbxml:
            wbxml = wbxml.replace('</externalReferences>',
                                  ext_ref_tag + '</externalReferences>')
        elif '<extLst>' in wbxml:
            wbxml = wbxml.replace('<extLst>', ext_refs_block + '<extLst>')
        else:
            wbxml = wbxml.replace('</workbook>', ext_refs_block + '</workbook>')
        entries['xl/workbook.xml'] = wbxml.encode('utf-8')

        # 4) Add content type for the external link
        ct_xml = entries.get('[Content_Types].xml', b'').decode('utf-8')
        ext_link_ct = (
            '<Override PartName="/xl/externalLinks/externalLink1.xml"'
            ' ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml"/>'
        )
        if 'externalLink1.xml' not in ct_xml:
            ct_xml = ct_xml.replace('</Types>', ext_link_ct + '</Types>')
            entries['[Content_Types].xml'] = ct_xml.encode('utf-8')

        logger.info(f"Created external link infrastructure in {filename} (rId{next_rid})")

    # --- Step 5: Write final ZIP ---
    temp_path = filepath + '.ref_setup_tmp'
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for name, data in entries.items():
                z_out.writestr(name, data)
        os.replace(temp_path, filepath)
        logger.info(f"Set up template references in {filename} → {info_filename}")
    except Exception as e:
        logger.error(f"Failed to set up references in {filename}: {e}")
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _strip_external_links(filepath):
    """
    Remove external link metadata from an Excel file.
    Only removes: externalLinks/ files, workbook.xml references,
    rels entries, and content type entries.

    Does NOT touch worksheet XML at all — avoids corruption risk.
    """
    import zipfile, re

    filename = os.path.basename(filepath)

    entries = {}
    with zipfile.ZipFile(filepath, 'r') as z:
        for name in z.namelist():
            entries[name] = z.read(name)

    # Check if there are external links to strip
    ext_link_files = [n for n in entries if n.startswith('xl/externalLinks/')]
    if not ext_link_files:
        return

    # Remove external link files
    for name in ext_link_files:
        del entries[name]

    # Remove <externalReferences> from workbook.xml
    wbxml = entries.get('xl/workbook.xml', b'').decode('utf-8')
    wbxml = re.sub(r'<externalReferences>.*?</externalReferences>', '', wbxml, flags=re.DOTALL)
    entries['xl/workbook.xml'] = wbxml.encode('utf-8')

    # Remove externalLink relationships from workbook.xml.rels
    rels_xml = entries.get('xl/_rels/workbook.xml.rels', b'').decode('utf-8')
    rels_xml = re.sub(r'<Relationship[^>]*Type="[^"]*externalLink[^"]*"[^>]*/?>',
                      '', rels_xml)
    entries['xl/_rels/workbook.xml.rels'] = rels_xml.encode('utf-8')

    # Remove external link content types
    ct_xml = entries.get('[Content_Types].xml', b'').decode('utf-8')
    ct_xml = re.sub(r'<Override[^>]*externalLink[^>]*/>', '', ct_xml)
    entries['[Content_Types].xml'] = ct_xml.encode('utf-8')

    # Write cleaned ZIP
    temp_path = filepath + '.strip_tmp'
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for name, data in entries.items():
                z_out.writestr(name, data)
        os.replace(temp_path, filepath)
        logger.info(f"Stripped {len(ext_link_files)} external link files from {filename}")
    except Exception as e:
        logger.error(f"Failed to strip external links from {filename}: {e}")
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def update_excel_with_libreoffice(filepath, client):
    """
    Populate a template's jobinfo(2) with raw client data via pure XML/ZIP surgery.
    """
    filename = os.path.basename(filepath)
    logger.info(f"Populating 01-INFO template: {filename}")

    try:
        cells_updated = _populate_jobinfo_via_xml(filepath, client)
        logger.info(f"Successfully populated {filename} with {cells_updated} cells")
        return {'success': True, 'updated_cells': cells_updated}
    except Exception as e:
        logger.error(f"Error updating {filename}: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}


def build_field_mapping(client):
    """
    Build complete field mapping from client data.
    Maps Excel label text (Column B) to the client field value for Column C.
    Includes ALL sections: customer, claim, insurance, mortgage, contractor,
    ALE (lessee, lessor, rental, RE company), rooms with work types, and more.
    """
    field_mapping = {}

    # Field definitions: Excel label → Client model field name
    field_definitions = {
        # ===== CUSTOMER / PROPERTY OWNER =====
        'Property-Owner Name': 'pOwner',
        'Property address: street': 'pAddress',
        # NOTE: 'Property city, state, zip' and 'Customer Email' appear in BOTH customer
        # and ALE sections - handled as ordered duplicates below
        'Cst-owner Phone#': 'cPhone',
        'Co-Owner.cst#2': 'coOwner2',
        'cst ph # 2': 'cPhone2',
        'Cst address # 2': 'cAddress2',
        'city, state-cst#2': 'cCityStateZip2',
        'email-cst #2': 'cEmail2',

        # ===== LOSS / CLAIM INFO =====
        'Cause of Loss': 'causeOfLoss',
        'rebuild  type 1': 'rebuildType1',
        'rebuild  type 2': 'rebuildType2',
        'rebuild  type 3': 'rebuildType3',
        'Year Built': 'yearBuilt',
        'Breathing issue': 'breathingIssue',
        'HMR': 'hazardMaterialRemediation',

        # ===== INSURANCE COMPANY =====
        'Insurance Co. Name': 'insuranceCo_Name',
        'Claim #': 'claimNumber',
        'policy #': 'policyNumber',
        'Email INS. co.': 'emailInsCo',
        'DESK Adjuster DA': 'deskAdjusterDA',
        'DA Phone': 'DAPhone',
        'DA Ph. Ext. #': 'DAPhExt',
        'DA Email': 'DAEmail',
        'Field Adjuster Name': 'fieldAdjusterName',
        'Phone # field adj': 'phoneFieldAdj',
        'Field adj email': 'fieldAdjEmail',
        'adj contents': 'adjContents',
        'adj CPS phone #': 'adjCpsPhone',
        'adj CPS email': 'adjCpsEmail',
        'TMP adj': 'emsAdj',
        'TMP adj phone #': 'emsAdjPhone',
        'adj TMP email': 'emsTmpEmail',
        'ATT: Loss Draft Dept.': 'attLossDraftDept',
        'address ins overnight mail': 'insAddressOvernightMail',
        'city, state-zip ins': 'insCityStateZip',
        'Insurance Co. Phone': 'insuranceCoPhone',
        'Website Ins Co.': 'insWebsite',
        'Mailing   address INS': 'insMailingAddress',
        'Mail city, state, zip INS': 'insMailCityStateZip',
        'FAX Ins. Co': 'fax_ins_co',
        'NEW CUSTOMER #': 'newCustomerID',
        'ROOM ID': 'roomID',

        # ===== MORTGAGE COMPANY =====
        'Mortgage co': 'mortgageCo',
        'Account# Mtge Co.': 'mortgageAccountCo',
        'Loan status': 'loanStatus',
        'contact person mtge': 'mortgageContactPerson',
        'Phone # MTGE contact': 'mortgagePhoneContact',
        'Ph. Ext. Mtge contact': 'mortgagePhoneExtContact',
        'Attn.: Loss Draft Dept': 'mortgageAttnLossDraftDept',
        'Mtge OVN mail': 'mortgageOverNightMail',
        'city, St., zip ,mtge OVN': 'mortgageCityStZipOVN',
        'Phone # MTGE co.': 'phone_mtge_co',
        'email mtge': 'mortgageEmail',
        'mtge website': 'mortgageWebsite',
        'MTGE co. Fax #': 'mortgageCoFax',
        'Mailing   address mtge': 'mortgageMailingAddress',
        'Mail city, state, zip mtge': 'mortgageCityStZip',
        'Initial Offer / phase 1 contract amount': 'mortgageInitialOfferPhase1ContractAmount',
        'Draw Request': 'drawRequest',

        # ===== CONTRACTOR / COMPANY =====
        'co name': 'coName',
        'Co. website': 'coWebsite',
        'co. EMAIL/co. status': 'coEmailstatus',
        'co address': 'coAddress',
        'co adress': 'coAddress',       # alternate spelling in some templates
        'co. city state': 'coCityState',
        'co. address 2': 'coAddress2',
        'co. city state 2': 'coCityState2',
        'co address 3': 'coCityState3',
        'co adress 3': 'coCityState3',   # alternate spelling in some templates
        'co. city state 3': 'coCityState3',
        'Co. logo 1': 'coLogo1',
        'Co. logo 2': 'coLogo2',
        'Co. logo 3': 'coLogo3',
        'Co. REP. / PH': 'coRepPH',
        'CO.REP.\nemail': 'coREPEmail',
        'Co PH # 2': 'coPhone2',
        'CO.REP. email 2': 'coREPEmail',
        'TIN W9': 'TinW9',
        'FedEx     account #': 'fedExAccount',

        # ===== CLAIM REPORTING =====
        'claim report date': 'claimReportDate',
        'Time OF CLAIM REPORT': 'timeOfClaimReport',
        'co.represesntative': 'insuranceCustomerServiceRep',
        'insurance customer service rep': 'insuranceCustomerServiceRep',
        'phone ext.': 'phoneExt',
        'phone ext': 'phoneExt',         # variant without period
        'Tarp ext. TMP ok': 'tarpExtTMPOk',
        'Tarp ext TMP ok': 'tarpExtTMPOk',  # variant without period
        'Int TMP ok': 'IntTMPOk',
        'DRY/PLA CUTOUT MOLD SPRAY  OK': 'DRYPLACUTOUTMOLDSPRAYOK',

        # ===== ALE - LESSEE / TENANT INFO =====
        'Lesse info / NAME': 'ale_lessee_name',
        'tenant lesee': 'ale_lessee_name',    # alternate label in some templates
        'HOME ADDRESS': 'ale_lessee_home_address',
        'Lessee city, state, zip': 'ale_lessee_city_state_zip',
        'Lessee Email': 'ale_lessee_email',
        'Lessee Phone#': 'ale_lessee_phone',
        'Customer Phone#': 'ale_lessee_phone',  # used in 30-MASTER ALE section

        # ===== ALE - RENTAL INFO =====
        'bedrooms': 'ale_rental_bedrooms',
        'BEDROOMS=': 'ale_rental_bedrooms',
        'months': 'ale_rental_months',
        'Amount / Month': 'ale_rental_amount_per_month',
        'TERMS $ AMOUNT': 'ale_rental_amount_per_month',

        # ===== ALE - LESSOR INFO =====
        'LESSOR': 'ale_lessor_name',
        'LESSOR INFO / NAME': 'ale_lessor_name',
        'Leased Address': 'ale_lessor_leased_address',
        'Lessor phone #': 'ale_lessor_phone',
        'Email lessor': 'ale_lessor_email',
        'Lessor Email': 'ale_lessor_email',
        'Lessor mailing Address': 'ale_lessor_mailing_address',
        'Lessor mailing city zip': 'ale_lessor_mailing_city_zip',
        'LESSOR CONTACT PERSON': 'ale_lessor_contact_person',

        # ===== ALE - REAL ESTATE COMPANY =====
        'RE MAILING ADDRESS': 'ale_re_mailing_address',
        'MAILING ADDRESS': 'ale_re_mailing_address',
        'RE city zip': 'ale_re_city_zip',
        'RE CONTACT': 'ale_re_contact_person',
        'CONTACT': 'ale_re_contact_person',
        'RE Email': 'ale_re_email',
        'RE phone #': 'ale_re_phone',
        'OWNER/BROKER': 'ale_re_owner_broker_name',
        'OWNER/BROKER phone #': 'ale_re_owner_broker_phone',
        'OWNER/BROKER Email': 'ale_re_owner_broker_email',
    }

    # Get field values
    def get_field_value(field_name):
        try:
            value = getattr(client, field_name, '')
            return str(value) if value else ''
        except:
            return ''

    # Add all text fields
    for excel_label, model_field in field_definitions.items():
        field_mapping[excel_label] = get_field_value(model_field)

    # Cust id = folder-name format (pOwner@pAddress), not the integer DB id
    owner = getattr(client, 'pOwner', '') or ''
    addr = getattr(client, 'pAddress', '') or ''
    field_mapping['Cust id'] = f"{owner}@{addr}" if owner or addr else ''

    # Add date fields
    if client.dateOfLoss:
        field_mapping['date of loss'] = safe_strftime(client.dateOfLoss, '%A, %B %d, %Y')
    if client.contractDate:
        field_mapping['Contract Date'] = safe_strftime(client.contractDate, '%Y-%m-%d')
    if client.claimReportDate:
        field_mapping['claim report date'] = safe_strftime(client.claimReportDate, '%Y-%m-%d')
    if client.ale_rental_start_date:
        field_mapping['START DATE'] = safe_strftime(client.ale_rental_start_date, '%A, %B %d, %Y')
    if client.ale_rental_end_date:
        field_mapping['END DATE'] = safe_strftime(client.ale_rental_end_date, '%A, %B %d, %Y')

    # Add boolean fields
    field_mapping['DEMO'] = 'Y' if getattr(client, 'demo', False) else 'N'
    field_mapping['Mitigation'] = 'Y' if getattr(client, 'mitigation', False) else 'N'
    field_mapping['Other Structures'] = 'Y' if getattr(client, 'otherStructures', False) else 'NA'
    field_mapping['Replacement'] = 'Y' if getattr(client, 'replacement', False) else 'N'
    field_mapping['CPS / CLN / CON/ CGN'] = 'Y' if getattr(client, 'CPSCLNCONCGN', False) else 'N'
    field_mapping['Loss of use/ ALE'] = 'Y' if getattr(client, 'lossOfUseALE', '') == 'Y' else ('TBD' if getattr(client, 'lossOfUseALE', '') == 'TBD' else 'N')

    # Add room data - support ALL label formats found across templates
    rooms = client.rooms.filter(is_encircle_entry=False).prefetch_related('work_type_values__work_type').order_by('sequence')
    for idx, room in enumerate(rooms, 1):
        if idx <= 25:
            # Format 1: Room/Area 1, Room/Area 2, etc. (30-MASTER, 50-CONTRACT, etc.)
            field_mapping[f"Room/Area {idx}"] = room.room_name
            # Format 2: Room/Area 101, Room/Area 102, etc. (01-INFO, 01-ROOMS templates)
            field_mapping[f"Room/Area {100 + idx}"] = room.room_name
            # Format 3: Just the number for ROOMS# sheet
            field_mapping[str(idx)] = room.room_name

            # Add work type values for each room (LOS, TRAVEL, NA, TBD)
            for wt_value in room.work_type_values.all():
                wt_id = wt_value.work_type.work_type_id
                value = wt_value.value_type or 'NA'
                field_mapping[f"Room {idx} WT{wt_id}"] = value
                field_mapping[f"Room/Area {idx} WT{wt_id}"] = value

    # ===== ORDERED DUPLICATE LABELS =====
    field_mapping['Property city, state, zip'] = [
        get_field_value('pCityStateZip'),
        get_field_value('ale_lessee_city_state_zip'),
    ]
    field_mapping['Customer Email'] = [
        get_field_value('cEmail'),
        get_field_value('ale_lessee_email'),
    ]
    field_mapping['city zip'] = [
        get_field_value('ale_lessor_city_zip'),
        get_field_value('ale_lessor_mailing_city_zip'),
        get_field_value('ale_re_city_zip'),
    ]
    field_mapping['phone #'] = [
        get_field_value('ale_lessor_phone'),
        get_field_value('ale_re_phone'),
        get_field_value('ale_re_owner_broker_phone'),
    ]
    field_mapping['Email'] = [
        get_field_value('ale_re_email'),
        get_field_value('ale_re_owner_broker_email'),
    ]

    return field_mapping

def create_libreoffice_macro_content(client):
    """Create LibreOffice Python macro content."""
    # Build field mapping
    field_mapping = {}

    # Helper function to get field value
    def get_field_value(field_name, default=''):
        try:
            value = getattr(client, field_name, default)
            if value is None:
                return default
            return str(value)
        except:
            return default

    # Add all fields - exact Excel labels mapped to Client model fields
    field_definitions = {
        'Property-Owner Name': 'pOwner',
        'Property address: street': 'pAddress',
        'Property city, state, zip': 'pCityStateZip',
        'Customer Email': 'cEmail',
        'Cst-owner Phone#': 'cPhone',
        'Co-Owner.cst#2': 'coOwner2',
        'cst ph # 2': 'cPhone2',
        'Cst address # 2': 'cAddress2',
        'city, state-cst#2': 'cCityStateZip2',
        'email-cst #2': 'cEmail2',
        'Cause of Loss': 'causeOfLoss',
        'rebuild  type 1': 'rebuildType1',
        'rebuild  type 2': 'rebuildType2',
        'rebuild  type 3': 'rebuildType3',
        'Year Built': 'yearBuilt',
        'Cust id': 'id',
        'Breathing issue': 'breathingIssue',
        'HMR': 'hazardMaterialRemediation',
        'Insurance Co. Name': 'insuranceCo_Name',
        'Claim #': 'claimNumber',
        'policy #': 'policyNumber',
        'Email INS. co.': 'emailInsCo',
        'DESK Adjuster DA': 'deskAdjusterDA',
        'DA Phone': 'DAPhone',
        'DA Ph. Ext. #': 'DAPhExt',
        'DA Email': 'DAEmail',
        'Field Adjuster Name': 'fieldAdjusterName',
        'Phone # field adj': 'phoneFieldAdj',
        'Field adj email': 'fieldAdjEmail',
        'adj contents': 'adjContents',
        'adj CPS phone #': 'adjCpsPhone',
        'adj CPS email': 'adjCpsEmail',
        'TMP adj': 'emsAdj',
        'TMP adj phone #': 'emsAdjPhone',
        'adj TMP email': 'emsTmpEmail',
        'ATT: Loss Draft Dept.': 'attLossDraftDept',
        'address ins overnight mail': 'insAddressOvernightMail',
        'city, state-zip ins': 'insCityStateZip',
        'Insurance Co. Phone': 'insuranceCoPhone',
        'Website Ins Co.': 'insWebsite',
        'Mailing   address INS': 'insMailingAddress',
        'Mail city, state, zip INS': 'insMailCityStateZip',
        'FAX Ins. Co': 'fax_ins_co',
        'NEW CUSTOMER #': 'newCustomerID',
        'ROOM ID': 'roomID',
        'Mortgage co': 'mortgageCo',
        'Account# Mtge Co.': 'mortgageAccountCo',
        'Loan status': 'loanStatus',
        'contact person mtge': 'mortgageContactPerson',
        'Phone # MTGE contact': 'mortgagePhoneContact',
        'Ph. Ext. Mtge contact': 'mortgagePhoneExtContact',
        'Attn.: Loss Draft Dept': 'mortgageAttnLossDraftDept',
        'Mtge OVN mail': 'mortgageOverNightMail',
        'city, St., zip ,mtge OVN': 'mortgageCityStZipOVN',
        'Phone # MTGE co.': 'phone_mtge_co',
        'email mtge': 'mortgageEmail',
        'mtge website': 'mortgageWebsite',
        'MTGE co. Fax #': 'mortgageCoFax',
        'Mailing   address mtge': 'mortgageMailingAddress',
        'Mail city, state, zip mtge': 'mortgageCityStZip',
        'Initial Offer / phase 1 contract amount': 'mortgageInitialOfferPhase1ContractAmount',
        'Draw Request': 'drawRequest',
        'co name': 'coName',
        'Co. website': 'coWebsite',
        'co. EMAIL/co. status': 'coEmailstatus',
        'co address': 'coAddress',
        'co. city state': 'coCityState',
        'co. address 2': 'coAddress2',
        'co. city state 2': 'coCityState2',
        'co address 3': 'coCityState3',
        'co. city state 3': 'coCityState3',
        'Co. logo 1': 'coLogo1',
        'Co. logo 2': 'coLogo2',
        'Co. logo 3': 'coLogo3',
        'Co. REP. / PH': 'coRepPH',
        'CO.REP.\nemail': 'coREPEmail',
        'Co PH # 2': 'coPhone2',
        'CO.REP. email 2': 'coREPEmail',
        'TIN W9': 'TinW9',
        'FedEx     account #': 'fedExAccount',
        'claim report date': 'claimReportDate',
        'Time OF CLAIM REPORT': 'timeOfClaimReport',
        'co.represesntative': 'insuranceCustomerServiceRep',
        'phone ext.': 'phoneExt',
        'Tarp ext. TMP ok': 'tarpExtTMPOk',
        'Int TMP ok': 'IntTMPOk',
        'DRY/PLA CUTOUT MOLD SPRAY  OK': 'DRYPLACUTOUTMOLDSPRAYOK',
        'Lesse info / NAME': 'ale_lessee_name',
        'HOME ADDRESS': 'ale_lessee_home_address',
        'Lessee city, state, zip': 'ale_lessee_city_state_zip',
        'Lessee Email': 'ale_lessee_email',
        'Lessee Phone#': 'ale_lessee_phone',
        'bedrooms': 'ale_rental_bedrooms',
        'months': 'ale_rental_months',
        'Amount / Month': 'ale_rental_amount_per_month',
        'Leased Address': 'ale_lessor_leased_address',
        'city zip': 'ale_lessor_city_zip',
        'Lessor phone #': 'ale_lessor_phone',
        'Lessor Email': 'ale_lessor_email',
        'Lessor mailing Address': 'ale_lessor_mailing_address',
        'Lessor mailing city zip': 'ale_lessor_mailing_city_zip',
        'LESSOR CONTACT PERSON': 'ale_lessor_contact_person',
        'RE MAILING ADDRESS': 'ale_re_mailing_address',
        'RE city zip': 'ale_re_city_zip',
        'RE CONTACT': 'ale_re_contact_person',
        'RE Email': 'ale_re_email',
        'RE phone #': 'ale_re_phone',
        'OWNER/BROKER': 'ale_re_owner_broker_name',
        'OWNER/BROKER phone #': 'ale_re_owner_broker_phone',
        'OWNER/BROKER Email': 'ale_re_owner_broker_email',
    }

    # Add date fields
    if client.dateOfLoss:
        field_mapping['date of loss'] = safe_strftime(client.dateOfLoss, '%A, %B %d, %Y')
    else:
        field_mapping['date of loss'] = ''

    if client.contractDate:
        field_mapping['Contract Date'] = safe_strftime(client.contractDate, '%Y-%m-%d')
    else:
        field_mapping['Contract Date'] = ''

    if client.claimReportDate:
        field_mapping['claim report date'] = safe_strftime(client.claimReportDate, '%Y-%m-%d')
    else:
        field_mapping['claim report date'] = ''

    if client.ale_rental_start_date:
        field_mapping['START DATE'] = safe_strftime(client.ale_rental_start_date, '%-m/%-d/%Y')
    else:
        field_mapping['START DATE'] = ''

    if client.ale_rental_end_date:
        field_mapping['END DATE'] = safe_strftime(client.ale_rental_end_date, '%-m/%-d/%Y')
    else:
        field_mapping['END DATE'] = ''

    # Add boolean fields
    field_mapping['DEMO'] = 'Y' if getattr(client, 'demo', False) else 'N'
    field_mapping['Mitigation'] = 'Y' if getattr(client, 'mitigation', False) else 'N'
    field_mapping['Other Structures'] = 'Y' if getattr(client, 'otherStructures', False) else 'NA'
    field_mapping['Replacement'] = 'Y' if getattr(client, 'replacement', False) else 'N'
    field_mapping['CPS / CLN / CON/ CGN'] = 'Y' if getattr(client, 'CPSCLNCONCGN', False) else 'N'
    field_mapping['Loss of use/ ALE'] = 'Y' if getattr(client, 'lossOfUseALE', '') == 'Y' else ('TBD' if getattr(client, 'lossOfUseALE', '') == 'TBD' else 'N')

    # Add text fields
    for excel_label, model_field in field_definitions.items():
        field_mapping[excel_label] = get_field_value(model_field)

    # Create macro content
    macro_lines = [
        'import uno',
        'import sys',
        'import os',
        '',
        'def update_jobinfo():',
        '    try:',
        '        # Get the document',
        '        desktop = XSCRIPTCONTEXT.getDesktop()',
        '        document = desktop.getCurrentComponent()',
        '        ',
        '        # Find the jobinfo sheet',
        '        sheet_names = document.Sheets.getElementNames()',
        '        sheet = None',
        '        ',
        '        for name in sheet_names:',
        '            if "jobinfo" in name.lower():',
        '                sheet = document.Sheets.getByName(name)',
        '                break',
        '        ',
        '        if not sheet:',
        '            print("No jobinfo sheet found")',
        '            return 0',
        '        ',
        '        # Field mapping',
        '        field_mapping = {',
    ]

    # Add field mapping to macro
    for label, value in field_mapping.items():
        escaped_label = label.replace("'", "\\'").replace('"', '\\"')
        escaped_value = str(value).replace("'", "\\'").replace('"', '\\"')
        macro_lines.append(f'            "{escaped_label}": "{escaped_value}",')

    macro_lines.extend([
        '        }',
        '        ',
        '        # Room data',
        '        room_mapping = {',
    ])

    # Add room data to macro
    rooms = client.rooms.filter(is_encircle_entry=False).order_by('sequence')
    for idx, room in enumerate(rooms, 1):
        if idx <= 25:
            room_label = f"Room/Area {idx}"
            room_value = room.room_name
            escaped_room_value = room_value.replace("'", "\\'").replace('"', '\\"')
            macro_lines.append(f'            "{room_label}": "{escaped_room_value}",')

    macro_lines.extend([
        '        }',
        '        ',
        '        updated = 0',
        '        max_rows = 200  # Limit search to first 200 rows',
        '        ',
        '        # Search for labels in column B (index 1) and update column C (index 2)',
        '        for row in range(max_rows):',
        '            try:',
        '                # Get cell B{row+1} (0-based index)',
        '                cell = sheet.getCellByPosition(1, row)  # Column B',
        '                label = cell.getString()',
        '                ',
        '                if label and label.strip():',
        '                    label_clean = label.strip()',
        '                    # Check field mapping first',
        '                    if label_clean in field_mapping:',
        '                        # Update cell C{row+1}',
        '                        value_cell = sheet.getCellByPosition(2, row)  # Column C',
        '                        value_cell.setString(field_mapping[label_clean])',
        '                        updated += 1',
        '                    # Check room mapping',
        '                    elif label_clean in room_mapping:',
        '                        # Update cell C{row+1}',
        '                        value_cell = sheet.getCellByPosition(2, row)  # Column C',
        '                        value_cell.setString(room_mapping[label_clean])',
        '                        updated += 1',
        '            except:',
        '                # Skip rows with errors',
        '                continue',
        '        ',
        '        # Save changes',
        '        document.store()',
        '        print(f"Updated {updated} cells")',
        '        return updated',
        '        ',
        '    except Exception as e:',
        '        print(f"Error in macro: {str(e)}")',
        '        return 0',
        '',
        '# Make the macro available',
        'g_exportedScripts = (update_jobinfo,)',
    ])

    return '\n'.join(macro_lines)

# ==================== MAIN TASKS ====================

@shared_task(bind=True, max_retries=3)
def create_server_folder_structure_task(self, client_id):
    """
    Create complete server-side folder structure for a client.
    Replaces create_onedrive_structure_task.
    """
    try:
        client = Client.objects.get(id=client_id)
        logger.info(f"Creating server folder structure for client {client_id}: {client.pOwner}")

        import hashlib

        # Create folder structure using claim_folder_utils
        structure = get_folder_structure(f"{client.pOwner}@{client.pAddress}")
        claims_root = get_claims_root()

        # Create main client folder
        client_folder_name = f"{client.pOwner}@{client.pAddress}"
        safe_folder_name = client_folder_name.replace('/', '_').replace('\\', '_').replace(':', '_')
        claim_folder = os.path.join(claims_root, safe_folder_name)

        os.makedirs(claim_folder, exist_ok=True)
        logger.info(f"Created claim folder: {claim_folder}")

        # Create all folders
        for folder_path in structure['folders']:
            full_path = os.path.join(claim_folder, folder_path)
            os.makedirs(full_path, exist_ok=True)
            logger.info(f"Created folder: {folder_path}")

        # Create all text files
        for file_path, content in structure['files'].items():
            full_file_path = os.path.join(claim_folder, file_path)
            with open(full_file_path, 'w') as f:
                f.write(content)
            logger.info(f"Created file: {file_path}")

        # Create metadata file
        metadata = {
            'client_id': client.id,
            'client_name': client.pOwner,
            'address': client.pAddress,
            'claim_number': client.claimNumber,
            'folder_name': safe_folder_name,
            'created_at': timezone.now().isoformat(),
        }

        metadata_path = os.path.join(claim_folder, 'claim_metadata.json')
        with open(metadata_path, 'w') as f:
            import json
            json.dump(metadata, f, indent=2)

        # Update client record
        client.server_folder_path = claim_folder
        client.folder_created_at = timezone.now()
        client.save(update_fields=['server_folder_path', 'folder_created_at'])

        # Create ClaimFile database records
        for file_rel_path in structure['files'].keys():
            try:
                full_path = os.path.join(claim_folder, file_rel_path)
                filename = os.path.basename(file_rel_path)

                with open(full_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                file_size = os.path.getsize(full_path)

                ClaimFile.objects.update_or_create(
                    client=client,
                    file_path=file_rel_path,
                    defaults={
                        'file_type': 'OTHER',
                        'file_name': filename,
                        'file_size': file_size,
                        'file_hash': file_hash,
                        'mime_type': 'text/plain',
                        'description': f'Folder text file: {filename}',
                        'version': 1,
                        'is_active': True,
                    }
                )
                logger.info(f"Created ClaimFile record for {filename}")

            except Exception as e:
                logger.error(f"Failed to create ClaimFile record for {file_rel_path}: {str(e)}")
                continue

        return {
            'success': True,
            'claim_folder': claim_folder,
            'templates_folder': os.path.join(claim_folder, f"Templates {safe_folder_name}"),
            'folder_name': safe_folder_name,
            'created_folders': len(structure['folders']),
            'created_files': len(structure['files'])
        }

    except Client.DoesNotExist:
        logger.error(f"Client {client_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to create server folder structure for client {client_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)

@shared_task(bind=True, max_retries=3)
def copy_templates_to_server_task(self, client_id):
    """
    Copy Excel templates to server claim folder.
    Uses LibreOffice to update templates with client data.
    """
    try:
        client = Client.objects.get(id=client_id)
        logger.info(f"Copying templates to server for client {client_id}: {client.pOwner}")

        import hashlib
        import mimetypes
        import glob

        # Copy base templates from active folder to claim Templates folder
        copied_templates = copy_templates_to_claim_folder(client)
        logger.info(f"Copied {len(copied_templates)} templates")

        # Populate templates with client data using LibreOffice
        templates_folder = get_templates_folder(client)
        population_result = populate_excel_templates(client, templates_folder)

        if population_result.get('success'):
            logger.info(f"Populated {population_result.get('total_processed', 0)} templates")
            if population_result.get('errors'):
                logger.warning(f"Encountered {len(population_result['errors'])} errors during population: {population_result['errors']}")
        else:
            logger.error(f"Failed to populate templates: {population_result.get('error')}")

        # Save room data to JSON (for future Excel population)
        rooms_json = save_rooms_to_json(client)
        logger.info(f"Saved rooms data to: {rooms_json}")

        # Save client info to JSON (for future Excel population)
        info_json = save_client_info_to_json(client)
        logger.info(f"Saved client info to: {info_json}")

        # Create ClaimFile database records for all copied templates
        templates_folder = get_templates_folder(client)
        claim_folder = client.get_server_folder_path()

        for template_filename in copied_templates:
            try:
                full_path = os.path.join(templates_folder, template_filename)
                rel_path = os.path.relpath(full_path, claim_folder)

                # Calculate file hash
                with open(full_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                # Get file size
                file_size = os.path.getsize(full_path)

                # Determine file type based on filename prefix
                file_type = 'OTHER'
                if template_filename.startswith('01-INFO'):
                    file_type = '01-INFO'
                elif template_filename.startswith('01-ROOMS'):
                    file_type = '01-ROOMS'
                elif template_filename.startswith('02-INS-CO'):
                    file_type = '02-INS-CO'
                elif template_filename.startswith('30-MASTER'):
                    file_type = '30-MASTER'
                elif template_filename.startswith('50-') or 'CONTRACT' in template_filename:
                    file_type = '50-CONTRACT'
                elif template_filename.startswith('60-') and 'SCOPE' in template_filename:
                    file_type = '60-SCOPE'
                elif template_filename.startswith('82-') and 'MIT' in template_filename:
                    file_type = '82-MIT'
                elif template_filename.startswith('92-') and 'CPS' in template_filename:
                    file_type = '92-CPS'
                elif template_filename.startswith('94-') and 'INVOICE' in template_filename:
                    file_type = '94-INVOICE'

                # Get MIME type
                mime_type, _ = mimetypes.guess_type(template_filename)

                # Create or update ClaimFile record
                ClaimFile.objects.update_or_create(
                    client=client,
                    file_path=rel_path,
                    defaults={
                        'file_type': file_type,
                        'file_name': template_filename,
                        'file_size': file_size,
                        'file_hash': file_hash,
                        'mime_type': mime_type or 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        'description': f'Template file: {template_filename}',
                        'version': 1,
                        'is_active': True,
                    }
                )
                logger.info(f"Created ClaimFile record for {template_filename}")

            except Exception as e:
                logger.error(f"Failed to create ClaimFile record for {template_filename}: {str(e)}")
                continue

        # Create ClaimFile records for JSON files
        for json_path in [rooms_json, info_json]:
            try:
                rel_path = os.path.relpath(json_path, claim_folder)
                json_filename = os.path.basename(json_path)

                with open(json_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                file_size = os.path.getsize(json_path)

                ClaimFile.objects.update_or_create(
                    client=client,
                    file_path=rel_path,
                    defaults={
                        'file_type': 'OTHER',
                        'file_name': json_filename,
                        'file_size': file_size,
                        'file_hash': file_hash,
                        'mime_type': 'application/json',
                        'description': f'Data file: {json_filename}',
                        'version': 1,
                        'is_active': True,
                    }
                )
                logger.info(f"Created ClaimFile record for {json_filename}")

            except Exception as e:
                logger.error(f"Failed to create ClaimFile record for JSON: {str(e)}")
                continue

        return {
            'success': True,
            'templates_copied': len(copied_templates),
            'template_files': copied_templates,
            'templates_populated': population_result.get('total_processed', 0),
            'population_errors': population_result.get('errors', []),
            'rooms_json': rooms_json,
            'info_json': info_json
        }

    except Client.DoesNotExist:
        logger.error(f"Client {client_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to copy templates for client {client_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)

def populate_excel_templates(client, templates_folder=None, method=None):
    """
    Populate ALL Excel templates in the client's folder with raw client data.

    3-tier fallback chain (each produces identical cell output):
      1. UNO listener  — persistent LO service, fastest, zero corruption
      2. LO subprocess — spawns LO's bundled Python, zero corruption but slower
      3. XML surgery   — pure regex/zip, works without LO, fixed regexes

    Uses the CURRENT files in the client folder, not base templates.

    Args:
        client: Client model instance
        templates_folder: Optional path override
        method: Optional method override ('auto'|'uno'|'xml'). Defaults to
                EXCEL_POPULATE_METHOD env var.
    """
    import glob as glob_mod

    try:
        if not templates_folder:
            templates_folder = get_templates_folder(client)

        if not os.path.exists(templates_folder):
            logger.error(f"Templates folder not found: {templates_folder}")
            return {'success': False, 'error': 'Templates folder not found'}

        excel_files = []
        excel_files.extend(glob_mod.glob(os.path.join(templates_folder, '*.xlsx')))
        excel_files.extend(glob_mod.glob(os.path.join(templates_folder, '*.xlsm')))
        excel_files = [f for f in excel_files if not os.path.basename(f).startswith('~$')]

        if not excel_files:
            return {'success': True, 'populated_files': [], 'errors': [], 'total_processed': 0}

        # Build field mapping once (lists preserved for duplicate-label handling)
        field_mapping = build_field_mapping(client)

        populated_files = []
        errors = []
        method_used = None
        # Per-call override > env var > module default
        force = (method or EXCEL_POPULATE_METHOD).lower()  # 'auto' | 'uno' | 'xml'

        # --- Tier 1: UNO listener (persistent LibreOffice service) ---
        if force in ('auto', 'uno'):
            try:
                from . import lo_uno_service
                if lo_uno_service.is_available():
                    pairs = [(f, field_mapping) for f in excel_files]
                    uno_results = lo_uno_service.populate_jobinfo_batch(pairs)
                    for filepath, cells in uno_results.items():
                        fn = os.path.basename(filepath)
                        if cells >= 0:
                            populated_files.append(fn)
                        else:
                            errors.append(f"{fn}: UNO write failed")
                    method_used = 'UNO listener'
                    logger.info(f"UNO populated {len(populated_files)}/{len(excel_files)} templates")
                elif force == 'uno':
                    raise RuntimeError("UNO listener not available and method=uno was forced")
            except ImportError:
                logger.debug("lo_uno_service not available (python3-uno not installed)")
            except Exception as e:
                logger.warning(f"UNO listener failed ({e}), trying LO subprocess...")

        # --- Tier 2: LO subprocess (bundled Python + lo_populate.py) ---
        if method_used is None and force == 'auto':
            try:
                pairs = [(f, field_mapping) for f in excel_files]
                lo_results = _populate_jobinfo_via_libreoffice(pairs)
                for filepath, cells in lo_results.items():
                    fn = os.path.basename(filepath)
                    if cells >= 0:
                        populated_files.append(fn)
                    else:
                        errors.append(f"{fn}: LO subprocess write failed")
                method_used = 'LO subprocess'
                logger.info(f"LO subprocess populated {len(populated_files)}/{len(excel_files)} templates")
            except Exception as e:
                logger.warning(f"LO subprocess unavailable ({e}), falling back to XML surgery")

        # --- Tier 3: XML surgery (pure regex/zip — no LibreOffice needed) ---
        if method_used is None and force in ('auto', 'xml'):
            method_used = 'XML surgery'
            for filepath in excel_files:
                filename = os.path.basename(filepath)
                try:
                    cells = _populate_jobinfo_via_xml(filepath, client)
                    if cells >= 0:
                        populated_files.append(filename)
                except Exception as e:
                    logger.error(f"XML fallback error on {filename}: {e}")
                    errors.append(f"{filename}: {str(e)}")

        logger.info(f"populate_excel_templates: method={method_used}, "
                     f"populated={len(populated_files)}/{len(excel_files)}")

        return {
            'success': True,
            'populated_files': populated_files,
            'errors': errors,
            'total_processed': len(populated_files),
            'method': method_used,
        }

    except Exception as e:
        logger.error(f"Failed to populate templates: {str(e)}", exc_info=True)
        return {'success': False, 'error': str(e)}

# ==================== COMPATIBILITY FUNCTIONS ====================

def update_jobinfo_tab(sheet, client):
    """
    Populate the jobinfo(2) sheet with all client data using openpyxl.
    Clears Column C first, then populates with current claim data.

    Args:
        sheet: openpyxl worksheet object (jobinfo(2) sheet)
        client: Client model instance

    Returns:
        int: Number of cells updated
    """
    from collections import deque

    field_mapping = build_field_mapping(client)
    normalized_mapping = {k.strip(): v for k, v in field_mapping.items()}

    dup_queues = {}
    for key, val in normalized_mapping.items():
        if isinstance(val, list):
            dup_queues[key] = deque(val)

    cells_updated = 0

    # First, completely clear ALL of Column C (data column)
    for row in range(1, sheet.max_row + 1):
        data_cell = sheet.cell(row=row, column=3)
        data_cell.value = None

    # Now populate with new data (only non-empty values)
    for row in range(1, sheet.max_row + 1):
        label_cell = sheet.cell(row=row, column=2)
        data_cell = sheet.cell(row=row, column=3)

        if label_cell.value:
            label_stripped = str(label_cell.value).strip()
            if label_stripped in normalized_mapping:
                if label_stripped in dup_queues:
                    queue = dup_queues[label_stripped]
                    if not queue:
                        continue
                    data_value = queue.popleft()
                else:
                    data_value = normalized_mapping[label_stripped]

                if data_value is None or data_value == '' or str(data_value) == 'None':
                    continue
                data_cell.value = data_value
                cells_updated += 1
                logger.debug(f"Updated row {row} '{label_stripped}' = {data_value}")

    logger.info(f"update_jobinfo_tab: Updated {cells_updated} cells for {client.pOwner}")
    return cells_updated


def populate_room_data(sheet, client, start_row, max_row):
    """
    Populate room data into the worksheet.
    Searches for Room/Area labels in Column B and fills in room names and work type values.
    """
    rooms = client.rooms.filter(is_encircle_entry=False).order_by('sequence')
    if not rooms:
        return 0

    cells_updated = 0

    room_mapping = {}
    for idx, room in enumerate(rooms, 1):
        if idx <= 25:
            room_mapping[f"Room/Area {idx}"] = room.room_name
            room_mapping[str(idx)] = room.room_name

    for row in range(start_row, min(max_row + 1, sheet.max_row + 1)):
        label_cell = sheet.cell(row=row, column=2)
        data_cell = sheet.cell(row=row, column=3)

        if label_cell.value:
            label_stripped = str(label_cell.value).strip()
            if label_stripped in room_mapping:
                data_cell.value = room_mapping[label_stripped]
                cells_updated += 1

    logger.info(f"populate_room_data: Updated {cells_updated} room cells for {client.pOwner}")
    return cells_updated

# ==================== HELPER FUNCTION FOR BACKWARDS COMPATIBILITY ====================

def update_excel_file(filepath, client):
    """
    Helper function to update Excel file.
    Can be called from other parts of your code.
    """
    return update_excel_with_libreoffice(filepath, client)


@shared_task(bind=True, max_retries=3)
def regenerate_client_excel_files(self, client_id):
    """
    Regenerate all Excel files for a client when their data is updated.
    This is triggered by the post_save signal when client data changes.
    """
    from django.core.cache import cache

    lock_key = f'excel_regen_lock:{client_id}'
    # Acquire a per-client exclusive lock.  If another worker is already
    # regenerating this client's files, re-queue rather than running
    # concurrently — concurrent LibreOffice writes to the same files cause
    # lock-violation errors (0x11b) and can leave partial ZIPs on disk.
    acquired = cache.add(lock_key, '1', timeout=900)  # 15-min safety TTL
    if not acquired:
        logger.info(
            f"Client {client_id} regen already in progress by another worker, "
            "re-queuing in 60s"
        )
        # Re-queue as a brand-new task so we don't consume this task's retry budget.
        regenerate_client_excel_files.apply_async(args=[client_id], countdown=60)
        return {'queued': True, 'reason': 'lock_busy'}

    try:
        client = Client.objects.get(id=client_id)
        logger.info(f"Regenerating Excel files for client {client_id}: {client.pOwner}")

        templates_folder = get_templates_folder(client)

        if not templates_folder or not os.path.exists(templates_folder):
            logger.warning(f"Templates folder not found for client {client_id}")
            return {'success': False, 'error': 'Templates folder not found'}

        excel_files = []
        for ext in ['*.xlsx', '*.xlsm']:
            pattern = os.path.join(templates_folder, ext)
            excel_files.extend(glob.glob(pattern))

        if not excel_files:
            logger.warning(f"No Excel files found in {templates_folder}")
            return {'success': False, 'error': 'No Excel files found'}

        logger.info(f"Found {len(excel_files)} Excel files to regenerate")

        # --- Pre-flight: recover any ODS-masquerading-as-xlsx files --------
        # This happens when LibreOffice previously saved without an explicit
        # FilterName, defaulting to ODS format.  Detect via ZIP structure:
        # valid OOXML has [Content_Types].xml; ODS has a "mimetype" entry.
        _source_dir = os.path.join(
            settings.BASE_DIR, 'docsAppR', 'templates', 'excel', 'active'
        )
        _recovered = []
        for fp in list(excel_files):
            import zipfile as _zf
            try:
                with _zf.ZipFile(fp, 'r') as _z:
                    _names = _z.namelist()
                _is_ooxml = '[Content_Types].xml' in _names
            except Exception:
                _is_ooxml = False  # Not a ZIP — also corrupt

            if not _is_ooxml:
                fn = os.path.basename(fp)
                ext = os.path.splitext(fn)[1]  # .xlsx or .xlsm
                # Strip the client suffix to find the base template name.
                # Naming convention: "01-INFO-{safe_folder_name}.xlsx"
                # Base template:     "01-INFO.xlsx"
                safe_folder = os.path.basename(client.get_server_folder_path())
                base_name = fn.replace(f'-{safe_folder}{ext}', ext).replace(f'-{safe_folder}', '')
                source_path = os.path.join(_source_dir, base_name)
                if os.path.exists(source_path):
                    try:
                        shutil.copy2(source_path, fp)
                        logger.warning(
                            f"Recovered ODS-corrupted {fn} from source template"
                        )
                        _recovered.append(fn)
                    except Exception as _e:
                        logger.error(f"Failed to recover {fn}: {_e}")
                else:
                    logger.error(
                        f"{fn} is ODS/corrupt and source template not found at "
                        f"{source_path} — skipping"
                    )

        if _recovered:
            logger.info(f"Recovered {len(_recovered)} ODS-corrupted files before regeneration")
        # --- End pre-flight -------------------------------------------------

        field_mapping = build_field_mapping(client)

        results = []
        method_used = None
        force = EXCEL_POPULATE_METHOD

        # --- Tier 1: UNO listener ---
        if force in ('auto', 'uno'):
            try:
                from . import lo_uno_service
                if lo_uno_service.is_available():
                    pairs = [(f, field_mapping) for f in excel_files]
                    uno_results = lo_uno_service.populate_jobinfo_batch(pairs)
                    for f, cells in uno_results.items():
                        bn = os.path.basename(f)
                        results.append({'file': bn, 'success': cells >= 0, 'cells_updated': cells})
                        if cells > 0:
                            logger.info(f"UNO regenerated {bn}: {cells} cells")
                    method_used = 'UNO listener'

                    # Per-file XML fallback: some templates (e.g. files with
                    # data connections, featurepropertybag, or 30+ sheets) can't
                    # be opened by LO UNO at all.  Retry those via ZIP surgery so
                    # the jobinfo sheet is still populated.
                    uno_failed = [f for f, c in uno_results.items() if c < 0]
                    if uno_failed:
                        logger.info(
                            f"UNO failed on {len(uno_failed)} file(s), "
                            "retrying with XML surgery"
                        )
                        for f in uno_failed:
                            bn = os.path.basename(f)
                            try:
                                cells = _populate_jobinfo_via_xml(f, client)
                                # Replace the failed result entry
                                for r in results:
                                    if r['file'] == bn:
                                        r['success'] = True
                                        r['cells_updated'] = cells
                                        break
                                logger.info(
                                    f"XML fallback: {bn} → {cells} cells"
                                )
                            except Exception as xml_err:
                                logger.error(
                                    f"XML fallback also failed for {bn}: {xml_err}"
                                )

                elif force == 'uno':
                    raise RuntimeError("UNO listener not available and method=uno was forced")
            except ImportError:
                logger.debug("lo_uno_service not available for regeneration")
            except Exception as e:
                logger.warning(f"UNO listener failed ({e}), trying LO subprocess...")

        # --- Tier 2: LO subprocess ---
        if method_used is None and force == 'auto':
            try:
                pairs = [(f, field_mapping) for f in excel_files]
                lo_results = _populate_jobinfo_via_libreoffice(pairs)
                for f, cells in lo_results.items():
                    bn = os.path.basename(f)
                    results.append({'file': bn, 'success': cells >= 0, 'cells_updated': cells})
                    if cells > 0:
                        logger.info(f"LO regenerated {bn}: {cells} cells")
                method_used = 'LO subprocess'
            except Exception as e:
                logger.warning(f"LO subprocess unavailable ({e}), falling back to XML")

        # --- Tier 3: XML surgery ---
        if method_used is None and force in ('auto', 'xml'):
            method_used = 'XML surgery'
            for f in excel_files:
                bn = os.path.basename(f)
                try:
                    cells = _populate_jobinfo_via_xml(f, client)
                    results.append({'file': bn, 'success': True, 'cells_updated': cells})
                except Exception as e:
                    results.append({'file': bn, 'success': False, 'error': str(e)})
                    logger.error(f"Failed to regenerate {bn}: {e}")

        logger.info(f"regenerate: method={method_used}")

        # Update ClaimFile timestamps for all populated files
        populated_names = {r['file'] for r in results if r.get('success') and r.get('cells_updated', 0) > 0}
        if populated_names:
            try:
                for cf in ClaimFile.objects.filter(client=client, file_name__in=populated_names, is_active=True):
                    cf.save(update_fields=['modified_at'])
            except Exception as e:
                logger.warning(f"Failed to update ClaimFile timestamps: {e}")

        # Also update JSON files
        try:
            save_rooms_to_json(client)
            save_client_info_to_json(client)
        except Exception as e:
            logger.error(f"Failed to update JSON files: {e}")

        success_count = sum(1 for r in results if r.get('success'))
        logger.info(f"Regeneration complete: {success_count}/{len(results)} files updated successfully")

        return {
            'success': True,
            'total_files': len(results),
            'successful': success_count,
            'results': results
        }

    except Client.DoesNotExist:
        logger.error(f"Client {client_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate Excel files for client {client_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)
    finally:
        cache.delete(lock_key)


# ==================== LABEL GENERATION AND EMAIL TASKS ====================

@shared_task(bind=True, max_retries=3)
def generate_and_email_labels_task(self, client_id):
    """
    Generate wall labels and box labels for all rooms in a claim.

    Actions:
    - Generates a combined Wall Labels PDF (all rooms, one page each)
    - Generates a combined Box Labels PDF (all rooms, one page each)
    - Saves both PDFs to the claim's server folder under a 'Labels' subfolder
    - Emails both PDFs to ALL_TEAM_EMAILS

    Triggered automatically when a new claim is created.
    """
    import re
    import io
    import os
    from django.conf import settings
    from django.core.mail import EmailMessage
    from .claim_folder_utils import get_claims_root

    try:
        client = Client.objects.get(id=client_id)
        rooms = (
            client.rooms
            .prefetch_related('work_type_values__work_type')
            .order_by('sequence')
        )

        if not rooms.exists():
            logger.info(f"No rooms found for client {client_id}, skipping label generation")
            return {'success': True, 'message': 'No rooms to generate labels for'}

        claim_name = client.pOwner or 'Unknown'
        claim_address = client.pAddress or ''
        safe_claim_name = "".join(c for c in claim_name if c.isalnum() or c in (' ', '-', '_')).strip()

        logger.info(f"Generating labels for client {client_id} ({claim_name}) with {rooms.count()} rooms")

        # ── Generate combined Wall Labels PDF ─────────────────────────────
        wall_labels_buffer = io.BytesIO()
        _create_combined_wall_labels_pdf(wall_labels_buffer, client, rooms)
        wall_labels_buffer.seek(0)
        wall_pdf_bytes = wall_labels_buffer.read()
        wall_labels_buffer.seek(0)

        # ── Generate combined Box Labels PDF ──────────────────────────────
        box_labels_buffer = io.BytesIO()
        _create_combined_box_labels_pdf(box_labels_buffer, client, rooms)
        box_labels_buffer.seek(0)
        box_pdf_bytes = box_labels_buffer.read()
        box_labels_buffer.seek(0)

        # ── Save both PDFs to claim folder / Labels subfolder ─────────────
        try:
            client_folder_name = (
                f"{client.pOwner}@{client.pAddress}"
                if client.pOwner and client.pAddress
                else f"Client_{client.id}"
            )
            safe_folder_name = re.sub(r'[<>:"/\\|?*]', '_', client_folder_name)
            claim_folder = (
                getattr(client, 'server_folder_path', None)
                or os.path.join(get_claims_root(), safe_folder_name)
            )
            labels_folder = os.path.join(claim_folder, 'Labels')
            os.makedirs(labels_folder, exist_ok=True)

            wall_path = os.path.join(labels_folder, f'{safe_claim_name}_Wall_Labels.pdf')
            with open(wall_path, 'wb') as f:
                f.write(wall_pdf_bytes)

            box_path = os.path.join(labels_folder, f'{safe_claim_name}_Box_Labels.pdf')
            with open(box_path, 'wb') as f:
                f.write(box_pdf_bytes)

            logger.info(f"Labels saved to {labels_folder}")
        except Exception as save_exc:
            logger.warning(f"Could not save labels to claim folder for {client_id}: {save_exc}")

        # ── Build recipient list ──────────────────────────────────────────
        recipients = ['galaxielsaga@gmail.com', 'wsbjoe9@gmail.com']

        # ── Send email ────────────────────────────────────────────────────
        subject = f'[NEW CLAIM LABELS] {claim_name} - Wall & Box Labels'
        body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #1e88e5;">New Claim Labels Generated</h2>

    <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0;">
        <p><strong>Claim Name:</strong> {claim_name}</p>
        <p><strong>Address:</strong> {claim_address}</p>
        <p><strong>Number of Rooms:</strong> {rooms.count()}</p>
    </div>

    <h3>Attached Files:</h3>
    <ul>
        <li><strong>Wall Labels PDF</strong> – Wall orientation labels (W=1 / CENTER / W=3 / W=4) for all rooms</li>
        <li><strong>Box Labels PDF</strong> – Box / room labels for all rooms</li>
    </ul>

    <p style="color: #666; font-size: 12px; margin-top: 20px;">
        Automated notification from the Claims Management System.
    </p>
</body>
</html>
"""
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        email.content_subtype = 'html'
        email.attach(f'{safe_claim_name}_Wall_Labels.pdf', wall_pdf_bytes, 'application/pdf')
        email.attach(f'{safe_claim_name}_Box_Labels.pdf', box_pdf_bytes, 'application/pdf')
        email.send()

        logger.info(
            f"Labels email sent for client {client_id} to {len(recipients)} recipients"
        )
        return {
            'success': True,
            'client_id': client_id,
            'rooms_count': rooms.count(),
            'recipients_count': len(recipients),
        }

    except Client.DoesNotExist:
        logger.error(f"Client {client_id} not found for label generation")
        return {'success': False, 'error': 'Client not found'}
    except Exception as e:
        logger.error(f"Failed to generate/email labels for client {client_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


def _create_combined_wall_labels_pdf(buffer, client, rooms):
    """
    Combined wall labels PDF for all rooms — 4×6 inch thermal.

    Layout (top → bottom):
      • Claim name (small, top-left)
      • Room name  (large, centred)
      • Dotted separator
      • Compass grid (W=2 top | W=1 left | CENTER | W=3 right | W=4 bottom)
      • Work-type data rows (2-column: 100/500, 200/600, 300/700, 400/-)
          – TRAVEL shown in blue bold
          – LOS shown in red bold
          – DAMAGED shown in red bold (visible here; suppressed from Encircle room names)
          – NA / TBD / empty → nothing shown
      • Footer: room count + address

    DAMAGED rule: value appears in these labels so the field crew can see it,
    but build_room_entries() strips it from Encircle room-name strings so the
    property name looks like "no value" in the Encircle room list.
    """
    import math as _math
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch as INCH
    from reportlab.lib.colors import HexColor, black
    from reportlab.pdfbase.pdfmetrics import stringWidth

    W = 4 * INCH
    H = 6 * INCH
    BLUE = HexColor('#1a3a8a')
    RED  = HexColor('#dc2626')
    GRID = HexColor('#aac0e8')

    # Work type pairs rendered in the data-row section (left_wt, right_wt).
    # Each entry: (wt_id, short_description) or (None, '') for a blank cell.
    LABEL_PAIRS = [
        ((100, "OVERVIEW"),      (500, "DEMO")),
        ((200, "SOURCE of LOSS"),(600, "WTR MIT")),
        ((300, "CPS"),           (700, "HMR")),
        ((400, "PPR"),           (None, "")),
    ]
    ROW_H   = 0.265 * INCH
    COL_MID = W / 2   # vertical divider between left and right columns

    def fit_text(text, max_w, x, y, max_fs, min_fs=7,
                 font="Helvetica-Bold", centered=True):
        fs = max_fs
        while fs >= min_fs and stringWidth(text, font, fs) > max_w:
            fs -= 1
        c.setFont(font, fs)
        if centered:
            c.drawCentredString(x, y, text)
        else:
            c.drawString(x, y, text)

    def wt_map(room):
        """Return {work_type_id: value_type} for a room (uses prefetched data)."""
        return {wtv.work_type.work_type_id: wtv.value_type
                for wtv in room.work_type_values.all()}

    def dotted_hline(x1, x2, y, width=0.6):
        c.setStrokeColor(GRID); c.setLineWidth(width); c.setDash(3, 3)
        c.line(x1, y, x2, y)
        c.setDash()

    def dotted_vline(x, y1, y2, width=0.5):
        c.setStrokeColor(GRID); c.setLineWidth(width); c.setDash(2, 3)
        c.line(x, y1, x, y2)
        c.setDash()

    WALL_COPIES = 2
    claim_name  = client.pOwner or 'Unknown'
    address     = (client.pAddress or '')[:50]
    room_list   = list(rooms)
    total_rooms = len(room_list)

    c = canvas.Canvas(buffer, pagesize=(W, H))
    total_labels = total_rooms * WALL_COPIES
    label_count  = 0

    for room in room_list:
        wtm       = wt_map(room)
        room_name = room.room_name
        seq       = room.sequence or 1

        for _ in range(WALL_COPIES):
            cx = W / 2

            # ── Claim name ─────────────────────────────────────────────────
            c.setFillColor(black)
            fit_text(claim_name, W - 0.4*INCH,
                     0.18*INCH, H - 0.26*INCH,
                     max_fs=9, font="Helvetica", centered=False)

            # ── Room name ───────────────────────────────────────────────────
            c.setFillColor(black)
            fit_text(room_name, W - 0.3*INCH,
                     cx, H - 0.65*INCH,
                     max_fs=26, font="Helvetica-Bold")

            # ── Separator below header ─────────────────────────────────────
            dotted_hline(0.2*INCH, W - 0.2*INCH, H - 0.85*INCH)

            # ── Compass diagram ─────────────────────────────────────────────
            # Spans 2.8 inches: from H-1.05*INCH (top) to H-3.85*INCH (bottom)
            diag_top = H - 1.05*INCH
            diag_bot = H - 3.85*INCH
            diag_mid = (diag_top + diag_bot) / 2

            col_w = W / 3
            c0_cx = col_w * 0.5
            c1_cx = W / 2
            c2_cx = col_w * 2.5
            R     = 0.32 * INCH

            def _up_arrow(ax, base_y, tip_y):
                aw = 0.18*INCH; sw = 0.06*INCH
                hh = min(0.15*INCH, (tip_y - base_y) * 0.42)
                p = c.beginPath()
                p.moveTo(ax,       tip_y)
                p.lineTo(ax+aw/2,  tip_y-hh); p.lineTo(ax+sw/2, tip_y-hh)
                p.lineTo(ax+sw/2,  base_y);   p.lineTo(ax-sw/2, base_y)
                p.lineTo(ax-sw/2,  tip_y-hh); p.lineTo(ax-aw/2, tip_y-hh)
                p.close()
                c.setFillColor(BLUE); c.setStrokeColor(HexColor('#1A4472'))
                c.setLineWidth(0.4); c.drawPath(p, fill=1, stroke=1)

            def _c_arrow(ax, ay, Rr, open_right):
                gap_half = 45; extent = 360 - gap_half * 2
                arc_s = gap_half if open_right else 180 + gap_half
                arc_e = arc_s + extent
                ah_ang = _math.radians(arc_e if open_right else arc_s)
                tx = -_math.sin(ah_ang) if open_right else  _math.sin(ah_ang)
                ty =  _math.cos(ah_ang) if open_right else -_math.cos(ah_ang)
                c.saveState()
                c.setStrokeColor(BLUE); c.setLineWidth(1.1); c.setLineCap(0)
                p = c.beginPath()
                p.arc(ax-Rr, ay-Rr, ax+Rr, ay+Rr, arc_s, extent)
                c.drawPath(p, fill=0, stroke=1)
                c.restoreState()
                hx = ax + Rr*_math.cos(ah_ang); hy = ay + Rr*_math.sin(ah_ang)
                hs = Rr*0.18; pw = Rr*0.12; px = -ty; py = tx
                p2 = c.beginPath()
                p2.moveTo(hx+tx*hs,          hy+ty*hs)
                p2.lineTo(hx-tx*hs+px*pw,    hy-ty*hs+py*pw)
                p2.lineTo(hx-tx*hs-px*pw,    hy-ty*hs-py*pw)
                p2.close()
                c.setFillColor(BLUE); c.setStrokeColor(BLUE)
                c.setLineWidth(0.3); c.drawPath(p2, fill=1, stroke=1)

            # W=2 — top centre
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(c1_cx, diag_mid + 0.82*INCH, "W=2")
            _up_arrow(c1_cx, diag_mid + 0.22*INCH, diag_mid + 0.68*INCH)

            # W=1 — left
            _c_arrow(c0_cx, diag_mid, R, open_right=True)
            c.setFillColor(black); c.setFont("Helvetica-Bold", 11)
            c.drawCentredString(c0_cx, diag_mid - 0.05*INCH, "W=1")

            # CENTER box
            bw = 0.78*INCH; bh = 0.40*INCH
            c.setStrokeColor(black); c.setLineWidth(1.1)
            c.rect(c1_cx-bw/2, diag_mid-bh/2, bw, bh)
            c.setFillColor(black); c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(c1_cx, diag_mid - 0.05*INCH, "CENTER")

            # W=3 — right
            _c_arrow(c2_cx, diag_mid, R, open_right=False)
            c.setFillColor(black); c.setFont("Helvetica-Bold", 11)
            c.drawCentredString(c2_cx, diag_mid - 0.05*INCH, "W=3")

            # W=4 — bottom centre
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(c1_cx, diag_mid - 0.83*INCH, "W=4")

            # ── Separator above data rows ───────────────────────────────────
            data_top = diag_bot - 0.10*INCH
            dotted_hline(0.1*INCH, W - 0.1*INCH, data_top)

            # ── Work-type data rows ─────────────────────────────────────────
            # Two columns side by side.
            # Value-type colour rules:
            #   TRAVEL  → blue bold
            #   LOS     → red bold
            #   DAMAGED → red bold  (shown here; hidden from Encircle room names)
            #   anything else → nothing shown
            for row_i, (left_pair, right_pair) in enumerate(LABEL_PAIRS):
                row_y_top = data_top - row_i * ROW_H
                row_y_bot = row_y_top - ROW_H
                text_y    = row_y_bot + ROW_H * 0.30

                # Horizontal row separator
                dotted_hline(0.1*INCH, W - 0.1*INCH, row_y_bot, width=0.5)
                # Vertical column divider
                dotted_vline(COL_MID, row_y_top, row_y_bot)

                for col_i, (wt_id, wt_desc) in enumerate((left_pair, right_pair)):
                    if wt_id is None:
                        continue
                    value_type = wtm.get(wt_id, '')
                    code_str   = str(wt_id + seq)
                    cell_x     = (0.12*INCH if col_i == 0 else COL_MID + 0.08*INCH)

                    # Code — bold black
                    c.setFillColor(black); c.setFont("Helvetica-Bold", 7)
                    c.drawString(cell_x, text_y, code_str)
                    x_after_code = cell_x + stringWidth(code_str, "Helvetica-Bold", 7) + 3

                    # Description — regular black
                    c.setFillColor(black); c.setFont("Helvetica", 7)
                    c.drawString(x_after_code, text_y, wt_desc)
                    x_after_desc = x_after_code + stringWidth(wt_desc, "Helvetica", 7) + 3

                    # Value type — coloured bold (only for TRAVEL / LOS / DAMAGED)
                    if value_type == 'TRAVEL':
                        c.setFillColor(black); c.setFont("Helvetica-Bold", 7)
                        c.drawString(x_after_desc, text_y, "TRAVEL")
                    elif value_type in ('LOS', 'DAMAGED'):
                        c.setFillColor(RED); c.setFont("Helvetica-Bold", 7)
                        c.drawString(x_after_desc, text_y, value_type)
                    # NA / TBD / empty → nothing drawn

            # ── Footer ─────────────────────────────────────────────────────
            footer_sep_y = data_top - len(LABEL_PAIRS) * ROW_H - 0.08*INCH
            dotted_hline(0.1*INCH, W - 0.1*INCH, footer_sep_y)
            footer_y = footer_sep_y - 0.18*INCH
            c.setFillColor(black); c.setFont("Helvetica", 7)
            c.drawRightString(W - 0.15*INCH, footer_y, address or claim_name[:40])

            label_count += 1
            if label_count < total_labels:
                c.showPage()

    c.save()


def _create_combined_box_labels_pdf(buffer, client, rooms):
    """
    Combined box labels PDF for all rooms — 4×3 inch thermal.
    Two-column layout: Col A (75%) = room name + claim name, Col B (25%) = BOX # + number.
    Box numbers restart at 1 for each room.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch as INCH
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth

    W = 4 * INCH
    H = 3 * INCH
    MARGIN = 0.15 * INCH

    col_a_w = W * 0.75
    col_b_x = col_a_w
    col_b_w = W * 0.25
    b_cx    = col_b_x + col_b_w / 2

    def fit_text(text, max_width, x, y, max_fs, min_fs=7,
                 font="Helvetica-Bold", centered=True):
        fs = max_fs
        while fs >= min_fs and stringWidth(text, font, fs) > max_width:
            fs -= 1
        c.setFont(font, fs)
        if centered:
            c.drawCentredString(x, y, text)
        else:
            c.drawString(x, y, text)

    BOX_COPIES = 20
    c = canvas.Canvas(buffer, pagesize=(W, H))
    claim_name = client.pOwner or 'Unknown'

    total_labels = len(rooms) * BOX_COPIES
    label_count = 0

    for room in rooms:
        room_name = room.room_name
        for box_num in range(1, BOX_COPIES + 1):
            # Col A: room name + claim name
            fit_text(room_name.upper(),
                     max_width=col_a_w - MARGIN * 2,
                     x=col_a_w / 2, y=H * 0.60,
                     max_fs=36, font="Helvetica-Bold")

            fit_text(claim_name,
                     max_width=col_a_w - MARGIN * 2,
                     x=col_a_w / 2, y=H * 0.33,
                     max_fs=15, font="Helvetica")

            # Vertical divider
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.8)
            c.line(col_b_x, MARGIN, col_b_x, H - MARGIN)

            # Col B: "BOX #" header
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(b_cx, H * 0.76, "BOX #")

            c.setLineWidth(0.5)
            c.line(col_b_x + MARGIN * 0.3, H * 0.69,
                   W - MARGIN * 0.3, H * 0.69)

            # Col B: box number (large, auto-fit)
            fit_text(str(box_num),
                     max_width=col_b_w - MARGIN,
                     x=b_cx, y=H * 0.24,
                     max_fs=52, min_fs=16, font="Helvetica-Bold")

            label_count += 1
            if label_count < total_labels:
                c.showPage()

    c.save()


# ==================== ENCIRCLE WEBHOOK TASKS ====================

@shared_task(bind=True, max_retries=3)
def send_floorplan_notification_task(self, claim_id, floorplan_url, claim_info):
    """
    Send email notification when a floorplan is created/available in Encircle.
    Downloads the floorplan and attaches it to the email.
    """
    from django.conf import settings
    from django.core.mail import EmailMessage
    import requests

    try:
        recipients = getattr(settings, 'ALL_TEAM_EMAILS', [])
        if not recipients:
            logger.warning("No team emails configured for floorplan notification")
            return {'success': False, 'error': 'No team emails configured'}

        claim_name = claim_info.get('name', 'Unknown Claim')
        claim_address = claim_info.get('address', '')
        encircle_claim_id = claim_info.get('encircle_id', claim_id)

        logger.info(f"Sending floorplan notification for Encircle claim {encircle_claim_id}")

        floorplan_data = None
        floorplan_filename = f'floorplan_{encircle_claim_id}.png'

        if floorplan_url:
            try:
                api_key = getattr(settings, 'ENCIRCLE_API_KEY', '')
                headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
                response = requests.get(floorplan_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    floorplan_data = response.content
                    content_type = response.headers.get('Content-Type', '')
                    if 'png' in content_type:
                        floorplan_filename = f'floorplan_{encircle_claim_id}.png'
                    elif 'jpeg' in content_type or 'jpg' in content_type:
                        floorplan_filename = f'floorplan_{encircle_claim_id}.jpg'
                    elif 'pdf' in content_type:
                        floorplan_filename = f'floorplan_{encircle_claim_id}.pdf'
            except Exception as e:
                logger.warning(f"Could not download floorplan from {floorplan_url}: {e}")

        subject = f'[FLOORPLAN AVAILABLE] {claim_name} - New Floorplan Created'
        body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #4caf50;">🏠 New Floorplan Available</h2>

    <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #4caf50;">
        <p><strong>Claim Name:</strong> {claim_name}</p>
        <p><strong>Address:</strong> {claim_address}</p>
        <p><strong>Encircle Claim ID:</strong> {encircle_claim_id}</p>
    </div>

    <p>A new floorplan has been created/updated in Encircle for this claim.</p>

    {'<p><strong>The floorplan is attached to this email.</strong></p>' if floorplan_data else '<p style="color: #f44336;">Note: Could not download the floorplan image. Please check Encircle directly.</p>'}

    <p style="color: #666; font-size: 12px; margin-top: 20px;">
        This is an automated notification from the Claims Management System via Encircle webhook.
    </p>
</body>
</html>
"""

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        email.content_subtype = 'html'

        if floorplan_data:
            content_type = 'image/png'
            if floorplan_filename.endswith('.jpg'):
                content_type = 'image/jpeg'
            elif floorplan_filename.endswith('.pdf'):
                content_type = 'application/pdf'
            email.attach(floorplan_filename, floorplan_data, content_type)

        email.send()

        logger.info(f"Floorplan notification sent for claim {encircle_claim_id} to {len(recipients)} recipients")

        return {
            'success': True,
            'claim_id': encircle_claim_id,
            'recipients_count': len(recipients),
            'floorplan_attached': floorplan_data is not None
        }

    except Exception as e:
        logger.error(f"Failed to send floorplan notification: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)


# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# Lightweight sub-claim Encircle push — no DB Client record created/modified
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def push_encircle_subclaim_task(self, primary_client_id, name_suffix, room_names, template_key):
    """
    Create an Encircle claim for a MIT/RHT/HMR sub-claim WITHOUT touching the
    Django Client table.  Uses the primary client's contact/insurance metadata
    with the name overridden to "{pOwner} {name_suffix}".

    Args:
        primary_client_id: UUID of the primary Client record (metadata source).
        name_suffix:        e.g. 'MIT', 'RHT'
        room_names:         list of room name strings to include
        template_key:       'readings_8000' | 'readings_9000' — passed straight
                            to build_room_entries()
    """
    from .models import Client
    from .encircle_client import EncircleAPIClient

    try:
        primary = Client.objects.get(id=primary_client_id)
    except Client.DoesNotExist:
        return {'success': False, 'error': f'Primary client {primary_client_id} not found'}

    api = EncircleAPIClient()

    # Build claim payload from primary client with modified name
    date_of_loss_str = ''
    if primary.dateOfLoss:
        try:
            date_of_loss_str = primary.dateOfLoss.strftime('%Y-%m-%d')
        except Exception:
            date_of_loss_str = str(primary.dateOfLoss)

    full_address = primary.pAddress or ''
    if primary.pCityStateZip:
        full_address = f"{full_address}, {primary.pCityStateZip}".strip(', ')

    claim_payload = {
        'contractor_identifier': f"{primary.id}_{name_suffix}",
        'policyholder_name':     f"{primary.pOwner} {name_suffix}",
        'policyholder_phone_number':   primary.cPhone or '',
        'policyholder_email_address':  primary.cEmail or '',
        'full_address':          full_address,
        'date_of_loss':          date_of_loss_str,
        'type_of_loss':          primary.causeOfLoss or '',
        'adjuster_name':         (primary.deskAdjusterDA or primary.fieldAdjusterName or '').strip(),
        'insurance_company_name': primary.insuranceCo_Name or '',
        'policy_number':         primary.policyNumber or '',
        'assignment_identifier': primary.claimNumber or '',
    }
    claim_payload = {k: v for k, v in claim_payload.items() if v}

    try:
        result = api.create_claim(claim_payload)
        encircle_claim_id = str(result.get('id') or result.get('claim_id') or '')
        if not encircle_claim_id:
            raise ValueError(f"Encircle did not return a claim id: {result}")
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

    # Build room entries — empty configs means all LOS values show as dots
    all_entries = build_room_entries(room_names, {}, [template_key])

    rooms_pushed = 0
    try:
        structure = api.get_or_create_default_structure(encircle_claim_id)
        structure_id = str(structure.get('id') or structure.get('structure_id') or '')
        for entry in all_entries:
            try:
                api.create_room(encircle_claim_id, structure_id, {'name': entry})
                rooms_pushed += 1
            except Exception as room_exc:
                logger.warning(f"[push_encircle_subclaim] room failed: {room_exc}")
    except Exception as exc:
        logger.warning(f"[push_encircle_subclaim] structure error: {exc}")

    logger.info(
        f"push_encircle_subclaim_task done: primary={primary_client_id} "
        f"suffix={name_suffix} encircle_id={encircle_claim_id} pushed={rooms_pushed}"
    )
    return {
        'success': True,
        'encircle_claim_id': encircle_claim_id,
        'rooms_pushed': rooms_pushed,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Encircle GreenField – push a local claim (+ rooms) to Encircle
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def push_claim_to_encircle_task(self, client_id, selected_templates=None, selected_work_types=None, skip_preamble=False):
    """
    Create (or re-sync) a local Client record as a property claim in Encircle.

    Args:
        client_id: UUID string of the Client record.
        selected_templates: list of template names to generate, e.g. ['basic', 'readings'].
            'basic' (100-700s) is always included.  Valid values also include
            'readings' (8000-9000s MC Day Readings) and 'readings default' (70000s).

    Steps:
      1. Build the Encircle claim payload from Client fields.
      2. POST to Encircle → get back the encircle claim id.
      3. Find or create the default structure ('Main Building').
      4. Create one Encircle room per local Room, encoding the LOS/TRAVEL
         work-type values as a readable description on each room.
      5. Save the Encircle claim id + sync timestamp back to the Client.

    Returns a dict: {'success': True, 'encircle_claim_id': ..., 'rooms_pushed': N}
    """
    from django.utils import timezone as tz
    from .models import Client, Room, RoomWorkTypeValue
    from .encircle_client import EncircleAPIClient

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        logger.error(f"push_claim_to_encircle_task: Client {client_id} not found")
        return {'success': False, 'error': f'Client {client_id} not found'}

    api = EncircleAPIClient()

    # ── 1. Build claim payload ─────────────────────────────────────────────
    date_of_loss_str = ''
    if client.dateOfLoss:
        try:
            date_of_loss_str = client.dateOfLoss.strftime('%Y-%m-%d')
        except Exception:
            date_of_loss_str = str(client.dateOfLoss)

    full_address = client.pAddress or ''
    if client.pCityStateZip:
        full_address = f"{full_address}, {client.pCityStateZip}".strip(', ')

    adjuster = (client.deskAdjusterDA or client.fieldAdjusterName or '').strip()

    claim_payload = {
        'contractor_identifier': str(client.id),
        'policyholder_name': client.pOwner or '',
        'policyholder_phone_number': client.cPhone or '',
        'policyholder_email_address': client.cEmail or '',
        'full_address': full_address,
        'date_of_loss': date_of_loss_str,
        'type_of_loss': client.causeOfLoss or '',
        'adjuster_name': adjuster,
        'insurance_company_name': client.insuranceCo_Name or '',
        'policy_number': client.policyNumber or '',
        'assignment_identifier': client.claimNumber or '',
    }
    # Strip empty strings so Encircle doesn't reject optional blank fields
    claim_payload = {k: v for k, v in claim_payload.items() if v}

    # ── 2. Create (or skip if already synced) ─────────────────────────────
    try:
        existing_encircle_id = getattr(client, 'encircle_claim_id', None)
        if existing_encircle_id:
            # Already pushed – use existing Encircle claim id for room sync
            encircle_claim_id = existing_encircle_id
            logger.info(f"Client {client_id} already has Encircle id {encircle_claim_id}; syncing rooms only")
        else:
            logger.info(f"Sending claim payload to Encircle: {claim_payload}")
            result = api.create_claim(claim_payload)
            encircle_claim_id = str(result.get('id') or result.get('claim_id') or '')
            if not encircle_claim_id:
                raise ValueError(f"Encircle did not return a claim id. Response: {result}")
            logger.info(f"Created Encircle claim {encircle_claim_id} for client {client_id}")
            # Persist the Encircle claim id back to our DB so we don't duplicate on retry
            # Use .update() instead of .save() to bypass the post_save signal and avoid
            # triggering a spurious third concurrent regenerate_client_excel_files task.
            try:
                from django.utils import timezone as _tz
                Client.objects.filter(id=client_id).update(
                    encircle_claim_id=encircle_claim_id,
                    encircle_synced_at=_tz.now(),
                )
                client.encircle_claim_id = encircle_claim_id  # keep in-memory copy current
            except Exception as save_exc:
                logger.warning(f"Could not save encircle_claim_id to client {client_id} (migration pending?): {save_exc}")
    except Exception as exc:
        logger.error(f"Failed to create Encircle claim for client {client_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)

    # ── 3. Build room entry list ───────────────────────────────────────────
    # Prefer pre-generated numbered entries (is_encircle_entry=True) created
    # at Step 2 save time.  Fall back to the old build_room_entries() path for
    # clients that pre-date this feature.
    rooms_pushed = 0

    encircle_entries_qs = (
        Room.objects
        .filter(client=client, is_encircle_entry=True)
        .order_by('sequence')
    )

    if encircle_entries_qs.exists():
        # New path: entries already computed — use them directly
        all_entries = list(encircle_entries_qs.values_list('room_name', flat=True))
        logger.info(
            f"push_claim_to_encircle_task: using {len(all_entries)} pre-generated "
            f"Encircle entries for client {client_id}"
        )
    else:
        # Legacy path: compute from base rooms + configs (pre-migration clients)
        logger.info(
            f"push_claim_to_encircle_task: no pre-generated entries found for client "
            f"{client_id}; falling back to build_room_entries()"
        )
        rooms_qs = (
            Room.objects
            .filter(client=client, is_encircle_entry=False)
            .prefetch_related('work_type_values__work_type')
            .order_by('sequence')
        )
        room_names = []
        configs = {}
        for room in rooms_qs:
            room_names.append(room.room_name)
            room_config = {}
            for wtv in room.work_type_values.all():
                room_config[wtv.work_type.work_type_id] = wtv.value_type
            configs[room.room_name] = room_config

        if not selected_templates:
            selected_templates = []
        else:
            selected_templates = list(selected_templates)
        if selected_work_types:
            selected_work_types = [int(wt) for wt in selected_work_types]

        all_entries = build_room_entries(room_names, configs, selected_templates, selected_work_types, skip_preamble)
        logger.info(
            f"push_claim_to_encircle_task: built {len(all_entries)} entries "
            f"from {len(room_names)} rooms"
        )


    try:
        # Get or create the default structure ("Main Building")
        structure = api.get_or_create_default_structure(encircle_claim_id)
        structure_id = str(structure.get('id') or structure.get('structure_id') or '')
        if not structure_id:
            raise ValueError(f"Could not resolve structure id from: {structure}")

        logger.info(
            f"Pushing {len(all_entries)} room entries to Encircle claim "
            f"{encircle_claim_id} structure {structure_id}"
        )
        for idx, entry in enumerate(all_entries):
            try:
                api.create_room(encircle_claim_id, structure_id, {'name': entry})
                rooms_pushed += 1
                logger.info(f"  [push] {idx+1}/{len(all_entries)}: {entry[:80]}")
            except Exception as room_exc:
                logger.warning(
                    f"  [push FAILED] {idx+1}/{len(all_entries)} '{entry[:60]}': {room_exc}"
                )
    except Exception as exc:
        logger.warning(f"Could not apply room list to Encircle claim {encircle_claim_id}: {exc}")

    # ── 5. Save Encircle id back to the Client ─────────────────────────────
    try:
        Client.objects.filter(id=client_id).update(
            encircle_claim_id=encircle_claim_id,
            encircle_synced_at=tz.now(),
        )
    except Exception as exc:
        logger.warning(f"Could not save encircle_claim_id to client {client_id}: {exc}")

    # ── 6. Verify rooms were created in Encircle ───────────────────────────
    verified_count = 0
    encircle_room_names = []
    try:
        rooms_response = api.get_claim_rooms(encircle_claim_id, structure_id)
        # Response may be a list directly or a dict with a 'rooms'/'data' key
        if isinstance(rooms_response, list):
            encircle_room_names = [r.get('name', '') for r in rooms_response]
        elif isinstance(rooms_response, dict):
            items = rooms_response.get('rooms') or rooms_response.get('data') or []
            encircle_room_names = [r.get('name', '') for r in items]
        verified_count = len(encircle_room_names)
        logger.info(
            f"push_claim_to_encircle_task verify: found {verified_count} rooms in Encircle "
            f"(expected {rooms_pushed}): {[n[:40] for n in encircle_room_names[:5]]}{'...' if verified_count > 5 else ''}"
        )
    except Exception as verify_exc:
        logger.warning(f"Could not verify Encircle rooms for claim {encircle_claim_id}: {verify_exc}")

    logger.info(
        f"push_claim_to_encircle_task done: client={client_id}, "
        f"encircle_claim_id={encircle_claim_id}, rooms_pushed={rooms_pushed}, "
        f"rooms_verified={verified_count}"
    )
    return {
        'success': True,
        'encircle_claim_id': encircle_claim_id,
        'rooms_pushed': rooms_pushed,
        'rooms_verified': verified_count,
        'encircle_room_names': encircle_room_names[:20],  # first 20 for display
    }


# ──────────────────────────────────────────────────────────────────────────────
# Shared helper – build Encircle room entry strings (no I/O, no Celery)
# ──────────────────────────────────────────────────────────────────────────────

def build_room_entries(room_names, configs, selected_templates=None, selected_work_types=None, skip_preamble=False):
    """
    Pure function: build the ordered list of Encircle room entry strings.

    Args:
        room_names:          ordered list of room name strings
        configs:             dict  {room_name: {work_type_id: value_type, ...}}
        selected_templates:  list of 'basic', 'readings', 'readings default'
                             Defaults to ['basic', 'readings'].
        selected_work_types: optional list of int work type IDs to include in
                             the 'basic' template (100-700). If None, all are included.

    Returns:
        list[str]  – entries ready to POST as room names to Encircle
    """
    if not selected_templates:
        selected_templates = ['basic', 'readings']

    # Value types that should NOT appear as a prefix in Encircle room names.
    # DAMAGED is tracked in labels but hidden from room name strings so it
    # looks like "no value" in the Encircle room list.
    _HIDE_IN_NAME = {'.', '', None, 'NA', 'TBD', 'DAMAGED'}

    def _los(room_name):
        cfg = configs.get(room_name, {})
        v = cfg.get(100, cfg.get('100', '.'))
        return "…........." if v in _HIDE_IN_NAME else v

    # ── basic (100–700s) ─────────────────────────────────────────────────────
    work_type_descs = {
        100: "= … JOB/ROOMS OVERVIEW PICS ..",
        200: "….. SOURCE of LOSS PICS …..",
        300: "….. C.P.S. …...",
        400: "….. PPR …..",
        500: "…… DMO = DEMOLITION …....",
        600: "… WTR MITIGATION EQUIPMENT & W.I.P . ...",
        700: "… HMR = HAZARDOUS MATERIALS ...",
    }
    section_labels_basic = {
        100: "100 .... = ... JOB/ROOMS OVERVIEW PICS .. ==========================",
        200: "200 .... ..... SOURCE of LOSS PICS ..... ===========================",
        300: "300 .... ..... C.P.S. ...... =======================================",
        400: "400 .... PPR ===================================================",
        500: "500 .... ...... DMO = DEMOLITION ....... ===========================",
        600: "600 . WTR MITIGATION EQUIPMENT & W.I.P. ============================",
        700: "700 . HMR = HAZARDOUS MATERIALS ====================================",
    }

    basic_entries = [] if skip_preamble else [
        "0.0001 ….. JOBSITE VERIFICATION",
        "0.0002 . MECHANICALS = WATER METER READING & PLUMBING REPORT/INVOICE",
        "0.0003 . MECHANICALS = ELECTRICAL HAZARDS",
        "0.0004 . EXT DAMAGE IF APPLICABLE ROOF TARPS",
        "0.07 DRYING CHAMBER # 1",
        "0.08 DRYING CHAMBER # 2",
        "0.09 DRYING CHAMBER # 3",
        "0.10 INTERIOR GENERAL WTR ITEMS",
        "0.11 ADMINISTRATION EXPENSES",
        "0.12 PERSONAL PROTECTION EQUIPMENT PPE",
        "0.13 ELECTRICAL",
        "0.14 EXHAUST SYSTEM SET UP (per level)",
        "1997 . LEAD & HMR TESTING LAB RESULTS",
        "1998 . KITCHEN CABINETS SIZES U & L =LF/ CT = SF; APPLIANCES",
        "1999 . BATHROOM FIXTURES CAB SIZE & FIXTURES & TYPE",
    ]
    wt_list = [100, 200, 300, 500, 600, 700, 400]
    if selected_work_types:
        wt_list = [wt for wt in wt_list if wt in selected_work_types]
    for work_type in wt_list:
        basic_entries.append(section_labels_basic[work_type])
        for idx, room_name in enumerate(room_names):
            room_cfg = configs.get(room_name, {})
            config_value = room_cfg.get(100, room_cfg.get('100', '.'))
            # DAMAGED is suppressed from the room name (visible in labels only)
            display_value = "" if config_value in _HIDE_IN_NAME else config_value
            prefix = f"{display_value} " if display_value else ""
            basic_entries.append(f"{work_type + idx + 1} {prefix}…. {room_name} {work_type_descs[work_type]}")
        if work_type == 300:
            basic_entries.extend([
                "3222 . CPS DAY2 WIP OVERVIEW WIP BOXES PACKOUT PICS",
                "3322 . CPS3 DAY3 STORAGE OVERVIEW STORAGE MOVE OUT PICS",
                "3444 . CPS4 DAY4 PACKBACK OVERVIEW PACK-BACK / RESET PICS",
            ])
        elif work_type == 400:
            basic_entries.extend([
                "4111.1 . REPLACEMENT 1 CON OVERVIEW DAY PICS",
                "4222.2 . REPLACEMENT 2 CON WIP",
                "4333.3 . REPLACEMENT 3 CON STORAGE",
                "4444.4 . REPLACEMENT 4 CON DISPOSAL",
            ])
    if not skip_preamble:
        basic_entries.extend([
            "9998.0 . REBUILD OVERVIEW WORK IN PROGRESS.......WIP",
            "9999.0 . REBUILD INTERIOR COMPLETED WORK",
        ])

    # ── 8000s MC Day Readings ─────────────────────────────────────────────────
    def _build_8000s():
        entries = []
        entries.append("8000 ….. ======= MC READINGS STABILIZATION ===============")
        for idx, room_name in enumerate(room_names):
            entries.append(f"{8001 + idx}.0 . {room_name} … MC READINGS STABILIZATION  {_los(room_name)}")
        section_labels = {
            8100: "8100.0 . ...  DAY1    MC READINGS ..  =========  ===============  =====",
            8200: "8200.0 . ...  DAY2    MC READINGS ..  ===============  ======",
            8300: "8300.0 . ….. DAY 3 …..  =====================  ======",
            8400: "8400.0 . ….. DAY 4 …..  ===============   =======",
        }
        descs = {
            8100: "   ...  DAY1    MC READINGS .. ",
            8200: "  ...  DAY2    MC READINGS ..",
            8300: "  ...  DAY3    MC READINGS ..",
            8400: "  ...  DAY4    MC READINGS",
        }
        for work_type in [8100, 8200, 8300, 8400]:
            entries.append(section_labels[work_type])
            day_num = str(work_type)[3]
            for idx, room_name in enumerate(room_names):
                entries.append(
                    f"{work_type + idx + 1}.{day_num} . {room_name} {descs[work_type]}  {_los(room_name)}"
                )
        return entries

    # ── 9000s Dry Chamber Readings ────────────────────────────────────────────
    def _build_9000s():
        entries = ["9000 RH &T & GPP  DRY CHAMBERS [DC] . READINGS =================="]
        entries.extend([
            "9100.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 1 ….. ",
            "9100.0 …. EXTERIOR & UNAFFECTED AREA  ….. DAY 1 ….. ",
            "9101.0 …. DRY CHAMBER # 1 ….. DAY 1 …..  RH &T & GPP ",
            "9102.0 …. DRY CHAMBER # 2 ….. DAY 1 …..  RH &T & GPP ",
            "9103.0 …. DRY CHAMBER # 3 ….. DAY 1 …..  RH &T & GPP ",
            "9104.0 …. DRY CHAMBER # 4 ….. DAY 1 …..  RH &T & GPP ",
            "9200.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 2 ….. ",
            "9200.2 …. EXTERIOR & UNAFFECTED AREA ….. DAY 2 ….. ",
            "9201.2 …. DRY CHAMBER # 1 ….. DAY 2 …..  RH &T & GPP ",
            "9202.2 …. DRY CHAMBER # 2 ….. DAY 2 …..  RH &T & GPP ",
            "9203.2 …. DRY CHAMBER # 3 ….. DAY 2 …..  RH &T & GPP ",
            "9204.2 …. DRY CHAMBER # 4 ….. DAY 2 …..  RH &T & GPP ",
            "9205.2 …. DRY CHAMBER # 5 ….. DAY 2 …..  RH &T & GPP ",
            "9300.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 3 ….. ",
            "9300.0 …. EXTERIOR & UNAFFECTED AREA ….. DAY 3 ….. ",
            "9301.0 …. DRY CHAMBER # 1 ….. DAY 3 …..  RH &T & GPP ",
            "9302.0 …. DRY CHAMBER # 2 ….. DAY 3 …..  RH &T & GPP ",
            "9303.0 …. DRY CHAMBER # 3 ….. DAY 3 …..  RH &T & GPP ",
            "9304.0 …. DRY CHAMBER # 4 ….. DAY 3 …..  RH &T & GPP ",
            "9400.0 RH &T & GPP  DRY CHAMBERS [DC] . READINGS  =========== ….. DAY 4 ….. ",
            "9400.0 …. EXTERIOR & UNAFFECTED AREA ….. DAY 4 ….. ",
            "9401.0 …. DRY CHAMBER # 1 ….. DAY 4 …..  RH &T & GPP ",
            "9402.0 …. DRY CHAMBER # 2 ….. DAY 4 …..  RH &T & GPP ",
            "9403.0 …. DRY CHAMBER # 3 ….. DAY 4 …..  RH &T & GPP ",
            "9404.0 …. DRY CHAMBER # 4 ….. DAY 4 …..  RH &T & GPP ",
        ])
        return entries

    def _build_readings_default():
        entries = ["8000 ….. ======= MC READINGS STABILIZATION ==============="]
        for idx, room_name in enumerate(room_names):
            entries.append(f"{8001 + idx}.0 . {room_name} … MC READINGS STABILIZATION  {_los(room_name)}")
        return entries

    # ── 10000s Siding ─────────────────────────────────────────────────────────
    def _build_siding():
        return [
            "10 ….. ======= SIDING =======================================",
            "10.0 . JOBSITE VERIFICATION …. SIDING",
            "11.0 . SOURCE OF LOSS …. SIDING",
            "12.0 . ROOF …. SIDING",
            "13.0 . PPR NON SALVAGABLES …. SIDING",
            "14.0 . EXTERIOR …. SIDING",
            "15.0 . AIR CONDITIONING …. SIDING",
            "16.0 . PATIO/DECK …. SIDING",
            "17.0 . DOOR & WINDOWS TRIM …. SIDING",
            "18.0 . SOFFIT & FASCIA …. SIDING",
            "19.0 . SDG ACCESSORIES …. SIDING",
            "20.0 . JOB CONDITIONS …. SIDING",
            "21.0 . DOWN SPOUTS & GUTTERS …. SIDING",
            "22.0 . ELECTRICAL ACCESSORIES …. SIDING",
            "23.0 . DEMO & DUMPSTER …. SIDING",
            "24.0 . FINAL CLN …. SIDING",
            "25.0 . GARAGE …. SIDING",
            "26.0 . ROOF ACCESORIES …. SIDING"
            ""
        ]

    # ── Assemble in priority order ───────────────────────────────────────────
    template_priority = {
        'readings_8000': 1,
        'readings_9000': 1,
        'siding_10000': 1,    # 10000s Siding
        'readings': 1,        # legacy: 8000s + 9000s combined
        'extended': 2,
        'basic': 3,
        'readings default': 5,
        'job_types': 0,
    }
    sorted_tpls = sorted(selected_templates, key=lambda x: template_priority.get(x, 99))

    all_entries = []
    for tpl in sorted_tpls:
        if tpl == 'basic':
            all_entries.extend(basic_entries)
        elif tpl == 'readings_8000':
            all_entries.extend(_build_8000s())
        elif tpl == 'readings_9000':
            all_entries.extend(_build_9000s())
        elif tpl == 'siding_10000':
            all_entries.extend(_build_siding())
        elif tpl == 'readings':
            # legacy: combined 8000s + 9000s
            all_entries.extend(_build_8000s())
            all_entries.extend(_build_9000s())
        elif tpl == 'readings default':
            all_entries.extend(_build_readings_default())

    return all_entries


# ──────────────────────────────────────────────────────────────────────────────
# Encircle – push rooms only to an EXISTING Encircle claim (correction tool)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def push_rooms_to_encircle_task(self, client_id, encircle_claim_id, selected_templates=None):
    """
    Push room entries from a local Client to a specific existing Encircle claim,
    without touching the claim's metadata.  Use this to correct a claim that was
    previously pushed with wrong rooms.

    Args:
        client_id:         UUID/int of the local Client record.
        encircle_claim_id: The target Encircle claim id (string).
        selected_templates: list of template keys — same as push_claim_to_encircle_task.
                            Defaults to ['basic', 'readings'].
    """
    from .models import Client, Room
    from .encircle_client import EncircleAPIClient

    if not selected_templates:
        selected_templates = ['basic', 'readings']

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        logger.error(f"push_rooms_to_encircle_task: Client {client_id} not found")
        return {'success': False, 'error': f'Client {client_id} not found'}

    api = EncircleAPIClient()

    # ── Build room entry list ─────────────────────────────────────────────────
    # Prefer pre-generated numbered entries; fall back to old compute path.
    encircle_entries_qs = (
        Room.objects
        .filter(client=client, is_encircle_entry=True)
        .order_by('sequence')
    )

    if encircle_entries_qs.exists():
        all_entries = list(encircle_entries_qs.values_list('room_name', flat=True))
        logger.info(
            f"push_rooms_to_encircle_task: using {len(all_entries)} pre-generated entries "
            f"for client {client_id}"
        )
    else:
        rooms_qs = (
            Room.objects
            .filter(client=client, is_encircle_entry=False)
            .prefetch_related('work_type_values__work_type')
            .order_by('sequence')
        )
        room_names = []
        configs = {}
        for room in rooms_qs:
            room_names.append(room.room_name)
            room_config = {}
            for wtv in room.work_type_values.all():
                room_config[wtv.work_type.work_type_id] = wtv.value_type
            configs[room.room_name] = room_config

        if not room_names:
            return {'success': False, 'error': f'Client {client_id} has no rooms'}

        all_entries = build_room_entries(room_names, configs, selected_templates)

    # ── Push to the specified Encircle claim ──────────────────────────────────
    rooms_pushed = 0
    try:
        structure = api.get_or_create_default_structure(encircle_claim_id)
        structure_id = str(structure.get('id') or structure.get('structure_id') or '')
        if not structure_id:
            raise ValueError(f"Could not resolve structure id from: {structure}")

        logger.info(
            f"push_rooms_to_encircle_task: pushing {len(all_entries)} entries "
            f"to Encircle claim {encircle_claim_id} (client {client_id})"
        )
        for entry in all_entries:
            try:
                api.create_room(encircle_claim_id, structure_id, {'name': entry})
                rooms_pushed += 1
            except Exception as room_exc:
                logger.warning(
                    f"Could not push room '{entry[:60]}' to claim {encircle_claim_id}: {room_exc}"
                )
    except Exception as exc:
        logger.error(
            f"push_rooms_to_encircle_task failed for claim {encircle_claim_id}: {exc}",
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60)

    logger.info(
        f"push_rooms_to_encircle_task done: client={client_id}, "
        f"encircle_claim_id={encircle_claim_id}, rooms_pushed={rooms_pushed}"
    )
    return {
        'success': True,
        'encircle_claim_id': encircle_claim_id,
        'rooms_pushed': rooms_pushed,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Encircle – migrate photos from old rooms → new rooms, then delete old rooms
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def migrate_encircle_rooms_task(self, encircle_claim_id):
    """
    For a given Encircle claim, clean up the old-format DAY0 rooms:

    OLD format (to delete):
        "8101 TRAVEL .0 …. FOYER ... DAY0 MC READINGS .."
        "8103 LOS .0 …. DINING ROOM ... DAY0 MC READINGS .."
        Detected by: name contains 'DAY0' or 'DAY # 0' (case-insensitive)

    NEW format (to keep):
        "8001.0 . FOYER … MC READINGS STABILIZATION  TRAVEL"
        "8101.1 . FOYER    ...  DAY1    MC READINGS ..   TRAVEL"
        These do NOT contain 'DAY0'.

    For each old room with media:
        1. Extract the embedded room name from between '….' and '...' in the old entry.
        2. Find the best-matching new room: the lowest-numbered new room whose
           name contains the extracted room name tokens (case-insensitive).
        3. Move all media there.
    Then delete the old room.

    Returns:
        {
            'success': True,
            'old_rooms_found': N,
            'old_rooms_deleted': N,
            'photos_moved': N,
            'photos_failed': N,
            'unmatched_rooms': ['old room name', ...],
        }
    """
    import re as _re
    from .encircle_client import EncircleAPIClient

    api = EncircleAPIClient()

    # ── 1. Get structure ──────────────────────────────────────────────────────
    try:
        structure = api.get_or_create_default_structure(encircle_claim_id)
        structure_id = str(structure.get('id') or structure.get('structure_id') or '')
        if not structure_id:
            raise ValueError(f"Could not resolve structure id: {structure}")
    except Exception as exc:
        logger.error(f"migrate_encircle_rooms_task: cannot get structure — {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)

    # ── 2. List all rooms ─────────────────────────────────────────────────────
    try:
        rooms_resp = api.get_claim_rooms(encircle_claim_id, structure_id)
        all_rooms = rooms_resp.get('list', []) if isinstance(rooms_resp, dict) else []
    except Exception as exc:
        logger.error(f"migrate_encircle_rooms_task: cannot list rooms — {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)

    # ── 3. Partition: old = contains DAY0 / DAY # 0, new = everything else ───
    _day0_re = _re.compile(r'DAY\s*#?\s*0', _re.IGNORECASE)
    old_rooms = [r for r in all_rooms if _day0_re.search(r.get('name', ''))]
    new_rooms = [r for r in all_rooms if not _day0_re.search(r.get('name', ''))]

    logger.info(
        f"migrate_encircle_rooms_task: claim={encircle_claim_id}, "
        f"old(DAY0)={len(old_rooms)}, new={len(new_rooms)}"
    )

    if not old_rooms:
        return {
            'success': True,
            'message': 'No old DAY0-format rooms found — nothing to migrate.',
            'old_rooms_found': 0,
            'old_rooms_deleted': 0,
            'photos_moved': 0,
            'photos_failed': 0,
            'unmatched_rooms': [],
        }

    def _norm_tokens(s):
        """Return sorted uppercase word tokens, stripping punctuation/ellipsis."""
        return _re.sub(r'[^A-Z0-9]', ' ', s.upper()).split()

    def _extract_room_name(old_name):
        """
        Extract the embedded local room name from the old DAY0 entry.
        Old format:  "8101 TRAVEL .0 …. FOYER ... DAY0 MC READINGS .."
        The room name sits between the first '….' (or '....') and ' ...'
        e.g. → "FOYER"
        """
        # Match text between …. / .... and the following ' ...' or ' DAY'
        m = _re.search(r'[…\.]{2,}\s+(.+?)\s+(?:\.{3}|DAY)', old_name, _re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return ''

    # ── 4. Move photos & collect unmatched ───────────────────────────────────
    photos_moved    = 0
    photos_failed   = 0
    unmatched_rooms = []
    old_rooms_deleted = 0

    for old_room in old_rooms:
        old_id   = str(old_room.get('id', ''))
        old_name = old_room.get('name', '').strip()

        # -- fetch media for this old room --
        try:
            media_items = api.get_room_media(encircle_claim_id, structure_id, old_id)
        except Exception as exc:
            logger.warning(f"migrate: cannot fetch media for old room '{old_name}' ({old_id}): {exc}")
            media_items = []

        if media_items:
            # Extract the core room name from the old entry
            extracted = _extract_room_name(old_name)
            extracted_tokens = _norm_tokens(extracted) if extracted else []

            # Find the first new room whose name contains all extracted tokens
            target_room = None
            if extracted_tokens:
                for new_room in new_rooms:
                    new_tokens = _norm_tokens(new_room.get('name', ''))
                    if all(tok in new_tokens for tok in extracted_tokens):
                        target_room = new_room
                        break

            if target_room is None:
                logger.warning(
                    f"migrate: no matching new room for old room '{old_name}' "
                    f"(extracted: '{extracted}') — {len(media_items)} item(s) unmatched"
                )
                unmatched_rooms.append(old_name)
            else:
                target_id = str(target_room.get('id', ''))
                logger.info(
                    f"migrate: moving {len(media_items)} item(s) "
                    f"'{old_name}' → '{target_room.get('name', '')}'"
                )
                for media in media_items:
                    media_id = str(media.get('id', ''))
                    try:
                        api.reassign_media(encircle_claim_id, media_id, target_id)
                        photos_moved += 1
                    except Exception as exc:
                        logger.warning(
                            f"migrate: failed to move media {media_id} "
                            f"from '{old_name}': {exc}"
                        )
                        photos_failed += 1

        # -- delete the old room regardless of whether it had media --
        try:
            api.delete_room(encircle_claim_id, structure_id, old_id)
            old_rooms_deleted += 1
            logger.info(f"migrate: deleted old room '{old_name}' ({old_id})")
        except Exception as exc:
            logger.warning(f"migrate: failed to delete old room '{old_name}' ({old_id}): {exc}")

    logger.info(
        f"migrate_encircle_rooms_task done: claim={encircle_claim_id}, "
        f"deleted={old_rooms_deleted}/{len(old_rooms)}, "
        f"photos_moved={photos_moved}, photos_failed={photos_failed}, "
        f"unmatched={unmatched_rooms}"
    )
    return {
        'success': True,
        'old_rooms_found': len(old_rooms),
        'old_rooms_deleted': old_rooms_deleted,
        'photos_moved': photos_moved,
        'photos_failed': photos_failed,
        'unmatched_rooms': unmatched_rooms,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Encircle – duplicate a claim (for safe test-before-run workflow)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2)
def duplicate_encircle_claim_task(self, source_claim_id, suffix='(TEST COPY)'):
    """
    Create a duplicate of an existing Encircle claim so migrations can be
    tested on the copy before touching the real claim.

    Steps:
      1. Fetch source claim metadata.
      2. Create a new claim with the same fields but policyholder_name
         suffixed with `suffix` (default: '(TEST COPY)').
      3. Copy every room name from the source structure into the new claim.

    Returns:
        {
            'success': True,
            'source_claim_id': ...,
            'new_claim_id': ...,
            'new_claim_name': ...,
            'rooms_copied': N,
        }
    """
    from .encircle_client import EncircleAPIClient

    api = EncircleAPIClient()

    # ── 1. Fetch source claim ─────────────────────────────────────────────────
    try:
        src = api.get_claim_details(source_claim_id)
    except Exception as exc:
        logger.error(f"duplicate_encircle_claim_task: cannot fetch source claim {source_claim_id} — {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)

    # ── 2. Build new claim payload ────────────────────────────────────────────
    base_name = (src.get('policyholder_name') or '').strip()
    new_name  = f"{base_name} {suffix}".strip()

    new_payload = {
        'policyholder_name':      new_name,
        'full_address':           src.get('full_address') or '',
        'type_of_loss':           src.get('type_of_loss') or 'Other',
        'date_of_loss':           src.get('date_of_loss') or '',
        'adjuster_name':          src.get('adjuster_name') or '',
        'insurance_company_name': src.get('insurance_company_name') or '',
        'policy_number':          src.get('policy_number') or '',
    }
    new_payload = {k: v for k, v in new_payload.items() if v}

    try:
        new_claim = api.create_claim(new_payload)
        new_claim_id = str(new_claim.get('id') or '')
        if not new_claim_id:
            raise ValueError(f"No id returned: {new_claim}")
        logger.info(f"duplicate_encircle_claim_task: created new claim {new_claim_id} ('{new_name}')")
    except Exception as exc:
        logger.error(f"duplicate_encircle_claim_task: create_claim failed — {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)

    # ── 3. Copy rooms from source ─────────────────────────────────────────────
    rooms_copied = 0
    try:
        src_structure = api.get_or_create_default_structure(source_claim_id)
        src_structure_id = str(src_structure.get('id') or '')

        src_rooms_resp = api.get_claim_rooms(source_claim_id, src_structure_id)
        src_rooms = src_rooms_resp.get('list', []) if isinstance(src_rooms_resp, dict) else []

        dst_structure = api.get_or_create_default_structure(new_claim_id)
        dst_structure_id = str(dst_structure.get('id') or '')

        for room in src_rooms:
            room_name = (room.get('name') or '').strip()
            if not room_name:
                continue
            try:
                api.create_room(new_claim_id, dst_structure_id, {'name': room_name})
                rooms_copied += 1
            except Exception as exc:
                logger.warning(f"duplicate_encircle_claim_task: failed to copy room '{room_name}': {exc}")
    except Exception as exc:
        logger.warning(f"duplicate_encircle_claim_task: room copy failed — {exc}", exc_info=True)

    logger.info(
        f"duplicate_encircle_claim_task done: source={source_claim_id} → "
        f"new={new_claim_id}, rooms_copied={rooms_copied}"
    )
    return {
        'success': True,
        'source_claim_id': source_claim_id,
        'new_claim_id': new_claim_id,
        'new_claim_name': new_name,
        'rooms_copied': rooms_copied,
    }


# ==================== TEMPLATES LINK EMAIL TASK ====================

@shared_task(bind=True, max_retries=3)
def send_templates_link_task(self, client_id):
    """
    Email a signed download link for this claim's Excel templates to the
    standard notification list.

    Triggered automatically at claim creation alongside the labels task.
    Recipients can click the link — no login required — to browse and
    download every Excel file generated for the claim.

    Uses Django's signing framework so the token is tamper-proof and
    identifies the claim without exposing the DB primary key directly.
    """
    import os
    from django.conf import settings
    from django.core.mail import EmailMessage
    from django.core.signing import dumps as signing_dumps

    RECIPIENTS = ['galaxielsaga@gmail.com', 'wsbjoe9@gmail.com']
    SITE_URL = getattr(settings, 'SITE_URL', 'https://claimetapp.com')

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        logger.error(f"send_templates_link_task: client {client_id} not found")
        return {'success': False, 'error': 'Client not found'}

    try:
        # Sign the claim id — tamper-proof, no expiry
        token = signing_dumps(client_id, salt='claim-templates-link')
        templates_url = f"{SITE_URL}/claims/templates/{token}/"

        claim_name    = client.pOwner    or f'Claim {client_id}'
        claim_address = client.pAddress  or '—'
        claim_number  = client.claimNumber or '—'
        cause         = client.causeOfLoss or '—'

        subject = f'[CLAIM TEMPLATES READY] {claim_name}'

        body = f"""
<html>
<body style="font-family:Arial,sans-serif;color:#1e293b;max-width:600px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#1e40af,#0ea5e9);border-radius:12px;
              padding:28px 32px;color:#fff;margin-bottom:24px;">
    <h2 style="margin:0 0 6px;font-size:20px;">📂 Claim Templates Ready</h2>
    <p style="margin:0;opacity:.85;font-size:14px;">
      Excel templates have been generated and populated for the claim below.
    </p>
  </div>

  <div style="background:#f8fafc;border-radius:10px;padding:20px 24px;
              margin-bottom:24px;border:1px solid #e2e8f0;">
    <table style="width:100%;font-size:14px;border-collapse:collapse;">
      <tr><td style="padding:5px 0;color:#64748b;width:130px;">Insured</td>
          <td style="padding:5px 0;font-weight:700;">{claim_name}</td></tr>
      <tr><td style="padding:5px 0;color:#64748b;">Address</td>
          <td style="padding:5px 0;">{claim_address}</td></tr>
      <tr><td style="padding:5px 0;color:#64748b;">Claim #</td>
          <td style="padding:5px 0;font-family:monospace;">{claim_number}</td></tr>
      <tr><td style="padding:5px 0;color:#64748b;">Cause of Loss</td>
          <td style="padding:5px 0;">{cause}</td></tr>
    </table>
  </div>

  <div style="text-align:center;margin:32px 0;">
    <a href="{templates_url}"
       style="display:inline-block;background:#1e40af;color:#fff;
              text-decoration:none;padding:16px 36px;border-radius:10px;
              font-size:16px;font-weight:700;letter-spacing:.3px;">
      📥 View &amp; Download Templates
    </a>
    <p style="font-size:12px;color:#94a3b8;margin-top:12px;">
      No login required — link is secure and specific to this claim.
    </p>
  </div>

  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
  <p style="font-size:11px;color:#94a3b8;text-align:center;">
    Automated notification · Claimet App
  </p>

</body>
</html>
"""

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=RECIPIENTS,
        )
        email.content_subtype = 'html'
        email.send()

        logger.info(
            f"send_templates_link_task: sent for client {client_id} "
            f"({claim_name}) to {RECIPIENTS}"
        )
        return {
            'success': True,
            'client_id': client_id,
            'recipients': RECIPIENTS,
            'templates_url': templates_url,
        }

    except Exception as exc:
        logger.error(
            f"send_templates_link_task: failed for client {client_id}: {exc}",
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60)