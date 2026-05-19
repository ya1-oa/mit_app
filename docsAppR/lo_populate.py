#!/usr/bin/env python3
"""
Runs under LibreOffice's own Python (/usr/lib/libreoffice/program/python3)
which has 'uno' built in — no python3-uno system package required.
Called by Django/Celery via subprocess to write claim data into Excel jobinfo(2) sheets.

Usage:
    /usr/lib/libreoffice/program/python3 lo_populate.py input.json output.json

input.json:
    {
        "files": [
            {"path": "/abs/path/to/file.xlsx", "labels": {"Label Text": "value", ...}},
            ...
        ]
    }
    Values may be strings or lists (lists consumed top-to-bottom for duplicate labels).

output.json:
    [{"path": "...", "cells": 5, "success": true}, ...]
"""
import sys
import os
import json
from collections import deque

# Ensure LO's own program dir is on sys.path so 'uno' can be imported.
# When called via /usr/lib/libreoffice/program/python3, the executable's
# directory is the LO program dir which already has uno available.
lo_prog = os.path.dirname(os.path.abspath(sys.executable))
if lo_prog not in sys.path:
    sys.path.insert(0, lo_prog)

import uno
from com.sun.star.beans import PropertyValue


def main():
    if len(sys.argv) < 3:
        print("Usage: lo_populate.py input.json output.json", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, encoding='utf-8') as f:
        data = json.load(f)

    local_ctx = uno.getComponentContext()
    smgr = local_ctx.ServiceManager
    desktop = smgr.createInstanceWithContext('com.sun.star.frame.Desktop', local_ctx)

    # Hidden=True: no GUI window
    # MacroExecutionMode=0: disable macros (we only write cells, VBA not needed)
    # UpdateDocMode=0: don't prompt/update external links — use cached values as-is
    hidden_props = (
        PropertyValue('Hidden', 0, True, 0),
        PropertyValue('MacroExecutionMode', 0, 0, 0),
        PropertyValue('UpdateDocMode', 0, 0, 0),
    )

    results = []
    for file_info in data['files']:
        filepath = file_info['path']
        label_values = file_info.get('labels', {})
        doc = None
        try:
            # Build per-label deques so duplicate labels consume values top-to-bottom
            queues = {
                k: deque(v) if isinstance(v, list) else deque([v])
                for k, v in label_values.items()
                if v is not None and str(v) not in ('', 'None')
            }

            file_url = uno.systemPathToFileUrl(os.path.abspath(filepath))
            doc = desktop.loadComponentFromURL(file_url, '_blank', 0, hidden_props)

            sheets = doc.getSheets()
            jobinfo = None
            for i in range(sheets.getCount()):
                name = sheets.getByIndex(i).getName()
                if name in ('jobinfo(2)', 'jobinfo'):
                    jobinfo = sheets.getByIndex(i)
                    break

            updated = 0
            if jobinfo is not None:
                for row in range(300):
                    b_cell = jobinfo.getCellByPosition(1, row)  # Column B (0-indexed col 1)
                    label = b_cell.getString().strip()
                    if label and label in queues and queues[label]:
                        val = queues[label].popleft()
                        c_cell = jobinfo.getCellByPosition(2, row)  # Column C (col 2)
                        c_cell.setString(str(val) if val is not None else '')
                        updated += 1

            doc.store()
            doc.close(True)
            doc = None
            results.append({'path': filepath, 'cells': updated, 'success': True})

        except Exception as e:
            results.append({
                'path': filepath, 'cells': 0, 'success': False, 'error': str(e)
            })
            if doc is not None:
                try:
                    doc.close(True)
                except Exception:
                    pass

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f)


if __name__ == '__main__':
    main()
