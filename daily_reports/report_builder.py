"""
daily_reports/report_builder.py

Builds the HTML body for the two report types:
  - build_high_priority_html(config) → HTML string for daily report
  - build_deep_report_html()         → HTML string for weekly deep report
"""
from __future__ import annotations

import datetime
from django.utils import timezone


# ── Style constants ────────────────────────────────────────────────────────────

_BASE = """
<style>
  body { font-family: Arial, sans-serif; background: #f8fafc; margin: 0; padding: 0; }
  .wrapper { max-width: 760px; margin: 0 auto; background: #fff; }
  .header  { background: #1e3a5f; color: #fff; padding: 24px 28px 18px; }
  .header h1 { margin: 0 0 4px; font-size: 20px; letter-spacing: .3px; }
  .header .sub { font-size: 13px; opacity: .75; }
  .section { padding: 0 28px 4px; }
  .section-title {
    background: #1e40af; color: #fff;
    padding: 9px 14px; font-size: 13px; font-weight: bold;
    margin: 18px 0 0; border-radius: 4px 4px 0 0;
  }
  .section-title .count { float: right; opacity: .8; }
  .claim-card {
    border: 1px solid #e2e8f0; border-top: none;
    padding: 12px 14px 10px; margin-bottom: 2px;
    background: #fff;
  }
  .claim-name { font-weight: bold; color: #0f172a; font-size: 13px; }
  .claim-sub  { font-size: 11px; color: #64748b; margin-bottom: 8px; }
  .item-row   { display: flex; align-items: baseline; gap: 8px; padding: 3px 0; font-size: 12px; }
  .badge-urgent  { background: #fee2e2; color: #b91c1c; border-radius: 3px; padding: 1px 6px; font-size: 11px; font-weight: bold; }
  .badge-warn    { background: #fef3c7; color: #92400e; border-radius: 3px; padding: 1px 6px; font-size: 11px; font-weight: bold; }
  .badge-ok      { background: #d1fae5; color: #065f46; border-radius: 3px; padding: 1px 6px; font-size: 11px; }
  .badge-pending { background: #f1f5f9; color: #475569; border-radius: 3px; padding: 1px 6px; font-size: 11px; }
  .demand { background: #fff1f2; border-left: 3px solid #e11d48; padding: 8px 10px; font-size: 12px; color: #881337; margin: 6px 0; }
  .summary-bar { background: #f1f5f9; padding: 12px 28px; font-size: 13px; border-top: 2px solid #e2e8f0; margin-top: 4px; }
  .summary-bar strong { color: #b91c1c; }
  .footer { padding: 16px 28px 20px; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; }
  .no-items { padding: 12px 14px; font-size: 12px; color: #64748b; border: 1px solid #e2e8f0; border-top: none; }
  .tag-signed   { color: #059669; }
  .tag-unsigned { color: #dc2626; font-weight: bold; }
  .days-badge { font-size: 10px; color: #64748b; }
  /* Deep report */
  .app-section  { border: 1px solid #e2e8f0; margin-bottom: 10px; border-radius: 4px; overflow: hidden; }
  .app-header   { background: #1e40af; color: #fff; padding: 8px 14px; font-size: 12px; font-weight: bold; display: flex; justify-content: space-between; }
  .progress-bar { height: 6px; background: #e2e8f0; margin: 0; }
  .progress-fill { height: 6px; background: #22c55e; }
  .task-row     { padding: 7px 14px; font-size: 12px; border-bottom: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center; }
  .task-row:last-child { border-bottom: none; }
  .pct { font-size: 11px; color: #64748b; }
  .status-done  { color: #059669; }
  .status-prog  { color: #d97706; }
  .status-block { color: #dc2626; }
  .status-todo  { color: #64748b; }
</style>
"""


def _dedup_sig_requests(reqs):
    """
    Deduplicate signature requests by signer_role — the most recently sent
    request for each role is the active one.

    Why: re-sending a signing link creates a new LeaseSignatureRequest row
    with a new token for the same party (same role/email).  A lease has at
    most 3 parties (tenant / landlord / re_company), so at most 3 active
    requests.  We want to show 3 parties max, not N sends.

    Returns a list of LeaseSignatureRequest objects, one per role, each
    annotated with ._resend_count (int, ≥1) so the UI can flag re-sends.
    """
    from collections import defaultdict
    by_role = defaultdict(list)
    for r in reqs:
        by_role[r.signer_role].append(r)
    result = []
    for role_reqs in by_role.values():
        active = max(role_reqs, key=lambda r: r.sent_at)
        active._resend_count = len(role_reqs)
        result.append(active)
    return result


