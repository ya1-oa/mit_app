"""
Encircle Dashboard app views.
All Encircle API interactions, sync/comparison, webhooks, and room entry generation.
"""
import csv
import datetime as dt
import json
import logging
import re
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template import Context, Template
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.conf import settings

from docsAppR.encircle_client import (
    EncircleAPIClient,
    EncircleDataProcessor,
    EncircleExcelExporter,
)
from docsAppR.onedrive_utils import (
    SHARED_ROOT_LINK,
    _access_token_from_refresh,
    _find_estimates_folder,
    _get_shared_root_item,
    _list_children_by_path,
    _share_id_from_url,
)
from docsAppR.room_entry_generator import (
    generate_8000_9000_entries,
    generate_8000s_entries,
    generate_9000s_entries,
    generate_10000s_entries,
    generate_70000_entries,
    generate_job_types_entries,
)
from automations.tasks import RoomTemplateAutomation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache constants
# ---------------------------------------------------------------------------
ENCIRCLE_CACHE_KEY = 'encircle_claims_data'
ONEDRIVE_CACHE_KEY = 'onedrive_claims_data'
CACHE_TIMEOUT = 3600 * 24  # 24 hours

# ---------------------------------------------------------------------------
# Test-data exclusion patterns
# ---------------------------------------------------------------------------
_TEST_EXCLUDE_PATTERNS = [
    'HOW2', 'TEST', 'TEMPLATE', 'SAMPLE', 'ROOMLISTS', 'READINGS',
    'TMPL', 'CHECKLIST', 'TRAILER', 'WAREHOUSE', 'DEFAULT', 'TEMP',
    'PLACEHOLDER', 'EXAMPLE', 'DEMO', 'XXXX', 'AAA', '===', 'BACKEND', 'TUTORIAL'
]


# ===========================================================================
# Simple normalisation helpers
# ===========================================================================

def normalize_text(text):
    if not text:
        return ""
    return ' '.join(text.upper().split())


def normalize_year_code(code):
    if not code:
        return ""
    match = re.match(r'^([A-Z]{2}\d{2})', code.upper())
    if match:
        return match.group(1)
    return code.upper()


def normalize_name(name):
    if not name:
        return ""
    name = name.upper().strip()
    variations = {
        'CLEGGETT': 'CLEGGET',
        'CLEGGET': 'CLEGGET',
        'GOLLATTE': 'GOLLATE',
        'GOLLATE': 'GOLLATE',
        'THORNTON': 'THORTON',
        'THORTON': 'THORTON',
    }
    for original, normalized in variations.items():
        if original in name:
            name = name.replace(original, normalized)
    return name


def extract_tokens(text):
    if not text:
        return set()
    text = normalize_name(text)
    parts = text.split('@')
    main_part = parts[0] if parts else text
    address_part = parts[1] if len(parts) > 1 else ""
    tokens = re.findall(r'\b[A-Z0-9]{2,}\b', main_part.upper())
    if address_part:
        tokens.extend(re.findall(r'\b[A-Z0-9]{2,}\b', address_part.upper()))
    normalized_codes = {normalize_year_code(t) for t in tokens if normalize_year_code(t) != t}
    noise = {'LLC', 'INC', 'THE', 'AND', 'FOR', 'CLAIM', 'EST', 'FIRE', 'WATER',
             'STORM', 'WTR', 'RFG', 'INT', 'CPS', 'USAA', 'DMO', 'SOL', 'FSR', 'MIT'}
    tokens = [t for t in tokens if t not in noise and len(t) >= 2]
    return set(tokens) | normalized_codes


def extract_location_code(text):
    if not text:
        return None
    match = re.search(r'\b([A-Z]{2}\d{2}[A-Z0-9\-]*)\b', text.upper())
    if match:
        return normalize_year_code(match.group(1))
    return None


def extract_contractor_id_from_folder(folder_name):
    if not folder_name:
        return ''
    s = str(folder_name).strip().upper()
    m = re.search(r'\b([A-Z]{2,3}\d{2,3}-\d{2,4})\b', s)
    if m:
        return m.group(1)
    m = re.search(r'\b([A-Z]{2,3}\d{2,3}[A-Z]{0,3})\b', s)
    if m:
        return m.group(1)
    m = re.search(r'\b(\d{6,})\b', s)
    if m:
        return m.group(1)
    m = re.search(r'\b(C\d{3,})\b', s)
    if m:
        return m.group(1)
    m = re.search(r'\b(\d{3}-\d{3,})\b', s)
    if m:
        return m.group(1)
    return ''


