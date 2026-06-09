"""
docsAppR/encircle_sync.py

Encircle → Claimet inbound synchronisation engine.

Public API
----------
run_encircle_sync(triggered_by='schedule')
    Pull all claims from Encircle, upsert into the local Client table,
    and write an EncircleSyncLog record.  Returns the completed log instance.

Design decisions
----------------
* Matching key : Client.encircle_claim_id == Encircle claim `id`.
* New claims    : Any Encircle claim whose ID is not yet in the DB is created.
* Existing claims: Encircle-authoritative fields are refreshed every run.
* Claimet-only   : ALE, mortgage, room entries, lease, contractor workflow
                   fields are never touched by this sync.
* Transactions   : Each claim upsert runs in its own savepoint so a single
                   bad record does not abort the whole batch.
* Logging        : Structured via Python logging + EncircleSyncLog DB row.
"""

import logging
import re
from datetime import datetime

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Address parser
# ---------------------------------------------------------------------------

def _parse_full_address(full_address: str):
    """
    Split an Encircle full_address string into (street, city_state_zip).

    Encircle returns addresses like:
        "123 Main St, Cleveland, OH 44120"
        "123 Main St, Cleveland OH 44120"   (no comma before state)

    Returns (street, city_state_zip) where city_state_zip is left intact for
    pCityStateZip.  Returns ('', '') if the input is blank.
    """
    if not full_address:
        return '', ''
    full_address = full_address.strip()
    # Try splitting on first comma
    parts = full_address.split(',', 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    # Fall back: treat everything as the street
    return full_address, ''


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

# Fields on Client that are owned by Encircle (always refreshed during sync).
# Format: encircle_key → client_field_name
# A value of None means "handled specially in _map_encircle_to_client".
ENCIRCLE_FIELD_MAP = {
    # Core claim metadata
    'policyholder_name':           'pOwner',
    'policyholder_phone_number':   'cPhone',
    'policyholder_email_address':  'cEmail',
    # full_address → handled specially (split into street + city_state_zip)
    'full_address':                None,
    # Insurance
    'insurance_company_name':      'insuranceCo_Name',
    'policy_number':               'policyNumber',
    # Loss
    'type_of_loss':                'causeOfLoss',
    # date_of_loss → handled specially (parse to datetime)
    'date_of_loss':                None,
    # Adjuster
    'adjuster_name':               'deskAdjusterDA',
    # Contractor / job identifier
    'contractor_identifier':       'newCustomerID',
    # Encircle-only metadata (new fields)
    'permalink_url':               'encircle_permalink_url',
    'project_manager_name':        'encircle_project_manager',
    'loss_details':                'encircle_loss_details',
    'cat_code':                    'encircle_cat_code',
    'assignment_identifier':       'encircle_assignment_id',
    # date_claim_created → handled specially
    'date_claim_created':          None,
}

# Claimet-only fields that sync must NEVER overwrite:
# (ALE, mortgage, rooms, lease workflow, contractor FK, etc.)
# This list is here for documentation — the mapping above simply excludes them.
_CLAIMET_ONLY_FIELDS = [
    'ale_lessee_name', 'ale_lessee_home_address', 'ale_rental_amount_per_month',
    'ale_lessor_name', 'ale_re_company_name',
    'mortgageCo', 'mortgageAccountCo', 'mortgageContactPerson',
    'contractor',  # FK to contractor_hub.Contractor
    'demo', 'mitigation', 'otherStructures', 'replacement', 'CPSCLNCONCGN',
    'drawRequest', 'claimReportDate',
]


def _parse_date(raw) -> datetime | None:
    """Parse an Encircle date string to a timezone-aware datetime."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if timezone.is_aware(raw) else timezone.make_aware(raw)
    raw = str(raw).strip()
    # ISO format with various separators
    for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(raw[:len(fmt) + 4], fmt)
            return timezone.make_aware(dt)
        except ValueError:
            continue
    logger.debug("Could not parse date: %r", raw)
    return None


def _build_client_fields(encircle_data: dict, is_new: bool) -> dict:
    """
    Map an Encircle claim dict to a dict of Client field values.

    For existing (non-new) claims we still overwrite Encircle-authoritative
    fields; only Claimet-specific business fields are excluded (they're just
    not in this mapping at all).
    """
    fields = {}

    for enc_key, client_field in ENCIRCLE_FIELD_MAP.items():
        raw = encircle_data.get(enc_key)

        # ── Special handling ──────────────────────────────────────────────
        if enc_key == 'full_address':
            street, csz = _parse_full_address(raw or '')
            fields['pAddress'] = street
            if is_new or csz:
                # Only set pCityStateZip if we have something useful
                fields['pCityStateZip'] = csz
            continue

        if enc_key == 'date_of_loss':
            fields['dateOfLoss'] = _parse_date(raw)
            continue

        if enc_key == 'date_claim_created':
            fields['encircle_date_created'] = _parse_date(raw)
            continue

        # ── Direct mapping ────────────────────────────────────────────────
        if client_field is None:
            continue  # handled above or intentionally skipped

        if raw is not None:
            # Convert non-strings to string for CharField targets
            if isinstance(raw, (int, float)):
                raw = str(raw)
            fields[client_field] = raw

    # Always stamp when this record was last synced
    fields['encircle_last_synced_at'] = timezone.now()

    return fields


# ---------------------------------------------------------------------------
# Single-claim upsert
# ---------------------------------------------------------------------------

def upsert_client_from_encircle(encircle_data: dict) -> tuple[object, bool]:
    """
    Create or update a Client record from an Encircle claim dict.

    Returns (client_instance, created) where `created` is True for new records.
    Raises on unrecoverable error; caller wraps in a savepoint.
    """
    from .models import Client

    enc_id = str(encircle_data.get('id') or '').strip()
    if not enc_id:
        raise ValueError("Encircle claim has no id — skipping")

    # Check for existing record
    existing = Client.objects.filter(encircle_claim_id=enc_id).first()
    is_new = existing is None

    fields = _build_client_fields(encircle_data, is_new=is_new)

    if is_new:
        # Set the matching key
        fields['encircle_claim_id'] = enc_id
        client = Client(**fields)
        client.save()
        logger.info("Created Client from Encircle claim %s (%s)", enc_id,
                    fields.get('pOwner', '—'))
        return client, True
    else:
        # Update only the fields in our map
        for attr, val in fields.items():
            setattr(existing, attr, val)
        existing.save(update_fields=list(fields.keys()))
        logger.debug("Updated Client %s from Encircle claim %s", existing.pk, enc_id)
        return existing, False


# ---------------------------------------------------------------------------
# Full sync orchestrator
# ---------------------------------------------------------------------------

def run_encircle_sync(triggered_by: str = 'schedule') -> 'EncircleSyncLog':
    """
    Pull all claims from Encircle and upsert them into the local Client table.

    Creates an EncircleSyncLog row at the start, updates it on completion.
    Always returns the log instance (even when the whole run fails).
    """
    from .models import EncircleSyncLog
    from .encircle_client import EncircleAPIClient, EncircleDataProcessor

    log = EncircleSyncLog.objects.create(
        status='running',
        triggered_by=triggered_by,
    )
    logger.info("Encircle sync started (log id=%s, triggered_by=%s)", log.pk, triggered_by)

    try:
        api       = EncircleAPIClient()
        processor = EncircleDataProcessor()

        # ── Fetch all claims (paginated) ──────────────────────────────────
        logger.info("Fetching all Encircle claims …")
        raw_claims_resp = api.get_all_claims()
        raw_list        = raw_claims_resp.get('list', [])
        logger.info("Encircle returned %d claims in list page(s)", len(raw_list))

        errors = []
        created_count = 0
        updated_count = 0

        for raw_claim in raw_list:
            enc_id = str(raw_claim.get('id') or '').strip()
            if not enc_id:
                logger.warning("Skipping Encircle claim with no id: %r", raw_claim)
                errors.append({'encircle_id': None, 'error': 'missing id in list item'})
                continue

            try:
                # ── Fetch full detail for each claim ──────────────────────
                try:
                    detail_raw  = api.get_claim_details(enc_id)
                    detail      = processor.process_claim_details(detail_raw)
                except Exception as detail_exc:
                    logger.warning(
                        "Could not fetch details for Encircle claim %s: %s — using list data",
                        enc_id, detail_exc
                    )
                    # Fall back to the list-level data (less complete but better than nothing)
                    detail = dict(raw_claim)

                # ── Upsert inside a savepoint so one bad record is isolated ──
                with transaction.atomic():
                    _, created = upsert_client_from_encircle(detail)

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as exc:
                logger.error(
                    "Error processing Encircle claim %s: %s", enc_id, exc, exc_info=True
                )
                errors.append({'encircle_id': enc_id, 'error': str(exc)})

        # ── Finalise log ──────────────────────────────────────────────────
        total_processed = created_count + updated_count
        has_errors      = bool(errors)

        if has_errors and total_processed == 0:
            final_status = 'failed'
        elif has_errors:
            final_status = 'partial'
        else:
            final_status = 'success'

        log.completed_at     = timezone.now()
        log.status           = final_status
        log.claims_processed = total_processed
        log.claims_created   = created_count
        log.claims_updated   = updated_count
        log.error_count      = len(errors)
        log.error_details    = errors[:100]  # cap stored errors at 100
        log.save()

        logger.info(
            "Encircle sync finished: status=%s  processed=%d  created=%d  "
            "updated=%d  errors=%d",
            final_status, total_processed, created_count, updated_count, len(errors)
        )

    except Exception as fatal_exc:
        logger.error("Encircle sync fatal error: %s", fatal_exc, exc_info=True)
        log.completed_at  = timezone.now()
        log.status        = 'failed'
        log.error_count   = 1
        log.error_details = [{'encircle_id': None, 'error': str(fatal_exc)}]
        log.save()

    return log
