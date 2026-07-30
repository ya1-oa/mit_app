"""
equipment_checker/tasks.py
==========================
Celery task for verifying water mitigation equipment documentation
using Claude Vision + reference PDF (HUTCH EQPT LIST.pdf).
"""
import json
import re
import base64
import time
import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

# Reference equipment PDF — lives at app/HUTCH EQPT LIST.pdf
REFERENCE_PDF_PATH = Path(__file__).parent.parent / 'HUTCH EQPT LIST.pdf'

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif'}

# Prompt used when a structured room-photo PDF report is provided
EQUIPMENT_PROMPT_PDF = """AS A WATER MITIGATION SPECIALIST WHO HAS REVIEWED THOUSANDS OF WATER MITIGATION CLAIMS FOR PROPER DOCUMENTATION,
USE THE ATTACHED REFERENCE DOCUMENT (EQUIPMENT PICTURES) AND YOUR EXTENSIVE KNOWLEDGE TO IDENTIFY WATER MITIGATION EQUIPMENT AND WORK ACTIVITIES.

THE SECOND ATTACHED DOCUMENT IS A ROOM-BY-ROOM JOB SITE PHOTO REPORT.
Each section in the report is headed by a ROOM NAME followed by the photos taken in that room.
Use the room names in the report to match against the work items below.

FOR EACH WORK ITEM LISTED BELOW, DETERMINE WHETHER THE JOB SITE REPORT PROVIDES ADEQUATE PHOTOGRAPHIC DOCUMENTATION.
INSURERS WILL ONLY PAY FOR ITEMS DOCUMENTED WITH PICTURES.

Work items to verify:
{items_list}

For each item assign one of these statuses:
- FOUND: Clear, unambiguous photographic evidence exists in the report
- PARTIAL: Some evidence is present but documentation is limited (only 1 photo, partially obscured, distant shot, etc.)
- NOT FOUND: No photographic evidence found for this item

Respond with ONLY a raw JSON array — no markdown, no explanation, nothing else:
[
  {{"room": "BATH DN", "description": "Vinyl tile", "status": "FOUND", "note": "Clearly visible on page 19; flooring removal shown in 2 photos"}},
  {{"room": "REAR HALL DN", "description": "Tear out baseboard", "status": "PARTIAL", "note": "Only 1 room photo on page 21; activity appears billable but would benefit from more close-up documentation"}},
  {{"room": "Administration Expenses (PER LEVEL)", "description": "Emergency service call", "status": "NOT FOUND", "note": "No matching room photo section found in the report"}}
]

Be specific in your notes. Reference page numbers where visible. If PARTIAL, mention what additional documentation would help.
If NOT FOUND, briefly explain what photo evidence would be needed."""

# Prompt used when only individual images (no PDF report) are provided
EQUIPMENT_PROMPT_IMAGES = """AS A WATER MITIGATION SPECIALIST WHO HAS REVIEWED THOUSANDS OF WATER MITIGATION CLAIMS FOR PROPER DOCUMENTATION,
USE THE ATTACHED REFERENCE DOCUMENT (EQUIPMENT PICTURES) AND YOUR EXTENSIVE KNOWLEDGE TO IDENTIFY WATER MITIGATION EQUIPMENT AND WORK ACTIVITIES IN THE UPLOADED JOB SITE PHOTOS.

FOR EACH WORK ITEM LISTED BELOW, DETERMINE WHETHER THE JOB SITE PHOTOS PROVIDE ADEQUATE PHOTOGRAPHIC DOCUMENTATION.
INSURERS WILL ONLY PAY FOR ITEMS DOCUMENTED WITH PICTURES.

Work items to verify:
{items_list}

For each item assign one of these statuses:
- FOUND: Clear, unambiguous photographic evidence exists in the submitted photos
- PARTIAL: Some evidence is visible but documentation is limited (only 1 photo, partially obscured, distant shot, etc.)
- NOT FOUND: No photographic evidence found in the submitted photos

Respond with ONLY a raw JSON array — no markdown, no explanation, nothing else:
[
  {{"room": "BATH DN", "description": "Vinyl tile", "status": "FOUND", "note": "Clearly visible in 2 photos showing flooring removal"}},
  {{"room": "REAR HALL DN", "description": "Tear out baseboard", "status": "PARTIAL", "note": "Only 1 room photo; activity appears billable but would benefit from more close-up documentation"}},
  {{"room": "Administration Expenses (PER LEVEL)", "description": "Emergency service call", "status": "NOT FOUND", "note": "No matching room photo section found in the submitted photos"}}
]

Be specific in your notes. If PARTIAL, mention what additional documentation would help.
If NOT FOUND, briefly explain what photo evidence would be needed."""


