"""
Celery tasks for the box_calculator PPR (Pre-Packout Report) AI pipeline.
"""
from __future__ import annotations

import logging
import os
import pathlib
import uuid

import requests as req_lib
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def process_cps_room_task(
    self,
    session_id: int,
    room_name: str,
    image_paths: list[str],
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Analyze uploaded room images and store PPR box count estimates.

    Updates BoxCalcCPSRoom.status through: pending → processing → complete|error.
    """
    from .models import BoxCalcCPSSession, BoxCalcCPSRoom
    from .cps_analyzer import analyze_room_ppr, CPS_COLUMNS

    self.update_state(state="PROGRESS", meta={"room_name": room_name, "stage": "analyzing"})

    try:
        session = BoxCalcCPSSession.objects.get(id=session_id)
    except BoxCalcCPSSession.DoesNotExist:
        logger.error("PPR session %s not found", session_id)
        return {"success": False, "error": "Session not found"}

    cps_room, _ = BoxCalcCPSRoom.objects.get_or_create(
        session=session,
        room_name=room_name,
    )
    cps_room.status = "processing"
    cps_room.celery_task_id = self.request.id
    cps_room.save(update_fields=["status", "celery_task_id"])

    logger.info("CPS analyze start — session=%s room=%r images=%d model=%s",
                session_id, room_name, len(image_paths), model)

    result = analyze_room_ppr(
        room_name=room_name,
        image_paths=image_paths,
        model=model,
    )

    logger.info("CPS analyze result — session=%s room=%r success=%s total=%s confidence=%s error=%s",
                session_id, room_name, result["success"], result.get("total"),
                result.get("confidence"), result.get("error"))

    if result["success"]:
        counts = result["counts"]
        logger.info("CPS counts — room=%r %s", room_name,
                    " ".join(f"{k}={v}" for k, v in counts.items() if v))
        for col in CPS_COLUMNS:
            setattr(cps_room, col, counts.get(col, 0))
        cps_room.status = "complete"
        cps_room.confidence = result["confidence"]
        cps_room.ai_notes = result["notes"]
        cps_room.images_count = result["images_used"]
    else:
        logger.error("CPS analyze FAILED — session=%s room=%r error=%s",
                     session_id, room_name, result.get("error"))
        cps_room.status = "error"
        cps_room.ai_notes = result.get("error", "Unknown error")

    cps_room.save()

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


@shared_task(bind=True, max_retries=0)
def download_encircle_room_task(
    self,
    session_id: int,
    room_name: str,
    encircle_claim_id: str,
    structure_id: str,
    encircle_room_id: str,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    """
    Download photos from Encircle for a 300-series packout room and run CPS analysis.
    Updates BoxCalcCPSRoom status through: pending → processing → complete|error.
    """
    from .models import BoxCalcCPSSession, BoxCalcCPSRoom
    from .cps_analyzer import analyze_room_ppr, CPS_COLUMNS
    from docsAppR.encircle_client import EncircleAPIClient

    self.update_state(state="PROGRESS", meta={"room_name": room_name, "stage": "downloading"})

    try:
        session = BoxCalcCPSSession.objects.get(id=session_id)
    except BoxCalcCPSSession.DoesNotExist:
        logger.error("CPS session %s not found", session_id)
        return {"success": False, "error": "Session not found"}

    cps_room, _ = BoxCalcCPSRoom.objects.get_or_create(session=session, room_name=room_name)
    cps_room.status = "processing"
    cps_room.celery_task_id = self.request.id
    cps_room.save(update_fields=["status", "celery_task_id"])

    # ── Fetch media list from Encircle ────────────────────────────────────────
    try:
        api = EncircleAPIClient()
        all_media = api.get_room_media(encircle_claim_id, structure_id, encircle_room_id)
    except Exception as e:
        err_str = str(e)
        # 404 = room exists in Encircle but no photos have been uploaded yet
        if "404" in err_str:
            cps_room.ai_notes = "No photos uploaded to this room in Encircle"
        else:
            cps_room.ai_notes = f"Encircle API error: {e}"
        cps_room.status = "error"
        cps_room.save()
        return {"success": False, "error": err_str, "room_name": room_name}

    # Extract photo URLs (skip documents, audio, video)
    photo_urls = []
    for item in all_media:
        item_type = (item.get("type") or item.get("media_type") or "").lower()
        if item_type and not any(t in item_type for t in ("photo", "image", "jpg", "jpeg", "png", "webp")):
            continue
        url = (item.get("download_uri") or item.get("url") or
               item.get("download_url") or item.get("image_url"))
        if url:
            photo_urls.append(url)

    if not photo_urls:
        cps_room.status = "error"
        cps_room.ai_notes = "No photos found in Encircle for this room"
        cps_room.save()
        return {"success": False, "error": "No photos found", "room_name": room_name}

    # ── Download up to 5 photos ───────────────────────────────────────────────
    self.update_state(state="PROGRESS", meta={
        "room_name": room_name, "stage": "analyzing",
        "photos_found": len(photo_urls),
    })

    tmp_dir = pathlib.Path("/tmp") / f"encircle_cps_{session_id}_{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    for url in photo_urls[:5]:
        try:
            resp = req_lib.get(url, timeout=30)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            ext = {
                "image/jpeg": ".jpg", "image/png": ".png",
                "image/webp": ".webp", "image/bmp": ".bmp",
            }.get(ct, ".jpg")
            dest = tmp_dir / f"{uuid.uuid4().hex}{ext}"
            dest.write_bytes(resp.content)
            saved_paths.append(str(dest))
        except Exception as e:
            logger.warning("Photo download failed for room %s: %s", room_name, e)

    if not saved_paths:
        cps_room.status = "error"
        cps_room.ai_notes = "Could not download any photos from Encircle"
        cps_room.save()
        return {"success": False, "error": "Photo download failed", "room_name": room_name}

    # ── Run CPS analysis ──────────────────────────────────────────────────────
    logger.info("CPS Encircle analyze start — session=%s room=%r photos_downloaded=%d",
                session_id, room_name, len(saved_paths))

    result = analyze_room_ppr(room_name=room_name, image_paths=saved_paths, model=model)

    logger.info("CPS Encircle analyze result — session=%s room=%r success=%s total=%s confidence=%s error=%s",
                session_id, room_name, result["success"], result.get("total"),
                result.get("confidence"), result.get("error"))

    if result["success"]:
        counts = result["counts"]
        logger.info("CPS Encircle counts — room=%r %s", room_name,
                    " ".join(f"{k}={v}" for k, v in counts.items() if v))
        for col in CPS_COLUMNS:
            setattr(cps_room, col, counts.get(col, 0))
        cps_room.status = "complete"
        cps_room.confidence = result["confidence"]
        cps_room.ai_notes = result["notes"]
        cps_room.images_count = result["images_used"]
    else:
        logger.error("CPS Encircle FAILED — session=%s room=%r error=%s",
                     session_id, room_name, result.get("error"))
        cps_room.status = "error"
        cps_room.ai_notes = result.get("error", "Unknown error")

    cps_room.save()

    # Cleanup temp files
    for path in saved_paths:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        tmp_dir.rmdir()
    except OSError:
        pass

    return {
        "success": result["success"],
        "session_id": session_id,
        "room_name": room_name,
        "total": result.get("total", 0),
        "error": result.get("error"),
    }
