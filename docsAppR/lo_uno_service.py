# docsAppR/lo_uno_service.py
"""
LibreOffice UNO bridge for native Excel population.

Connects to a persistent LibreOffice instance running in headless listener
mode (systemd service on port 2002). Populates jobinfo(2) Column C via the
UNO API — zero ZIP surgery, zero repair prompts, VBA/macros/formulas intact.

Fallback chain in tasks.py:
  1. UNO listener  (this module — preferred, zero corruption)
  2. LO subprocess (lo_populate.py — also zero corruption but slower)
  3. XML surgery   (pure regex — works without LO, fixed regex in tasks.py)

Setup:
  sudo apt install libreoffice python3-uno
  sudo systemctl enable --now libreoffice-uno.service
"""

import logging
import os
import time
from collections import deque

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection parameters — override via Django settings or env vars
# ---------------------------------------------------------------------------
UNO_HOST = os.environ.get('UNO_HOST', '127.0.0.1')
UNO_PORT = int(os.environ.get('UNO_PORT', '2002'))
UNO_CONNECT_TIMEOUT = int(os.environ.get('UNO_CONNECT_TIMEOUT', '10'))
UNO_MAX_RETRIES = int(os.environ.get('UNO_MAX_RETRIES', '3'))


def _import_uno():
    """
    Import uno and related types. Raises ImportError if python3-uno
    is not installed or not visible from this interpreter.

    If you're in a virtualenv, it must have been created with
    --system-site-packages, or uno won't be importable.
    """
    import uno  # noqa: F811
    from com.sun.star.beans import PropertyValue  # noqa: F811
    from com.sun.star.connection import NoConnectException  # noqa: F811
    return uno, PropertyValue, NoConnectException


def is_available():
    """
    Quick check: can we import uno AND connect to the listener?
    Returns True/False without raising.
    """
    try:
        uno, _, NoConnectException = _import_uno()
        desktop = _connect(uno, NoConnectException, retries=1, timeout=3)
        return desktop is not None
    except Exception:
        return False


def _connect(uno, NoConnectException, retries=None, timeout=None):
    """
    Connect to the running LibreOffice listener.

    Returns the Desktop object, or raises RuntimeError after retries.
    """
    retries = retries if retries is not None else UNO_MAX_RETRIES
    timeout = timeout if timeout is not None else UNO_CONNECT_TIMEOUT

    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )

    url = (
        f"uno:socket,host={UNO_HOST},port={UNO_PORT};"
        f"urp;StarOffice.ComponentContext"
    )

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            ctx = resolver.resolve(url)
            smgr = ctx.ServiceManager
            desktop = smgr.createInstanceWithContext(
                "com.sun.star.frame.Desktop", ctx
            )
            if desktop is not None:
                return desktop
        except NoConnectException as e:
            last_err = e
            if attempt < retries:
                wait = min(attempt * 2, timeout)
                logger.debug(
                    f"UNO connect attempt {attempt}/{retries} failed, "
                    f"retrying in {wait}s..."
                )
                time.sleep(wait)
        except Exception as e:
            last_err = e
            break

    raise RuntimeError(
        f"Cannot connect to LibreOffice at {UNO_HOST}:{UNO_PORT} "
        f"after {retries} attempts: {last_err}"
    )


def _open_document(desktop, filepath, uno):
    """Open an Excel file via UNO. Returns the document component."""
    file_url = uno.systemPathToFileUrl(os.path.abspath(filepath))

    # Hidden = don't show a window (headless), MacroExecutionMode = 0 (don't run macros)
    from com.sun.star.beans import PropertyValue
    props = (
        _make_prop("Hidden", True, PropertyValue),
        _make_prop("MacroExecutionMode", 0, PropertyValue),
    )

    doc = desktop.loadComponentFromURL(file_url, "_blank", 0, props)
    if doc is None:
        raise RuntimeError(f"LibreOffice failed to open {filepath}")
    return doc


