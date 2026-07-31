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

def _section_ppr_signatures(config) -> tuple[str, int, int]:
    """Returns (html, total_items, urgent_count)."""
    from cps_report.models import CPSReportSession, CPSReportRoom
    esc = config.escalation_days

    # Sessions with at least one unsigned room
    sessions = (
        CPSReportSession.objects
        .exclude(status='error')
        .prefetch_related('rooms__items', 'client')
        .order_by('-updated_at')
    )
    # Filter to only sessions with any unsigned room
    sessions = [s for s in sessions if s.rooms.filter(signature_name='').exists()]

    if not sessions:
        return '<div class="no-items">✅ All PPR rooms are signed.</div>', 0, 0

    total_rooms = urgent = 0
    cards = []
    for session in sessions:
        rooms = list(session.rooms.all().order_by('order', 'room_number'))
        unsigned = [r for r in rooms if not r.signature_name]
        total_rooms += len(unsigned)

        days = _days_ago(session.updated_at)
        if days >= esc:
            urgent += len(unsigned)

        rows = []
        for room in rooms:
            if room.signature_name:
                rows.append(
                    f'<div class="item-row">'
                    f'<span class="tag-signed">✔</span>'
                    f'<span>{room.room_number} {room.room_name}</span>'
                    f'<span class="badge-ok">Signed — {room.signature_name}</span>'
                    f'</div>'
                )
            else:
                rows.append(
                    f'<div class="item-row">'
                    f'<span class="tag-unsigned">✗</span>'
                    f'<span><strong>{room.room_number} {room.room_name}</strong></span>'
                    f'<span class="badge-urgent">UNSIGNED</span>'
                    f'{_days_badge(days, esc)}'
                    f'</div>'
                )

        demand_html = ''
        if days >= esc:
            demand_html = (
                f'<div class="demand">⚠ DEMAND: This session has had unsigned rooms for '
                f'<strong>{days} days</strong>. Immediate signature collection required.</div>'
            )

        cards.append(
            f'<div class="claim-card">'
            f'<div class="claim-name">{session.client.pOwner or "—"}</div>'
            f'<div class="claim-sub">Claim #{session.client.claimNumber or "—"} &nbsp;·&nbsp; '
            f'PPR Run: {session.display_name} &nbsp;·&nbsp; Status: {session.status}</div>'
            f'{demand_html}'
            f'{"".join(rows)}'
            f'</div>'
        )

    html = ''.join(cards)
    return html, total_rooms, urgent


def _section_ppr_pricing(config) -> tuple[str, int, int]:
    """Sessions with rooms that have items priced at $0."""
    from cps_report.models import CPSReportSession
    esc = config.escalation_days

    sessions = (
        CPSReportSession.objects
        .filter(status='complete')
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
    """Leases in 'sent_for_signature' status with pending signer requests."""
    from docsAppR.models import Lease, LeaseSignatureRequest
    esc = config.escalation_days

    leases = (
        Lease.objects
        .exclude(status__in=['cancelled', 'completed', 'signed'])
        .filter(sent_for_signature_at__isnull=False)
        .select_related('client')
        .prefetch_related('signature_requests')
        .order_by('sent_for_signature_at')
    )

    if not leases.exists():
        return '<div class="no-items">✅ No leases awaiting signatures.</div>', 0, 0

    total = urgent = 0
    cards = []
    for lease in leases:
        reqs = list(lease.signature_requests.all())
        pending_reqs = [r for r in reqs if r.status == 'pending']
        total += len(pending_reqs)
        days = _days_ago(lease.sent_for_signature_at)
        if days >= esc:
            urgent += len(pending_reqs)

        rows = []
        for req in reqs:
            if req.status == 'signed':
                rows.append(
                    f'<div class="item-row">'
                    f'<span class="tag-signed">✔</span>'
                    f'<span>{req.get_signer_role_display()} — {req.signer_name}</span>'
                    f'<span class="badge-ok">Signed</span>'
                    f'</div>'
                )
            elif req.status == 'pending':
                rows.append(
                    f'<div class="item-row">'
                    f'<span class="tag-unsigned">✗</span>'
                    f'<span><strong>{req.get_signer_role_display()} — {req.signer_name}</strong> ({req.signer_email})</span>'
                    f'<span class="badge-urgent">PENDING</span>'
                    f'{_days_badge(days, esc)}'
                    f'</div>'
                )
            else:
                rows.append(
                    f'<div class="item-row">'
                    f'<span>·</span>'
                    f'<span>{req.get_signer_role_display()} — {req.signer_name}</span>'
                    f'<span class="badge-pending">{req.status.title()}</span>'
                    f'</div>'
                )

        demand_html = ''
        if days >= esc and pending_reqs:
            names = ', '.join(r.signer_name for r in pending_reqs)
            demand_html = (
                f'<div class="demand">⚠ DEMAND: Lease sent {days} days ago. '
                f'Still waiting on: <strong>{names}</strong>. Follow up immediately.</div>'
            )

        addr = ' '.join(filter(None, [
            lease.property_address,
            lease.property_city,
            lease.property_state,
        ]))
        cards.append(
            f'<div class="claim-card">'
            f'<div class="claim-name">{lease.client.pOwner if lease.client else "—"}</div>'
            f'<div class="claim-sub">'
            f'Property: {addr or "—"} &nbsp;·&nbsp; '
            f'Status: {_fmt_status(lease.status)} &nbsp;·&nbsp; '
            f'Sent: {lease.sent_for_signature_at.strftime("%b %d, %Y") if lease.sent_for_signature_at else "—"}'
            f'</div>'
            f'{demand_html}'
            f'{"".join(rows)}'
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
        return '<div class="no-items">No high priority items currently flagged.</div>', 0, 0

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

        cards.append(
            f'<div class="claim-card" style="border-left:3px solid #e11d48;">'
            f'<div class="claim-name">⚡ {item.client.pOwner or "—"}</div>'
            f'<div class="claim-sub">'
            f'Claim #{item.client.claimNumber or "—"} &nbsp;·&nbsp; {item.get_item_type_display()} &nbsp;·&nbsp; '
            f'Flagged {days}d ago &nbsp;·&nbsp; {sub_info}'
            f'</div>'
            f'{"<div style=\"font-size:12px;color:#0f172a;margin:4px 0;\">"+item.priority_note+"</div>" if item.priority_note else ""}'
            f'{"<div style=\"font-size:11px;color:#64748b;\">Needs: "+item.resolution_criteria+"</div>" if item.resolution_criteria else ""}'
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
        total    = CPSReportSession.objects.count()
        complete = CPSReportSession.objects.filter(status='complete').count()
        pending  = CPSReportSession.objects.filter(status__in=['pending', 'processing']).count()
        unsigned = CPSReportSession.objects.filter(rooms__signature_name='').distinct().count()
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