def _render_description(text: str) -> str:
    """
    Convert a plain-text description into structured HTML.
    Lines starting with  *  or  •  become <li> bullet points.
    Other non-empty lines become <p> paragraphs.
    """
    if not text:
        return ''
    lines = text.split('\n')
    parts = []
    in_list = False
    for line in lines:
        s = line.strip()
        if s.startswith('* ') or s.startswith('• ') or s.startswith('- '):
            if not in_list:
                parts.append('<ul style="margin:4px 0 4px 14px;padding:0;">')
                in_list = True
            bullet_text = s[2:]
            parts.append(f'<li style="margin:2px 0;">{bullet_text}</li>')
        else:
            if in_list:
                parts.append('</ul>')
                in_list = False
            if s:
                parts.append(
                    f'<p style="margin:3px 0;color:#475569;font-size:12px;">{s}</p>'
                )
    if in_list:
        parts.append('</ul>')
    return ''.join(parts)


def _days_ago(dt) -> int:
    """Days since a datetime (timezone-aware or naive)."""
    if dt is None:
        return 0
    now = timezone.now()
    if timezone.is_naive(dt):
        from django.utils.timezone import make_aware
        dt = make_aware(dt)
    return max(0, (now - dt).days)


def _days_badge(days: int, escalation: int) -> str:
    if days == 0:
        return '<span class="days-badge">today</span>'
    if days >= escalation:
        return f'<span class="badge-urgent">⚠ {days}d</span>'
    if days >= max(1, escalation - 1):
        return f'<span class="badge-warn">{days}d</span>'
    return f'<span class="days-badge">{days}d ago</span>'


def _fmt_status(status: str) -> str:
    labels = {
        'draft': 'Draft', 'generated': 'Generated', 'review': 'Under Review',
        'sent_for_signature': 'Sent for Signature', 'signed': 'Signed',
        'invoice_created': 'Invoice Created', 'package_sent': 'Pkg Sent',
        'payment_pending': 'Payment Pending', 'payment_received': 'Payment Rcvd',
        'completed': 'Completed', 'cancelled': 'Cancelled',
    }
    return labels.get(status, status.replace('_', ' ').title())


# ── Section builders ──────────────────────────────────────────────────────────

def _section_priority_tasks(config) -> tuple[str, int, int]:
    """Priority tasks (Level 1/2/3) defined by the user. Returns (html, total, urgent)."""
    from daily_reports.models import PriorityTask

    tasks = (
        PriorityTask.objects
        .filter(config=config)
        .exclude(status='done')
        .select_related('app_module')
        .order_by('level', 'created_at')
    )

    if not tasks:
        return '<div class="no-items">No open priority tasks.</div>', 0, 0

    LEVEL_CFG = {
        'level_1': ('#fee2e2', '#b91c1c', '🔴 L1 — CRITICAL'),
        'level_2': ('#fff7ed', '#c2410c', '🟠 L2 — HIGH'),
        'level_3': ('#eff6ff', '#1d4ed8', '🔵 L3 — STANDARD'),
    }

    cards = []
    for t in tasks:
        bg, color, label = LEVEL_CFG.get(t.level, ('#fff', '#000', t.level))
        module_str = (
            f'<span style="font-size:10px;background:#e0e7ff;color:#3730a3;'
            f'border-radius:3px;padding:1px 6px;margin-left:6px;">'
            f'{t.app_module.name}</span>'
        ) if t.app_module else ''
        due_str = (
            f'<span style="font-size:10px;color:#dc2626;margin-left:6px;">'
            f'Due {t.due_date}</span>'
        ) if t.due_date else ''
        desc_rendered = _render_description(t.description)
        desc_str = (
            f'<div style="font-size:12px;color:#475569;margin-top:4px;">{desc_rendered}</div>'
        ) if desc_rendered else ''
        status_label = {'open': 'Open', 'in_progress': 'In Progress'}.get(t.status, t.status)
        cards.append(
            f'<div class="claim-card" style="border-left:4px solid {color};background:{bg};">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
            f'<div>'
            f'<span style="font-size:11px;font-weight:bold;color:{color};">{label}</span>'
            f'{module_str}{due_str}'
            f'<div style="font-size:13px;font-weight:bold;color:#0f172a;margin-top:2px;">{t.title}</div>'
            f'{desc_str}'
            f'</div>'
            f'<span class="badge-pending" style="white-space:nowrap;margin-left:8px;">{status_label}</span>'
            f'</div></div>'
        )

    return ''.join(cards), len(tasks), 0


