import logging
import re
import time as _time
from celery import shared_task

logger = logging.getLogger(__name__)


def _send_signing_notification(room, client_email=None):
    """
    Send email notification when a CPS Report room is signed.
    Uses the dedicated lease mailbox if configured, otherwise falls back to default.
    """
    from docsAppR.models import Client
    from django.core.mail import EmailMessage
    from .email_utils import get_lease_email_connection, get_lease_from_email
    
    # Use tenant owner email (client.email or client.pEmail) for production
    # TEMPORARY: For testing, use your email until tenant email is available
    if not client_email:
        try:
            client = room.session.client
            client_email = getattr(client, 'email', None) or getattr(client, 'pEmail', None)
        except Exception:
            pass
    
    # TEMPORARY OVERRIDE - Remove this block when ready to use tenant emails
    if not client_email:
        # TODO: Replace with tenant owner email from settings
        # Example in Django settings.py: TEMP_NOTIFICATION_EMAIL = 'galaxielsaga@gmail.com'
        logger.warning(f"No email address found for CPS session {room.session.id}, using default notification email")
        client_email = getattr(settings, 'TEMP_NOTIFICATION_EMAIL', 'galaxielsaga@gmail.com')
    
    try:
        connection = get_lease_email_connection()
        
        subject = f"CPS Report Room Signed: {room.room_number} {room.room_name}"
        
        body_text = (
            f"A room in your CPS report has been signed.\n\n"
            f"Room: {room.room_number} {room.room_name}\n"
            f"Signed by: {room.signature_name}\n"
            f"Signed at: {room.signed_at.strftime('%B %d, %Y at %I:%M %p')}\n\n"
            f"Session ID: {room.session.id}\n"
            f"View your report: /cps-report/session/{room.session.id}/"
        )
        
        email = EmailMessage(
            subject=subject,
            body=body_text,
            from_email=get_lease_from_email(),
            to=[client_email],
            connection=connection,
        )
        email.send()
        logger.info(f"Sent signing notification for room {room.id} to {client_email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send signing notification for room {room.id}: {exc}")
        return False


def _session_log(session_id, msg):
    """Append a timestamped log line to Redis so the progress page can show it live."""
    from django.core.cache import cache
    key = f'ppr:live_logs:{session_id}'
    now = _time.strftime('%H:%M:%S')
    entry = {'t': now, 'msg': msg}
    logs = cache.get(key) or []
    logs.append(entry)
    if len(logs) > 200:
        logs = logs[-200:]
    cache.set(key, logs, timeout=7200)
    print(f"[PPR-LOG] {now} {msg}", flush=True)


