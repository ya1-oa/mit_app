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
import html as _html
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def _e(text) -> str:
    """HTML-escape a value that will be inserted into report markup."""
    return _html.escape(str(text)) if text is not None else ''

logger = logging.getLogger(__name__)



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
    thead { display: table-header-group; }   /* repeat header on every page */
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

    # Build equipment table grouped by category
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
                  <td>{'Yes' if i.requires_stabilization_photo else 'No'}</td>
                </tr>"""
            for i in cat_items
        )
        equip_sections += f"""
        <h2>{_e(cat_label.get(cat, cat))} ({len(cat_items)} items)</h2>
        <table>
          <thead><tr>
            <th>Equipment Item</th><th>Required Qty</th>
            <th>Workbook Source</th><th>Stab. Photo Req.</th>
          </tr></thead>
          <tbody>{rows}</tbody>
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
    Generate the Outstanding Photo Requirements PDF for *audit*.

    ONLY shows equipment that still needs photographs — confirmed items
    are never listed.  Confirmed items are counted in a header note so
    the recipient can see progress, but they take up no table space.

    If every item is confirmed this generates a clean all-clear page
    rather than an empty table.

    Returns the absolute path to the saved PDF.
    """
    all_items = list(
        audit.required_equipment
        .select_related('photo_observation')
        .order_by('category', 'display_name')
    )
    if not all_items:
        raise RuntimeError(
            f'No required equipment for audit #{audit.pk}. '
            'Run the workbook and photo review steps first.'
        )

    # ── Separate confirmed from still-needed ────────────────────────
    confirmed_count = 0
    needs_work = []   # (item, obs|None)

    for item in all_items:
        obs = getattr(item, 'photo_observation', None)
        if obs is None:
            needs_work.append((item, None))          # no review yet → missing
        elif obs.status == 'confirmed':
            confirmed_count += 1                      # done — skip from report
        else:
            needs_work.append((item, obs))            # partial / missing / manual

    total      = len(all_items)
    need_count = len(needs_work)

    # ── Build table rows — only items that still need work ──────────
    cat_label   = dict(audit.required_equipment.model.CATEGORY_CHOICES)
    table_rows  = ''
    current_cat = None

    for item, obs in needs_work:
        # Category sub-header row (groups items without a separate <h2>)
        if item.category != current_cat:
            current_cat = item.category
            table_rows += (
                f'<tr style="background:#e8eaf6;">'
                f'<td colspan="4" style="font-weight:bold; font-size:9pt;'
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
            action     = 'Photo review has not been run yet — photograph all units.'

        table_rows += (
            f'<tr>'
            f'<td>{_e(item.display_name)}</td>'
            f'<td style="text-align:center">{item.required_quantity}</td>'
            f'<td style="text-align:center">{already}</td>'
            f'<td style="text-align:center; {need_style}">{need_str}</td>'
            f'<td style="font-size:8.5pt">{_e(action)}</td>'
            f'</tr>'
        )

    # ── Main body: table or all-clear banner ────────────────────────
    if need_count == 0:
        body_section = """
        <div style="text-align:center; padding:48px 20px; color:#2e7d32;">
          <div style="font-size:30pt; margin-bottom:10px;">✓</div>
          <div style="font-size:14pt; font-weight:bold;">All equipment confirmed</div>
          <div style="font-size:10pt; color:#555; margin-top:8px;">
            No outstanding photo requirements for this audit.
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

    # ── Stabilization section — only items WITHOUT a confirmed stab photo ──
    stab_rows = ''
    for item in all_items:
        if not item.requires_stabilization_photo:
            continue
        obs   = getattr(item, 'photo_observation', None)
        found = obs.stabilization_photo_found if obs else None
        if found is True:
            continue   # confirmed — do not list
        if found is False:
            icon  = '✗'
            color = '#c62828'
            note  = obs.ai_notes or 'Not found. Must show unit running with drain/hose visible.'
        else:
            icon  = '?'
            color = '#6a1b9a'
            note  = (obs.ai_notes if obs else '') or 'Unknown — inspector to verify on-site.'

        stab_rows += (
            f'<tr>'
            f'<td>{_e(item.display_name)}</td>'
            f'<td style="color:{color}; font-weight:bold; text-align:center;'
            f' font-size:13pt">{icon}</td>'
            f'<td style="font-size:8.5pt">{_e(note)}</td>'
            f'</tr>'
        )

    stab_section = ''
    if stab_rows:
        stab_section = f"""
        <h2>Missing Stabilization Photos</h2>
        <table>
          <thead><tr>
            <th>Equipment</th>
            <th style="width:80px; text-align:center">Status</th>
            <th>What&rsquo;s Required</th>
          </tr></thead>
          <tbody>{stab_rows}</tbody>
        </table>"""

    # ── Summary line below header ────────────────────────────────────
    if need_count == 0:
        summary_note = (
            f'<p class="meta" style="color:#2e7d32; font-weight:bold; margin-top:6px;">'
            f'&#10003; All {total} items confirmed &mdash; no action required.</p>'
        )
    else:
        summary_note = (
            f'<p class="meta" style="color:#c62828; margin-top:6px;">'
            f'<strong>{need_count} of {total} item(s)</strong> still require photographs. '
            f'{confirmed_count} already confirmed.'
            f'</p>'
        )

    html = f"""<!DOCTYPE html>
    <html><head><meta charset="UTF-8">
    <style>{_base_css()}</style></head><body>
    {_header_html(audit, 'Outstanding Photo Requirements &mdash; MIT Day 3')}
    {summary_note}
    {body_section}
    {stab_section}
    <div class="footer">Claimet App &mdash; MIT Day 3 Equipment Audit &mdash; Report #{audit.pk}</div>
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