def _section_ppr_signatures(config) -> tuple[str, int, int]:
    """Compact per-session summary. Pinned sessions get a detail card; rest get a count line."""
    from cps_report.models import CPSReportSession
    esc = config.escalation_days
    pinned_ids = list(getattr(config, 'pinned_ppr_sessions', None) or [])

    all_sessions = (
        CPSReportSession.objects
        .filter(archived=False)
        .exclude(status='error')
        .select_related('client')
        .prefetch_related('rooms')
        .order_by('-updated_at')
    )
    # Only sessions with at least one unsigned room
    all_sessions = [s for s in all_sessions if s.rooms.filter(signature_name='').exists()]

    if not all_sessions:
        return '<div class="no-items">✅ All PPR rooms are signed.</div>', 0, 0

    total_unsigned = sum(s.rooms.filter(signature_name='').count() for s in all_sessions)
    total_sessions = len(all_sessions)
    urgent = 0
    cards = []

    if pinned_ids:
        # Feature pinned sessions with detail cards
        pinned = [s for s in all_sessions if s.id in pinned_ids]
        unpinned_count = total_sessions - len(pinned)
        unpinned_unsigned = sum(s.rooms.filter(signature_name='').count()
                                for s in all_sessions if s.id not in pinned_ids)

        for session in pinned:
            rooms = list(session.rooms.all().order_by('order', 'room_number'))
            unsigned_rooms = [r for r in rooms if not r.signature_name]
            signed_count   = len(rooms) - len(unsigned_rooms)
            days = _days_ago(session.updated_at)
            if days >= esc:
                urgent += len(unsigned_rooms)

            status_color = '#b91c1c' if days >= esc else '#64748b'
            demand_html = ''
            if days >= esc:
                demand_html = (
                    f'<div class="demand">⚠ DEMAND: Unsigned for <strong>{days} days</strong>. '
                    f'Immediate signature collection required.</div>'
                )
            unsigned_names = ', '.join(
                f'{r.room_number} {r.room_name}'.strip() for r in unsigned_rooms
            ) or '—'
            cards.append(
                f'<div class="claim-card" style="border-left:4px solid {status_color};">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'<div>'
                f'<div class="claim-name">{session.client.pOwner or "—"}</div>'
                f'<div class="claim-sub">Claim #{session.client.claimNumber or "—"} &nbsp;·&nbsp; '
                f'{session.display_name} &nbsp;·&nbsp; {_days_badge(days, esc)}</div>'
                f'</div>'
                f'<span class="badge-urgent">{len(unsigned_rooms)} UNSIGNED</span>'
                f'</div>'
                f'<div style="font-size:12px;margin-top:6px;">'
                f'<strong>{signed_count}/{len(rooms)}</strong> rooms signed &nbsp;·&nbsp; '
                f'Pending: {unsigned_names}'
                f'</div>'
                f'{demand_html}'
                f'</div>'
            )

        if unpinned_count:
            cards.append(
                f'<div class="no-items" style="color:#64748b;font-style:italic;">'
                f'+ {unpinned_count} more session(s) with {unpinned_unsigned} unsigned room(s) '
                f'not featured — pin them on the dashboard to include details.'
                f'</div>'
            )
    else:
        # No pinned sessions — show one summary line per session
        for session in all_sessions:
            rooms = list(session.rooms.all())
            unsigned_rooms = [r for r in rooms if not r.signature_name]
            days = _days_ago(session.updated_at)
            if days >= esc:
                urgent += len(unsigned_rooms)
            status_color = '#b91c1c' if days >= esc else '#e2e8f0'
            demand_html = ''
            if days >= esc:
                demand_html = (
                    f'<div class="demand" style="margin-top:4px;">⚠ Unsigned for '
                    f'<strong>{days} days</strong> — follow up immediately.</div>'
                )
            cards.append(
                f'<div class="claim-card" style="border-left:3px solid {status_color};padding:8px 14px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<span style="font-weight:bold;font-size:13px;">{session.client.pOwner or "—"}</span>'
                f'<span class="claim-sub" style="display:inline;margin-left:8px;">'
                f'#{session.client.claimNumber or "—"} &nbsp;·&nbsp; {session.display_name}</span>'
                f'</div>'
                f'<span class="badge-urgent" style="white-space:nowrap;">'
                f'{len(unsigned_rooms)}/{len(rooms)} unsigned</span>'
                f'</div>'
                f'{demand_html}'
                f'</div>'
            )
        cards.append(
            f'<div class="no-items" style="color:#64748b;font-style:italic;">'
            f'Pin specific sessions on the dashboard to expand their details in the report.'
            f'</div>'
        )

    return ''.join(cards), total_unsigned, urgent


