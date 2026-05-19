"""
docsAppR/sensor_tasks.py — backward-compatibility shim.

The implementation has moved to sensor_renamer/tasks.py.
This module re-exports everything so any existing code that imports from here
continues to work without modification.
"""
from sensor_renamer.tasks import (  # noqa: F401
    process_sensor_images_task,
    ALL_SUBFOLDERS, SUB_RH, SUB_T, SUB_GPP, SUB_MC, SUB_NA,
    SUPPORTED_EXTS,
    build_filenames, result_has_na, safe_dest,
    _encode_b64, _rf, _parse_response, _extract_with_claude,
    _fv, AUTO_PROMPT,
)
