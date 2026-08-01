"""
cps_report/duplicate_checker.py

Finds duplicate items and duplicate images within a CPSReportSession.

Item duplicates: text-based comparison of item descriptions across all rooms.
Image duplicates: perceptual (dHash) comparison of image URLs across all rooms.

Image comparison uses Pillow only — no external imagehash library required.
dHash: resize to 9x8 greyscale, compare adjacent columns → 64-bit fingerprint.
Hamming distance ≤ HASH_THRESHOLD → likely duplicate.
"""
import io
import logging
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests
from PIL import Image

logger = logging.getLogger(__name__)

HASH_THRESHOLD  = 8   # bits different — ≤ this → probable duplicate image
TEXT_THRESHOLD  = 0.85  # SequenceMatcher ratio — ≥ this → probable duplicate item
DOWNLOAD_TIMEOUT = 8    # seconds per image
MAX_WORKERS      = 10   # parallel image downloads


# ── Perceptual hash helpers ───────────────────────────────────────────────────

def _dhash(image: Image.Image, hash_size: int = 8) -> int:
    """
    Difference hash (dHash).  Returns a 64-bit int fingerprint.
    Image is resized to (hash_size+1) x hash_size greyscale,
    then bits are set where the left pixel is brighter than the right.
    """
    img = image.convert('L').resize((hash_size + 1, hash_size), Image.LANCZOS)
    pixels = list(img.getdata())
    bits = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left  = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count('1')


def _download_and_hash(url: str):
    """Download one image URL and return (url, hash_int) or (url, None) on error."""
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        return url, _dhash(img)
    except Exception as exc:
        logger.debug('Image hash failed for %s: %s', url, exc)
        return url, None


# ── Text duplicate detection ──────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return ' '.join(text.lower().split())


def find_text_duplicates(session):
    """
    Compare every item description across all rooms in the session.
    Returns a list of dicts, each describing a duplicate pair:
      {
        'item_a': {'id', 'room', 'description'},
        'item_b': {'id', 'room', 'description'},
        'score': 0.0–1.0,
        'exact': bool,
      }
    """
    items = []
    for room in session.rooms.prefetch_related('items').order_by('order'):
        for item in room.items.all():
            desc = (item.description or '').strip()
            if not desc:
                continue
            items.append({
                'id':          item.id,
                'room':        room.room_name or f'Room {room.order}',
                'room_id':     room.id,
                'description': desc,
                '_norm':       _normalise(desc),
            })

    duplicates = []
    seen = set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            key = (items[i]['id'], items[j]['id'])
            if key in seen:
                continue
            seen.add(key)
            a_norm = items[i]['_norm']
            b_norm = items[j]['_norm']
            if a_norm == b_norm:
                score = 1.0
                exact = True
            else:
                score = SequenceMatcher(None, a_norm, b_norm).ratio()
                exact = False
            if score >= TEXT_THRESHOLD:
                duplicates.append({
                    'item_a': {
                        'id':          items[i]['id'],
                        'room':        items[i]['room'],
                        'room_id':     items[i]['room_id'],
                        'description': items[i]['description'],
                    },
                    'item_b': {
                        'id':          items[j]['id'],
                        'room':        items[j]['room'],
                        'room_id':     items[j]['room_id'],
                        'description': items[j]['description'],
                    },
                    'score': round(score, 3),
                    'exact': exact,
                })

    duplicates.sort(key=lambda d: -d['score'])
    return duplicates


# ── Image duplicate detection ─────────────────────────────────────────────────

def find_image_duplicates(session):
    """
    Download every unique image URL in the session, compute dHash,
    and find pairs with Hamming distance ≤ HASH_THRESHOLD.

    Returns a list of dicts:
      {
        'url_a': str, 'url_b': str,
        'rooms_a': [room_name, ...], 'rooms_b': [room_name, ...],
        'hamming': int,
        'exact': bool (hamming == 0),
      }
    """
    # Build url → [room names] mapping
    url_to_rooms = {}
    for room in session.rooms.all().order_by('order'):
        rname = room.room_name or f'Room {room.order}'
        for url in (room.analyzed_image_urls or []):
            if url:
                url_to_rooms.setdefault(url, []).append(rname)
        for item in room.items.all():
            for url in (item.source_image_urls or []):
                if url and url not in url_to_rooms:
                    url_to_rooms.setdefault(url, []).append(rname)

    all_urls = list(url_to_rooms.keys())
    if not all_urls:
        return []

    # Parallel download + hash
    url_hashes = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_download_and_hash, url): url for url in all_urls}
        for future in as_completed(futures):
            url, h = future.result()
            if h is not None:
                url_hashes[url] = h

    hashed_urls = list(url_hashes.items())   # [(url, hash), ...]

    duplicates = []
    for i in range(len(hashed_urls)):
        for j in range(i + 1, len(hashed_urls)):
            url_a, h_a = hashed_urls[i]
            url_b, h_b = hashed_urls[j]
            dist = _hamming(h_a, h_b)
            if dist <= HASH_THRESHOLD:
                duplicates.append({
                    'url_a':   url_a,
                    'url_b':   url_b,
                    'rooms_a': url_to_rooms.get(url_a, []),
                    'rooms_b': url_to_rooms.get(url_b, []),
                    'hamming': dist,
                    'exact':   dist == 0,
                })

    duplicates.sort(key=lambda d: d['hamming'])
    return duplicates


# ── Top-level entry point ─────────────────────────────────────────────────────

def run_duplicate_check(session):
    """
    Run both checks and return a combined result dict.
    Called from the view — runs synchronously (reasonable for ≤300 images).
    """
    text_dupes  = find_text_duplicates(session)
    image_dupes = find_image_duplicates(session)
    return {
        'text_duplicates':  text_dupes,
        'image_duplicates': image_dupes,
        'text_count':       len(text_dupes),
        'image_count':      len(image_dupes),
        'exact_text':       sum(1 for d in text_dupes  if d['exact']),
        'exact_images':     sum(1 for d in image_dupes if d['exact']),
    }