def _section_ppr_pricing(config) -> tuple[str, int, int]:
    """Sessions with rooms that have items priced at $0."""
    from cps_report.models import CPSReportSession
    esc = config.escalation_days

    sessions = (
        CPSReportSession.objects
        .filter(archived=False, status='complete')
        .prefetch_related('rooms__items', 'client')
        .order_by('-updated_at')
    )

    flagged = []
    for s in sessions:
        zero_items = []
        for room in s.rooms.all():
            for item in room.items.filter(structural=False):
                if not item.replacement_value_each or float(item.replacement_value_each) == 0:
                    zero_items.append((room, item))
        if zero_items:
            flagged.append((s, zero_items))

    if not flagged:
        return '<div class="no-items">✅ All PPR sessions have complete pricing.</div>', 0, 0

    total = urgent = 0
    cards = []
    for session, zero_items in flagged:
        total += len(zero_items)
        days  = _days_ago(session.updated_at)
        if days >= esc:
            urgent += len(zero_items)

        rows = []
        for room, item in zero_items[:10]:
            rows.append(
                f'<div class="item-row">'
                f'<span class="tag-unsigned">$0</span>'
                f'<span>{room.room_number} {room.room_name} — {item.description}</span>'
                f'{_days_badge(days, esc)}'
                f'</div>'
            )
        if len(zero_items) > 10:
            rows.append(f'<div class="item-row" style="color:#64748b;">… and {len(zero_items)-10} more items</div>')

        demand_html = ''
        if days >= esc:
            demand_html = (
                f'<div class="demand">⚠ DEMAND: {len(zero_items)} items have $0.00 pricing '
                f'for {days} days. Please verify and reprice.</div>'
            )

        cards.append(
            f'<div class="claim-card">'
            f'<div class="claim-name">{session.client.pOwner or "—"}</div>'
            f'<div class="claim-sub">Claim #{session.client.claimNumber or "—"} &nbsp;·&nbsp; {session.display_name}</div>'
            f'{demand_html}'
            f'{"".join(rows)}'
            f'</div>'
        )

    return ''.join(cards), total, urgent