def _make_prop(name, value, PropertyValue):
    """Create a UNO PropertyValue."""
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def _find_jobinfo_sheet(doc):
    """
    Find the jobinfo(2) or jobinfo sheet in a document.
    Returns (sheet, sheet_name) or (None, None).
    """
    sheets = doc.getSheets()
    # Prefer 'jobinfo(2)' over 'jobinfo'
    for target in ['jobinfo(2)', 'jobinfo']:
        for i in range(sheets.getCount()):
            s = sheets.getByIndex(i)
            if s.getName() == target:
                return s, target
    # Fallback: case-insensitive partial match
    for i in range(sheets.getCount()):
        s = sheets.getByIndex(i)
        if 'jobinfo' in s.getName().lower():
            return s, s.getName()
    return None, None


def _save_and_close(doc):
    """Save the document in its original format and close it."""
    from com.sun.star.beans import PropertyValue

    url = doc.getURL()
    ext = url.rsplit('.', 1)[-1].lower().split('%')[0]  # handle %XX-encoded extensions
    _FILTER = {
        'xlsx': 'Calc MS Excel 2007 XML',
        'xlsm': 'Calc MS Excel 2007 XML VBA',
        'xls':  'MS Excel 97',
    }
    filter_name = _FILTER.get(ext, 'Calc MS Excel 2007 XML')

    def _filter_prop():
        p = PropertyValue()
        p.Name = 'FilterName'
        p.Value = filter_name
        return (p,)

    try:
        doc.store()
    except Exception as e:
        logger.warning(f"doc.store() failed ({e}), trying storeToURL with filter={filter_name}...")
        try:
            doc.storeToURL(url, _filter_prop())
        except Exception as e2:
            logger.error(f"storeToURL also failed ({e2})")
            raise RuntimeError(f"Cannot save {url}: {e2}") from e2
    finally:
        try:
            doc.close(True)
        except Exception:
            try:
                doc.dispose()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def populate_jobinfo(filepath, field_mapping):
    """
    Populate a single file's jobinfo(2) Column C via UNO.

    Args:
        filepath: Absolute path to .xlsx / .xlsm file
        field_mapping: dict of {label_str: value_or_list, ...}
            Lists are consumed in order for duplicate labels (same as XML path).

    Returns:
        int: Number of cells written (0 if sheet not found, -1 on error)

    Raises:
        RuntimeError: If UNO connection fails
        ImportError: If python3-uno is not installed
    """
    uno_mod, PropertyValue, NoConnectException = _import_uno()
    desktop = _connect(uno_mod, NoConnectException)

    filename = os.path.basename(filepath)
    doc = None
    try:
        doc = _open_document(desktop, filepath, uno_mod)
        sheet, sheet_name = _find_jobinfo_sheet(doc)
        if sheet is None:
            logger.warning(f"UNO: No jobinfo sheet in {filename}")
            return 0

        # Normalize mapping + build duplicate queues (same logic as XML path)
        normalized = {k.strip(): v for k, v in field_mapping.items()}
        dup_queues = {
            k: deque(v) for k, v in normalized.items() if isinstance(v, list)
        }

        cells_updated = 0

        # Determine used row range — don't scan 1M rows.
        # getCellRangeByName("B:B") is slow; instead scan until 20 consecutive
        # empty B cells after we've seen at least one label.
        max_empty_run = 20
        empty_run = 0
        seen_label = False

        row = 0
        while empty_run < max_empty_run or not seen_label:
            if row > 2000:
                break  # absolute safety cap

            # Column B = index 1
            label_cell = sheet.getCellByPosition(1, row)
            label = label_cell.getString()

            if not label or not label.strip():
                empty_run += 1
                row += 1
                continue

            empty_run = 0
            seen_label = True
            label_stripped = label.strip()

            # Clear Column C first (mirrors XML behavior)
            data_cell = sheet.getCellByPosition(2, row)

            if label_stripped not in normalized:
                # Label exists but no mapping — clear any stale value
                data_cell.setString('')
                row += 1
                continue

            # Resolve value (handle duplicate-label queues)
            if label_stripped in dup_queues:
                q = dup_queues[label_stripped]
                if q:
                    data_value = q.popleft()
                else:
                    data_cell.setString('')
                    row += 1
                    continue
            else:
                data_value = normalized[label_stripped]

            if (data_value is None
                    or data_value == ''
                    or str(data_value) == 'None'):
                data_cell.setString('')
                row += 1
                continue

            data_cell.setString(str(data_value))
            cells_updated += 1
            row += 1

        _save_and_close(doc)
        doc = None
        logger.info(f"UNO populated {filename}: {cells_updated} cells")
        return cells_updated

    except Exception as e:
        logger.error(f"UNO populate failed for {filename}: {e}", exc_info=True)
        if doc is not None:
            try:
                doc.close(False)  # discard changes
            except Exception:
                try:
                    doc.dispose()
                except Exception:
                    pass
        raise
    finally:
        if doc is not None:
            try:
                doc.close(True)
            except Exception:
                pass


