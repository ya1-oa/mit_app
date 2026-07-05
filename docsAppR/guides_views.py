"""
Guides and instructions for all apps in the system.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def guides_home(request):
    """Main guides and instructions page."""
    guides = {
        'claims': {
            'icon': 'fas fa-folder-open',
            'color': '#3b82f6',
            'title': 'Claims Manager',
            'description': 'Create and manage insurance claims, organize files, track claim status.',
            'steps': [
                {
                    'title': 'Create a New Claim',
                    'details': [
                        'Click "New Claim" button on the Claims page',
                        'Enter property owner name, address, and claim details',
                        'Select claim type (MIT, CPS, or PPR) to enable document checklists',
                        'Add rooms and assign work types for each room',
                        'Save to create the claim and set up folder structure',
                    ]
                },
                {
                    'title': 'Upload Files to a Claim',
                    'details': [
                        'Go to the claim detail page',
                        'Click "Upload Files" in the Files tab',
                        'Drag and drop or select files to upload',
                        'Files are organized by room and automatically saved',
                        'Access uploaded files anytime from the claim page',
                    ]
                },
                {
                    'title': 'Track Claim Progress',
                    'details': [
                        'Check the Checklist tab to see required documents',
                        'Completion % shows progress toward full documentation',
                        'Green checkmarks = completed items, red = still needed',
                        'Add notes to checklist items for team communication',
                    ]
                },
            ]
        },
        'scope': {
            'icon': 'fas fa-clipboard-list',
            'color': '#10b981',
            'title': 'Scope Checklist',
            'description': 'Room-by-room scope checklists with PDF and email export.',
            'steps': [
                {
                    'title': 'Create a Room Scope Checklist',
                    'details': [
                        'From a claim, click "Create Scope Checklist"',
                        'Select the room you want to scope',
                        'Check boxes for work items present in the room',
                        'Add notes for each item if needed',
                        'Save the checklist',
                    ]
                },
                {
                    'title': 'Generate PDF Report',
                    'details': [
                        'Open the completed checklist',
                        'Click "Export to PDF"',
                        'Choose options: include photos, detailed items, signatures',
                        'PDF is generated and ready to download or email',
                    ]
                },
                {
                    'title': 'Email Scope to Customer',
                    'details': [
                        'From the checklist, click "Send to Customer"',
                        'The scope PDF will be attached to a new email',
                        'Select recipient(s) and add any message',
                        'Email is sent with tracking enabled',
                    ]
                },
            ]
        },
        'lease': {
            'icon': 'fas fa-file-contract',
            'color': '#8b5cf6',
            'title': 'Lease Manager',
            'description': 'Manage ALE leases, generate documents, track workflow status.',
            'steps': [
                {
                    'title': 'Create a New Lease',
                    'details': [
                        'Go to Lease Manager → Create Draft Lease',
                        'Select the claim/property owner',
                        'Fill in lessor (landlord) information',
                        'Enter property address and rental terms',
                        'Add real estate company and broker details',
                        'Save to create draft',
                    ]
                },
                {
                    'title': 'Pre-fill from ALE Data',
                    'details': [
                        'If ALE data exists on the claim, click "Import from ALE"',
                        'System auto-fills lessor, property, and rental info from claim data',
                        'Review and edit any fields as needed',
                        'Submit to populate the lease',
                    ]
                },
                {
                    'title': 'Track Lease Workflow',
                    'details': [
                        'Go to Claim Detail → "ALE / Leases" tab',
                        'See all leases for this claim with progress %',
                        'Check off workflow steps as they complete:',
                        '  • Draft Lease Created',
                        '  • Send for Signature',
                        '  • RE Company Signed',
                        '  • Tenant Signed',
                        '  • Landlord Signed',
                        '  • All Signatures Received',
                        'Add notes when completing each step',
                    ]
                },
                {
                    'title': 'Generate Demand Letter',
                    'details': [
                        'From a lease, click "Generate Demand Letter"',
                        'Fill in outstanding items (arrears, damages, etc.)',
                        'Set deadline for payment',
                        'System generates professional PDF with all claim details',
                        'PDF is ready to attach to email or send separately',
                    ]
                },
                {
                    'title': 'Send Lease Package',
                    'details': [
                        'Click "Send Package" on the lease',
                        'System auto-selects lease documents and key contacts',
                        'Add recipients (RE company, broker, lessee)',
                        'Include demand letter if needed',
                        'Set send time (now or schedule for later)',
                        'Email is sent with open/click tracking',
                    ]
                },
            ]
        },
        'email': {
            'icon': 'fas fa-envelope',
            'color': '#f59e0b',
            'title': 'Email Manager',
            'description': 'Send, schedule, and track emails with claim context and attachments.',
            'steps': [
                {
                    'title': 'Send a Quick Email',
                    'details': [
                        'Go to Email Manager → Compose Email',
                        'Enter recipients, subject, and message',
                        'Click "Send Now" to send immediately',
                        'Email is logged and tracking is enabled',
                    ]
                },
                {
                    'title': 'Send Claim-Aware Email',
                    'details': [
                        'Click "Select Claim" at top of compose form',
                        'Choose the claim - all contacts auto-populate below',
                        'Select specific contacts from the dropdown',
                        'Attachments from this claim appear ready to select',
                        'Compose message and send (or schedule)',
                    ]
                },
                {
                    'title': 'Attach Claim Files',
                    'details': [
                        'In compose form with claim selected:',
                        '  • Leases: all generated lease PDFs for this claim',
                        '  • Generated Docs: Excel files, invoices, reports',
                        '  • Documents: system-generated files',
                        'Check boxes for files to attach',
                        'Multiple files can be attached to one email',
                    ]
                },
                {
                    'title': 'Schedule Batch Emails',
                    'details': [
                        'Go to Email Manager → Schedule Batch',
                        'Create a batch name (e.g. "July Follow-ups")',
                        'Click calendar to pick send times',
                        'Add each email with recipients, subject, body',
                        'Configure follow-ups (optional):',
                        '  • Send after X days',
                        '  • Send if unopened after X days',
                        '  • Send automatically when opened',
                        'Emails send automatically at scheduled times',
                    ]
                },
                {
                    'title': 'Track Email Opens & Clicks',
                    'details': [
                        'Go to Email Manager → Sent History',
                        'See all sent emails with status (opened/unopened)',
                        'Click count shows how many links recipients clicked',
                        'Filter by claim, date range, or open status',
                        'Hover over email to see details',
                    ]
                },
            ]
        },
        'labels': {
            'icon': 'fas fa-tags',
            'color': '#ef4444',
            'title': 'Box Labels',
            'description': 'Generate printable box labels per room for any claim.',
            'steps': [
                {
                    'title': 'Generate Box Labels',
                    'details': [
                        'Go to Box Labels app',
                        'Select a claim and room',
                        'Enter number of boxes for that room',
                        'System generates labels with:',
                        '  • Claim number and property owner',
                        '  • Room name',
                        '  • Sequential box numbers (Box 1, Box 2, etc.)',
                        'Print labels directly or download as PDF',
                    ]
                },
                {
                    'title': 'Organize by Room',
                    'details': [
                        'Generate labels for each room separately',
                        'Use different colors or markers to distinguish rooms',
                        'Stick labels on boxes before packing contents',
                        'Makes inventory and storage tracking much easier',
                    ]
                },
            ]
        },
        'wall_labels': {
            'icon': 'fas fa-compass',
            'color': '#ec4899',
            'title': 'Wall Labels',
            'description': 'Create directional wall labels for equipment placement.',
            'steps': [
                {
                    'title': 'Create Wall Direction Labels',
                    'details': [
                        'Go to Wall Labels app',
                        'Select a claim and room',
                        'Choose directions: North, South, East, West, or Center',
                        'System generates printable labels with:',
                        '  • Room name',
                        '  • Direction indicator',
                        '  • Space for equipment notes',
                        'Print and post on walls to guide equipment placement',
                    ]
                },
            ]
        },
        'reading_browser': {
            'icon': 'fas fa-camera',
            'color': '#06b6d4',
            'title': 'Reading Browser',
            'description': 'Browse, sort, rename, and export moisture reading images.',
            'steps': [
                {
                    'title': 'Import Reading Images',
                    'details': [
                        'Go to Reading Browser',
                        'Click "Upload Images" to select moisture reading photos',
                        'Images are organized by date and location',
                        'System extracts reading values from image filenames',
                    ]
                },
                {
                    'title': 'Sort and Filter',
                    'details': [
                        'Filter by room, date range, or reading value',
                        'Sort by room, date, or reading (ascending/descending)',
                        'Use search to find specific readings',
                    ]
                },
                {
                    'title': 'Rename Images',
                    'details': [
                        'Click on an image to rename it',
                        'Standardize naming convention for your workflow',
                        'Include date, location, and reading value in name',
                    ]
                },
                {
                    'title': 'Export Report',
                    'details': [
                        'Select images to include in report',
                        'Click "Export to PDF"',
                        'PDF includes images, readings, and summary stats',
                        'Ready to attach to emails or claim file',
                    ]
                },
            ]
        },
        'claim_images': {
            'icon': 'fas fa-images',
            'color': '#64748b',
            'title': 'Claim Images',
            'description': 'Download and organize photo sets from Encircle claims.',
            'steps': [
                {
                    'title': 'Download Photos from Encircle',
                    'details': [
                        'Go to Claim Images app',
                        'Select a claim with Encircle integration',
                        'Click "Download from Encircle"',
                        'System fetches all claim photos',
                        'Photos are organized by room and date',
                    ]
                },
                {
                    'title': 'Organize Photos',
                    'details': [
                        'View photos organized by room',
                        'Rename photos for better organization',
                        'Group photos for specific purposes (overview, damage, etc.)',
                        'Add captions or notes to photos',
                    ]
                },
                {
                    'title': 'Export Sets',
                    'details': [
                        'Select specific photos to export',
                        'Bundle into organized PDF or ZIP file',
                        'Share with contractors, insurance, or customer',
                    ]
                },
            ]
        },
        'sensor_renamer': {
            'icon': 'fas fa-microscope',
            'color': '#84cc16',
            'title': 'Sensor Renamer (AI)',
            'description': 'AI-powered tool that reads sensor images and renames files automatically.',
            'steps': [
                {
                    'title': 'Upload Sensor Images',
                    'details': [
                        'Go to Sensor Renamer app',
                        'Upload photos of moisture sensor readings',
                        'AI analyzes each image to extract:',
                        '  • Sensor type (moisture, temperature, etc.)',
                        '  • Reading value (e.g. "28%")',
                        '  • Location/room (if visible)',
                        '  • Date/timestamp (if shown)',
                    ]
                },
                {
                    'title': 'Auto-Rename Files',
                    'details': [
                        'Review AI-detected values before applying',
                        'Click "Apply Renames" to rename all files',
                        'Files are renamed with standardized format:',
                        '  [Room]_[Sensor Type]_[Reading Value]_[Date].jpg',
                        'Saves hours of manual naming',
                    ]
                },
                {
                    'title': 'Verify Accuracy',
                    'details': [
                        'Spot-check a few renamed files',
                        'If AI misread something, edit names manually',
                        'Correction helps improve AI accuracy over time',
                    ]
                },
            ]
        },
        'equipment_checker': {
            'icon': 'fas fa-clipboard-check',
            'color': '#f97316',
            'title': 'Equipment Checker (AI)',
            'description': 'Verify equipment documentation photos using Claude Vision AI.',
            'steps': [
                {
                    'title': 'Upload Equipment Photos',
                    'details': [
                        'Go to Equipment Checker app',
                        'Upload photos of equipment on site',
                        'For each photo, AI analyzes:',
                        '  • Equipment type (dehumidifier, air mover, etc.)',
                        '  • Equipment condition (working, damaged, missing)',
                        '  • Visible brand/model information',
                        '  • Serial number (if visible)',
                        '  • Power status',
                    ]
                },
                {
                    'title': 'Verify Details',
                    'details': [
                        'Review AI findings for accuracy',
                        'Confirm equipment is documented correctly',
                        'Flag any missing or broken equipment',
                        'Export verification report',
                    ]
                },
                {
                    'title': 'Generate Report',
                    'details': [
                        'Create equipment inventory from verified photos',
                        'Report shows all equipment on site with status',
                        'Attach to claim for insurance documentation',
                    ]
                },
            ]
        },
        'cps_schedule': {
            'icon': 'fas fa-file-invoice-dollar',
            'color': '#059669',
            'title': 'CPS Schedule of Loss',
            'description': 'AI-powered contents pricing from Encircle room photos for pack-out claims.',
            'steps': [
                {
                    'title': 'Upload Room Photos',
                    'details': [
                        'Go to CPS Schedule of Loss app',
                        'Upload photos of each room showing contents',
                        'Include full room views and detail shots',
                        'AI analyzes photos to identify items',
                    ]
                },
                {
                    'title': 'AI Generates Pricing',
                    'details': [
                        'System uses computer vision to identify items',
                        'Cross-references with pricing database',
                        'Generates line-item breakdown with:',
                        '  • Item description',
                        '  • Quantity',
                        '  • Unit price',
                        '  • Total value',
                    ]
                },
                {
                    'title': 'Review & Adjust',
                    'details': [
                        'Review AI-generated items and prices',
                        'Edit quantities or values as needed',
                        'Add items AI missed',
                        'Remove duplicates or errors',
                    ]
                },
                {
                    'title': 'Export as Xactimate',
                    'details': [
                        'Export pricing schedule as Xactimate-compatible format',
                        'Import directly into Xactimate for invoicing',
                        'Saves significant time vs. manual item entry',
                    ]
                },
            ]
        },
        'encircle': {
            'icon': 'fas fa-circle-nodes',
            'color': '#0ea5e9',
            'title': 'Encircle Dashboard',
            'description': 'View all Encircle claims, sync with OneDrive, export reports.',
            'steps': [
                {
                    'title': 'Connect Encircle Account',
                    'details': [
                        'Go to Encircle Dashboard',
                        'Click "Connect Encircle" (if not already connected)',
                        'Authorize access to your Encircle account',
                        'All your Encircle claims appear in the dashboard',
                    ]
                },
                {
                    'title': 'View Claim List',
                    'details': [
                        'See all claims from Encircle with:',
                        '  • Claim number',
                        '  • Property address',
                        '  • Date created',
                        '  • Status (in progress, completed, archived)',
                        'Click on a claim to view details',
                    ]
                },
                {
                    'title': 'Sync with OneDrive',
                    'details': [
                        'Click "Sync to OneDrive" for a claim',
                        'All claim photos and documents are downloaded',
                        'Organized folder structure created automatically',
                        'Updates are synced on a schedule',
                    ]
                },
                {
                    'title': 'Export Report',
                    'details': [
                        'Select a claim and click "Generate Report"',
                        'Choose report type:',
                        '  • Summary (overview only)',
                        '  • Detailed (with photos)',
                        '  • Full (everything)',
                        'Report is generated as PDF',
                        'Download or email directly',
                    ]
                },
            ]
        },
        'push_rooms': {
            'icon': 'fas fa-upload',
            'color': '#7c3aed',
            'title': 'Push Rooms',
            'description': 'Push room entries directly to Encircle claims in bulk.',
            'steps': [
                {
                    'title': 'Prepare Room Data',
                    'details': [
                        'Go to Push Rooms app',
                        'Select claim to update in Encircle',
                        'Enter room information:',
                        '  • Room name',
                        '  • Work type (100, 200, 300, etc.)',
                        '  • LOS value (if applicable)',
                        '  • Notes',
                    ]
                },
                {
                    'title': 'Add Multiple Rooms',
                    'details': [
                        'Click "Add Room" to add more entries',
                        'Bulk add many rooms at once',
                        'Review all entries before pushing',
                    ]
                },
                {
                    'title': 'Push to Encircle',
                    'details': [
                        'Click "Push to Encircle" button',
                        'System uploads all room entries to the claim',
                        'Encircle is updated in real-time',
                        'Confirmation shows successful entries',
                    ]
                },
            ]
        },
        'copy_photos': {
            'icon': 'fas fa-copy',
            'color': '#6366f1',
            'title': 'Copy Photos',
            'description': 'Copy photos between rooms and claims inside Encircle.',
            'steps': [
                {
                    'title': 'Select Source Room',
                    'details': [
                        'Go to Copy Photos app',
                        'Select source claim and source room',
                        'View all photos in that room',
                    ]
                },
                {
                    'title': 'Choose Target',
                    'details': [
                        'Select target claim and target room(s)',
                        'Can copy to one room or multiple rooms',
                    ]
                },
                {
                    'title': 'Copy Photos',
                    'details': [
                        'Select specific photos to copy or select all',
                        'Click "Copy Selected Photos"',
                        'Confirm the copy operation',
                        'Photos are duplicated to target room(s)',
                        'Useful for similar rooms or backup documentation',
                    ]
                },
            ]
        },
        'contractor_hub': {
            'icon': 'fas fa-hard-hat',
            'color': '#7c3aed',
            'title': 'Contractor Bid Hub',
            'description': 'Build GC estimates, manage subcontractor bids, generate Xactimate-format invoices.',
            'steps': [
                {
                    'title': 'Create a New Estimate',
                    'details': [
                        'Go to Contractor Bid Hub → New Estimate',
                        'Select claim and general contractor',
                        'Enter scope of work and budget',
                        'System creates line-item structure',
                    ]
                },
                {
                    'title': 'Request Subcontractor Bids',
                    'details': [
                        'Click "Request Bids"',
                        'Select subcontractors to bid on the work',
                        'System emails bid request with scope details',
                        'Subs submit bids through secure form',
                    ]
                },
                {
                    'title': 'Review & Compare Bids',
                    'details': [
                        'See all submitted bids side-by-side',
                        'Compare pricing, scope, timeline',
                        'Accept or reject individual bids',
                        'Add comments or negotiate details',
                    ]
                },
                {
                    'title': 'Generate Invoice',
                    'details': [
                        'Build final invoice from accepted bids',
                        'Combine GC costs and selected sub bids',
                        'Add overhead, profit margin, taxes',
                        'Generate Xactimate-compatible invoice',
                        'Email to insurance or customer',
                    ]
                },
            ]
        },
        'tasks': {
            'icon': 'fas fa-tasks',
            'color': '#6366f1',
            'title': 'Task Board',
            'description': 'Kanban-style task manager for team to-dos and project tracking.',
            'steps': [
                {
                    'title': 'Create a New Task',
                    'details': [
                        'Click "New Task" button on the board',
                        'Fill in task details:',
                        '  • Title (required)',
                        '  • Description',
                        '  • Priority (low, medium, high, urgent)',
                        '  • Category (general, claim, lease, email, etc.)',
                        '  • Due date',
                        '  • Assign to team member',
                        '  • Link to claim or lease (optional)',
                        'Click "Create Task"',
                    ]
                },
                {
                    'title': 'Move Tasks Between Columns',
                    'details': [
                        'Drag tasks across the board:',
                        '  • To Do → In Progress → Review → Done',
                        'Each move updates task status instantly',
                        'Backlog column for future work',
                    ]
                },
                {
                    'title': 'Mark Task Complete',
                    'details': [
                        'When task is done, click "Done" button',
                        'Add completion notes (what you did)',
                        'For dev tasks: mark unit tests + beta test status',
                        'Assigner + admin notified of completion',
                        'Task moves to Done column with timestamp',
                    ]
                },
                {
                    'title': 'Track Team Progress',
                    'details': [
                        'Stat cards show open, overdue, urgent tasks',
                        'Filter by priority, category, or assignee',
                        'Toggle "Mine only" to see your tasks',
                        'Jump to specific tasks by clicking stat cards',
                    ]
                },
            ]
        },
        'email_compose': {
            'icon': 'fas fa-pen-to-square',
            'color': '#f59e0b',
            'title': 'Compose Email',
            'description': 'Send emails directly with claim context, attachments, and scheduling.',
            'steps': [
                {
                    'title': 'Send a Quick Email',
                    'details': [
                        'Go to Compose Email page',
                        'Enter recipients, subject, message',
                        'Click "Send Now" to send immediately',
                    ]
                },
                {
                    'title': 'Email with Claim Context',
                    'details': [
                        'Click "Select Claim" to choose a claim',
                        'All contacts for that claim appear automatically',
                        'Select which contacts to email',
                        'Attachments from claim (leases, docs, Excel) available',
                        'Compose and send',
                    ]
                },
                {
                    'title': 'Attach Files',
                    'details': [
                        'With claim selected, all attachable files appear:',
                        '  • Generated lease PDFs',
                        '  • Excel reports',
                        '  • System-generated documents',
                        'Check boxes to attach files',
                    ]
                },
                {
                    'title': 'Schedule for Later',
                    'details': [
                        'Click "Schedule Send" instead of "Send Now"',
                        'Pick date and time to send',
                        'Email sends automatically at scheduled time',
                        'Useful for batch follow-ups',
                    ]
                },
            ]
        },
        'activity_log': {
            'icon': 'fas fa-history',
            'color': '#0f172a',
            'title': 'Activity Log',
            'description': 'Full audit trail of every action across all apps.',
            'steps': [
                {
                    'title': 'View All Activity',
                    'details': [
                        'Go to Activity Log page',
                        'See every action in the system:',
                        '  • Emails sent (who, when, open status)',
                        '  • Leases created / updated',
                        '  • Demand letters generated',
                        '  • Documents uploaded',
                        '  • Tasks completed',
                        '  • User logins',
                        'Most recent activity listed first',
                    ]
                },
                {
                    'title': 'Filter Activity',
                    'details': [
                        'Filter by action type (email sent, lease created, etc.)',
                        'Search by user email',
                        'Filter by date range',
                        'Find activity for specific claim',
                    ]
                },
                {
                    'title': 'View Details',
                    'details': [
                        'Click on any activity entry for full details',
                        'See who did it, when, and what happened',
                        'Links to related claims, leases, or documents',
                        'Complete audit trail for compliance',
                    ]
                },
            ]
        },
        'dashboard': {
            'icon': 'fas fa-chart-bar',
            'color': '#475569',
            'title': 'Dashboard Stats',
            'description': 'Claims overview, statistics, and pipeline summary.',
            'steps': [
                {
                    'title': 'View Dashboard',
                    'details': [
                        'Go to Dashboard page',
                        'See high-level statistics:',
                        '  • Total claims',
                        '  • Active claims (in progress)',
                        '  • Completed claims',
                        '  • Total leases',
                        '  • Pending documents',
                    ]
                },
                {
                    'title': 'Pipeline Status',
                    'details': [
                        'Visual breakdown of claim statuses',
                        'See which claims need attention',
                        'Identify bottlenecks in your workflow',
                    ]
                },
                {
                    'title': 'Recent Activity',
                    'details': [
                        'See latest emails sent, documents uploaded, leases created',
                        'Quick links to recently updated claims',
                        'Spot check on team activity',
                    ]
                },
            ]
        },
    }

    context = {
        'guides': guides,
    }
    return render(request, 'account/guides.html', context)