def _section_lease_signatures(config) -> tuple[str, int, int]:
    """
    Lease signature summary, deduplicated by signer role.

    A lease has at most 3 parties (tenant / landlord / re_company).
    Re-sending a link creates a new LeaseSignatureRequest row but the party
    count stays at 3.  We show the latest request per role and flag any role
    that was sent more than once with a "(re-sent Nx)" note.
    """
    from docsAppR.models import Lease
    esc = config.escalation_days
    pinned_ids = [str(x) for x in (getattr(config, 'pinned_leases', None) or [])]

    all_leases = list(
        Lease.objects
        .exclude(status__in=['cancelled', 'completed', 'signed'])
        .filter(sent_for_signature_at__isnull=False)
        .select_related('client')
        .prefetch_related('signature_requests')
        .order_by('sent_for_signature_at')
    )

    if not all_leases:
        return '<div class="no-items">✅ No leases awaiting signatures.</div>', 0, 0

    ROLE_LABEL = {'tenant': 'Tenant', 'landlord': 'Landlord', 're_company': 'RE Company'}

    def _signer_rows(active_reqs):
        """Build signed / pending rows from the deduplicated request list."""
        signed_parts  = []
        pending_parts = []
        for r in sorted(active_reqs, key=lambda x: x.signer_role):
            role_label = ROLE_LABEL.get(r.signer_role, r.signer_role)
            resend_tag = (
                f' <span style="font-size:9px;color:#f59e0b;font-weight:bold;">'
                f'(re-sent {r._resend_count}×)</span>'
            ) if r._resend_count > 1 else ''
            if r.status == 'signed':
                sent_date = r.signed_at.strftime('%b %d') if r.signed_at else '—'
                signed_parts.append(
                    f'<span class="tag-signed">✔ {role_label}: {r.signer_name}'
                    f'<span style="font-size:9px;color:#64748b;margin-left:4px;">'
                    f'signed {sent_date}</span></span>'
                )
            else:
                status_icon = {'viewed': '👁', 'declined': '❌', 'expired': '⌛'}.get(r.status, '⏳')
                pending_parts.append(
                    f'<span class="tag-unsigned">{status_icon} {role_label}: {r.signer_name}'
                    f'{resend_tag}</span>'
                )
        return signed_parts, pending_parts

    total = urgent = 0
    cards = []

    if pinned_ids:
        pinned   = [l for l in all_leases if str(l.id) in pinned_ids]
        unpinned = [l for l in all_leases if str(l.id) not in pinned_ids]

        for lease in pinned:
            all_reqs    = list(lease.signature_requests.all())
            active_reqs = _dedup_sig_requests(all_reqs)
            pending_active = [r for r in active_reqs if r.status != 'signed']
            total  += len(pending_active)
            days    = _days_ago(lease.sent_for_signature_at)
            if days >= esc:
                urgent += len(pending_active)

            signed_parts, pending_parts = _signer_rows(active_reqs)
            addr         = ' '.join(filter(None, [lease.property_address,
                                                   lease.property_city, lease.property_state]))
            status_color = '#b91c1c' if days >= esc else '#64748b'

            demand_html = ''
            if days >= esc and pending_active:
                pending_names = ', '.join(r.signer_name for r in pending_active)
                demand_html = (
                    f'<div class="demand">⚠ DEMAND: Sent {days} days ago. '
                    f'Waiting on: <strong>{pending_names}</strong>. '
                    f'Follow up immediately.</div>'
                )

            signer_html = ''
            if signed_parts:
                signer_html += (
                    f'<div style="font-size:11px;margin-top:6px;display:flex;gap:12px;flex-wrap:wrap;">'
                    + '&nbsp;&nbsp;'.join(signed_parts) + '</div>'
                )
            if pending_parts:
                signer_html += (
                    f'<div style="font-size:11px;margin-top:4px;display:flex;gap:12px;flex-wrap:wrap;">'
                    + '&nbsp;&nbsp;'.join(pending_parts) + '</div>'
                )

            cards.append(
                f'<div class="claim-card" style="border-left:4px solid {status_color};">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'<div>'
                f'<div class="claim-name">{lease.client.pOwner if lease.client else "—"}</div>'
                f'<div class="claim-sub">{addr or "—"} &nbsp;·&nbsp; Sent: '
                f'{lease.sent_for_signature_at.strftime("%b %d") if lease.sent_for_signature_at else "—"}'
                f' &nbsp;·&nbsp; {_days_badge(days, esc)}</div>'
                f'</div>'
                f'<span class="badge-urgent">{len(pending_active)}/3 UNSIGNED</span>'
                f'</div>'
                f'{signer_html}'
                f'{demand_html}'
                f'</div>'
            )

        if unpinned:
            u_pending = 0
            for l in unpinned:
                active = _dedup_sig_requests(list(l.signature_requests.all()))
                u_pending += sum(1 for r in active if r.status != 'signed')
            total += u_pending
            cards.append(
                f'<div class="no-items" style="color:#64748b;font-style:italic;">'
                f'+ {len(unpinned)} more lease(s) with {u_pending} unsigned party/parties '
                f'— pin them on the dashboard to include details.'
                f'</div>'
            )
    else:
        for lease in all_leases:
            all_reqs    = list(lease.signature_requests.all())
            active_reqs = _dedup_sig_requests(all_reqs)
            pending_active = [r for r in active_reqs if r.status != 'signed']
            total  += len(pending_active)
            days    = _days_ago(lease.sent_for_signature_at)
            if days >= esc:
                urgent += len(pending_active)

            status_color = '#b91c1c' if days >= esc else '#e2e8f0'
            addr         = ' '.join(filter(None, [lease.property_address,
                                                   lease.property_city, lease.property_state]))
            _, pending_parts = _signer_rows(active_reqs)
            pending_inline = ', '.join(
                r.signer_name + (f' (re-sent {r._resend_count}×)' if r._resend_count > 1 else '')
                for r in pending_active
            ) or '—'

            demand_html = ''
            if days >= esc and pending_active:
                demand_html = (
                    f'<div class="demand" style="margin-top:4px;">'
                    f'⚠ Sent {days} days ago — follow up immediately.</div>'
                )
            cards.append(
                f'<div class="claim-card" style="border-left:3px solid {status_color};padding:8px 14px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<span style="font-weight:bold;font-size:13px;">'
                f'{lease.client.pOwner if lease.client else "—"}</span>'
                f'<span class="claim-sub" style="display:inline;margin-left:8px;">{addr or "—"}</span>'
                f'</div>'
                f'<span class="badge-urgent" style="white-space:nowrap;">'
                f'{len(pending_active)}/3 unsigned</span>'
                f'</div>'
                f'<div style="font-size:11px;margin-top:4px;color:#475569;">'
                f'Waiting on: {pending_inline}</div>'
                f'{demand_html}'
                f'</div>'
            )
        cards.append(
            f'<div class="no-items" style="color:#64748b;font-style:italic;">'
            f'Pin specific leases on the dashboard to expand their details.'
            f'</div>'
        )

    return ''.join(cards), total, urgent


