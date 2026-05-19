"""
docsAppR/equipment_checker_tasks.py — backward-compatibility shim.

The implementation has moved to equipment_checker/tasks.py.
This module re-exports everything so any existing code that imports from here
continues to work without modification.
"""
from equipment_checker.tasks import (  # noqa: F401
    process_equipment_check_task,
    REFERENCE_PDF_PATH, SUPPORTED_EXTS,
    EQUIPMENT_PROMPT_PDF, EQUIPMENT_PROMPT_IMAGES,
    _encode_image_b64, _encode_pdf_b64,
    _parse_items, _parse_response,
)
