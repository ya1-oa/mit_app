"""
sensor_renamer/tasks.py
=======================
Celery task for processing sensor/instrument images with Claude Vision.
Runs as a background task; dispatched from sensor_renamer.views.
"""
import re
import json
import time
import base64
import shutil
import concurrent.futures
import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

# ── Sub-folder names (must match template expectations) ──────────────────────
SUB_RH  = "RH_T_GPP"
SUB_T   = "T_RH_GPP"
SUB_GPP = "GPP_RH_T"
SUB_MC  = "MC"
SUB_NA  = "NA_Review"
ALL_SUBFOLDERS = (SUB_RH, SUB_T, SUB_GPP, SUB_MC, SUB_NA)

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

AUTO_PROMPT = """You are a precise sensor-display reading extraction system.

Examine this image and first determine what TYPE of sensor device is shown:

  TYPE A — Moisture Content (MC) meter:
    • Typically shows ONE primary numeric reading
    • Usually a handheld pin-type or non-contact moisture meter
    • Display shows a single percentage value (e.g. 19.5, 8.3)
    • May be labeled: MC, Moisture, M%, %MC, or just a bare number with %

  TYPE B — Environmental / Air Quality logger:
    • Shows MULTIPLE readings simultaneously (2 or 3 values)
    • Readings are: RH (relative humidity %), T (temperature °C or °F),
      and GPP (e.g. g/kg, ppm, µmol/m²/s, or similar)
    • Each value is clearly labeled on-screen or on the device face

INSTRUCTIONS:
1. Look at the entire device — count how many distinct numeric readings are displayed.
2. Identify the device type (A = single MC value, B = multi-value RH/T/GPP).
3. Read each value exactly as shown. Round to ONE decimal place.
4. If a value is present but unreadable, use null. Do NOT guess.
5. Respond with ONLY a raw JSON object — no markdown, no text, nothing else.

JSON schema:
  For TYPE A (MC device):
    {"type": "MC", "MC": <float|null>}

  For TYPE B (RH/T/GPP device):
    {"type": "RH_T_GPP", "RH": <float|null>, "T": <float|null>, "GPP": <float|null>}

Valid response examples:
  {"type": "MC", "MC": 19.5}
  {"type": "MC", "MC": null}
  {"type": "RH_T_GPP", "RH": 65.3, "T": 22.1, "GPP": 450.7}
  {"type": "RH_T_GPP", "RH": 72.0, "T": null, "GPP": 310.5}
"""


# ── Pure helper functions ─────────────────────────────────────────────────────

def _encode_b64(path: Path):
    ext = path.suffix.lower().lstrip(".")
    mt = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "bmp": "image/bmp", "tiff": "image/tiff", "tif": "image/tiff",
        "webp": "image/webp",
    }.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode(), mt


def _rf(val):
    try:
        return round(float(val), 1) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_response(text: str) -> dict:
    text = re.sub(r"^```[a-z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
        dtype = data.get("type", "unknown")
        if dtype == "MC":
            return {"device_type": "MC", "MC": _rf(data.get("MC")),
                    "RH": None, "T": None, "GPP": None}
        elif dtype == "RH_T_GPP":
            return {"device_type": "RH_T_GPP", "MC": None,
                    "RH": _rf(data.get("RH")), "T": _rf(data.get("T")),
                    "GPP": _rf(data.get("GPP"))}
    except Exception:
        pass
    return {"device_type": "unknown", "MC": None, "RH": None, "T": None, "GPP": None}


def _extract_with_claude(api_key: str, image_path: Path, model: str, retries: int = 4) -> dict:
    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=api_key)
    b64, mt = _encode_b64(image_path)
    for attempt in range(1, retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=300,
                messages=[{"role": "user", "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": mt, "data": b64}},
                    {"type": "text", "text": AUTO_PROMPT},
                ]}],
            )
            return _parse_response(resp.content[0].text)
        except _anthropic.RateLimitError:
            time.sleep(min(60, 2 ** attempt))
        except _anthropic.APIError:
            if attempt == retries:
                raise
            time.sleep(3)
    return {"device_type": "unknown", "MC": None, "RH": None, "T": None, "GPP": None}


def _fv(val) -> str:
    return f"{val:.1f}" if val is not None else "NA"


def result_has_na(result: dict) -> bool:
    if result["device_type"] == "MC":
        return result["MC"] is None
    if result["device_type"] == "RH_T_GPP":
        return any(result[k] is None for k in ("RH", "T", "GPP"))
    return True