def _section_lease_pipeline(config) -> tuple[str, int, int]:
    """All active leases showing their pipeline stage."""
    from docsAppR.models import Lease
    esc = config.escalation_days

    leases = (
        Lease.objects
        .exclude(status='cancelled')
        .select_related('client')
        .order_by('status', '-updated_at')
    )

    if not leases.exists():
        return '<div class="no-items">No active leases.</div>', 0, 0

    # Group by status
    from collections import defaultdict
    by_status = defaultdict(list)
    for lease in leases:
        by_status[lease.status].append(lease)

    STATUS_ORDER = [
        'draft', 'generated', 'review', 'sent_for_signature',
        'signed', 'invoice_created', 'package_sent',
        'payment_pending', 'payment_received', 'completed',
    ]
    TERMINAL = {'completed', 'cancelled', 'payment_received'}
    urgent = 0
    rows = []
    for status in STATUS_ORDER:
        group = by_status.get(status, [])
        if not group:
            continue
        for lease in group:
            days = _days_ago(lease.updated_at)
            is_terminal = status in TERMINAL
            if not is_terminal and days >= esc:
                urgent += 1
                badge = f'<span class="badge-urgent">STALE {days}d</span>'
            elif not is_terminal and days >= max(1, esc - 1):
                badge = f'<span class="badge-warn">{days}d</span>'
            elif is_terminal:
                badge = f'<span class="badge-ok">{_fmt_status(status)}</span>'
            else:
                badge = f'<span class="badge-pending">{_fmt_status(status)}</span>'

            client_name = lease.client.pOwner if lease.client else '—'
            addr = ' '.join(filter(None, [lease.property_address, lease.property_city]))
            rows.append(
                f'<div class="task-row">'
                f'<div><strong>{client_name}</strong>&nbsp; <span style="color:#64748b;font-size:11px;">{addr or "—"}</span></div>'
                f'{badge}'
                f'</div>'
            )

    html = (
        f'<div class="app-section">'
        f'<div class="app-header">'
        f'<span>All Active Leases by Pipeline Stage</span>'
        f'<span>{leases.count()} total</span>'
        f'</div>'
        f'{"".join(rows)}'
        f'</div>'
    )
    return html, leases.count(), urgent


def _section_high_priority(config) -> tuple[str, int, int]:
    """User-flagged high priority items."""
    from daily_reports.models import HighPriorityItem
    items = (
        HighPriorityItem.objects
        .filter(config=config, is_resolved=False)
        .select_related('client', 'ppr_session', 'lease', 'added_by')
        .order_by('-added_at')
    )

    # Auto-resolve any that have completed
    for item in items:
        item.check_auto_resolve()

    items = items.filter(is_resolved=False)

    if not items.exists():
        return '', 0, 0  # Hide section entirely when empty

    total = items.count()
    esc = config.escalation_days
    urgent = 0
    cards = []
    for item in items:
        days = _days_ago(item.added_at)
        if days >= esc:
            urgent += 1

        sub_info = ''
        if item.ppr_session:
            sub_info = f'PPR: {item.ppr_session.display_name} (status: {item.ppr_session.status})'
        elif item.lease:
            sub_info = f'Lease: {_fmt_status(item.lease.status)}'

        demand_html = ''
        if item.demand_language:
            demand_html = f'<div class="demand">📢 {item.demand_language}</div>'
        elif days >= esc:
            demand_html = (
                f'<div class="demand">⚠ DEMAND REVIEW: This item has been flagged for '
                f'<strong>{days} days</strong> with no resolution. Immediate action required.</div>'
            )

        note_html = (
            f'<div style="font-size:12px;color:#0f172a;margin:4px 0;">{item.priority_note}</div>'
            if item.priority_note else ''
        )
        resolution_html = (
            f'<div style="font-size:11px;color:#64748b;">Needs: {item.resolution_criteria}</div>'
            if item.resolution_criteria else ''
        )
        cards.append(
            f'<div class="claim-card" style="border-left:3px solid #e11d48;">'
            f'<div class="claim-name">⚡ {item.client.pOwner or "—"}</div>'
            f'<div class="claim-sub">'
            f'Claim #{item.client.claimNumber or "—"} &nbsp;·&nbsp; {item.get_item_type_display()} &nbsp;·&nbsp; '
            f'Flagged {days}d ago &nbsp;·&nbsp; {sub_info}'
            f'</div>'
            f'{note_html}'
            f'{resolution_html}'
            f'{demand_html}'
            f'</div>'
        )

    return ''.join(cards), total, urgent


# ── Main builder ──────────────────────────────────────────────────────────────