def populate_jobinfo_batch(filepaths_and_mappings):
    """
    Populate multiple files' jobinfo(2) via a single UNO connection.

    Args:
        filepaths_and_mappings: list of (filepath, field_mapping_dict) tuples

    Returns:
        dict: {filepath: cells_updated} where -1 means per-file error
    """
    uno_mod, PropertyValue, NoConnectException = _import_uno()
    desktop = _connect(uno_mod, NoConnectException)

    results = {}
    for filepath, field_mapping in filepaths_and_mappings:
        filename = os.path.basename(filepath)
        doc = None
        try:
            doc = _open_document(desktop, filepath, uno_mod)
            sheet, sheet_name = _find_jobinfo_sheet(doc)
            if sheet is None:
                logger.warning(f"UNO batch: No jobinfo sheet in {filename}")
                results[filepath] = 0
                _save_and_close(doc)
                doc = None
                continue

            # Same population logic as single-file version
            normalized = {k.strip(): v for k, v in field_mapping.items()}
            dup_queues = {
                k: deque(v) for k, v in normalized.items()
                if isinstance(v, list)
            }

            cells_updated = 0
            max_empty_run = 20
            empty_run = 0
            seen_label = False
            row = 0

            while empty_run < max_empty_run or not seen_label:
                if row > 2000:
                    break

                label_cell = sheet.getCellByPosition(1, row)
                label = label_cell.getString()

                if not label or not label.strip():
                    empty_run += 1
                    row += 1
                    continue

                empty_run = 0
                seen_label = True
                label_stripped = label.strip()
                data_cell = sheet.getCellByPosition(2, row)

                if label_stripped not in normalized:
                    data_cell.setString('')
                    row += 1
                    continue

                if label_stripped in dup_queues:
                    q = dup_queues[label_stripped]
                    if q:
                        data_value = q.popleft()
                    else:
                        data_cell.setString('')
                        row += 1
                        continue
                else:
                    data_value = normalized[label_stripped]

                if (data_value is None
                        or data_value == ''
                        or str(data_value) == 'None'):
                    data_cell.setString('')
                    row += 1
                    continue

                data_cell.setString(str(data_value))
                cells_updated += 1
                row += 1

            _save_and_close(doc)
            doc = None
            results[filepath] = cells_updated
            logger.info(f"UNO batch: {filename} → {cells_updated} cells")

        except Exception as e:
            logger.error(f"UNO batch failed for {filename}: {e}")
            results[filepath] = -1
            if doc is not None:
                try:
                    doc.close(False)
                except Exception:
                    try:
                        doc.dispose()
                    except Exception:
                        pass
                doc = None

    return results