"""
docsAppR/sensor_views.py — backward-compatibility shim.

The implementation has moved to sensor_renamer/views.py.
This module re-exports everything so any existing code that imports from here
continues to work without modification.
"""
from sensor_renamer.views import (  # noqa: F401
    sensor_image_renamer,
    guide_sensor_renamer,
    sensor_upload,
    sensor_task_status,
    sensor_download_zip,
    sensor_download_subfolder,
    sensor_browse_session,
    sensor_correct,
)
