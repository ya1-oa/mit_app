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
    rooms = client.rooms.all().prefetch_related('work_type_values__work_type').order_by('sequence')
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
    rooms = client.rooms.all().order_by('sequence')
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
    rooms = client.rooms.all().order_by('sequence')
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


# ==================== LABEL GENERATION AND EMAIL TASKS ====================

@shared_task(bind=True, max_retries=3)
def generate_and_email_labels_task(self, client_id):
    """
    Generate wall labels and box labels for all rooms in a claim.

    Actions:
    - Generates a combined Wall Labels PDF (all rooms, one page each)
    - Generates a combined Box Labels PDF (all rooms, one page each)
    - Saves both PDFs to the claim's server folder under a 'Labels' subfolder
    - Emails both PDFs to wsbjoe9@gmail.com and ALL_TEAM_EMAILS

    Triggered automatically when a new claim is created.
    """
    import re
    import io
    import os
    from django.conf import settings
    from django.core.mail import EmailMessage
    from .claim_folder_utils import get_claims_root

    FIXED_RECIPIENT = 'wsbjoe9@gmail.com'

    try:
        client = Client.objects.get(id=client_id)
        rooms = client.rooms.all().order_by('sequence')

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
        team_emails = getattr(settings, 'ALL_TEAM_EMAILS', [])
        recipients = list({FIXED_RECIPIENT} | set(team_emails))  # always include fixed

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
    """Create a combined PDF with wall labels for all rooms."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch as INCH
    from reportlab.lib import colors

    LABEL_WIDTH = 4 * INCH
    LABEL_HEIGHT = 3 * INCH

    WALL_COPIES = 2

    c = canvas.Canvas(buffer, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))

    total_labels = len(rooms) * WALL_COPIES
    label_count = 0

    for room in rooms:
        room_name = room.room_name
        for _ in range(WALL_COPIES):
            c.setFont("Helvetica-Bold", 28)
            c.drawCentredString(LABEL_WIDTH / 2, LABEL_HEIGHT - 0.5 * INCH, room_name)

            center_y = LABEL_HEIGHT / 2 - 0.1 * INCH
            center_x = LABEL_WIDTH / 2

            c.setFont("Helvetica", 10)
            c.drawCentredString(center_x - 1.2 * INCH, center_y, "W=1")

            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(center_x, center_y + 0.3 * INCH, "CENTER")
            c.line(center_x, center_y, center_x, center_y + 0.2 * INCH)
            c.line(center_x - 0.05 * INCH, center_y + 0.15 * INCH, center_x, center_y + 0.2 * INCH)
            c.line(center_x + 0.05 * INCH, center_y + 0.15 * INCH, center_x, center_y + 0.2 * INCH)

            c.setFont("Helvetica", 10)
            c.drawCentredString(center_x + 1.2 * INCH, center_y, "W=3")
            c.drawCentredString(center_x, center_y - 0.5 * INCH, "W=4")

            c.setStrokeColor(colors.blue)
            c.setLineWidth(2)
            c.arc(center_x - 1.5 * INCH, center_y - 0.15 * INCH,
                  center_x - 0.9 * INCH, center_y + 0.15 * INCH,
                  startAng=30, extent=120)
            c.arc(center_x + 0.9 * INCH, center_y - 0.15 * INCH,
                  center_x + 1.5 * INCH, center_y + 0.15 * INCH,
                  startAng=30, extent=120)

            c.setStrokeColor(colors.black)
            c.setLineWidth(1)

            c.setDash(3, 3)
            c.line(0.5 * INCH, LABEL_HEIGHT - 0.9 * INCH,
                   LABEL_WIDTH - 0.5 * INCH, LABEL_HEIGHT - 0.9 * INCH)
            c.setDash()

            label_count += 1
            if label_count < total_labels:
                c.showPage()

    c.save()


def _create_combined_box_labels_pdf(buffer, client, rooms):
    """Create a combined PDF with box/room labels for all rooms."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch as INCH
    from reportlab.lib import colors

    LABEL_WIDTH = 4 * INCH
    LABEL_HEIGHT = 3 * INCH

    BOX_COPIES = 20

    c = canvas.Canvas(buffer, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
    claim_name = client.pOwner or 'Unknown'

    total_labels = len(rooms) * BOX_COPIES
    label_count = 0

    for room in rooms:
        room_name = room.room_name
        for _ in range(BOX_COPIES):
            c.setFont("Helvetica-Bold", 36)
            c.drawCentredString(LABEL_WIDTH / 2, LABEL_HEIGHT / 2 + 0.2 * INCH, room_name.upper())

            c.setFont("Helvetica", 14)
            c.drawCentredString(LABEL_WIDTH / 2, LABEL_HEIGHT / 2 - 0.4 * INCH, claim_name)

            c.setStrokeColor(colors.black)
            c.setLineWidth(2)
            c.rect(0.2 * INCH, 0.2 * INCH, LABEL_WIDTH - 0.4 * INCH, LABEL_HEIGHT - 0.4 * INCH)

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
# Encircle GreenField – push a local claim (+ rooms) to Encircle
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def push_claim_to_encircle_task(self, client_id, selected_templates=None):
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
    from .views import EncircleAPIClient

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

    # ── 3. Build room list from local rooms ───────────────────────────────
    rooms_qs = (
        Room.objects
        .filter(client=client)
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

    rooms_pushed = 0

    # Normalise selected_templates
    if not selected_templates:
        selected_templates = []
    else:
        selected_templates = list(selected_templates)

    if room_names:
        # ── 4. Build room entries for every selected template ────────────
        work_type_descs = {
            100: "= … JOB/ROOMS OVERVIEW PICS ..",
            200: "….. SOURCE of LOSS PICS …..",
            300: "….. C.P.S. …...",
            400: "….. PPR …..",
            500: "…… DMO = DEMOLITION …....",
            600: "… WTR MITIGATION EQUIPMENT & W.I.P . ...",
            700: "… HMR = HAZARDOUS MATERIALS ...",
        }
        section_labels = {
            100: "100 .... = ... JOB/ROOMS OVERVIEW PICS .. ==========================",
            200: "200 .... ..... SOURCE of LOSS PICS ..... ===========================",
            300: "300 .... ..... C.P.S. ...... =======================================",
            400: "400 .... PPR ===================================================",
            500: "500 .... ...... DMO = DEMOLITION ....... ===========================",
            600: "600 . WTR MITIGATION EQUIPMENT & W.I.P. ============================",
            700: "700 . HMR = HAZARDOUS MATERIALS ====================================",
        }

        # --- basic (100-700s) ---
        basic_entries = [
            "0.0001 ….. JOBSITE VERIFICATION",
            "0.0002 . MECHANICALS = WATER METER READING & PLUMBING REPORT/INVOICE",
            "0.0003 . MECHANICALS = ELECTRICAL HAZARDS",
            "0.0004 . EXT DAMAGE IF APPLICABLE ROOF TARPS",
            "1997 . LEAD & HMR TESTING LAB RESULTS",
            "1998 . KITCHEN CABINETS SIZES U & L =LF/ CT = SF; APPLIANCES",
            "1999 . BATHROOM FIXTURES CAB SIZE & FIXTURES & TYPE",
        ]
        for work_type in [100, 200, 300, 400, 500, 600, 700]:
            basic_entries.append(section_labels[work_type])
            for idx, room_name in enumerate(room_names):
                room_number = work_type + idx + 1
                room_cfg = configs.get(room_name, {})
                config_value = room_cfg.get(100, room_cfg.get('100', '.'))
                display_value = "" if config_value in ('.', '', None) else config_value
                prefix = f"{display_value} " if display_value else ""
                entry = f"{room_number} {prefix}…. {room_name} {work_type_descs[work_type]}"
                basic_entries.append(entry)
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
        basic_entries.extend([
            "9998.0 . REBUILD OVERVIEW WORK IN PROGRESS.......WIP",
            "9999.0 . REBUILD INTERIOR COMPLETED WORK",
        ])

        # --- readings (8000-9000s MC Day Readings) ---
        def _build_readings_entries():
            readings_section_labels = {
                8100: "8100.0 . ..... DAY 1 MC READINGS ..... ======================",
                8200: "8200.0 . ..... DAY 2 MC READINGS ..... ======================",
                8300: "8300.0 . ..... DAY 3 MC READINGS ..... ======================",
                8400: "8400.0 . ..... DAY 4 MC READINGS ..... ======================",
            }
            entries = []
            for work_type in [8100, 8200, 8300, 8400]:
                entries.append(readings_section_labels[work_type])
                for idx, room_name in enumerate(room_names):
                    room_number = work_type + idx + 1
                    room_cfg = configs.get(room_name, {})
                    config_value = room_cfg.get(100, room_cfg.get('100', '.'))
                    display_value = "" if config_value in ('.', '', None) else config_value
                    day_num = str(work_type)[3]
                    desc = f"  ...  DAY{day_num}    MC READINGS .."
                    prefix = f"{display_value} " if display_value else ""
                    entries.append(f"{room_number} {prefix}.{day_num} …. {room_name} {desc}")
            entries.append("9000 RH &T & GPP  DRY CHAMBERS [DC] . READINGS ==================")
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

        # --- readings default (70000s Stabilization) ---
        def _build_readings_default_entries():
            entries = ["70000 ….. ======= DAY # 0  …..  MC READINGS STABILIZATION ==============="]
            for idx, room_name in enumerate(room_names):
                room_number = 70101 + idx
                room_cfg = configs.get(room_name, {})
                config_value = room_cfg.get(100, room_cfg.get('100', '.'))
                display_value = "" if config_value in ('.', '', None) else config_value
                suffix = f" … {display_value}" if display_value else ""
                entries.append(
                    f"{room_number} …. {room_name} … DAY # 0  … MC READINGS STABILIZATION{suffix}"
                )
            return entries

        # ── 4. Push all selected templates as rooms directly into the Encircle claim ──
        # Build combined ordered entry list for all selected templates.
        # Priority order matches the original room list display.
        template_priority = {'readings': 1, 'extended': 2, 'basic': 3, 'readings default': 5, 'job_types': 0}
        sorted_templates = sorted(selected_templates, key=lambda x: template_priority.get(x, 99))

        all_entries = []
        for tpl in sorted_templates:
            if tpl == 'basic':
                all_entries.extend(basic_entries)
            elif tpl == 'readings':
                all_entries.extend(_build_readings_entries())
            elif tpl == 'readings default':
                all_entries.extend(_build_readings_default_entries())

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
            for entry in all_entries:
                try:
                    api.create_room(encircle_claim_id, structure_id, {'name': entry})
                    rooms_pushed += 1
                except Exception as room_exc:
                    logger.warning(
                        f"Could not push room '{entry[:60]}' to claim {encircle_claim_id}: {room_exc}"
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

    logger.info(
        f"push_claim_to_encircle_task done: client={client_id}, "
        f"encircle_claim_id={encircle_claim_id}, rooms_pushed={rooms_pushed}"
    )
    return {
        'success': True,
        'encircle_claim_id': encircle_claim_id,
        'rooms_pushed': rooms_pushed,
    }