def _encode_image_b64(path: Path):
    ext = path.suffix.lower().lstrip('.')
    mt = {
        'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
        'bmp': 'image/bmp', 'tiff': 'image/tiff', 'tif': 'image/tiff',
        'webp': 'image/webp',
    }.get(ext, 'image/jpeg')
    with open(path, 'rb') as f:
        return base64.standard_b64encode(f.read()).decode(), mt


def _encode_pdf_b64(path: Path) -> str:
    with open(path, 'rb') as f:
        return base64.standard_b64encode(f.read()).decode()


def _parse_items(raw_items: list) -> list:
    """Parse line items. Each item is 'Room | Description' or just 'Description'."""
    parsed = []
    for line in raw_items:
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            parts = line.split('|', 1)
            parsed.append({'room': parts[0].strip(), 'description': parts[1].strip()})
        else:
            parsed.append({'room': '', 'description': line})
    return parsed


def _parse_response(text: str) -> list:
    text = re.sub(r'^```[a-z]*\n?', '', text.strip())
    text = re.sub(r'\n?```$', '', text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    m = re.search(r'\[[\s\S]+\]', text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return []


@shared_task(bind=True, max_retries=0)
def process_equipment_check_task(self, session_id: str, image_paths: list,
                                  raw_items: list, model: str = 'claude-sonnet-4-6',
                                  job_pdf_path: str = ''):
    """
    Verify water mitigation equipment documentation against job site photos.

    Args:
        session_id:    UUID identifying this session
        image_paths:   Absolute paths to individual job site photos (may be empty if job_pdf_path set)
        raw_items:     Line items to verify ('Room | Description' or 'Description')
        model:         Claude model ID
        job_pdf_path:  Path to a room-photo PDF report (e.g. Encircle export). Optional.

    Returns:
        dict with per-item verification results and FOUND/PARTIAL/NOT FOUND counts.
    """
    from django.conf import settings as django_settings
    import anthropic as _anthropic

    api_key = getattr(django_settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'success': False, 'error': 'ANTHROPIC_API_KEY not configured in settings'}

    self.update_state(state='PROGRESS', meta={'step': 'Parsing line items…', 'percent': 5})

    items = _parse_items(raw_items)
    if not items:
        return {'success': False, 'error': 'No valid line items provided'}

    items_list = '\n'.join(
        f"{i+1}. {(item['room'] + ' | ') if item['room'] else ''}{item['description']}"
        for i, item in enumerate(items)
    )

    content = []
    has_job_pdf = False

    # 1. Equipment reference PDF (always first — Claude sees it as the reference doc)
    if REFERENCE_PDF_PATH.exists():
        try:
            pdf_b64 = _encode_pdf_b64(REFERENCE_PDF_PATH)
            content.append({
                'type': 'document',
                'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': pdf_b64},
            })
            logger.info(f"[equipment_check] Reference PDF: {REFERENCE_PDF_PATH.stat().st_size // 1024} KB")
        except Exception as e:
            logger.warning(f"[equipment_check] Could not load reference PDF: {e}")
    else:
        logger.warning(f"[equipment_check] Reference PDF not found at {REFERENCE_PDF_PATH}")

    # 2. Job site PDF report (room-by-room photo report, e.g. Encircle export)
    if job_pdf_path:
        job_pdf = Path(job_pdf_path)
        if job_pdf.exists():
            try:
                self.update_state(state='PROGRESS', meta={
                    'step': f'Loading job report PDF ({job_pdf.stat().st_size // 1024} KB)…',
                    'percent': 12,
                })
                job_b64 = _encode_pdf_b64(job_pdf)
                content.append({
                    'type': 'document',
                    'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': job_b64},
                })
                has_job_pdf = True
                logger.info(f"[equipment_check] Job PDF: {job_pdf.name} ({job_pdf.stat().st_size // 1024} KB)")
            except Exception as e:
                logger.warning(f"[equipment_check] Could not load job PDF {job_pdf_path}: {e}")
        else:
            logger.warning(f"[equipment_check] Job PDF path not found: {job_pdf_path}")

    # 3. Individual job site photos
    loaded = 0
    if image_paths:
        self.update_state(state='PROGRESS', meta={
            'step': f'Loading {len(image_paths)} individual photos…',
            'percent': 15,
        })
        for p in image_paths:
            try:
                b64, mt = _encode_image_b64(Path(p))
                content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': b64}})
                loaded += 1
            except Exception as e:
                logger.warning(f"[equipment_check] Could not load image {p}: {e}")

    if not has_job_pdf and not loaded:
        return {'success': False, 'error': 'No images or PDF report could be loaded'}

    prompt_template = EQUIPMENT_PROMPT_PDF if has_job_pdf else EQUIPMENT_PROMPT_IMAGES
    content.append({'type': 'text', 'text': prompt_template.format(items_list=items_list)})

    source_desc = []
    if has_job_pdf:
        source_desc.append('room report PDF')
    if loaded:
        source_desc.append(f'{loaded} photo{"s" if loaded != 1 else ""}')
    source_label = ' + '.join(source_desc)

    self.update_state(state='PROGRESS', meta={
        'step': f'Sending {source_label} + {len(items)} items to Claude…',
        'percent': 30,
    })

    client = _anthropic.Anthropic(api_key=api_key)
    result_data = None

    for attempt in range(1, 5):
        try:
            self.update_state(state='PROGRESS', meta={
                'step': f'Claude is analyzing {source_label}… (attempt {attempt})',
                'percent': 35 + attempt * 12,
            })
            resp = client.messages.create(
                model=model,
                max_tokens=8096,
                messages=[{'role': 'user', 'content': content}],
            )
            result_data = _parse_response(resp.content[0].text)
            break
        except _anthropic.RateLimitError:
            time.sleep(min(60, 2 ** attempt))
        except _anthropic.APIError as e:
            if attempt == 4:
                return {'success': False, 'error': f'Claude API error: {e}'}
            time.sleep(3)

    if result_data is None:
        return {'success': False, 'error': 'Failed to get a valid response from Claude'}

    found     = sum(1 for r in result_data if r.get('status') == 'FOUND')
    partial   = sum(1 for r in result_data if r.get('status') == 'PARTIAL')
    not_found = sum(1 for r in result_data if r.get('status') == 'NOT FOUND')

    logger.info(
        f"[equipment_check] session={session_id} pdf={has_job_pdf} images={loaded} "
        f"items={len(items)} FOUND={found} PARTIAL={partial} NOT_FOUND={not_found}"
    )

    return {
        'result_type': 'verify',
        'success': True,
        'session_id': session_id,
        'has_job_pdf': has_job_pdf,
        'image_count': loaded,
        'item_count': len(items),
        'found': found,
        'partial': partial,
        'not_found': not_found,
        'results': result_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-DETECT MODE
# ─────────────────────────────────────────────────────────────────────────────

DETECT_PROMPT = """AS AN EXPERT WATER MITIGATION SPECIALIST with thousands of field hours, examine every photo and/or report page provided and produce an EXHAUSTIVE equipment inventory of everything you can see on this job site.

Your goal: document every single piece of mitigation equipment exactly as a thorough adjuster review would require.

Look specifically for — but do not limit yourself to — these equipment types:
• Dehumidifiers (LGR, desiccant, refrigerant-cycle) — note brand, model, unit# or ID tag if visible
• Air movers / axial fans / centrifugal fans (Dri-Eaz, Turbo Dryer, Phoenix, etc.)
• HEPA air scrubbers / negative air machines / air filtration devices
• Injectidry wall-cavity or floor-mat drying systems
• Moisture meters, pin/pinless probes, psychrometers, thermo-hygrometers, dataloggers
• Water extraction equipment, truck-mount hoses, wands, carpet wands
• Poly containment barriers, plastic sheeting, tape, zipper-access doors
• Deodorizers, hydroxyl generators, ozone machines, thermal foggers
• Safety signage, caution tape, drying log sheets posted on walls
• Any equipment labels, unit ID numbers, barcode tags, or color-coded tags on the equipment

For EACH distinct piece of equipment return one entry:
- name: common equipment name (e.g. "LGR Dehumidifier", "Axial Air Mover")
- brand_model: brand and model if any text/label is visible, else ""
- room: room or area where it sits (use the room name from the report if available, else your best description or "Unknown")
- qty: how many units of this exact type are visible in this room entry
- unit_ids: list of any ID/serial/tag numbers visible on the units — e.g. ["DH-01", "AF-03"]. Empty list if none visible.
- confidence: "high" (clearly identifiable), "medium" (likely but partially obscured), or "low" (possible but hard to confirm)
- notes: any insurance-relevant observation, e.g. "hose routing visible", "power cords connected to power distribution unit", "placed in corner, limited airflow"

Also return:
- not_visible: list of equipment TYPES you would normally expect for a job of this apparent scope that you did NOT see clearly documented in these photos (helps identify documentation gaps)
- job_summary: one sentence describing the apparent scope (e.g. "2-level residential water loss with dehumidification and air-mover staging across 4 rooms")

Respond ONLY with valid JSON — no markdown fences, no preamble, no explanation:
{
  "detected_equipment": [
    {
      "name": "LGR Dehumidifier",
      "brand_model": "Dri-Eaz LGR 7000XLi",
      "room": "Master Bedroom",
      "qty": 2,
      "unit_ids": ["DH-01", "DH-02"],
      "confidence": "high",
      "notes": "Both units clearly visible, condensate hoses routed to floor drain"
    }
  ],
  "not_visible": ["air scrubbers", "moisture meters / dataloggers"],
  "job_summary": "Residential water loss with equipment staged in 3 rooms",
  "equipment_count": 5,
  "rooms_with_equipment": ["Master Bedroom", "Hallway", "Bathroom"]
}"""


@shared_task(bind=True, max_retries=0)
def process_equipment_detect_task(self, session_id: str, image_paths: list,
                                   model: str = 'claude-sonnet-4-6',
                                   job_pdf_path: str = ''):
    """
    Auto-detect all water mitigation equipment visible in uploaded photos / PDF.
    No pre-defined item list required — Claude inventories everything it sees.
    """
    from django.conf import settings as django_settings
    import anthropic as _anthropic

    api_key = getattr(django_settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'result_type': 'detect', 'success': False,
                'error': 'ANTHROPIC_API_KEY not configured'}

    self.update_state(state='PROGRESS', meta={'step': 'Preparing detection scan…', 'percent': 5})

    content = []

    # Reference equipment PDF (gives Claude visual anchors for equipment types)
    if REFERENCE_PDF_PATH.exists():
        try:
            content.append({
                'type': 'document',
                'source': {'type': 'base64', 'media_type': 'application/pdf',
                           'data': _encode_pdf_b64(REFERENCE_PDF_PATH)},
            })
        except Exception as e:
            logger.warning(f"[equipment_detect] Could not load reference PDF: {e}")

    # Job site PDF report
    has_job_pdf = False
    if job_pdf_path:
        job_pdf = Path(job_pdf_path)
        if job_pdf.exists():
            try:
                self.update_state(state='PROGRESS', meta={
                    'step': f'Loading job report PDF ({job_pdf.stat().st_size // 1024} KB)…',
                    'percent': 12,
                })
                content.append({
                    'type': 'document',
                    'source': {'type': 'base64', 'media_type': 'application/pdf',
                               'data': _encode_pdf_b64(job_pdf)},
                })
                has_job_pdf = True
            except Exception as e:
                logger.warning(f"[equipment_detect] Could not load job PDF: {e}")

    # Individual photos
    loaded = 0
    if image_paths:
        self.update_state(state='PROGRESS', meta={
            'step': f'Loading {len(image_paths)} photos…', 'percent': 15,
        })
        for p in image_paths:
            try:
                b64, mt = _encode_image_b64(Path(p))
                content.append({'type': 'image',
                                'source': {'type': 'base64', 'media_type': mt, 'data': b64}})
                loaded += 1
            except Exception as e:
                logger.warning(f"[equipment_detect] Could not load image {p}: {e}")

    if not has_job_pdf and not loaded:
        return {'result_type': 'detect', 'success': False,
                'error': 'No images or PDF could be loaded'}

    content.append({'type': 'text', 'text': DETECT_PROMPT})

    source_parts = []
    if has_job_pdf:
        source_parts.append('report PDF')
    if loaded:
        source_parts.append(f'{loaded} photo{"s" if loaded != 1 else ""}')
    source_label = ' + '.join(source_parts)

    self.update_state(state='PROGRESS', meta={
        'step': f'Scanning {source_label} for equipment…', 'percent': 30,
    })

    client = _anthropic.Anthropic(api_key=api_key)
    result_data = None

    for attempt in range(1, 5):
        try:
            self.update_state(state='PROGRESS', meta={
                'step': f'Claude is identifying equipment… (attempt {attempt})',
                'percent': 40 + attempt * 13,
            })
            resp = client.messages.create(
                model=model,
                max_tokens=8096,
                messages=[{'role': 'user', 'content': content}],
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r'^```[a-z]*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            result_data = json.loads(raw.strip())
            break
        except _anthropic.RateLimitError:
            time.sleep(min(60, 2 ** attempt))
        except json.JSONDecodeError as e:
            logger.error(f"[equipment_detect] JSON parse failed (attempt {attempt}): {e}")
            if attempt == 4:
                return {'result_type': 'detect', 'success': False,
                        'error': f'Could not parse Claude response: {e}'}
            time.sleep(2)
        except _anthropic.APIError as e:
            if attempt == 4:
                return {'result_type': 'detect', 'success': False,
                        'error': f'Claude API error: {e}'}
            time.sleep(3)

    if result_data is None:
        return {'result_type': 'detect', 'success': False,
                'error': 'No valid response from Claude after retries'}

    detected = result_data.get('detected_equipment', [])
    total_units = sum(int(d.get('qty', 1) or 1) for d in detected)

    logger.info(
        f"[equipment_detect] session={session_id} types={len(detected)} "
        f"total_units={total_units} pdf={has_job_pdf} images={loaded}"
    )

    return {
        'result_type': 'detect',
        'success': True,
        'session_id': session_id,
        'detected': detected,
        'not_visible': result_data.get('not_visible', []),
        'job_summary': result_data.get('job_summary', ''),
        'equipment_types': len(detected),
        'equipment_units': total_units,
        'rooms': result_data.get('rooms_with_equipment', []),
    }