@shared_task(bind=True)
def process_cps_session_task(self, session_id):
    """
    Process all rooms in a PPR session via Claude vision AI.
    Runs in Celery worker — frontend polls api_session_status for live updates.
    """
    from .models import CPSReportSession, CPSReportItem
    from .ai_analyzer import analyze_room_for_ppr, fetch_all_claim_media

    try:
        session = CPSReportSession.objects.get(id=session_id)
    except CPSReportSession.DoesNotExist:
        logger.error(f"PPR task: session {session_id} not found")
        return

    pricing_mode = session.pricing_mode or 'normal'
    session.status = 'processing'
    session.save(update_fields=['status'])
    log = lambda msg: _session_log(session_id, msg)
    logger.info(
        f"PPR task started for session {session_id} — {session.insured_name} "
        f"[pricing: {pricing_mode}]"
    )
    log(f"Session started — {session.insured_name} | claim {session.claim_number or session.encircle_claim_id} | mode: {pricing_mode}")

    try:
        log("Connecting to Encircle and fetching claim media…")
        all_claim_media = fetch_all_claim_media(session.encircle_claim_id)
        log(f"Fetched {len(all_claim_media)} media items from Encircle")
    except Exception as e:
        logger.error(f"PPR task: failed to fetch claim media: {e}", exc_info=True)
        log(f"ERROR fetching claim media: {e}")
        session.status = 'error'
        session.save(update_fields=['status'])
        return

    rooms = list(session.rooms.order_by('order').all())
    log(f"Processing {len(rooms)} rooms…")

    for room in rooms:
        room.status = 'processing'
        room.save(update_fields=['status'])

        has_secondary = bool(room.encircle_room_id_secondary)
        source_label = f"{room.room_number} {room.room_name}"
        logger.info(f"PPR task: processing room {source_label}" +
                    (" (primary + secondary)" if has_secondary else ""))
        log(f"Starting room: {source_label}" + (" (primary + secondary)" if has_secondary else ""))

        try:
            result_primary = analyze_room_for_ppr(
                room_name=source_label,
                room_number=room.room_number,
                prefetched_media=all_claim_media,
                pricing_mode=pricing_mode,
                log_fn=log,
            )
            all_items = list(result_primary.get('items', []))
            total_images = result_primary.get('images_used', 0)
            summaries = [result_primary.get('room_summary', '')]

            if has_secondary:
                secondary_number = re.match(r'^(\d+)', room.encircle_room_label_secondary or '')
                secondary_number = secondary_number.group(1) if secondary_number else ''
                logger.info(f"PPR task: processing secondary room {secondary_number} for {source_label}")
                log(f"Processing secondary images (room {secondary_number}) for {source_label}…")
                result_secondary = analyze_room_for_ppr(
                    room_name=source_label,
                    room_number=secondary_number,
                    prefetched_media=all_claim_media,
                    pricing_mode=pricing_mode,
                    log_fn=log,
                )
                all_items.extend(result_secondary.get('items', []))
                total_images += result_secondary.get('images_used', 0)
                if result_secondary.get('room_summary'):
                    summaries.append(f"[secondary] {result_secondary['room_summary']}")

            # Log AI usage for cost tracking
            total_input  = result_primary.get('input_tokens', 0)
            total_output = result_primary.get('output_tokens', 0)
            if has_secondary:
                total_input  += result_secondary.get('input_tokens', 0)
                total_output += result_secondary.get('output_tokens', 0)
            try:
                from docsAppR.models import AIUsageLog
                AIUsageLog.log_call(
                    operation='ppr_room',
                    model='claude-haiku-4-5-20251001',
                    input_tokens=total_input,
                    output_tokens=total_output,
                    images_count=total_images,
                    cps_session_id=session.id,
                    cps_room_id=room.id,
                    success=bool(result_primary.get('success') or all_items),
                    error_message=result_primary.get('error', '') or '',
                )
            except Exception as log_err:
                logger.warning(f"PPR usage log failed for room {room.id}: {log_err}")

            room.items.all().delete()
            for order, item_dict in enumerate(all_items):
                age_years = max(0, min(5, int(item_dict.get('age_years', 0) or 0)))
                age_months = max(0, min(11, int(item_dict.get('age_months', 0) or 0)))
                if age_years >= 5:
                    age_months = 0
                CPSReportItem.objects.create(
                    room=room,
                    order=order,
                    description=str(item_dict.get('description', ''))[:500],
                    brand=str(item_dict.get('brand', ''))[:200],
                    disposition='Replacement',
                    condition=str(item_dict.get('condition', ''))[:50],
                    qty=max(1, int(item_dict.get('qty', 1) or 1)),
                    model_number=str(item_dict.get('model_number', ''))[:200],
                    serial_number=str(item_dict.get('serial_number', ''))[:200],
                    retailer=str(item_dict.get('retailer', ''))[:200],
                    replacement_source=str(item_dict.get('replacement_source', 'Retail'))[:200],
                    purchase_price_each=float(item_dict.get('purchase_price_each', 0) or 0),
                    age_years=age_years,
                    age_months=age_months,
                    replacement_value_each=float(item_dict.get('replacement_value_each', 0) or 0),
                    notes=str(item_dict.get('notes', ''))[:500],
                    ai_suggested=True,
                    structural=bool(item_dict.get('structural', False)),
                    source_image_urls=list(item_dict.get('source_image_urls', []) or []),
                )

            # Collect the deduplicated URLs that were actually sent to Claude —
            # these are the exact images that produced the line items.
            analyzed_urls = list(result_primary.get('analyzed_urls', []))
            if has_secondary:
                secondary_urls = result_secondary.get('analyzed_urls', [])
                seen = set(analyzed_urls)
                analyzed_urls.extend(u for u in secondary_urls if u not in seen)

            room.images_used = total_images
            room.analyzed_image_urls = analyzed_urls
            room.ai_confidence = result_primary.get('confidence', '')
            room.ai_notes = ' | '.join(s for s in summaries if s)
            room.status = 'complete' if (result_primary.get('success') or all_items) else 'error'
            room.save(update_fields=['images_used', 'analyzed_image_urls', 'ai_confidence', 'ai_notes', 'status'])
            item_count = room.items.count()
            logger.info(
                f"PPR task: room {room.room_number} done — "
                f"{item_count} items, {total_images} images, {room.ai_confidence} confidence"
            )
            log(f"Room {source_label} complete — {item_count} items, {total_images} images ({room.ai_confidence} confidence)")

        except Exception as e:
            logger.error(f"PPR task: error on room {room.id} ({room.room_name}): {e}", exc_info=True)
            log(f"ERROR on room {source_label}: {e}")
            room.status = 'error'
            room.ai_notes = str(e)[:500]
            room.save(update_fields=['status', 'ai_notes'])

    session.status = 'complete'
    session.save(update_fields=['status'])
    logger.info(f"PPR task complete for session {session_id}")
    log("All rooms complete — generating summary report…")

    from .views import _auto_generate_summary
    _auto_generate_summary(session)

    # Queue photo PDF as a separate Celery task so it runs in a fresh worker
    # with its own memory budget — building the PDF inline exhausted memory on
    # large claims (28+ rooms, 200+ image downloads) and failed silently.
    log("Queuing photo evidence PDF (builds in background)…")
    try:
        regenerate_photo_pdf_task.delay(session_id)
        log("Photo PDF queued — available for download once built (typically 2–5 min).")
    except Exception as _queue_err:
        logger.warning(f"PPR task: could not queue photo PDF task: {_queue_err}")
        log(f"Photo PDF queue failed: {_queue_err}")

    log("Done. Report ready for download.")


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_cps_room_signing_notification(self, room_id, client_email=None):
    """
    Send email notification when a CPS Report room is signed.
    Called from views after a room signature is saved.
    """
    from .models import CPSReportRoom
    
    try:
        room = CPSReportRoom.objects.get(id=room_id)
    except CPSReportRoom.DoesNotExist:
        logger.error('send_cps_room_signing_notification: Room %s not found', room_id)
        return
    
    success = _send_signing_notification(room, client_email)
    
    if success:
        logger.info(f"Successfully sent signing notification for room {room_id}")
    else:
        logger.warning(f"Failed to send signing notification for room {room_id}, retrying...")
        raise self.retry(exc=Exception("Email sending failed"), max_retries=self.max_retries + 1)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def regenerate_photo_pdf_task(self, session_id: int):
    """
    Rebuild the Photo Evidence PDF for an existing session WITHOUT re-running
    the full AI analysis.  Uses the analyzed_image_urls stored on each room
    (populated since migration 0011).  For rooms that pre-date the migration
    the builder falls back to filter_room_images via the Encircle API.
    """
    from .models import CPSReportSession
    from .photo_pdf_builder import build_photo_pdf
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    try:
        session = CPSReportSession.objects.select_related('client').get(id=session_id)
    except CPSReportSession.DoesNotExist:
        logger.error('regenerate_photo_pdf_task: session %s not found', session_id)
        return

    room_count = session.rooms.count()
    logger.info(f"regenerate_photo_pdf_task: rebuilding photo PDF for session {session_id} ({room_count} rooms)")

    try:
        pdf_bytes = build_photo_pdf(session)
        _pdf_path = f'cps_photo_pdfs/{session_id}.pdf'
        if default_storage.exists(_pdf_path):
            default_storage.delete(_pdf_path)
        default_storage.save(_pdf_path, ContentFile(pdf_bytes))
        logger.info(
            f"regenerate_photo_pdf_task: DONE — saved {len(pdf_bytes):,} bytes → {_pdf_path}"
        )
    except Exception as exc:
        logger.error(
            f"regenerate_photo_pdf_task: FAILED for session {session_id} ({room_count} rooms): {exc}",
            exc_info=True,
        )
        raise self.retry(exc=exc)
