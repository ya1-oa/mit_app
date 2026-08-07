"""
python manage.py seed_modules

Idempotent seed command — creates all Claimet AppModules with accurate
status and representative DevTasks. Safe to re-run; uses get_or_create so
existing records are never overwritten.
"""
from django.core.management.base import BaseCommand
from dev_hub.models import AppModule, DevTask, TestCoverage


MODULES = [
    # (name, description, status, order, tasks)
    # tasks: [(title, task_type, status), ...]
    (
        'Core Platform',
        'Foundation app (docsAppR) — all shared models: Client, Lease, TaskItem, '
        'SentEmail, EmailBatch, AIUsageLog, Tenant, CustomUser, Document, and '
        'every cross-app data layer. Backbone of the entire platform.',
        'stable', 1,
        [
            ('Multi-tenant architecture', 'feature', 'done'),
            ('Custom user model (CustomUser)', 'feature', 'done'),
            ('Core Client (claim) record', 'feature', 'done'),
            ('Lease model + pipeline status', 'feature', 'done'),
            ('SentEmail open-tracking pixel', 'feature', 'done'),
            ('AIUsageLog cost tracking', 'feature', 'done'),
            ('Tenant invite system', 'feature', 'done'),
            ('Cross-app TaskItem model', 'feature', 'done'),
        ],
    ),
    (
        'Dashboard',
        'App landing page — grid of all Claimet modules with status tiles '
        'and quick navigation links.',
        'stable', 2,
        [
            ('App grid landing page', 'feature', 'done'),
            ('Quick-stats widgets', 'feature', 'done'),
        ],
    ),
    (
        'Claims Manager',
        'Central claim workspace — list, search, and detail view for every '
        'Client record. Filter by status, date of loss, and adjuster.',
        'stable', 3,
        [
            ('Claim list with filters', 'feature', 'done'),
            ('Claim detail / edit view', 'feature', 'done'),
            ('Date-of-loss and status filtering', 'feature', 'done'),
            ('Archived claims toggle', 'feature', 'done'),
        ],
    ),
    (
        'Scope Checklist',
        'Structured scope-of-work checklist for mitigation claims — tracks '
        'required documentation, room-by-room scope items, and sign-off status.',
        'stable', 4,
        [
            ('Scope checklist creation per claim', 'feature', 'done'),
            ('Room-by-room scope items', 'feature', 'done'),
            ('Checklist completion tracking', 'feature', 'done'),
        ],
    ),
    (
        'ALE Lease Manager',
        'Full ALE (Additional Living Expenses) lease workflow — create, edit, '
        'and pipeline-manage leases through draft → generated → sent → signed '
        '→ invoiced → completed. DocuSign-style multi-party signature collection '
        'with share links and per-signer status tracking.',
        'stable', 5,
        [
            ('Lease creation and editing', 'feature', 'done'),
            ('Multi-party signature workflow', 'feature', 'done'),
            ('Per-signer status tracking (LeaseSignatureRequest)', 'feature', 'done'),
            ('Public share link signing page', 'feature', 'done'),
            ('Pipeline status progression', 'feature', 'done'),
            ('Invoice creation from signed lease', 'feature', 'done'),
            ('Package + payment status tracking', 'feature', 'done'),
            ('Stale lease detection in daily reports', 'feature', 'done'),
        ],
    ),
    (
        'Email Manager',
        'Full-featured email system — compose, schedule, batch send, '
        'and track opens via pixel. Supports EmailBatch campaigns, '
        'ScheduledEmail queue, and per-SentEmail open tracking.',
        'stable', 6,
        [
            ('Email composition and sending', 'feature', 'done'),
            ('Open-tracking pixel (SentEmail)', 'feature', 'done'),
            ('Scheduled email queue', 'feature', 'done'),
            ('Batch campaign sending (EmailBatch)', 'feature', 'done'),
            ('Template library (EmailCampaign)', 'feature', 'done'),
            ('Attachment support (UploadedAttachment)', 'feature', 'done'),
        ],
    ),
    (
        'Labels',
        'Label printing and generation for claim packing jobs — box labels, '
        'wall labels, and evidence tags formatted for standard label sheets.',
        'stable', 7,
        [
            ('Box label generation', 'feature', 'done'),
            ('Wall label generation', 'feature', 'done'),
            ('Claim-linked label sets', 'feature', 'done'),
        ],
    ),
    (
        'Reading Browser',
        'Moisture / humidity reading browser — parses RH, Temperature, GPP, '
        'and MC values from ReadingImage filenames and presents them in a '
        'filterable, sortable data view per claim.',
        'stable', 8,
        [
            ('Reading image upload and parse', 'feature', 'done'),
            ('RH / Temp / GPP / MC extraction', 'feature', 'done'),
            ('Per-claim reading history', 'feature', 'done'),
        ],
    ),
    (
        'AI Sensor Renamer',
        'AI-assisted drying equipment sensor renaming tool — uses Claude '
        'Vision to read sensor displays in field photos and auto-generate '
        'standardized sensor labels.',
        'beta', 9,
        [
            ('Photo upload and Claude Vision analysis', 'feature', 'done'),
            ('Sensor label auto-generation', 'feature', 'done'),
            ('Rename export / copy workflow', 'feature', 'done'),
            ('Batch rename for multi-sensor jobs', 'feature', 'todo'),
        ],
    ),
    (
        'Equipment Checker',
        'Mitigation equipment tracking — check-in / check-out equipment '
        'per claim with condition notes and deployment history.',
        'beta', 10,
        [
            ('Equipment inventory list', 'feature', 'done'),
            ('Check-in / check-out workflow', 'feature', 'done'),
            ('Per-claim deployment history', 'feature', 'done'),
            ('Equipment condition reporting', 'feature', 'todo'),
        ],
    ),
    (
        'Claim Images',
        'Image upload and management per claim — supports bulk upload, '
        'categorization, and thumbnail browsing for insurance documentation.',
        'beta', 11,
        [
            ('Bulk image upload per claim', 'feature', 'done'),
            ('Image categorization / tagging', 'feature', 'done'),
            ('Thumbnail grid browser', 'feature', 'done'),
            ('Download selected images as zip', 'feature', 'todo'),
        ],
    ),
    (
        'Encircle Integration',
        'Encircle field-management platform sync — fetches rooms, photos, '
        'and claim data via the Encircle API; tracks sync status via '
        'EncircleSyncLog; supports manual and webhook-triggered syncing.',
        'stable', 12,
        [
            ('Encircle API client', 'feature', 'done'),
            ('Room and photo sync', 'feature', 'done'),
            ('Webhook integration', 'feature', 'done'),
            ('EncircleSyncLog dashboard', 'feature', 'done'),
            ('Manual sync trigger', 'feature', 'done'),
        ],
    ),
    (
        'Box Count Calculator',
        'Two-system box estimation: (1) manual BoxCalcSession/Room/Item '
        'with category-based volume calculator; (2) AI-powered BoxCalcCPSSession '
        'using Claude Vision on Encircle room photos to estimate 12 box types. '
        'Exports finished reports as PDF and Excel blobs stored in the DB.',
        'beta', 13,
        [
            ('Manual category-based calculator', 'feature', 'done'),
            ('AI room photo box estimation (Claude Vision)', 'feature', 'done'),
            ('12-box-type classification', 'feature', 'done'),
            ('PDF export of box count report', 'feature', 'done'),
            ('Excel export of box count report', 'feature', 'done'),
            ('PPR integration (box count → contractor bid)', 'feature', 'done'),
        ],
    ),
    (
        'PPR / Schedule of Loss',
        'AI-powered Personal Property Report generator — pulls Encircle room '
        'photos, identifies items via Claude Vision, fetches live replacement '
        'prices via Google Shopping, and generates signed Excel/PDF reports '
        'with per-room or per-session signature collection.',
        'beta', 14,
        [
            ('Encircle room + photo pull', 'feature', 'done'),
            ('Claude Vision item identification (CPSReportRoom)', 'feature', 'done'),
            ('Live pricing via Serper/Google Shopping', 'feature', 'done'),
            ('Schedule of Loss Excel export', 'feature', 'done'),
            ('Schedule of Loss PDF export', 'feature', 'done'),
            ('Evaluation Report Excel (per-item AI notes)', 'feature', 'done'),
            ('Per-session and per-room signature workflow', 'feature', 'done'),
            ('Public share link (sign_session / sign_room_direct)', 'feature', 'done'),
            ('Pricing audit view', 'feature', 'done'),
            ('Session archive and re-run', 'feature', 'done'),
            ('AI photo audit report (item-level photo proof)', 'feature', 'in_progress'),
            ('Duplicate item + image checker', 'feature', 'in_progress'),
            ('Room-level re-analysis without full re-run', 'feature', 'todo'),
        ],
    ),
    (
        'Contractor Bid Hub',
        'GC estimate builder using an Xactimate-style line-item structure — '
        'Contractor registry, RateItem library seeded from price-list imports, '
        'GCEstimate with 8 fixed sections and templated line items. Integrates '
        'box counts to auto-compute quantities.',
        'beta', 15,
        [
            ('Contractor registry', 'feature', 'done'),
            ('Xactimate RateItem library', 'feature', 'done'),
            ('Price-list import command', 'feature', 'done'),
            ('GCEstimate with 8 sections', 'feature', 'done'),
            ('LineItemTemplate auto-quantity from box counts', 'feature', 'done'),
            ('Estimate PDF export', 'feature', 'done'),
            ('AR tracking integration', 'feature', 'done'),
        ],
    ),
    (
        'Dev Hub',
        'Internal project management hub — tracks all platform sub-apps as '
        'AppModule records with DevTask items, TestCoverage, and automated '
        'weekly progress emails. Includes editable WeeklyReport (Mon–Fri log '
        'with PDF export) and Daily Ops status panel.',
        'in_dev', 16,
        [
            ('AppModule + DevTask system', 'feature', 'done'),
            ('Dashboard with live module cards', 'feature', 'done'),
            ('Inline task toggle and quick-add', 'feature', 'done'),
            ('Weekly progress report (automated + ad-hoc)', 'feature', 'done'),
            ('WeeklyReport editor and PDF export', 'feature', 'done'),
            ('AI Resources cost dashboard', 'feature', 'done'),
            ('Daily Ops status panel in dashboard', 'feature', 'done'),
            ('Daily Reports integration links', 'feature', 'done'),
            ('Seed command for all Claimet apps', 'feature', 'done'),
            ('TaskBoard ↔ AppModule link (board_tasks count in %)', 'feature', 'in_progress'),
            ('Test coverage tracking (TestCoverage model)', 'feature', 'done'),
        ],
    ),
    (
        'Task Manager',
        'Kanban task board using docsAppR.TaskItem — backlog / todo / '
        'in_progress / review / done / cancelled columns. Tasks link to '
        'claims or leases. Development tasks include code-audit fields '
        '(unit_tests_passed, beta_tested). Assignment and completion emails.',
        'beta', 17,
        [
            ('Kanban board (5 visible columns)', 'feature', 'done'),
            ('Task creation with assignment email', 'feature', 'done'),
            ('Task status column-move', 'feature', 'done'),
            ('Task complete flow with completion notes', 'feature', 'done'),
            ('Development task audit fields (unit tests, beta tested)', 'feature', 'done'),
            ('Claim and lease linking', 'feature', 'done'),
            ('Filter by category, priority, assignee', 'feature', 'done'),
            ('Link TaskItems to Dev Hub AppModule', 'feature', 'in_progress'),
        ],
    ),
    (
        'Accounts Receivable',
        'AR communication activity log for contractor invoices — tracks '
        'CommunicationActivity entries (email sent, manual note, reply, status '
        'change, follow-up) and reusable AREmailTemplate records per category. '
        'Integrates with Email Manager Celery scheduling for automated follow-ups.',
        'beta', 18,
        [
            ('CommunicationActivity log per estimate', 'feature', 'done'),
            ('AREmailTemplate library (initial, 30d, 60d, demand)', 'feature', 'done'),
            ('Automated follow-up Celery scheduling', 'feature', 'done'),
            ('AR board with aging view', 'feature', 'done'),
            ('Contractor invoice status tracking', 'feature', 'done'),
        ],
    ),
    (
        'MIT Day 3 Audit',
        'Automated MIT Day 3 equipment audit pipeline — extracts floor plan '
        'dimensions from Encircle, writes them into each client\'s existing '
        '82-MIT workbook (found via ClaimFile record or Templates folder), '
        'recalculates equipment quantities via LibreOffice, runs AI photo '
        'review, and generates PDF reports. Tracks Air Movers, DHM, AFD, '
        'HYDROXYL, BARRZ, BARRP, CCDU, WCDU, and all specialty equipment.',
        'in_dev', 19,
        [
            ('MITDay3Audit + MITDay3Config models', 'feature', 'done'),
            ('MITRoomDimension model with approval workflow', 'feature', 'done'),
            ('MITEquipmentItem model (per-audit device list)', 'feature', 'done'),
            ('MITReferencePhoto model (stabilization photos)', 'feature', 'done'),
            ('MITReport model (PDF output with download token)', 'feature', 'done'),
            ('find_and_copy_client_workbook() — per-client 82-MIT lookup', 'feature', 'done'),
            ('write_dimensions() — jobinfo(2) row 53 cols C/E/F/G', 'feature', 'done'),
            ('LibreOffice UNO recalc (port 2002) + subprocess fallback', 'feature', 'done'),
            ('read_total_equipment() — 3-pass TOTAL-EQPT + MIT-EQPT reads', 'feature', 'done'),
            ('HYDROXYL tracked from MIT-EQPT!C12 (DODHY, separate device)', 'feature', 'done'),
            ('Equipment categorization + stabilization photo flags', 'feature', 'done'),
            ('Celery task chain (dims → workbook → recalc → photos → PDF)', 'feature', 'done'),
            ('Dashboard — audit cards with status, equipment count, reports', 'feature', 'done'),
            ('Audit detail — dimension approval, equipment list, photo review', 'feature', 'done'),
            ('Config page — per-client workbook lookup explanation, cell map', 'feature', 'done'),
            ('Confirm LibreOffice installed in Docker container', 'test', 'todo'),
            ('Run git pull + migrate 0006 on server', 'secretarial', 'todo'),
            ('Full pipeline end-to-end test on a real claim', 'test', 'todo'),
            ('Encircle dimension extraction integration', 'feature', 'in_progress'),
            ('AI photo review (stabilization photo analysis)', 'feature', 'in_progress'),
            ('PDF report generation (WeasyPrint)', 'feature', 'in_progress'),
        ],
    ),
    (
        'Daily Reports System',
        'Two automated report types via Celery Beat: (1) daily high-priority '
        'report flagging specific items (PPR sessions, leases, general) until '
        'auto-resolved; (2) weekly deep operations report aggregating '
        'OperationalTask records across all apps. Includes in-app dashboard, '
        'config page, and task board.',
        'alpha', 19,
        [
            ('DailyReportConfig + HighPriorityItem models', 'feature', 'done'),
            ('OperationalTask model with per-app tracking', 'feature', 'done'),
            ('Daily high-priority email builder', 'feature', 'done'),
            ('Weekly deep report email builder', 'feature', 'done'),
            ('Celery Beat schedule (daily 7AM + weekly Mon 8:10AM)', 'feature', 'done'),
            ('In-app dashboard (high priority + report log)', 'feature', 'done'),
            ('Configuration page (recipients, sections, escalation)', 'feature', 'done'),
            ('Operational tasks board (% per app)', 'feature', 'done'),
            ('Dev Hub integration panel', 'feature', 'done'),
            ('Run database migrations on server', 'secretarial', 'todo'),
            ('Test first scheduled send end-to-end', 'test', 'todo'),
        ],
    ),
]


