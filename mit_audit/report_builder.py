"""
mit_audit/report_builder.py

Two WeasyPrint PDF reports:

  build_required_equipment_report(audit)
      Shows what the MIT Day 3 workbook calculated is needed.
      Used before photos are reviewed — gives the field crew a checklist.

  build_missing_equipment_report(audit)
      Compares required vs observed (AI photo review).
      The actionable output: what to re-photograph or re-deploy.
"""
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    'confirmed': '#2e7d32',   # green
    'partial':   '#f57c00',   # orange
    'missing':   '#c62828',   # red
    'manual':    '#6a1b9a',   # purple
}

_STATUS_LABELS = {
    'confirmed': '✓ Confirmed',
    'partial':   '⚠ Partial',
    'missing':   '✗ Missing',
    'manual':    '? Manual Review',
}


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
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th {
        background: #1a237e; color: #fff; text-align: left;
        padding: 6px 8px; font-size: 9pt;
    }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
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
        border: 1px solid #e0e0e0; border-radius: 4px; padding: 8px;
        text-align: center;
    }
    .stat-num { font-size: 18pt; font-weight: bold; }
    .stat-lbl { font-size: 8pt; color: #666; margin-top: 2px; }
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
      <p class="meta"><strong>Claim:</strong> {claim} &nbsp;|&nbsp;
         <strong>Client:</strong> {owner} &nbsp;|&nbsp;
         <strong>Address:</strong> {addr}</p>
      <p class="meta"><strong>Generated:</strong> {ts} &nbsp;|&nbsp;
         <strong>Audit #:</strong> {audit.pk} &nbsp;|&nbsp;
         <strong>Status:</strong> {audit.get_status_display()}</p>
    </div>
    """


def build_required_equipment_report(audit) -> str:
    """
    Generate the Required Equipment PDF for *audit*.
    Returns the absolute path to the saved PDF.
    Raises RuntimeError if no required equipment has been calculated yet.
    """
    from weasyprint import HTML as WP_HTML
    items = list(audit.required_equipment.order_by('category', 'display_name'))
    if not items:
        raise RuntimeError(
            f'No required equipment found for audit #{audit.pk}. '
            'Run the workbook calculation step first.'
        )

    rooms = list(audit.room_dimensions.filter(approved=True).order_by('room_name'))

    # Build room-dimension table
    room_rows = ''.join(
        f"""<tr>
              <td>{r.room_name}</td>
              <td>{r.length or '—'}</td>
              <td>{r.width or '—'}</td>
              <td>{r.height or '—'}</td>
              <td>{r.square_feet or '—'}</td>
              <td>{r.cubic_feet or '—'}</td>
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

    # Build equipment table grouped by category
    cat_label = dict(audit.required_equipment.model.CATEGORY_CHOICES)
    by_cat: dict = {}
    for item in items:
        by_cat.setdefault(item.category, []).append(item)

    equip_sections = ''
    for cat, cat_items in by_cat.items():
        rows = ''.join(
            f"""<tr>
                  <td>{i.display_name}</td>
                  <td style="text-align:center" class="qty-big">{i.required_quantity}</td>
                  <td>{i.source_sheet} / {i.workbook_cell or '—'}</td>
                  <td>{'Yes' if i.requires_stabilization_photo else 'No'}</td>
                </tr>"""
            for i in cat_items
        )
        equip_sections += f"""
        <h2>{cat_label.get(cat, cat)} ({len(cat_items)} items)</h2>
        <table>
          <tr>
            <th>Equipment Item</th><th>Required Qty</th>
            <th>Workbook Source</th><th>Stab. Photo Req.</th>
          </tr>
          {rows}
        </table>
        """

    total_units = sum(i.required_quantity for i in items)
    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Required Equipment Report — MIT Day 3')}
    <div class="notice">
      This report shows equipment calculated from the MIT Day 3 workbook using room
      dimensions extracted from the Encircle floor plan.  It is the source of truth
      for the subsequent photo audit.
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
        <div class="stat-num">{sum(1 for i in items if i.requires_stabilization_photo)}</div>
        <div class="stat-lbl">Stab. Photo Required</div>
      </div>
    </div>
    {room_table}
    {equip_sections}
    <div class="footer">Claimet App — MIT Day 3 Equipment Audit — Report #{audit.pk}</div>
    </body></html>"""

    return _save_pdf(html, audit, 'required_equipment')


def build_missing_equipment_report(audit) -> str:
    """
    Generate the Missing Equipment & Photos PDF for *audit*.
    Returns the absolute path to the saved PDF.
    """
    from weasyprint import HTML as WP_HTML
    items = list(
        audit.required_equipment
        .select_related('photo_observation')
        .order_by('category', 'display_name')
    )
    if not items:
        raise RuntimeError(
            f'No required equipment for audit #{audit.pk}. '
            'Run the workbook and photo review steps first.'
        )

    # Summary counts
    confirmed = missing = partial = manual = 0
    for item in items:
        obs = getattr(item, 'photo_observation', None)
        if not obs:
            missing += 1
        elif obs.status == 'confirmed':
            confirmed += 1
        elif obs.status == 'partial':
            partial += 1
        elif obs.status == 'missing':
            missing += 1
        else:
            manual += 1

    # Table rows
    table_rows = ''
    for item in items:
        obs = getattr(item, 'photo_observation', None)
        if obs:
            vis   = obs.visible_quantity
            miss  = obs.missing_quantity
            st    = obs.status
            conf  = obs.ai_confidence
            notes = obs.ai_notes or '—'
            action = obs.recommended_action or '—'
        else:
            vis   = 0
            miss  = item.required_quantity
            st    = 'missing'
            conf  = '—'
            notes = 'Photo review not yet run.'
            action = 'Run photo review.'

        color = _STATUS_COLORS.get(st, '#555')
        label = _STATUS_LABELS.get(st, st)
        miss_style = 'color:#c62828; font-weight:bold;' if miss > 0 else ''

        table_rows += f"""<tr>
          <td>{item.display_name}</td>
          <td style="text-align:center">{item.required_quantity}</td>
          <td style="text-align:center">{vis}</td>
          <td style="text-align:center; {miss_style}">{miss}</td>
          <td><span class="badge" style="background:{color}">{label}</span></td>
          <td style="font-size:8.5pt">{notes}</td>
          <td style="font-size:8.5pt">{action}</td>
        </tr>"""

    # Stabilization checklist
    stab_items  = [i for i in items if i.requires_stabilization_photo]
    stab_rows   = ''
    for item in stab_items:
        obs   = getattr(item, 'photo_observation', None)
        found = obs.stabilization_photo_found if obs else None
        if found is True:
            stab_icon = '✓'; stab_color = '#2e7d32'
        elif found is False:
            stab_icon = '✗'; stab_color = '#c62828'
        else:
            stab_icon = '?'; stab_color = '#6a1b9a'
        note = ''
        if obs:
            sc = obs.ai_notes or ''
            note = sc
        stab_rows += f"""<tr>
          <td>{item.display_name}</td>
          <td style="color:{stab_color}; font-weight:bold; text-align:center">{stab_icon}</td>
          <td style="font-size:8.5pt">{note}</td>
        </tr>"""

    stab_section = ''
    if stab_rows:
        stab_section = f"""
        <h2>Stabilization Photo Checklist</h2>
        <table>
          <tr><th>Equipment</th><th>Photo Found</th><th>Notes</th></tr>
          {stab_rows}
        </table>
        """

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Missing Equipment & Photo Report — MIT Day 3')}
    <div class="summary-grid">
      <div class="stat"><div class="stat-num" style="color:#2e7d32">{confirmed}</div>
        <div class="stat-lbl">Confirmed</div></div>
      <div class="stat"><div class="stat-num" style="color:#f57c00">{partial}</div>
        <div class="stat-lbl">Partial</div></div>
      <div class="stat"><div class="stat-num" style="color:#c62828">{missing}</div>
        <div class="stat-lbl">Missing</div></div>
      <div class="stat"><div class="stat-num" style="color:#6a1b9a">{manual}</div>
        <div class="stat-lbl">Manual Review</div></div>
    </div>
    <h2>Equipment Audit Results ({len(items)} items)</h2>
    <table>
      <tr>
        <th>Equipment</th><th>Required</th><th>Confirmed</th>
        <th>Missing</th><th>Status</th><th>AI Notes</th><th>Recommended Action</th>
      </tr>
      {table_rows}
    </table>
    {stab_section}
    <div class="footer">Claimet App — MIT Day 3 Equipment Audit — Report #{audit.pk}</div>
    </body></html>"""

    return _save_pdf(html, audit, 'missing_equipment')


def _save_pdf(html: str, audit, report_type: str) -> str:
    """
    Render *html* with WeasyPrint and save to MEDIA_ROOT/mit_audits/<id>/<type>.pdf.
    Returns the absolute path to the saved PDF.
    """
    from weasyprint import HTML as WP_HTML
    dest_dir = Path(settings.MEDIA_ROOT) / 'mit_audits' / str(audit.pk)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f'{report_type}_report.pdf'
    WP_HTML(string=html).write_pdf(str(dest))
    logger.info('[MIT] PDF saved: %s (%d bytes)', dest, dest.stat().st_size)
    return str(dest)