def build_high_priority_html(config) -> tuple[str, int, int]:
    """
    Build the full HTML email body for the daily High Priority Report.
    Returns (html, total_items, urgent_items).
    """
    now_str = datetime.datetime.now().strftime('%A, %B %d, %Y — %I:%M %p ET')
    esc = config.escalation_days

    sections_html = ''
    grand_total = 0
    grand_urgent = 0

    if getattr(config, 'include_priority_tasks', True):
        body, count, urg = _section_priority_tasks(config)
        grand_total += count
        sections_html += (
            f'<div class="section">'
            f'<div class="section-title" style="background:#7c3aed;">📌 PRIORITY TASKS'
            f'<span class="count">{count} open</span></div>'
            f'{body}</div>'
        )

    if config.include_ppr_signatures:
        body, count, urg = _section_ppr_signatures(config)
        grand_total += count
        grand_urgent += urg
        sections_html += (
            f'<div class="section">'
            f'<div class="section-title">📋 PPR REPORTS — AWAITING SIGNATURES'
            f'<span class="count">{count} pending</span></div>'
            f'{body}</div>'
        )

    if config.include_ppr_pricing:
        body, count, urg = _section_ppr_pricing(config)
        grand_total += count
        grand_urgent += urg
        sections_html += (
            f'<div class="section">'
            f'<div class="section-title">💰 PPR REPORTS — PRICING INCOMPLETE'
            f'<span class="count">{count} items</span></div>'
            f'{body}</div>'
        )

    if config.include_lease_sigs:
        body, count, urg = _section_lease_signatures(config)
        grand_total += count
        grand_urgent += urg
        sections_html += (
            f'<div class="section">'
            f'<div class="section-title">✍️ ALE LEASES — SIGNATURE STATUS'
            f'<span class="count">{count} pending</span></div>'
            f'{body}</div>'
        )

    if config.include_lease_pipeline:
        body, count, urg = _section_lease_pipeline(config)
        grand_urgent += urg
        sections_html += (
            f'<div class="section">'
            f'<div class="section-title">📊 LEASE PIPELINE STATUS'
            f'<span class="count">{count} active</span></div>'
            f'{body}</div>'
        )

    if config.include_high_priority:
        body, count, urg = _section_high_priority(config)
        if body:  # only render section when there are actual items
            grand_total += count
            grand_urgent += urg
            sections_html += (
                f'<div class="section">'
                f'<div class="section-title" style="background:#b91c1c;">⚡ HIGH PRIORITY TRACKED ITEMS'
                f'<span class="count">{count} active</span></div>'
                f'{body}</div>'
            )

    urgent_text = (
        f'<strong>{grand_urgent} URGENT</strong> (pending &gt;{esc} days) &nbsp;|&nbsp; '
        if grand_urgent else ''
    )

    html = f"""
<html><head>{_BASE}</head><body>
<div class="wrapper">
  <div class="header">
    <h1>🔴 HIGH PRIORITY DAILY STATUS REPORT</h1>
    <div class="sub">Claimet App &nbsp;·&nbsp; {now_str}</div>
  </div>
  <div class="summary-bar">
    {urgent_text}{grand_total} total open items tracked &nbsp;·&nbsp;
    Report continues daily until all items resolved
  </div>
  {sections_html}
  <div class="footer">
    This is an automated daily report from Claimet App.<br>
    Items marked <strong>URGENT</strong> have been pending for more than {esc} days.<br>
    Reports stop for an item when it reaches a completed/signed status.
  </div>
</div>
</body></html>
"""
    return html, grand_total, grand_urgent


# ── Deep Operations Report ────────────────────────────────────────────────────