def normalize_claim_name(name):
    normalized = name.upper().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    for word in ['CLAIM', 'INSURANCE', 'ESTIMATE', 'PROJECT', 'RENOVATION']:
        normalized = re.sub(r'\b' + re.escape(word) + r'\b', '', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def calculate_match_score(encircle_contractor, folder_name):
    if not encircle_contractor or not folder_name:
        return 0.0
    contractor_norm = normalize_text(encircle_contractor)
    folder_norm = normalize_text(folder_name)
    contractor_tokens = extract_tokens(contractor_norm)
    folder_tokens = extract_tokens(folder_norm)
    common_tokens = contractor_tokens.intersection(folder_tokens)
    num_matches = len(common_tokens)
    if num_matches >= 2:
        return 0.85
    score = 0.0
    if contractor_norm in folder_norm or folder_norm in contractor_norm:
        score += 0.4
    contractor_location = extract_location_code(contractor_norm)
    folder_location = extract_location_code(folder_norm)
    if contractor_location and folder_location:
        if contractor_location == folder_location:
            score += 0.3
        elif contractor_location[:4] == folder_location[:4]:
            score += 0.2
    if num_matches == 1:
        score += 0.3
    return min(score, 1.0)


def _is_valid_claim(claim):
    if not claim.get('policyholder_name') and not claim.get('contractor_identifier'):
        return False
    policyholder = (claim.get('policyholder_name') or '').upper()
    contractor = (claim.get('contractor_identifier') or '').upper()
    return not any(p in policyholder or p in contractor for p in _TEST_EXCLUDE_PATTERNS)


def _is_valid_folder(folder_claim):
    folder_name = (folder_claim.get('folder_name') or '').upper()
    exclude = _TEST_EXCLUDE_PATTERNS + [
        'CLOSED CLAIMS', 'PROOF OF LOSS', 'DRAWINGS', 'APPRAISALS', 'FOLDER', 'TEXT'
    ]
    if any(p in folder_name for p in exclude):
        return False
    return len(re.sub(r'[^A-Z]', '', folder_name)) >= 3


def find_duplicates(encircle_claims, onedrive_claims):
    duplicates = {'encircle_duplicates': [], 'onedrive_duplicates': []}
    contractor_count = defaultdict(list)
    for claim in encircle_claims:
        cid = claim.get('contractor_identifier', '')
        if cid and cid.strip():
            contractor_count[cid].append(claim)
    for cid, claims in contractor_count.items():
        if len(claims) > 1:
            duplicates['encircle_duplicates'].append({'contractor_id': cid, 'count': len(claims), 'claims': claims})
    folder_count = defaultdict(list)
    for claim in onedrive_claims:
        fn = claim.get('folder_name', '')
        if fn:
            folder_count[normalize_text(fn)].append(claim)
    for fn, claims in folder_count.items():
        if len(claims) > 1:
            duplicates['onedrive_duplicates'].append({'folder_name': fn, 'count': len(claims), 'claims': claims})
    return duplicates


# ===========================================================================
# Data fetching with cache
# ===========================================================================

def get_encircle_claims(use_cache=True):
    if use_cache:
        cached = cache.get(ENCIRCLE_CACHE_KEY)
        if cached:
            return cached
    api_client = EncircleAPIClient()
    processor = EncircleDataProcessor()
    raw_claims = api_client.get_all_claims()
    processed_claims = processor.process_claims_list(raw_claims)
    for claim in processed_claims:
        try:
            claim_details = api_client.get_claim_details(claim['id'])
            detailed = processor.process_claim_details(claim_details)
            claim['contractor_identifier'] = str(detailed.get('contractor_identifier', '') or '').strip()
            claim['policyholder_name'] = str(detailed.get('policyholder_name', '') or '').strip()
            claim['full_address'] = str(detailed.get('full_address', '') or '').strip()
            claim['insurance_company_name'] = str(detailed.get('insurance_company_name', '') or '').strip()
        except Exception as e:
            logger.warning(f"Could not fetch details for claim {claim['id']}: {e}")
            claim.setdefault('contractor_identifier', '')
            claim.setdefault('policyholder_name', '')
            claim.setdefault('full_address', '')
            claim.setdefault('insurance_company_name', '')
    cache.set(ENCIRCLE_CACHE_KEY, processed_claims, CACHE_TIMEOUT)
    return processed_claims


def get_onedrive_claims(use_cache=True):
    if use_cache:
        cached = cache.get(ONEDRIVE_CACHE_KEY)
        if cached:
            return cached
    token = _access_token_from_refresh()
    share_id = _share_id_from_url(SHARED_ROOT_LINK)
    root_item = _get_shared_root_item(token, share_id)
    drive_id = root_item["parentReference"]["driveId"]
    root_item_id = root_item["id"]
    estimates_item = _find_estimates_folder(token, drive_id, root_item_id)
    if not estimates_item:
        return []
    estimates_id = estimates_item.get('id')
    folders = _list_children_by_path(token, drive_id, estimates_id)
    claims = []
    for folder in folders:
        if not folder.get('folder'):
            continue
        folder_name = folder.get('name', '')
        folder_id = folder.get('id')
        if not folder_id:
            continue
        try:
            folder_contents = _list_children_by_path(token, drive_id, folder_id)
            has_info_file = any(
                item.get('name', '').lower().startswith('01-info') and
                item.get('name', '').lower().endswith(('.xlsx', '.xls'))
                for item in folder_contents
            )
            contractor_id = extract_contractor_id_from_folder(folder_name)
            claims.append({
                'folder_name': folder_name,
                'folder_id': folder_id,
                'has_info_file': has_info_file,
                'contractor_identifier': contractor_id,
                'normalized_name': normalize_claim_name(folder_name),
                'file_count': len(folder_contents),
            })
        except Exception as e:
            contractor_id = extract_contractor_id_from_folder(folder_name)
            claims.append({
                'folder_name': folder_name,
                'folder_id': folder_id,
                'has_info_file': False,
                'contractor_identifier': contractor_id,
                'normalized_name': normalize_claim_name(folder_name),
                'error': str(e),
                'file_count': 0,
            })
    cache.set(ONEDRIVE_CACHE_KEY, claims, CACHE_TIMEOUT)
    return claims


# ===========================================================================
# Matching & report generation
# ===========================================================================

def compare_claims(encircle_claims, onedrive_claims):
    valid_encircle = [c for c in encircle_claims if _is_valid_claim(c)]
    valid_onedrive = [c for c in onedrive_claims if _is_valid_folder(c)]
    encircle_test = [c for c in encircle_claims if not _is_valid_claim(c)]
    onedrive_test = [c for c in onedrive_claims if not _is_valid_folder(c)]

    results = {
        'summary': {
            'total_encircle': len(encircle_claims),
            'total_onedrive': len(onedrive_claims),
            'valid_encircle': len(valid_encircle),
            'valid_onedrive': len(valid_onedrive),
            'matches': 0,
            'encircle_only': 0,
            'onedrive_only': 0,
            'encircle_test_data': len(encircle_test),
            'onedrive_test_data': len(onedrive_test),
            'match_breakdown': {'high_confidence': 0, 'medium_confidence': 0, 'low_confidence': 0},
        },
        'matched_pairs': [],
        'encircle_missing_onedrive': [],
        'onedrive_extra': [],
        'encircle_test_data': encircle_test,
        'onedrive_test_data': onedrive_test,
        'duplicates': find_duplicates(valid_encircle, valid_onedrive),
    }

    matched_encircle = set()
    matched_onedrive = set()
    MATCH_THRESHOLD = 0.65

    for ec in valid_encircle:
        contractor_id = ec.get('contractor_identifier', '').strip()
        if not contractor_id:
            continue
        best_match, best_score = None, 0
        for od in valid_onedrive:
            if od['folder_id'] in matched_onedrive:
                continue
            score = calculate_match_score(contractor_id, od.get('folder_name', ''))
            if score > best_score:
                best_score, best_match = score, od
        if best_match and best_score >= MATCH_THRESHOLD:
            confidence = "High" if best_score >= 0.8 else "Medium" if best_score >= 0.65 else "Low"
            results['matched_pairs'].append({
                'encircle': ec,
                'onedrive': best_match,
                'match_type': f'Fuzzy Match ({confidence})',
                'confidence': f'{int(best_score * 100)}%',
            })
            matched_encircle.add(ec['id'])
            matched_onedrive.add(best_match['folder_id'])
            results['summary']['matches'] += 1
            key = 'high_confidence' if best_score >= 0.8 else 'medium_confidence' if best_score >= 0.65 else 'low_confidence'
            results['summary']['match_breakdown'][key] += 1

    for ec in valid_encircle:
        if ec['id'] not in matched_encircle:
            results['encircle_missing_onedrive'].append(ec)
            results['summary']['encircle_only'] += 1
    for od in valid_onedrive:
        if od['folder_id'] not in matched_onedrive:
            results['onedrive_extra'].append(od)
            results['summary']['onedrive_only'] += 1

    return results


def _coerce_report_defaults(results):
    results.setdefault('matched_pairs', [])
    results.setdefault('encircle_missing_onedrive', [])
    results.setdefault('onedrive_extra', [])
    results.setdefault('encircle_test_data', [])
    results.setdefault('onedrive_test_data', [])
    summary = results.setdefault('summary', {})
    summary.setdefault('total_encircle', 0)
    summary.setdefault('total_onedrive', 0)
    summary.setdefault('valid_encircle', 0)
    summary.setdefault('valid_onedrive', 0)
    summary.setdefault('matches', len(results['matched_pairs']))
    summary.setdefault('encircle_only', len(results['encircle_missing_onedrive']))
    summary.setdefault('onedrive_only', len(results['onedrive_extra']))
    summary.setdefault('encircle_test_data', len(results['encircle_test_data']))
    summary.setdefault('onedrive_test_data', len(results['onedrive_test_data']))
    summary.setdefault('match_breakdown', {'high_confidence': 0, 'medium_confidence': 0, 'low_confidence': 0})
    summary['issues_total'] = summary['encircle_only'] + summary['onedrive_only']
    summary['test_total'] = summary['encircle_test_data'] + summary['onedrive_test_data']
    unique_matched = len(set(pair['encircle']['id'] for pair in results['matched_pairs']))
    summary['unique_matches'] = unique_matched
    results['encircle_render_total'] = unique_matched + summary['encircle_only']
    results['onedrive_render_total'] = summary['matches'] + summary['onedrive_only']
    return results


def generate_comparison_report(comparison_results, is_refresh=False):
    template_content = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claims Sync Report</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background:#f5f5f5; color:#333; line-height:1.4; }
.container { max-width:1800px; margin:0 auto; background:white; }
.header { background:linear-gradient(135deg,#2c3e50 0%,#3498db 100%); color:white; padding:30px; text-align:center; position:relative; }
.header h1 { font-size:2em; margin-bottom:8px; }
.cache-badge { position:absolute; top:15px; right:20px; background:rgba(255,255,255,.2); padding:8px 15px; border-radius:20px; font-size:.85em; }
.cache-badge.cached { background:#27ae60; }
.cache-badge.fresh { background:#e74c3c; }
.status-bar { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; padding:20px; background:#ecf0f1; }
.status-card { background:white; padding:12px; border-radius:6px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,.1); }
.status-card .label { font-size:.75em; color:#666; margin-bottom:6px; font-weight:600; text-transform:uppercase; }
.status-card .value { font-size:1.6em; font-weight:bold; }
.status-card .sub-value { font-size:.7em; color:#999; margin-top:3px; }
.status-card.matched .value { color:#27ae60; }
.status-card.missing .value { color:#e74c3c; }
.status-card.encircle .value { color:#3498db; }
.status-card.onedrive .value { color:#2980b9; }
.status-card.test-data .value { color:#f39c12; }
.content { padding:20px; }
.section { margin-bottom:30px; }
.section-title { font-size:1.3em; font-weight:600; color:#2c3e50; margin-bottom:15px; padding-bottom:8px; border-bottom:2px solid #3498db; }
.claims-list { background:#f8f9fa; padding:15px; border-radius:6px; max-height:400px; overflow-y:auto; }
.claim-row { display:flex; align-items:center; padding:8px 12px; margin-bottom:5px; background:white; border-radius:4px; border-left:4px solid #e74c3c; font-size:.9em; }
.claim-row.matched { border-left-color:#27ae60; background:#f0f8ff; }
.claim-row.unmatched { border-left-color:#e74c3c; background:#fff5f5; }
.claim-row.extra { border-left-color:#f39c12; background:#fff9e6; }
.claim-name { flex:1; font-weight:600; }
.claim-details { flex:2; color:#666; font-size:.85em; }
.claim-id { flex:1; color:#999; font-size:.8em; }
.note { background:#fff9e6; padding:10px; border-radius:4px; margin:12px 0; border-left:4px solid #f39c12; font-size:.9em; }
.match-breakdown { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin:12px 0; }
.breakdown-item { background:#f8f9fa; padding:8px; border-radius:4px; text-align:center; }
.breakdown-item .count { font-size:1.1em; font-weight:bold; color:#2c3e50; }
.breakdown-item .label { font-size:.75em; color:#666; }
.footer { text-align:center; padding:15px; color:#999; font-size:.8em; border-top:1px solid #ecf0f1; }
.refresh-links { text-align:center; padding:15px; background:#ecf0f1; }
.refresh-links a { display:inline-block; margin:0 10px; padding:10px 20px; background:#3498db; color:white; text-decoration:none; border-radius:4px; font-weight:600; }
.refresh-links a.refresh { background:#e74c3c; }
.refresh-links a.export { background:#27ae60; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Claims Sync Report</h1>
    <p>Encircle System vs OneDrive Storage</p>
    {% if is_refresh %}<div class="cache-badge fresh">Fresh Data</div>
    {% else %}<div class="cache-badge cached">Cached Data</div>{% endif %}
  </div>
  <div class="refresh-links">
    <a href="?">View Report (Cached)</a>
    <a href="/sync/refresh/" class="refresh">Refresh Data</a>
    <a href="/sync/export/encircle/" class="export">Export Encircle CSV</a>
    <a href="/sync/export/onedrive/" class="export">Export OneDrive CSV</a>
  </div>
  <div class="status-bar">
    <div class="status-card encircle">
      <div class="label">Encircle Total</div>
      <div class="value">{{ summary.valid_encircle|default:0 }}</div>
      <div class="sub-value">{{ summary.encircle_test_data|default:0 }} test excluded</div>
    </div>
    <div class="status-card onedrive">
      <div class="label">OneDrive Total</div>
      <div class="value">{{ summary.valid_onedrive|default:0 }}</div>
      <div class="sub-value">{{ summary.onedrive_test_data|default:0 }} test excluded</div>
    </div>
    <div class="status-card matched">
      <div class="label">Matches</div>
      <div class="value">{{ summary.matches|default:0 }}</div>
      <div class="sub-value">real claims only</div>
    </div>
    <div class="status-card missing">
      <div class="label">Issues</div>
      <div class="value">{{ summary.issues_total|default:0 }}</div>
      <div class="sub-value">need attention</div>
    </div>
    <div class="status-card test-data">
      <div class="label">Test Data</div>
      <div class="value">{{ summary.test_total|default:0 }}</div>
      <div class="sub-value">auto-filtered</div>
    </div>
  </div>
  <div class="content">
    <div class="section">
      <div class="section-title">Claims to ADD to Encircle ({{ summary.onedrive_only }})</div>
      <div class="note"><strong>ACTION NEEDED:</strong> These OneDrive folders have no matching Encircle claim.</div>
      {% if onedrive_extra %}
      <div class="claims-list">
        {% for folder in onedrive_extra %}
        <div class="claim-row extra">
          <div class="claim-name">+ {{ folder.folder_name }}</div>
          <div class="claim-details">Contractor: {{ folder.contractor_identifier }} | Files: {{ folder.file_count|default:0 }}</div>
          <div class="claim-id">ID: {{ folder.folder_id|truncatechars:15 }}</div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <div class="note" style="background:#d4edda; border-left-color:#27ae60;">All OneDrive folders have matching Encircle claims.</div>
      {% endif %}
    </div>
    <div class="section">
      <div class="section-title">Claims Missing from OneDrive ({{ summary.encircle_only }})</div>
      <div class="note"><strong>ACTION REQUIRED:</strong> These Encircle claims have NO folders in OneDrive.</div>
      {% if encircle_missing_onedrive %}
      <div class="claims-list">
        {% for claim in encircle_missing_onedrive %}
        <div class="claim-row unmatched">
          <div class="claim-name">X {{ claim.policyholder_name }}</div>
          <div class="claim-details">Contractor: {{ claim.contractor_identifier }} | Address: {{ claim.full_address|default:""|truncatewords:3 }}</div>
          <div class="claim-id">ID: {{ claim.id }}</div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <div class="note" style="background:#d4edda; border-left-color:#27ae60;">All Encircle claims have folders in OneDrive!</div>
      {% endif %}
    </div>
    {% if summary.match_breakdown %}
    <div class="section">
      <div class="section-title">Match Breakdown</div>
      <div class="match-breakdown">
        <div class="breakdown-item"><div class="count">{{ summary.match_breakdown.high_confidence|default:0 }}</div><div class="label">High Confidence (80%+)</div></div>
        <div class="breakdown-item"><div class="count">{{ summary.match_breakdown.medium_confidence|default:0 }}</div><div class="label">Medium (65-80%)</div></div>
        <div class="breakdown-item"><div class="count">{{ summary.match_breakdown.low_confidence|default:0 }}</div><div class="label">Low (&lt;65%)</div></div>
      </div>
    </div>
    {% endif %}
    <div class="section">
      <div class="section-title">Successfully Matched Claims ({{ summary.matches }})</div>
      {% if matched_pairs %}
      <div class="claims-list">
        {% for pair in matched_pairs %}
        <div class="claim-row matched">
          <div class="claim-name">✓ {{ pair.encircle.policyholder_name }}</div>
          <div class="claim-details">→ {{ pair.onedrive.folder_name }} | Confidence: {{ pair.confidence }}</div>
          <div class="claim-id">ID: {{ pair.encircle.id }}</div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      <div class="note" style="background:#fff5f5; border-left-color:#e74c3c;">No matches found. Check your data sources.</div>
      {% endif %}
    </div>
  </div>
  <div class="footer">
    <p>Generated: {{ generated_date }} | Status: {% if is_refresh %}Fresh Download{% else %}Using Cache{% endif %} | Issues: {{ summary.issues_total|default:0 }}</p>
  </div>
</div>
</body>
</html>
"""
    comparison_results = _coerce_report_defaults(comparison_results)
    comparison_results['generated_date'] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    comparison_results['is_refresh'] = is_refresh
    template = Template(template_content)
    context = Context(comparison_results)
    return template.render(context)


# ===========================================================================
# Floor plan helpers
# ===========================================================================

def process_floor_data(raw_data):
    result = {
        'floors': [],
        'summary': {'totalFloors': 0, 'totalRooms': 0, 'roomsByType': {}}
    }
    if not raw_data or 'list' not in raw_data or not raw_data['list']:
        return result
    floor_names = ['Basement', 'Main Floor', 'Second Floor', 'Third Floor', 'Attic']
    floor_count = 0
    for floor_group in raw_data['list']:
        if 'floors' not in floor_group:
            continue
        for i, floor in enumerate(floor_group['floors']):
            if 'features' not in floor:
                continue
            floor_name = floor_names[floor_count] if floor_count < len(floor_names) else f"Floor {floor_count + 1}"
            floor_count += 1
            result['floors'].append({'name': floor_name, 'features': floor['features']})
    result['summary']['totalFloors'] = floor_count
    return result


# ===========================================================================
# Webhook helpers
# ===========================================================================

def _verify_encircle_signature(payload_body, signature, secret):
    import hmac
    import hashlib
    if not signature or not secret:
        return True
    expected = hmac.new(secret.encode('utf-8'), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _process_encircle_webhook(payload):
    from docsAppR.tasks import send_floorplan_notification_task

    event_type = payload.get('event_type', payload.get('type', ''))
    data = payload.get('data', {})
    claim_data = payload.get('claim', payload.get('property_claim', {}))

    is_floorplan_event = False
    floorplan_url = None

    if 'floor_plan' in event_type.lower():
        is_floorplan_event = True
        floorplan_url = data.get('url') or data.get('download_url') or data.get('image_url')
    elif event_type in ['media.created', 'media.updated']:
        media_type = data.get('media_type', data.get('type', ''))
        if 'floor' in media_type.lower() or 'plan' in media_type.lower():
            is_floorplan_event = True
            floorplan_url = data.get('url') or data.get('download_url') or data.get('image_url')

    if not is_floorplan_event:
        if 'floor_plan_dimensions' in data or 'floor_plan' in data:
            is_floorplan_event = True
            fp_data = data.get('floor_plan_dimensions', data.get('floor_plan', {}))
            if isinstance(fp_data, dict):
                floorplan_url = fp_data.get('url') or fp_data.get('image_url')

    if is_floorplan_event:
        claim_id = (
            claim_data.get('id') or data.get('property_claim_id') or
            data.get('claim_id') or payload.get('property_claim_id')
        )
        claim_info = {
            'encircle_id': claim_id,
            'name': claim_data.get('name', claim_data.get('contractor_identifier', f'Claim {claim_id}')),
            'address': claim_data.get('address', claim_data.get('location', {}).get('address', ''))
        }
        if claim_id:
            send_floorplan_notification_task.delay(
                claim_id=str(claim_id),
                floorplan_url=floorplan_url,
                claim_info=claim_info
            )
            return {'action': 'floorplan_notification_queued', 'claim_id': claim_id}
        return {'action': 'skipped', 'reason': 'no_claim_id'}

    return {'action': 'ignored', 'event_type': event_type}


# ===========================================================================
# Views
# ===========================================================================

@login_required
def encircle_claims_dashboard(request):
    return render(request, 'account/encircle_dashboard.html')


@login_required
def portfolio_summary(request):
    return render(request, 'docsAppR/portfolio_summary.html')


@login_required
def export_claims_to_excel(request, claim_id=None):
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        exporter = EncircleExcelExporter()

        if claim_id:
            raw_claim_details = api_client.get_claim_details(claim_id)
            claim_details = processor.process_claim_details(raw_claim_details)
            structures_response = api_client.get_claim_structures(claim_id)
            if not structures_response or not structures_response.get('list'):
                raise ValueError(f"No structures found for claim {claim_id}")
            structure_id = structures_response['list'][0]['id']
            raw_rooms_data = api_client.get_claim_rooms(claim_id, structure_id)
            rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)
            floor_plan_data = None
            try:
                floor_plan_data = processor.process_floor_plan_data(api_client.get_claim_floor_plan(claim_id))
            except Exception as e:
                logger.warning(f"Could not fetch floor plan: {e}")
            export_data = {'claim_details': claim_details, 'rooms': rooms_data, 'floor_plan': floor_plan_data}
        else:
            raw_claims = api_client.get_all_claims()
            processed_claims = processor.process_claims_list(raw_claims)
            all_rooms_data = []
            all_floor_plan_data = {}
            for i, claim in enumerate(processed_claims):
                current_claim_id = claim.get('id')
                if not current_claim_id:
                    continue
                try:
                    structures_response = api_client.get_claim_structures(current_claim_id)
                    if not structures_response or not structures_response.get('list'):
                        continue
                    structure_id = structures_response['list'][0]['id']
                    try:
                        raw_rooms_data = api_client.get_claim_rooms(current_claim_id, structure_id)
                        rooms_data, _ = processor.process_claim_rooms(raw_rooms_data)
                        if rooms_data:
                            for room in rooms_data:
                                room['claim_id'] = current_claim_id
                                room['claim_name'] = claim.get('policyholder_name', 'Unknown')
                            all_rooms_data.extend(rooms_data)
                    except Exception as e:
                        logger.warning(f"Could not fetch rooms for claim {current_claim_id}: {e}")
                    try:
                        raw_fp = api_client.get_claim_floor_plan(current_claim_id)
                        if raw_fp:
                            fp_data = processor.process_floor_plan_data(raw_fp)
                            if fp_data:
                                all_floor_plan_data[f"Claim_{current_claim_id}"] = fp_data
                    except Exception as e:
                        logger.warning(f"Could not fetch floor plan for claim {current_claim_id}: {e}")
                except Exception as e:
                    logger.error(f"Critical error processing claim {current_claim_id}: {e}")
                    continue
            export_data = {
                'claims': processed_claims,
                'rooms': all_rooms_data or [],
                'floor_plan': all_floor_plan_data or {},
            }

        excel_file, filename = exporter.export_claims(export_data)
        if not excel_file:
            raise ValueError("Excel file generation returned None")
        excel_content = excel_file.getvalue()
        if len(excel_content) == 0:
            raise ValueError("Generated Excel file is empty")
        response = HttpResponse(
            excel_content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = len(excel_content)
        return response

    except Exception as e:
        import traceback
        logger.error(f"Error exporting to Excel: {e}\n{traceback.format_exc()}")
        messages.error(request, f"Error generating Excel file: {e}")
        return redirect('encircle_claims_dashboard')


def fetch_all_claims_api(request):
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        raw_claims = api_client.get_all_claims()
        processed_claims = processor.process_claims_list(raw_claims)
        for claim in processed_claims:
            try:
                structures_response = api_client.get_claim_structures(claim['id'])
                if not structures_response or 'list' not in structures_response:
                    claim['total_rooms'] = 'N/A'
                    claim['room_types'] = []
                    continue
                structures_list = structures_response.get('list', [])
                if not structures_list:
                    claim['total_rooms'] = 0
                    claim['room_types'] = []
                    continue
                first_structure_id = structures_list[0].get('id')
                if not first_structure_id:
                    claim['total_rooms'] = 'N/A'
                    claim['room_types'] = []
                    continue
                rooms_response = api_client.get_claim_rooms(claim['id'], first_structure_id)
                if not rooms_response or 'list' not in rooms_response:
                    claim['total_rooms'] = 'N/A'
                    claim['room_types'] = []
                    continue
                processed_data, processed_types = processor.process_claim_rooms(rooms_response)
                claim['total_rooms'] = len(processed_data)
                claim['room_types'] = processed_types[:5]
            except Exception as e:
                logger.warning(f"Error processing rooms for claim {claim['id']}: {e}")
                claim['total_rooms'] = 'N/A'
                claim['room_types'] = []
            break
        return JsonResponse({'success': True, 'claims': processed_claims, 'total_claims': len(processed_claims)})
    except Exception as e:
        logger.error(f"Error fetching claims: {e}")
        return JsonResponse({'success': False, 'error': str(e), 'claims': [], 'total_claims': 0}, status=500)


def fetch_claim_details_api(request, claim_id):
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        raw_claim_details = api_client.get_claim_details(claim_id)
        claim_details = processor.process_claim_details(raw_claim_details)
        structures_response = api_client.get_claim_structures(claim_id)
        structure_id = structures_response['list'][0]['id']
        raw_rooms_data = api_client.get_claim_rooms(claim_id, structure_id)
        rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)
        floor_plan_data = None
        try:
            floor_plan_data = processor.process_floor_plan_data(api_client.get_claim_floor_plan(claim_id))
        except Exception as e:
            logger.warning(f"Could not fetch floor plan for claim {claim_id}: {e}")
        return JsonResponse({
            'success': True,
            'claim_details': claim_details,
            'rooms': rooms_data,
            'room_types': room_types,
            'total_rooms': len(rooms_data),
            'floor_plan': floor_plan_data,
        })
    except Exception as e:
        logger.error(f"Error fetching claim details for {claim_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def fetch_claim_rooms_api(request, claim_id, structure_id):
    try:
        api_client = EncircleAPIClient()
        processor = EncircleDataProcessor()
        raw_rooms_data = api_client.get_claim_rooms(claim_id, structure_id)
        rooms_data, room_types = processor.process_claim_rooms(raw_rooms_data)
        return JsonResponse({'success': True, 'rooms': rooms_data, 'room_types': room_types, 'total_rooms': len(rooms_data)})
    except Exception as e:
        logger.error(f"Error fetching rooms for claim {claim_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def fetch_dimensions_API(request, claim_id):
    import requests as req
    try:
        api_key = "367382d2-0b2d-4b01-9d06-8f18fd492f5e"
        url = f"https://api.encircleapp.com/v2/property_claims/{claim_id}/floor_plan_dimensions"
        headers = {"Authorization": f"Bearer {api_key}"}
        response = req.get(url, headers=headers)
        raw_data = response.json()
        return JsonResponse(process_floor_data(raw_data))
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def sync_encircle_onedrive(request):
    try:
        encircle_claims = get_encircle_claims(use_cache=True)
        onedrive_claims = get_onedrive_claims(use_cache=True)
        comparison_results = compare_claims(encircle_claims, onedrive_claims)
        html_report = generate_comparison_report(comparison_results)
        return HttpResponse(html_report, content_type='text/html')
    except Exception as e:
        logger.error(f"Error syncing Encircle and OneDrive: {e}")
        return HttpResponse(f"<h1>Error</h1><p>{e}</p>", content_type='text/html', status=500)


@login_required
@require_GET
def sync_encircle_onedrive_refresh(request):
    try:
        cache.delete(ENCIRCLE_CACHE_KEY)
        cache.delete(ONEDRIVE_CACHE_KEY)
        encircle_claims = get_encircle_claims(use_cache=False)
        onedrive_claims = get_onedrive_claims(use_cache=False)
        comparison_results = compare_claims(encircle_claims, onedrive_claims)
        html_report = generate_comparison_report(comparison_results, is_refresh=True)
        return HttpResponse(html_report, content_type='text/html')
    except Exception as e:
        logger.error(f"Error syncing Encircle and OneDrive: {e}")
        return HttpResponse(f"<h1>Error</h1><p>{e}</p>", content_type='text/html', status=500)


@login_required
@require_GET
def export_encircle_csv(request):
    try:
        encircle_claims = get_encircle_claims(use_cache=True)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="encircle_claims_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['Claim ID', 'Policyholder Name', 'Contractor Identifier', 'Full Address', 'Insurance Company', 'Status', 'Created Date'])
        for claim in encircle_claims:
            writer.writerow([
                claim.get('id', ''), claim.get('policyholder_name', ''), claim.get('contractor_identifier', ''),
                claim.get('full_address', ''), claim.get('insurance_company_name', ''),
                claim.get('status', ''), claim.get('created_date', '')
            ])
        return response
    except Exception as e:
        logger.error(f"Error exporting Encircle CSV: {e}")
        return HttpResponse(f"Error exporting data: {e}", status=500)


@login_required
@require_GET
def export_onedrive_csv(request):
    try:
        onedrive_claims = get_onedrive_claims(use_cache=True)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="onedrive_folders_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['Folder Name', 'Folder ID', 'Contractor Identifier', 'Normalized Name', 'Has Info File', 'File Count', 'Error'])
        for claim in onedrive_claims:
            writer.writerow([
                claim.get('folder_name', ''), claim.get('folder_id', ''), claim.get('contractor_identifier', ''),
                claim.get('normalized_name', ''), 'Yes' if claim.get('has_info_file') else 'No',
                claim.get('file_count', 0), claim.get('error', '')
            ])
        return response
    except Exception as e:
        logger.error(f"Error exporting OneDrive CSV: {e}")
        return HttpResponse(f"Error exporting data: {e}", status=500)


@csrf_exempt
def encircle_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        event_type = payload.get('event_type', payload.get('type', 'unknown'))
        logger.info(f"Encircle webhook received: event_type={event_type}")

        webhook_secret = getattr(settings, 'ENCIRCLE_WEBHOOK_SECRET', '')
        if webhook_secret:
            signature = request.headers.get('X-Encircle-Signature', '')
            if not _verify_encircle_signature(request.body, signature, webhook_secret):
                return JsonResponse({'error': 'Invalid signature'}, status=401)

        result = _process_encircle_webhook(payload)
        return JsonResponse({'success': True, 'message': 'Webhook processed', 'result': result})
    except Exception as e:
        logger.error(f"Error processing Encircle webhook: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def encircle_webhook_test(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        claim_id = data.get('claim_id', 'test_123')
        claim_name = data.get('claim_name', 'Test Claim')
        claim_address = data.get('claim_address', '123 Test Street')
        floorplan_url = data.get('floorplan_url', '')

        from docsAppR.tasks import send_floorplan_notification_task

        send_floorplan_notification_task.delay(
            claim_id=str(claim_id),
            floorplan_url=floorplan_url,
            claim_info={'encircle_id': claim_id, 'name': claim_name, 'address': claim_address}
        )
        return JsonResponse({'success': True, 'message': 'Test floorplan notification queued', 'claim_id': claim_id})
    except Exception as e:
        logger.error(f"Error in encircle_webhook_test: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def generate_room_entries_from_configs(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        room_data_json = request.POST.get('room_data_json')
        selected_templates = request.POST.getlist('selected_templates')
        selected_work_types = request.POST.getlist('selected_work_types')

        # job_types must be processed last (appears first in Encircle)
        if 'job_types' in selected_templates:
            selected_templates = [t for t in selected_templates if t != 'job_types']
            selected_templates.append('job_types')

        if not room_data_json:
            return JsonResponse({'error': 'No room data provided'}, status=400)

        room_data = json.loads(room_data_json)
        rooms = room_data.get('rooms', [])
        configs = room_data.get('configs', {})

        if not rooms:
            return JsonResponse({'error': 'No rooms provided'}, status=400)
        if not selected_templates:
            return JsonResponse({'error': 'No templates selected'}, status=400)

        work_type_descs = {
            100: "= … JOB/ROOMS OVERVIEW PICS ..",
            200: "….. SOURCE of LOSS PICS …..",
            300: "….. C.P.S. …...",
            400: "….. PPR …..",
            500: "…… DMO = DEMOLITION …....",
            600: "… WTR MITIGATION EQUIPMENT & W.I.P . ...",
            700: "… HMR = HAZARDOUS MATERIALS ..."
        }
        section_labels = {
            100: "100 .... = ... JOB/ROOMS OVERVIEW PICS .. ==========================",
            200: "200 .... ..... SOURCE of LOSS PICS ..... ===========================",
            300: "300 .... ..... C.P.S. ...... =======================================",
            400: "400 .... PPR ===================================================",
            500: "500 .... ...... DMO = DEMOLITION ....... ===========================",
            600: "600 . WTR MITIGATION EQUIPMENT & W.I.P. ============================",
            700: "700 . HMR = HAZARDOUS MATERIALS ====================================",
        }

        room_entries_by_template = {}

        if 'basic' in selected_templates:
            work_types = sorted([int(wt) for wt in selected_work_types]) if selected_work_types else [100, 200, 300, 400, 500, 600, 700]
            basic_entries = [
                "0.0001 ….. JOBSITE VERIFICATION",
                "0.0002 . MECHANICALS = WATER METER READING & PLUMBING REPORT/INVOICE",
                "0.0003 . MECHANICALS = ELECTRICAL HAZARDS",
                "0.0004 . EXT DAMAGE IF APPLICABLE ROOF TARPS",
                "1997 . LEAD & HMR TESTING LAB RESULTS",
                "1998 . KITCHEN CABINETS SIZES U & L =LF/ CT = SF; APPLIANCES",
                "1999 . BATHROOM FIXTURES CAB SIZE & FIXTURES & TYPE",
            ]
            for wt in work_types:
                basic_entries.append(section_labels[wt])
                for idx, room_name in enumerate(rooms):
                    room_config = configs.get(room_name, {})
                    config_value = room_config.get(100, room_config.get('100', '.'))
                    display_value = "…........." if config_value == "." else config_value
                    basic_entries.append(f"{wt + idx + 1} {display_value} …. {room_name} {work_type_descs[wt]}")
                if wt == 300:
                    basic_entries.extend([
                        "3222 . CPS DAY2 WIP OVERVIEW WIP BOXES PACKOUT PICS",
                        "3223 . CPS DAY2 WIP ROOM CLEARED",
                        "3322 . CPS3 DAY3 STORAGE OVERVIEW STORAGE MOVE OUT PICS",
                        "3444 . CPS4 DAY4 PACKBACK OVERVIEW PACK-BACK / RESET PICS",
                    ])
                elif wt == 400:
                    basic_entries.extend([
                        "4111.1 . REPLACEMENT 1 CON OVERVIEW DAY PICS",
                        "4222.2 . REPLACEMENT 2 CON WIP",
                        "4333.3 . REPLACEMENT 3 CON STORAGE",
                        "4444.4 . REPLACEMENT 4 CON DISPOSAL",
                    ])
            basic_entries.extend(["9998.0 . REBUILD OVERVIEW WORK IN PROGRESS.......WIP", "9999.0 . REBUILD INTERIOR COMPLETED WORK"])
            room_entries_by_template['basic'] = basic_entries

        if 'extended' in selected_templates:
            extended_entries = ["400 .... NON SALVAGEABLE ITEMS ====================================="]
            for idx, room_name in enumerate(rooms):
                room_config = configs.get(room_name, {})
                config_value = room_config.get(100, room_config.get('100', '.'))
                display_value = "…........." if config_value == "." else config_value
                extended_entries.append(f"{400 + idx + 1} …. {room_name} {work_type_descs[400]} {display_value}")
            room_entries_by_template['extended'] = extended_entries

        if 'readings_8000' in selected_templates:
            room_entries_by_template['readings_8000'] = generate_8000s_entries(rooms, configs)
        if 'readings_9000' in selected_templates:
            room_entries_by_template['readings_9000'] = generate_9000s_entries()
        if 'siding_10000' in selected_templates:
            room_entries_by_template['siding_10000'] = generate_10000s_entries()
        if 'readings' in selected_templates:
            room_entries_by_template['readings'] = generate_8000_9000_entries(rooms, configs)
        if 'readings default' in selected_templates:
            room_entries_by_template['readings default'] = generate_70000_entries(rooms, configs)
        if 'job_types' in selected_templates:
            room_entries_by_template['job_types'] = generate_job_types_entries()

        template_priority = {
            'readings_8000': 1, 'readings_9000': 1, 'siding_10000': 1, 'readings': 1,
            'extended': 2, 'basic': 3, 'readings default': 5, 'job_types': 0,
        }
        selected_templates = sorted(selected_templates, key=lambda x: template_priority.get(x, 99))

        automation = RoomTemplateAutomation(headless=True)
        results = automation.run_automation_with_room_data(
            room_entries=room_entries_by_template,
            selected_template_ids=selected_templates,
            delete_existing=True
        )

        return JsonResponse({
            'overall_status': results.get('overall_status', 'unknown'),
            'templates_successful': results.get('templates_successful', 0),
            'templates_failed': results.get('templates_failed', 0),
            'templates_processed': results.get('templates_processed', []),
            'login_status': results.get('login_status'),
            'navigation_status': results.get('navigation_status'),
            'deletion_results': results.get('deletion_results'),
            'processed_rooms': len(rooms),
            'selected_templates': selected_templates,
            'room_entries_generated': {t: len(e) for t, e in room_entries_by_template.items()}
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except ImportError as e:
        return JsonResponse({'error': f'Automation module not available: {e}'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
