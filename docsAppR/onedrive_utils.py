"""OneDrive/SharePoint API helper utilities."""

import base64
import logging
import os
import re
import requests
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CLIENT_ID     = os.getenv("GRAPH_CLIENT_ID")
REDIRECT_URI  = os.getenv("GRAPH_REDIRECT_URI", "https://login.microsoftonline.com/common/oauth2/nativeclient")
SCOPE         = os.getenv("GRAPH_SCOPE", "offline_access Files.ReadWrite.All")
TENANT        = os.getenv("GRAPH_TENANT", "consumers")
REFRESH_TOKEN = os.getenv("GRAPH_REFRESH_TOKEN")
SHARED_ROOT_LINK = os.getenv("SHARED_ROOT_LINK")
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
GRAPH = "https://graph.microsoft.com/v1.0"

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}

# --- Token Management ---
def _access_token_from_refresh():
    if not REFRESH_TOKEN:
        raise RuntimeError("GRAPH_REFRESH_TOKEN is missing.")
    data = {
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI
    }
    r = requests.post(TOKEN_URL, data=data, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Token refresh failed: {r.status_code} {r.text}")
    return r.json()["access_token"]

def _share_id_from_url(shared_url: str) -> str:
    b = shared_url.encode("utf-8")
    s = base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")
    return "u!" + s

# --- OneDrive Navigation ---
def _encode_path_segments(relative_path: str) -> str:
    segments = relative_path.split('/')
    encoded = ':/' + '/'.join(f"'{quote(seg, safe='')}'" for seg in segments)
    return encoded

def _get_shared_root_item(token: str, share_id: str):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH}/shares/{share_id}/driveItem"
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

def _list_children_by_path(token: str, drive_id: str, item_id: str, relative_path: str = None):
    headers = {"Authorization": f"Bearer {token}"}
    if relative_path:
        encoded_path = _encode_path_segments(relative_path)
        url = f"{GRAPH}/drives/{drive_id}/items/{item_id}{encoded_path}:/children"
    else:
        url = f"{GRAPH}/drives/{drive_id}/items/{item_id}/children"
    url += "?$select=id,name,folder,file,@microsoft.graph.downloadUrl"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("value", [])

# --- Helpers ---
def _is_image(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in IMG_EXT)

def _day_label(name: str):
    if "rht" not in name.lower():
        return None
    m = re.search(r"day\s*([1-4])", name, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None

def _num_prefix(filename: str):
    m = re.match(r"^\s*(\d+)", filename)
    return int(m.group(1)) if m else None

def _find_estimates_folder(token: str, drive_id: str, item_id: str):
    try:
        children = _list_children_by_path(token, drive_id, item_id)
        logger.info(f"Found {len(children)} children in folder")
        for child in children:
            name = child.get('name', '')
            if not child.get('folder'):
                continue
            name_lower = name.lower()
            if '01-' in name_lower and ('insurance' in name_lower or 'estimates' in name_lower or 'current-ins' in name_lower):
                logger.info(f"✓ Found estimates folder: {name}")
                return child
        for child in children:
            if not child.get('folder'):
                continue
            name_lower = child.get('name', '').lower()
            if name_lower in ['documents', 'claims', 'projects']:
                logger.info(f"Recursing into {child.get('name')}...")
                result = _find_estimates_folder(token, drive_id, child.get('id'))
                if result:
                    return result
        return None
    except Exception as e:
        logger.error(f"Error searching for estimates folder: {str(e)}")
        return None
