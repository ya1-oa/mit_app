"""
mit_audit/report_builder.py

Four WeasyPrint PDF reports (split by photo type):

  build_required_equipment_report(audit)
      All water-mitigation equipment calculated by the workbook.
      Field crew checklist: how many of each unit must be deployed.

  build_required_stab_report(audit)
      Equipment that specifically requires a stabilization photo.
      Tells the crew what each stab photo must show.

  build_missing_equipment_report(audit)
      Equipment placement photos still outstanding.
      Lists items where visible_quantity < required_quantity.

  build_missing_stab_report(audit)
      Stabilization photos still outstanding.
      Lists stab-required items where stabilization_photo_found is not True.
"""
import html as _html
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def _e(text) -> str:
    """HTML-escape a value for insertion into report markup."""
    return _html.escape(str(text)) if text is not None else ''


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared CSS and header
# ---------------------------------------------------------------------------

def _base_css() -> str:
    return """
    @page { size: letter; margin: 2cm; }
    * { box-sizing: border-box; }
    body {
        font-family: 'DejaVu Sans', Arial, sans-serif;
        font-size: 10pt; color: #212121; line-height: 1.45;
    }
    h1 { font-size: 16pt; color: #1a237e; margin: 0 0 4px; }
    h2 { font-size: 12pt; color: #283593; margin: 18px 0 6px; border-bottom: 1px solid #3949ab; }
    .header { border-bottom: 2px solid #1a237e; padding-bottom: 10px; margin-bottom: 16px; }
    .meta { font-size: 9pt; color: #555; margin: 2px 0; }
    .notice {
        background: #fff8e1; border-left: 4px solid #f9a825;
        padding: 8px 12px; margin: 10px 0; font-size: 9.5pt;
    }
    .notice-green {
        background: #e8f5e9; border-left: 4px solid #43a047;
        padding: 8px 12px; margin: 10px 0; font-size: 9.5pt;
    }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    thead { display: table-header-group; }
    th {
        background: #1a237e; color: #fff; text-align: left;
        padding: 6px 8px; font-size: 9pt;
    }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
    tr { page-break-inside: avoid; }
    tr:nth-child(even) td { background: #f5f5f5; }
    .badge {
        display: inline-block; padding: 2px 8px; border-radius: 3px;
        font-size: 8.5pt; font-weight: bold; color: #fff;
    }
    .qty-big { font-size: 13pt; font-weight: bold; }
    .footer { margin-top: 24px; font-size: 8pt; color: #888; text-align: center; }
    .summary-grid {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 12px 0;
    }
    .stat {
        border: 1px solid #e0e0e0; border-radius: 4px; padding: 8px; text-align: center;
    }
    .stat-num { font-size: 18pt; font-weight: bold; }
    .stat-lbl { font-size: 8pt; color: #666; margin-top: 2px; }
    .all-clear {
        text-align: center; padding: 48px 20px; color: #2e7d32;
    }
    .all-clear-icon { font-size: 30pt; margin-bottom: 10px; }
    .all-clear-title { font-size: 14pt; font-weight: bold; }
    .all-clear-sub { font-size: 10pt; color: #555; margin-top: 8px; }
    """


def _header_html(audit, title: str) -> str:
    client = audit.client
    claim  = client.claimNumber or f'Client #{client.pk}'
    owner  = client.pOwner or '—'
    addr   = getattr(client, 'propertyAddress', '') or ''
    ts     = timezone.now().strftime('%B %d, %Y %H:%M')
    return f"""
    <div class="header">
      <h1>{title}</h1>
      <p class="meta"><strong>Claim:</strong> {_e(claim)} &nbsp;|&nbsp;
         <strong>Client:</strong> {_e(owner)} &nbsp;|&nbsp;
         <strong>Address:</strong> {_e(addr)}</p>
      <p class="meta"><strong>Generated:</strong> {_e(ts)} &nbsp;|&nbsp;
         <strong>Audit #:</strong> {audit.pk} &nbsp;|&nbsp;
         <strong>Status:</strong> {_e(audit.get_status_display())}</p>
    </div>
    """


def _save_pdf(html: str, audit, report_type: str) -> str:
    """Render html with WeasyPrint, save to MEDIA_ROOT/mit_audits/<id>/<type>.pdf."""
    from weasyprint import HTML as WP_HTML
    dest_dir = Path(settings.MEDIA_ROOT) / 'mit_audits' / str(audit.pk)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f'{report_type}_report.pdf'
    WP_HTML(string=html).write_pdf(str(dest))
    logger.info('[MIT] PDF saved: %s (%d bytes)', dest, dest.stat().st_size)
    return str(dest)