def build_filenames(result: dict, ext: str) -> dict:
    dtype = result["device_type"]
    na = result_has_na(result)
    if dtype == "RH_T_GPP" and not na:
        rh, t, gpp = _fv(result["RH"]), _fv(result["T"]), _fv(result["GPP"])
        return {
            SUB_RH:  f"RH{rh}_T{t}_GPP{gpp}{ext}",
            SUB_T:   f"T{t}_RH{rh}_GPP{gpp}{ext}",
            SUB_GPP: f"GPP{gpp}_RH{rh}_T{t}{ext}",
        }
    if dtype == "MC" and not na:
        return {SUB_MC: f"MC{_fv(result['MC'])}{ext}"}
    if dtype == "RH_T_GPP":
        name = f"RH{_fv(result['RH'])}_T{_fv(result['T'])}_GPP{_fv(result['GPP'])}{ext}"
    elif dtype == "MC":
        name = f"MC{_fv(result['MC'])}{ext}"
    else:
        name = f"UNKNOWN{ext}"
    return {SUB_NA: name}


def safe_dest(dest_dir: Path, filename: str) -> Path:
    c = dest_dir / filename
    if not c.exists():
        return c
    stem, sfx = Path(filename).stem, Path(filename).suffix
    n = 2
    while True:
        c = dest_dir / f"{stem}_{n}{sfx}"
        if not c.exists():
            return c
        n += 1


# ── Celery Task ───────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=0)
def process_sensor_images_task(self, session_id: str, image_paths: list,
                                model: str = "claude-sonnet-4-6", workers: int = 4):
    """
    Process sensor images with Claude Vision. Runs in Celery background worker.

    Args:
        session_id:   UUID string identifying this batch session
        image_paths:  List of absolute paths to uploaded images
        model:        Claude model ID
        workers:      Thread concurrency for API calls

    Returns:
        dict with per-image results and summary counts.
    """
    from django.conf import settings as django_settings

    api_key = getattr(django_settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'success': False, 'error': 'ANTHROPIC_API_KEY not configured in settings'}

    output_root = Path(django_settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'output'
    for sub in ALL_SUBFOLDERS:
        (output_root / sub).mkdir(parents=True, exist_ok=True)

    total = len(image_paths)
    done_count = [0]
    results = []

    def process_one(img_path_str: str) -> dict:
        img_path = Path(img_path_str)
        try:
            result = _extract_with_claude(api_key, img_path, model)
        except Exception as exc:
            logger.warning(f"Claude API error for {img_path.name}: {exc}")
            result = {"device_type": "unknown", "MC": None, "RH": None, "T": None, "GPP": None}

        ext = img_path.suffix.lower()
        na = result_has_na(result)
        dtype = result["device_type"]
        file_map = build_filenames(result, ext)

        for sub, fname in file_map.items():
            sub_dir = output_root / sub
            sub_dir.mkdir(parents=True, exist_ok=True)
            dest = safe_dest(sub_dir, fname)
            try:
                shutil.copy2(img_path, dest)
            except Exception as copy_exc:
                logger.warning(f"Copy error for {img_path.name} → {sub}/{fname}: {copy_exc}")

        done_count[0] += 1
        self.update_state(state='PROGRESS', meta={
            'done': done_count[0],
            'total': total,
            'percent': int(done_count[0] / total * 100),
            'current_file': img_path.name,
        })
        logger.info(f"[sensor] {done_count[0]}/{total} [{dtype}] {img_path.name} → "
                    + ", ".join(file_map.keys()))

        return {
            'original': img_path.name,
            'device_type': dtype,
            'has_na': na,
            'destinations': ', '.join(f'{s}/{f}' for s, f in file_map.items()),
            'MC':  result['MC'],
            'RH':  result['RH'],
            'T':   result['T'],
            'GPP': result['GPP'],
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(process_one, p): p for p in image_paths}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                logger.error(f"Worker error: {exc}")
                results.append({'original': str(futures[future]), 'device_type': 'unknown',
                                 'has_na': True, 'error': str(exc)})

    na_count  = sum(1 for r in results if r.get('has_na'))
    rh_count  = sum(1 for r in results if r.get('device_type') == 'RH_T_GPP' and not r.get('has_na'))
    mc_count  = sum(1 for r in results if r.get('device_type') == 'MC' and not r.get('has_na'))
    unk_count = sum(1 for r in results if r.get('device_type') == 'unknown')

    logger.info(f"[sensor] session {session_id} done — "
                f"RH:{rh_count} MC:{mc_count} NA:{na_count} UNK:{unk_count}")

    return {
        'success': True,
        'session_id': session_id,
        'total': total,
        'rh_count': rh_count,
        'mc_count': mc_count,
        'na_count': na_count,
        'unk_count': unk_count,
        'results': results,
    }