class Command(BaseCommand):
    help = 'Seed Dev Hub with all Claimet AppModules and representative tasks.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--overwrite-tasks',
            action='store_true',
            help='Delete existing DevTasks before seeding (default: skip if tasks exist)',
        )

    def handle(self, *args, **options):
        overwrite = options['overwrite_tasks']
        created_modules = 0
        created_tasks = 0

        for name, description, status, order, tasks in MODULES:
            module, created = AppModule.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'status':      status,
                    'order':       order,
                },
            )
            if created:
                created_modules += 1
                self.stdout.write(f'  + Module: {name}')
            else:
                # Update description and status if they're still defaults
                updated = False
                if not module.description:
                    module.description = description
                    updated = True
                if updated:
                    module.save(update_fields=['description'])
                self.stdout.write(f'  ~ Module exists: {name}')

            # Seed tasks
            existing_count = module.tasks.count()
            if existing_count > 0 and not overwrite:
                self.stdout.write(
                    f'    Skipping tasks ({existing_count} already exist). '
                    f'Use --overwrite-tasks to replace.'
                )
                continue

            if overwrite and existing_count:
                module.tasks.all().delete()
                self.stdout.write(f'    Deleted {existing_count} existing tasks')

            for i, (title, task_type, task_status) in enumerate(tasks):
                DevTask.objects.create(
                    module=module,
                    title=title,
                    task_type=task_type,
                    status=task_status,
                    order=i,
                )
                created_tasks += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone. Created {created_modules} new modules, {created_tasks} new tasks.'
            )
        )
