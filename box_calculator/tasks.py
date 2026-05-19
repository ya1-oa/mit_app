"""
Celery tasks for the box_calculator PPR (Pre-Packout Report) AI pipeline.
"""
from __future__ import annotations

import logging
import os
import shutil

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def process_ppr_room_task(
    self,
    session_id: int,
    room_name: str,
    image_paths: list[str],
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Analyze uploaded room images and store PPR box count estimates.

    Updates BoxCalcPPRRoom.status through: pending → processing → complete|error.
    """
    from .models import BoxCalcPPRSession, BoxCalcPPRRoom
    from .ppr_analyzer import analyze_room_ppr, PPR_COLUMNS

    self.update_state(state="PROGRESS", meta={"room_name": room_name, "stage": "analyzing"})

    try:
        session = BoxCalcPPRSession.objects.get(id=session_id)
    except BoxCalcPPRSession.DoesNotExist:
        logger.error("PPR session %s not found", session_id)
        return {"success": False, "error": "Session not found"}

    ppr_room, _ = BoxCalcPPRRoom.objects.get_or_create(
        session=session,
        room_name=room_name,
    )
    ppr_room.status = "processing"
    ppr_room.celery_task_id = self.request.id
    ppr_room.save(update_fields=["status", "celery_task_id"])

    result = analyze_room_ppr(
        room_name=room_name,
        image_paths=image_paths,
        model=model,
    )

    if result["success"]:
        counts = result["counts"]
        for col in PPR_COLUMNS:
            setattr(ppr_room, col, counts.get(col, 0))
        ppr_room.status = "complete"
        ppr_room.confidence = result["confidence"]
        ppr_room.ai_notes = result["notes"]
        ppr_room.images_count = result["images_used"]
    else:
        ppr_room.status = "error"
        ppr_room.ai_notes = result.get("error", "Unknown error")

    ppr_room.save()

    # Clean up temp image files
    for path in image_paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    return {
        "success": result["success"],
        "session_id": session_id,
        "room_name": room_name,
        "total": result["total"],
        "error": result.get("error"),
    }