# ---------------------------------------------------------------------------
# Report 1: Required Water Mitigation Equipment
# ---------------------------------------------------------------------------

def build_required_equipment_report(audit) -> str:
    """
    All equipment calculated by the workbook.
    Grouped by category with required quantities.
    """
    items = list(audit.required_equipment.order_by('category', 'display_name'))
    if not items:
        raise RuntimeError(
            f'No required equipment for audit #{audit.pk}. '
            'Run the workbook calculation step first.'
        )

    rooms = list(audit.room_dimensions.filter(approved=True).order_by('room_name'))

    # Room dimensions table
    room_rows = ''.join(
        f"""<tr>
              <td>{_e(r.room_name)}</td>
              <td>{_e(r.length) or '—'}</td>
              <td>{_e(r.width) or '—'}</td>
              <td>{_e(r.height) or '—'}</td>
              <td>{_e(r.square_feet) or '—'}</td>
              <td>{_e(r.cubic_feet) or '—'}</td>
            </tr>"""
        for r in rooms
    )
    room_table = f"""
    <h2>Room Dimensions Used ({len(rooms)} rooms)</h2>
    <table>
      <tr>
        <th>Room</th><th>Length (ft)</th><th>Width (ft)</th><th>Height (ft)</th>
        <th>Sq Ft</th><th>Cu Ft</th>
      </tr>
      {room_rows}
    </table>
    """ if rooms else ''

    # Equipment grouped by category
    cat_label = dict(audit.required_equipment.model.CATEGORY_CHOICES)
    by_cat: dict = {}
    for item in items:
        by_cat.setdefault(item.category, []).append(item)

    equip_sections = ''
    for cat, cat_items in by_cat.items():
        rows = ''.join(
            f"""<tr>
                  <td>{_e(i.display_name)}</td>
                  <td style="text-align:center" class="qty-big">{i.required_quantity}</td>
                  <td>{_e(i.source_sheet)} / {_e(i.workbook_cell) or '—'}</td>
                </tr>"""
            for i in cat_items
        )
        equip_sections += f"""
        <h2>{_e(cat_label.get(cat, cat))} ({len(cat_items)} items)</h2>
        <table>
          <thead><tr>
            <th>Equipment Item</th>
            <th style="width:110px; text-align:center">Required Qty</th>
            <th>Workbook Source</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """

    stab_count  = sum(1 for i in items if i.requires_stabilization_photo)
    total_units = sum(i.required_quantity for i in items)

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Required Water Mitigation Equipment — MIT Day 3')}
    <div class="notice">
      Equipment quantities calculated from the MIT Day 3 workbook using room dimensions
      from the Encircle floor plan.  See the <em>Required Stabilization Photos</em> report
      for items that additionally require a running-equipment confirmation photo.
    </div>
    <div class="summary-grid">
      <div class="stat">
        <div class="stat-num">{len(items)}</div>
        <div class="stat-lbl">Equipment Types</div>
      </div>
      <div class="stat">
        <div class="stat-num">{total_units}</div>
        <div class="stat-lbl">Total Units Required</div>
      </div>
      <div class="stat">
        <div class="stat-num">{len(rooms)}</div>
        <div class="stat-lbl">Rooms</div>
      </div>
      <div class="stat">
        <div class="stat-num">{stab_count}</div>
        <div class="stat-lbl">Need Stabilization Photo</div>
      </div>
    </div>
    {room_table}
    {equip_sections}
    <div class="footer">Claimet App — MIT Day 3 Equipment Audit — Report #{audit.pk}</div>
    </body></html>"""

    return _save_pdf(html, audit, 'required_equipment')


# ---------------------------------------------------------------------------
# Report 2: Required Stabilization Photos
# ---------------------------------------------------------------------------

def build_required_stab_report(audit) -> str:
    """
    Lists every equipment item that requires a stabilization photo,
    with what the photo must show.  Includes current AI-observed status.
    """
    stab_items = list(
        audit.required_equipment
        .filter(requires_stabilization_photo=True)
        .select_related('photo_observation')
        .order_by('category', 'display_name')
    )

    if not stab_items:
        # No stab items — generate an informational page
        html = f"""<!DOCTYPE html>
        <html><head><meta charset="UTF-8">
        <style>{_base_css()}</style></head><body>
        {_header_html(audit, 'Required Stabilization Photos — MIT Day 3')}
        <div class="notice-green">
          No equipment on this job requires a stabilization photo.
          All items are verified by standard placement/operation photographs.
        </div>
        <div class="footer">Claimet App — MIT Day 3 Equipment Audit — Report #{audit.pk}</div>
        </body></html>"""
        return _save_pdf(html, audit, 'required_stab')

    cat_label = dict(audit.required_equipment.model.CATEGORY_CHOICES)

    # What each Drying Chamber Stabilization item's photo must show.
    # Only these 4 categories require stabilization photos.
    STAB_GUIDANCE = {
        'dehumidifier': (
            'Photo must show the unit powered on with the display illuminated. '
            'Drain hose or condensate line must be clearly visible and routed to a drain or bucket. '
            'Ideally capture a reading showing relative humidity (RH) falling below the target.'
        ),
        'air_cleaner': (
            'Photo must show the HEPA air scrubber running (indicator light on / fan audible). '
            'Capture the intake and exhaust side to confirm airflow direction.'
        ),
        'zipper_wall': (
            'Photo must show the containment barrier fully sealed — no gaps around edges, '
            'floor, ceiling, or zipper. Both sides of the zipper closure must be visible. '
            'Support poles must be clearly tensioned against floor and ceiling.'
        ),
        'double_zipper': (
            'MINIMUM 2 photos showing: the double zipper wall AND at least 2 support poles. '
            'Both poles MUST be clearly visible — 1 pole is NOT sufficient.'
        ),
    }
    DEFAULT_GUIDANCE = (
        'Photo must confirm the unit is powered on and functioning as intended. '
        'All connections and indicators must be clearly visible.'
    )

    table_rows = ''
    current_cat = None
    confirmed = 0
    missing   = 0
    unknown   = 0

    for item in stab_items:
        obs   = getattr(item, 'photo_observation', None)
        found = obs.stabilization_photo_found if obs else None

        if found is True:
            status_cell = '<span style="color:#2e7d32; font-weight:bold;">✓ Confirmed</span>'
            confirmed  += 1
        elif found is False:
            status_cell = '<span style="color:#c62828; font-weight:bold;">✗ Missing</span>'
            missing    += 1
        else:
            status_cell = '<span style="color:#6a1b9a; font-weight:bold;">? Not yet reviewed</span>'
            unknown    += 1

        guidance = STAB_GUIDANCE.get(item.category, DEFAULT_GUIDANCE)

        if item.category != current_cat:
            current_cat = item.category
            table_rows += (
                f'<tr style="background:#e8eaf6;">'
                f'<td colspan="4" style="font-weight:bold; font-size:9pt; padding:6px 8px; color:#283593;">'
                f'{_e(cat_label.get(item.category, item.category))}'
                f'</td></tr>'
            )

        table_rows += (
            f'<tr>'
            f'<td class="fw-semibold">{_e(item.display_name)}</td>'
            f'<td style="text-align:center">{item.required_quantity}</td>'
            f'<td>{status_cell}</td>'
            f'<td style="font-size:8.5pt; color:#424242">{_e(guidance)}</td>'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Required Stabilization Photos — MIT Day 3')}
    <div class="notice">
      A stabilization photo confirms that drying equipment is <strong>actively running</strong>
      and functioning correctly — not just deployed.  Each item below requires one photo
      meeting the criteria described.  IICRC S500 standard requires stabilization documentation
      no later than Day 3.
    </div>
    <div class="summary-grid">
      <div class="stat">
        <div class="stat-num">{len(stab_items)}</div>
        <div class="stat-lbl">Items Requiring Stabilization Photo</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#2e7d32">{confirmed}</div>
        <div class="stat-lbl">Confirmed</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#c62828">{missing}</div>
        <div class="stat-lbl">Missing</div>
      </div>
      <div class="stat">
        <div class="stat-num" style="color:#6a1b9a">{unknown}</div>
        <div class="stat-lbl">Not Reviewed</div>
      </div>
    </div>
    <h2>Stabilization Photo Checklist</h2>
    <table>
      <thead><tr>
        <th>Equipment</th>
        <th style="width:80px; text-align:center">Qty</th>
        <th style="width:130px">AI Status</th>
        <th>What the Photo Must Show</th>
      </tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    <div class="footer">Claimet App — MIT Day 3 Equipment Audit — Report #{audit.pk}</div>
    </body></html>"""

    return _save_pdf(html, audit, 'required_stab')


