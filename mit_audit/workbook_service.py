"""
mit_audit/workbook_service.py

Three responsibilities:
  1. copy_template_for_job()  — make a per-job copy of the MIT Day 3 template
  2. write_dimensions()       — fill room L/W/H into the Job Information sheet
  3. recalc_and_read_equipment() — trigger LibreOffice UNO recalc, then read
                                    the Total Equipment tab

Why LibreOffice for recalc?
  openpyxl cannot evaluate Excel formulas.  The Total Equipment tab totals are
  formula-driven (SUM / IF / VLOOKUP chains referencing the dimensions we just
  wrote).  LibreOffice UNO opens the workbook, recalculates every formula in
  memory, then saves — leaving a file openpyxl can re-open with data_only=True
  to read the computed values.

Fallback chain (mirrors docsAppR/tasks.py):
  1. UNO listener on port 2002         (preferred — zero corruption)
  2. LibreOffice subprocess            (slower but also zero corruption)
  3. raw openpyxl data_only read       (formulas show as None — may still work
                                        if the template ships with cached values)
"""
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default cell map used when MITDay3Config.dimension_cell_map is empty.
# Update these once you have mapped the actual MIT Day 3 template.
# ---------------------------------------------------------------------------
DEFAULT_DIMENSION_MAP = {
    'job_info_sheet':  'Job Information',
    'room_start_row':  8,        # first row containing a room name
    'room_name_col':   'B',      # column B: room label
    'length_col':      'C',      # column C: length (ft)
    'width_col':       'D',      # column D: width (ft)
    'height_col':      'E',      # column E: height (ft)
    'max_rows':        50,       # stop scanning after this many rows
}

# Equipment type keywords for auto-categorisation when reading Total Equipment.
_CATEGORY_KEYWORDS = {
    'dehumidifier':  ['dehumid', 'lgr', 'desiccant'],
    'air_cleaner':   ['air clean', 'scrubber', 'hepa', 'filtration', 'negative air'],
    'zipper_wall':   ['zipper', 'containment', 'poly barrier'],
    'double_zipper': ['double zipper', 'dbl zipper'],
    'blower':        ['blower', 'air mover', 'axial', 'centrifugal', 'fan'],
    'wall_cavity':   ['wall cavity', 'injectidry', 'wall dry'],
    'floor_drying':  ['floor mat', 'floor dry', 'drying mat', 'extraction mat'],
    'hydroxyl':      ['hydroxyl', 'dodhy', 'odor counteract'],
    'heater':        ['heater', 'heat'],
}

# Stabilization items require dedicated stabilization photos showing the equipment
# connected and running — not just present in the room.
_STABILIZATION_TYPES = {'dehumidifier', 'air_cleaner', 'zipper_wall', 'double_zipper', 'hydroxyl'}


def _categorise(name: str) -> tuple[str, bool]:
    """Return (category, requires_stabilization_photo) for a display name."""
    lower = name.lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return cat, cat in _STABILIZATION_TYPES
    return 'other', False


def get_template_path() -> Path | None:
    """
    Return the absolute path to the MIT Day 3 template, or None if not configured.
    Checks MITDay3Config first; falls back to MEDIA_ROOT/mit_templates/MIT_Day3.xlsx.
    """
    from mit_audit.models import MITDay3Config
    cfg = MITDay3Config.get()
    if cfg.template_path:
        p = Path(settings.MEDIA_ROOT) / cfg.template_path
        if p.exists():
            return p
        logger.warning('MIT template configured but not found: %s', p)
    # Default fallback location
    fallback = Path(settings.MEDIA_ROOT) / 'mit_templates' / 'MIT_Day3.xlsx'
    if fallback.exists():
        return fallback
    return None