def build_deep_report_html() -> str:
    """
    Build the HTML for the Weekly Deep Operations Report.
    Aggregates live stats per Claimet app + OperationalTask items.
    """
    from daily_reports.models import OperationalTask
    from collections import defaultdict

    now_str = datetime.datetime.now().strftime('%A, %B %d, %Y — %I:%M %p ET')

    # ── Live app stats ─────────────────────────────────────────────────────────
    def _ppr_stats():
        from cps_report.models import CPSReportSession
        total    = CPSReportSession.objects.filter(archived=False).count()
        complete = CPSReportSession.objects.filter(archived=False, status='complete').count()
        pending  = CPSReportSession.objects.filter(archived=False, status__in=['pending', 'processing']).count()
        unsigned = CPSReportSession.objects.filter(archived=False, rooms__signature_name='').distinct().count()
        pct = round(complete / total * 100) if total else 0
        return {'total': total, 'complete': complete, 'pending': pending,
                'unsigned_rooms': unsigned, 'pct': pct,
                'label': 'PPR / Schedule of Loss'}

    def _lease_stats():
        from docsAppR.models import Lease
        total     = Lease.objects.count()
        signed    = Lease.objects.filter(status__in=['signed', 'completed', 'payment_received']).count()
        pending   = Lease.objects.filter(status='sent_for_signature').count()
        drafts    = Lease.objects.filter(status__in=['draft', 'generated']).count()
        pct = round(signed / total * 100) if total else 0
        return {'total': total, 'signed': signed, 'pending': pending,
                'drafts': drafts, 'pct': pct, 'label': 'ALE Lease Manager'}

    def _lease_sig_stats():
        try:
            from docsAppR.models import LeaseSignatureRequest
            total   = LeaseSignatureRequest.objects.count()
            signed  = LeaseSignatureRequest.objects.filter(status='signed').count()
            pending = LeaseSignatureRequest.objects.filter(status='pending').count()
            pct = round(signed / total * 100) if total else 0
            return {'total': total, 'signed': signed, 'pending': pending, 'pct': pct}
        except Exception:
            return None

    ppr   = _ppr_stats()
    lease = _lease_stats()
    lsig  = _lease_sig_stats()

    # ── Operational tasks per app ──────────────────────────────────────────────
    tasks = list(
        OperationalTask.objects
        .exclude(status='done')
        .select_related('assigned_to')
        .order_by('app', '-priority', 'created_at')
    )

    by_app = defaultdict(list)
    for t in tasks:
        by_app[t.app].append(t)

    APP_LABELS = dict(OperationalTask.APP_CHOICES)

    PRIORITY_ICON = {
        'critical': '🔴',
        'high':     '🟠',
        'normal':   '🟡',
        'low':      '⚪',
    }
    STATUS_CLASS = {
        'todo':        'status-todo',
        'in_progress': 'status-prog',
        'blocked':     'status-block',
        'done':        'status-done',
    }

    tasks_html = ''
    if by_app:
        for app_key, app_tasks in sorted(by_app.items()):
            total_t = len(app_tasks)
            avg_pct = round(sum(t.percent_complete for t in app_tasks) / total_t) if total_t else 0
            task_rows = ''
            for t in app_tasks:
                icon = PRIORITY_ICON.get(t.priority, '·')
                cls  = STATUS_CLASS.get(t.status, '')
                due  = f' &nbsp;<span style="color:#94a3b8">due {t.due_date.strftime("%b %d")}</span>' if t.due_date else ''
                task_rows += (
                    f'<div class="task-row">'
                    f'<div>{icon} <span class="{cls}">{t.title}</span>{due}</div>'
                    f'<div class="pct">{t.percent_complete}%</div>'
                    f'</div>'
                )
            fill_color = '#22c55e' if avg_pct >= 70 else '#f59e0b' if avg_pct >= 30 else '#ef4444'
            tasks_html += (
                f'<div class="app-section">'
                f'<div class="app-header">'
                f'<span>{APP_LABELS.get(app_key, app_key)}</span>'
                f'<span>{avg_pct}% avg &nbsp;·&nbsp; {total_t} open tasks</span>'
                f'</div>'
                f'<div class="progress-bar"><div class="progress-fill" style="width:{avg_pct}%;background:{fill_color};"></div></div>'
                f'{task_rows}'
                f'</div>'
            )
    else:
        tasks_html = '<div class="no-items">No open operational tasks. Add tasks in the Daily Reports dashboard.</div>'

    # ── Live stats summary ─────────────────────────────────────────────────────
    sig_row = ''
    if lsig:
        sig_row = (
            f'<tr>'
            f'<td style="padding:6px 10px;">Lease Signatures</td>'
            f'<td>{lsig["total"]}</td>'
            f'<td style="color:#059669;">{lsig["signed"]} signed</td>'
            f'<td style="color:#dc2626;">{lsig["pending"]} pending</td>'
            f'<td>{lsig["pct"]}%</td>'
            f'</tr>'
        )

    live_stats = f"""
<div class="section">
  <div class="section-title">📈 LIVE APP STATS</div>
  <div class="claim-card" style="padding:0;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <tr style="background:#f1f5f9;font-weight:bold;">
        <th style="padding:8px 10px;text-align:left;">App</th>
        <th style="padding:8px 10px;">Total</th>
        <th style="padding:8px 10px;">Complete</th>
        <th style="padding:8px 10px;">Pending</th>
        <th style="padding:8px 10px;">% Done</th>
      </tr>
      <tr>
        <td style="padding:6px 10px;font-weight:bold;">PPR Reports</td>
        <td style="text-align:center;">{ppr['total']}</td>
        <td style="text-align:center;color:#059669;">{ppr['complete']}</td>
        <td style="text-align:center;color:#dc2626;">{ppr['pending']} running · {ppr['unsigned_rooms']} unsigned rooms</td>
        <td style="text-align:center;">{ppr['pct']}%</td>
      </tr>
      <tr style="background:#f8fafc;">
        <td style="padding:6px 10px;font-weight:bold;">ALE Leases</td>
        <td style="text-align:center;">{lease['total']}</td>
        <td style="text-align:center;color:#059669;">{lease['signed']}</td>
        <td style="text-align:center;color:#dc2626;">{lease['pending']} awaiting sig · {lease['drafts']} drafts</td>
        <td style="text-align:center;">{lease['pct']}%</td>
      </tr>
      {sig_row}
    </table>
  </div>
</div>
"""

    html = f"""
<html><head>{_BASE}</head><body>
<div class="wrapper">
  <div class="header" style="background:#1e3a5f;">
    <h1>📊 WEEKLY DEEP OPERATIONS REPORT</h1>
    <div class="sub">Claimet App &nbsp;·&nbsp; {now_str}</div>
  </div>
  {live_stats}
  <div class="section">
    <div class="section-title">🗂 OPERATIONAL TASKS BY APP
      <span class="count">{len(tasks)} open</span>
    </div>
    <div style="padding:10px 0;">{tasks_html}</div>
  </div>
  <div class="footer">
    Automated weekly deep report from Claimet App.<br>
    Manage tasks at <em>claimetapp.com/daily-reports/tasks/</em>
  </div>
</div>
</body></html>
"""
    return html
