"""
Live price lookup via Serper.dev (Google Shopping results API).

Given an item search query, returns a list of real product listings, each with
a vendor, price, and a direct link to that product at that price. This replaces
AI-guessed replacement values with verifiable market prices.

Configuration:
    SERPER_API_KEY  — required. Get a free key at https://serper.dev
                      Read from Django settings or the environment.

If no key is configured, search functions return an empty list so the caller
can gracefully fall back to an AI estimate.
"""
from __future__ import annotations

import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

_SERPER_SHOPPING_URL = "https://google.serper.dev/shopping"
_TIMEOUT = 20


def _get_api_key() -> str:
    key = os.getenv('SERPER_API_KEY', '')
    if not key:
        try:
            from django.conf import settings
            key = getattr(settings, 'SERPER_API_KEY', '') or ''
        except Exception:
            key = ''
    return key


def is_configured() -> bool:
    return bool(_get_api_key())


_PRICE_RE = re.compile(r'[-+]?\d[\d,]*\.?\d*')


def _parse_price(raw) -> float | None:
    """Turn '$1,299.00', '1299', 'US$45.99' → 1299.0 / 45.99. None if unparseable."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = _PRICE_RE.search(str(raw).replace(',', ''))
    if not m:
        return None
    try:
        val = float(m.group().replace(',', ''))
        return val if val > 0 else None
    except ValueError:
        return None


def search_item_prices(query: str, num: int = 8, gl: str = 'us') -> list[dict]:
    """
    Search Google Shopping (via Serper.dev) for `query` and return listings:

        [{"vendor": str, "price": float, "url": str, "title": str, "in_stock": bool}, ...]

    Sorted cheapest-first among listings that have a usable price and link.
    Returns [] on any failure or if SERPER_API_KEY is not configured.
    """
    query = (query or '').strip()
    if not query:
        return []

    api_key = _get_api_key()
    if not api_key:
        logger.warning("price_finder: SERPER_API_KEY not configured — skipping live lookup")
        return []

    try:
        resp = requests.post(
            _SERPER_SHOPPING_URL,
            headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'},
            json={'q': query, 'gl': gl, 'num': num},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning(f"price_finder: search failed for {query!r}: {exc}")
        return []

    listings: list[dict] = []
    for row in (data.get('shopping') or []):
        price = _parse_price(row.get('price'))
        url   = row.get('link') or ''
        if price is None or not url:
            continue
        listings.append({
            'vendor':   (row.get('source') or '').strip(),
            'price':    price,
            'url':      url,
            'title':    (row.get('title') or '').strip()[:300],
            'in_stock': 'out of stock' not in (str(row.get('availability') or '')).lower(),
        })

    listings.sort(key=lambda x: x['price'])
    logger.info(f"price_finder: {len(listings)} listings for {query!r}")
    return listings[:num]