def copy_template_for_job(audit_id: int) -> str:
    """
    Copy the MIT Day 3 template to a job-specific location and return the
    absolute path.  Raises FileNotFoundError if the template is missing.
    """
    template = get_template_path()
    if not template:
        raise FileNotFoundError(
            'MIT Day 3 template workbook not found.  '
            'Upload it via Admin → MIT Day 3 Config → template_path.'
        )
    dest_dir = Path(settings.MEDIA_ROOT) / 'mit_audits' / str(audit_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f'MIT_Day3_Job_{audit_id}.xlsx'
    shutil.copy2(template, dest)
    logger.info('[MIT] Copied template → %s', dest)
    return str(dest)


def write_dimensions(workbook_path: str, room_dimensions) -> list[dict]:
    """
    Write approved room dimensions into the Job Information sheet.

    Args:
        workbook_path:   Absolute path to the job workbook copy.
        room_dimensions: QuerySet or list of MITRoomDimension instances
                         (only those with approved=True are written).

    Returns:
        List of dicts: [{ 'room_name', 'row', 'written': True/False }, ...]
    """
    import openpyxl
    from mit_audit.models import MITDay3Config
    cfg_obj = MITDay3Config.get()
    cell_map = cfg_obj.dimension_cell_map or DEFAULT_DIMENSION_MAP

    sheet_name  = cell_map.get('job_info_sheet', DEFAULT_DIMENSION_MAP['job_info_sheet'])
    start_row   = int(cell_map.get('room_start_row', DEFAULT_DIMENSION_MAP['room_start_row']))
    name_col    = cell_map.get('room_name_col',  DEFAULT_DIMENSION_MAP['room_name_col'])
    length_col  = cell_map.get('length_col',     DEFAULT_DIMENSION_MAP['length_col'])
    width_col   = cell_map.get('width_col',      DEFAULT_DIMENSION_MAP['width_col'])
    height_col  = cell_map.get('height_col',     DEFAULT_DIMENSION_MAP['height_col'])
    max_rows    = int(cell_map.get('max_rows',   DEFAULT_DIMENSION_MAP['max_rows']))

    approved = [d for d in room_dimensions if d.approved]
    if not approved:
        logger.warning('[MIT] No approved dimensions to write for %s', workbook_path)
        return []

    wb = openpyxl.load_workbook(workbook_path)
    if sheet_name not in wb.sheetnames:
        # Try the first sheet as a fallback
        ws = wb.active
        logger.warning('[MIT] Sheet "%s" not found — writing to active sheet "%s"',
                       sheet_name, ws.title)
    else:
        ws = wb[sheet_name]

    results = []
    # Build a map from normalised room name → workbook row (scan existing labels)
    existing_rows: dict[str, int] = {}
    for r in range(start_row, start_row + max_rows):
        cell_val = ws[f'{name_col}{r}'].value
        if cell_val:
            existing_rows[str(cell_val).strip().upper()] = r

    written_rows = set()
    for dim in approved:
        target_row = existing_rows.get(dim.room_name.strip().upper())
        if target_row is None:
            # Append to the next free row
            target_row = start_row + max_rows + len(written_rows)

        ws[f'{length_col}{target_row}'] = float(dim.length) if dim.length else None
        ws[f'{width_col}{target_row}']  = float(dim.width)  if dim.width  else None
        ws[f'{height_col}{target_row}'] = float(dim.height) if dim.height else None

        dim.workbook_row = target_row
        dim.save(update_fields=['workbook_row'])
        written_rows.add(target_row)
        results.append({'room_name': dim.room_name, 'row': target_row, 'written': True})
        logger.debug('[MIT] Wrote %s → row %d (L=%s W=%s H=%s)',
                     dim.room_name, target_row, dim.length, dim.width, dim.height)

    wb.save(workbook_path)
    logger.info('[MIT] Saved workbook with %d room dimensions → %s',
                len(results), workbook_path)
    return results


def recalculate_via_uno(workbook_path: str) -> bool:
    """
    Open the workbook in the persistent LibreOffice UNO listener (port 2002),
    trigger a full recalculation, then save back to the same path.
    Returns True on success, False if UNO is unavailable (caller should fallback).
    """
    try:
        from docsAppR.lo_uno_service import _import_uno, _connect, _make_prop
        uno, PropertyValue, NoConnectException = _import_uno()
        desktop = _connect(uno, NoConnectException)

        file_url = uno.systemPathToFileUrl(workbook_path)
        props = [
            _make_prop('Hidden', True),
            _make_prop('MacroExecutionMode', 4),  # ALWAYS_EXECUTE_NO_WARN
        ]
        doc = desktop.loadComponentFromURL(file_url, '_blank', 0, tuple(props))

        # Force recalculation of all formula cells
        sheet_enum = doc.Sheets.createEnumeration()
        while sheet_enum.hasMoreElements():
            sheet = sheet_enum.nextElement()
            cell_enum = sheet.createEnumeration()
            while cell_enum.hasMoreElements():
                cell_range = cell_enum.nextElement()
                cell_inner = cell_range.createEnumeration()
                while cell_inner.hasMoreElements():
                    cell = cell_inner.nextElement()
                    try:
                        if hasattr(cell, 'FormulaResultType') and cell.FormulaResultType is not None:
                            pass  # accessing the attribute forces evaluation
                    except Exception:
                        pass

        doc.store()
        doc.close(True)
        logger.info('[MIT] LibreOffice UNO recalc + save complete: %s', workbook_path)
        return True
    except ImportError:
        logger.info('[MIT] UNO not importable — skipping UNO recalc')
        return False
    except Exception as exc:
        logger.warning('[MIT] UNO recalc failed (%s), will try subprocess fallback', exc)
        return False


def recalculate_via_subprocess(workbook_path: str) -> bool:
    """
    Fallback: call LibreOffice headless as a subprocess to convert and save.
    Converts xlsx → ods → xlsx (round-trip forces formula evaluation).
    Slower than UNO but does not require python3-uno.
    """
    lo_candidates = [
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/usr/local/bin/libreoffice',
        '/opt/libreoffice/program/soffice',
    ]
    lo_bin = next((c for c in lo_candidates if os.path.exists(c)), None)
    if not lo_bin:
        logger.warning('[MIT] LibreOffice binary not found — skipping subprocess recalc')
        return False

    src = Path(workbook_path)
    with tempfile.TemporaryDirectory() as tmp:
        # Convert to ods (forces recalc) then back to xlsx
        try:
            subprocess.run(
                [lo_bin, '--headless', '--convert-to', 'ods',
                 '--outdir', tmp, str(src)],
                timeout=120, check=True, capture_output=True
            )
            ods_path = Path(tmp) / (src.stem + '.ods')
            subprocess.run(
                [lo_bin, '--headless', '--convert-to', 'xlsx',
                 '--outdir', tmp, str(ods_path)],
                timeout=120, check=True, capture_output=True
            )
            out_xlsx = Path(tmp) / (src.stem + '.xlsx')
            if out_xlsx.exists():
                shutil.copy2(out_xlsx, workbook_path)
                logger.info('[MIT] Subprocess recalc complete: %s', workbook_path)
                return True
        except subprocess.TimeoutExpired:
            logger.error('[MIT] LibreOffice subprocess timed out')
        except subprocess.CalledProcessError as exc:
            logger.error('[MIT] LibreOffice subprocess error: %s', exc)
    return False


def read_total_equipment(workbook_path: str) -> list[dict]:
    """
    Read the Total Equipment tab and return one dict per row where qty > 0.

    Falls back gracefully: if formulas show as None (no recalc happened),
    the row is skipped — the caller must ensure recalc ran first.

    Returns:
        [
          {
            'display_name': 'LGR Dehumidifier',
            'equipment_type': 'dehumidifier',
            'category': 'dehumidifier',
            'required_quantity': 3,
            'source_sheet': 'Total Equipment',
            'workbook_row': 14,
            'workbook_cell': 'D14',
            'requires_stabilization_photo': True,
          },
          ...
        ]
    """
    import openpyxl
    from mit_audit.models import MITDay3Config

    cfg_obj   = MITDay3Config.get()
    sheet_name = cfg_obj.total_equipment_sheet or 'Total Equipment'
    cell_map   = cfg_obj.equipment_cell_map    # list of dicts, may be empty

    # Open data_only so cached / recalculated values are returned instead of formulas
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    if sheet_name not in wb.sheetnames:
        logger.warning('[MIT] Total Equipment sheet "%s" not found; sheets: %s',
                       sheet_name, wb.sheetnames)
        return []

    ws      = wb[sheet_name]
    results = []

    if cell_map:
        # Explicit map from admin config — most reliable
        for entry in cell_map:
            row      = int(entry['row'])
            name_col = entry.get('name_col', 'B')
            qty_col  = entry.get('qty_col', 'D')
            name_val = ws[f'{name_col}{row}'].value
            qty_val  = ws[f'{qty_col}{row}'].value
            if not name_val or qty_val is None:
                continue
            try:
                qty = int(qty_val)
            except (ValueError, TypeError):
                continue
            if qty <= 0:
                continue
            eq_type = entry.get('equipment_type', name_val)
            cat, stab = _categorise(str(name_val))
            results.append({
                'display_name':               str(name_val).strip(),
                'equipment_type':             eq_type,
                'category':                   cat,
                'required_quantity':          qty,
                'source_sheet':               sheet_name,
                'workbook_row':               row,
                'workbook_cell':              f'{qty_col}{row}',
                'requires_stabilization_photo': stab,
            })
    else:
        # Auto-scan mode: read every row, look for a name in col B and qty in col D.
        # This covers the common MIT Day 3 layout; adjust columns in the config if needed.
        for row in ws.iter_rows(min_row=2, values_only=False):
            name_cell = row[1] if len(row) > 1 else None   # column B (index 1)
            qty_cell  = row[3] if len(row) > 3 else None   # column D (index 3)
            if not name_cell or not qty_cell:
                continue
            name_val = name_cell.value
            qty_val  = qty_cell.value
            if not name_val or qty_val is None:
                continue
            try:
                qty = int(float(qty_val))
            except (ValueError, TypeError):
                continue
            if qty <= 0:
                continue
            cat, stab = _categorise(str(name_val))
            results.append({
                'display_name':               str(name_val).strip(),
                'equipment_type':             str(name_val).strip().lower().replace(' ', '_'),
                'category':                   cat,
                'required_quantity':          qty,
                'source_sheet':               sheet_name,
                'workbook_row':               name_cell.row,
                'workbook_cell':              qty_cell.coordinate,
                'requires_stabilization_photo': stab,
            })

    logger.info('[MIT] Read %d equipment items (qty > 0) from %s', len(results), workbook_path)
    return results