# ---------------------------------------------------------------------------
# Report 3: Missing Water Mitigation Photos
# ---------------------------------------------------------------------------

def build_missing_equipment_report(audit) -> str:
    """
    Equipment placement photos still outstanding.
    Lists items where visible_quantity < required_quantity.
    Excludes the stabilization-photo status (that is Report 4).
    """
    all_items = list(
        audit.required_equipment
        .select_related('photo_observation')
        .order_by('category', 'display_name')
    )
    if not all_items:
        raise RuntimeError(
            f'No required equipment for audit #{audit.pk}. '
            'Run the workbook and photo-review steps first.'
        )

    confirmed_count = 0
    needs_work = []

    for item in all_items:
        obs = getattr(item, 'photo_observation', None)
        if obs is None:
            needs_work.append((item, None))
        elif obs.status == 'confirmed':
            confirmed_count += 1
        else:
            needs_work.append((item, obs))

    total      = len(all_items)
    need_count = len(needs_work)

    cat_label   = dict(audit.required_equipment.model.CATEGORY_CHOICES)
    table_rows  = ''
    current_cat = None

    for item, obs in needs_work:
        if item.category != current_cat:
            current_cat = item.category
            table_rows += (
                f'<tr style="background:#e8eaf6;">'
                f'<td colspan="5" style="font-weight:bold; font-size:9pt;'
                f' padding:6px 8px; color:#283593;">'
                f'{_e(cat_label.get(item.category, item.category))}'
                f'</td></tr>'
            )

        if obs:
            already    = obs.visible_quantity
            still_need = obs.missing_quantity or max(0, item.required_quantity - obs.visible_quantity)
            if obs.status == 'manual':
                need_str   = '?'
                need_style = 'color:#6a1b9a; font-weight:bold;'
                action     = obs.recommended_action or 'Inspector must verify this item on-site.'
            else:
                need_str   = str(still_need)
                need_style = 'color:#c62828; font-weight:bold;'
                action     = obs.recommended_action or (
                    f'Photograph {still_need} more unit(s) clearly visible in frame.'
                )
        else:
            already    = 0
            still_need = item.required_quantity
            need_str   = str(still_need)
            need_style = 'color:#c62828; font-weight:bold;'
            action     = 'Photo review not yet run — photograph all units.'

        table_rows += (
            f'<tr>'
            f'<td>{_e(item.display_name)}</td>'
            f'<td style="text-align:center">{item.required_quantity}</td>'
            f'<td style="text-align:center">{already}</td>'
            f'<td style="text-align:center; {need_style}">{need_str}</td>'
            f'<td style="font-size:8.5pt">{_e(action)}</td>'
            f'</tr>'
        )

    if need_count == 0:
        body_section = """
        <div class="all-clear">
          <div class="all-clear-icon">✓</div>
          <div class="all-clear-title">All equipment placement photos confirmed</div>
          <div class="all-clear-sub">
            No outstanding water mitigation photo requirements for this audit.
          </div>
        </div>"""
    else:
        body_section = f"""
        <h2>Equipment Needing Photos &mdash; {need_count} of {total} items</h2>
        <table>
          <thead><tr>
            <th>Equipment</th>
            <th style="width:72px; text-align:center">Required</th>
            <th style="width:72px; text-align:center">In Photos</th>
            <th style="width:72px; text-align:center">Still Need</th>
            <th>What to Photograph</th>
          </tr></thead>
          <tbody>{table_rows}</tbody>
        </table>"""

    if need_count == 0:
        summary_note = (
            f'<p class="meta" style="color:#2e7d32; font-weight:bold; margin-top:6px;">'
            f'&#10003; All {total} items confirmed &mdash; no action required.</p>'
        )
    else:
        summary_note = (
            f'<p class="meta" style="color:#c62828; margin-top:6px;">'
            f'<strong>{need_count} of {total} item(s)</strong> still require photographs. '
            f'{confirmed_count} already confirmed. '
            f'See <em>Missing Stabilization Photos</em> report for stabilization photo status.</p>'
        )

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Missing Water Mitigation Photos &mdash; MIT Day 3')}
    {summary_note}
    {body_section}
    <div class="footer">Claimet App &mdash; MIT Day 3 Equipment Audit &mdash; Report #{audit.pk}</div>
    </body></html>"""

    return _save_pdf(html, audit, 'missing_equipment')


# ---------------------------------------------------------------------------
# Report 4: Missing Stabilization Photos
# ---------------------------------------------------------------------------

def build_missing_stab_report(audit) -> str:
    """
    Stabilization photos still outstanding.
    Only lists items with requires_stabilization_photo=True
    where stabilization_photo_found is not True.
    """
    stab_items = list(
        audit.required_equipment
        .filter(requires_stabilization_photo=True)
        .select_related('photo_observation')
        .order_by('category', 'display_name')
    )

    if not stab_items:
        html = f"""<!DOCTYPE html>
        <html><head><meta charset="UTF-8">
        <style>{_base_css()}</style></head><body>
        {_header_html(audit, 'Missing Stabilization Photos — MIT Day 3')}
        <div class="notice-green">
          No equipment on this job requires a stabilization photo.
        </div>
        <div class="footer">Claimet App — MIT Day 3 Equipment Audit — Report #{audit.pk}</div>
        </body></html>"""
        return _save_pdf(html, audit, 'missing_stab')

    # Separate confirmed from still-needed
    confirmed_stab = []
    missing_stab   = []

    for item in stab_items:
        obs   = getattr(item, 'photo_observation', None)
        found = obs.stabilization_photo_found if obs else None
        if found is True:
            confirmed_stab.append(item)
        else:
            missing_stab.append((item, obs))

    cat_label = dict(audit.required_equipment.model.CATEGORY_CHOICES)

    if not missing_stab:
        body_section = """
        <div class="all-clear">
          <div class="all-clear-icon">✓</div>
          <div class="all-clear-title">All stabilization photos confirmed</div>
          <div class="all-clear-sub">
            No outstanding stabilization photo requirements for this audit.
          </div>
        </div>"""
        summary_note = (
            f'<p class="meta" style="color:#2e7d32; font-weight:bold; margin-top:6px;">'
            f'&#10003; All {len(stab_items)} stabilization photo(s) confirmed.</p>'
        )
    else:
        table_rows  = ''
        current_cat = None

        for item, obs in missing_stab:
            if item.category != current_cat:
                current_cat = item.category
                table_rows += (
                    f'<tr style="background:#e8eaf6;">'
                    f'<td colspan="3" style="font-weight:bold; font-size:9pt;'
                    f' padding:6px 8px; color:#283593;">'
                    f'{_e(cat_label.get(item.category, item.category))}'
                    f'</td></tr>'
                )

            found = obs.stabilization_photo_found if obs else None
            if found is False:
                icon  = '✗'
                color = '#c62828'
                note  = (obs.ai_notes if obs else '') or (
                    'Not found. Must show unit running with all connections visible.'
                )
            else:
                icon  = '?'
                color = '#6a1b9a'
                note  = (obs.ai_notes if obs else '') or (
                    'Photo review not yet run — photograph unit running with all connections visible.'
                )

            table_rows += (
                f'<tr>'
                f'<td>{_e(item.display_name)}</td>'
                f'<td style="color:{color}; font-weight:bold; text-align:center;'
                f' font-size:13pt">{icon}</td>'
                f'<td style="font-size:8.5pt">{_e(note)}</td>'
                f'</tr>'
            )

        missing_label  = len(missing_stab)
        confirm_label  = len(confirmed_stab)
        body_section   = f"""
        <h2>Outstanding Stabilization Photos &mdash; {missing_label} of {len(stab_items)} items</h2>
        <table>
          <thead><tr>
            <th>Equipment</th>
            <th style="width:80px; text-align:center">Status</th>
            <th>Notes / Action Required</th>
          </tr></thead>
          <tbody>{table_rows}</tbody>
        </table>"""

        summary_note = (
            f'<p class="meta" style="color:#c62828; margin-top:6px;">'
            f'<strong>{missing_label} of {len(stab_items)} item(s)</strong> '
            f'still require stabilization photos. '
            f'{confirm_label} confirmed.</p>'
        )

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Missing Stabilization Photos &mdash; MIT Day 3')}
    {summary_note}
    <div class="notice">
      A stabilization photo is required for each item listed below.
      The photo must show the unit powered on and actively drying/treating the space.
      See the <em>Required Stabilization Photos</em> report for exact photo criteria per item.
    </div>
    {body_section}
    <div class="footer">Claimet App &mdash; MIT Day 3 Equipment Audit &mdash; Report #{audit.pk}</div>
    </body></html>"""

    return _save_pdf(html, audit, 'missing_stab')
