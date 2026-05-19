"""
docsAppR/equipment_checker_views.py — backward-compatibility shim.

The implementation has moved to equipment_checker/views.py.
This module re-exports everything so any existing code that imports from here
continues to work without modification.
"""
from equipment_checker.views import (  # noqa: F401
    equipment_checker,
    guide_equipment_checker,
    equipment_upload,
    equipment_task_status,
    equipment_export_csv,
)
