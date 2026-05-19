# Claimetapp — Water Mitigation Claims Management Platform

> Full-stack production SaaS for water mitigation contractors. Handles the entire claim lifecycle — from initial claim creation to AI-generated contents inventories, equipment verification, pack-out estimation, and multi-format document delivery — deployed on a production VPS serving real clients.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2-green)](https://djangoproject.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)](https://docker.com)
[![Celery](https://img.shields.io/badge/Celery-5.3-brightgreen)](https://docs.celeryq.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791)](https://postgresql.org)
[![Claude AI](https://img.shields.io/badge/Claude-Vision%20AI-orange)](https://anthropic.com)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Feature Modules](#feature-modules)
- [AI Pipelines](#ai-pipelines)
- [Background Task System](#background-task-system)
- [API Integrations](#api-integrations)
- [Document Generation](#document-generation)
- [Data Models](#data-models)
- [Infrastructure & Deployment](#infrastructure--deployment)
- [Security](#security)
- [Testing](#testing)
- [Local Development Setup](#local-development-setup)
- [Environment Variables](#environment-variables)
- [Architectural Decisions](#architectural-decisions)

---

## Overview

Claimetapp eliminates hours of manual data entry for water and fire mitigation contractors. A technician documents a damaged property in Encircle (field software), and this platform handles everything else:

| Workflow | What Claimetapp Automates |
|----------|--------------------------|
| Contents Inventory | AI analyzes Encircle room photos → generates full Schedule of Loss with replacement values, depreciation, ACV |
| Equipment Verification | Claude Vision compares job-site photos against reference documentation → FOUND/PARTIAL/NOT FOUND per line item |
| Pack-Out Estimation | AI categorizes room contents → calculates box counts by type (small/medium/dish-pack/wardrobe/XL) |
| Encircle Sync | Push claim structure, room entries, and 8000/9000-series line items directly via Encircle API |
| Document Delivery | Generate PDFs (ReportLab/WeasyPrint), Excel (openpyxl), thermal labels (ReportLab), and LibreOffice-populated templates |
| OneDrive Management | Auto-create claim folder hierarchies, sync templates, file browser backed by Microsoft Graph API |

**Scale:** 13 Django apps, 7 Docker services, 3 AI pipelines, 3 external API integrations, 4 document output formats. Deployed and serving real clients.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Internet (HTTPS)                            │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │
                          ┌───────────▼───────────┐
                          │         Nginx          │
                          │  SSL/TLS 1.2+          │
                          │  Static/media serving  │
                          │  Security headers      │
                          │  100MB upload limit    │
                          │  900s proxy timeout    │
                          └───────────┬───────────┘
                                      │
                ┌─────────────────────▼──────────────────────┐
                │               Gunicorn                       │
                │   gthread worker class                       │
                │   (cpu_count × 2) + 1  workers              │
                │   4 threads/worker · 900s timeout            │
                │           Django 4.2                         │
                └──┬──────────────────────────────┬───────────┘
                   │                              │
      ┌────────────▼──────────┐      ┌────────────▼──────────┐
      │    PostgreSQL 15       │      │       Redis 7          │
      │   (primary database)   │      │  (Celery broker +      │
      │   ACID transactions    │      │   result backend)      │
      │   JSONB for flex data  │      │   AOF persistence      │
      └───────────────────────┘      └────────────┬──────────┘
                                                   │
                  ┌────────────────────────────────┼────────────────┐
                  │                                │                │
       ┌──────────▼─────────┐        ┌─────────────▼──────┐  ┌─────▼────────────┐
       │   Celery Worker    │        │   Celery Beat       │  │  LibreOffice UNO │
       │  4 concurrent      │        │  DB-backed          │  │  Headless        │
       │  processes         │        │  scheduler          │  │  socket :2002    │
       │                    │        │                     │  │  Template pop.   │
       │  CPS AI analysis   │        │  Daily OneDrive     │  │  PDF conversion  │
       │  Equipment check   │        │  subscription       │  └──────────────────┘
       │  Folder creation   │        │  renewal            │
       │  Label generation  │        └────────────────────┘
       └────────────────────┘

External APIs:
  ┌─────────────────┐  ┌──────────────────────┐  ┌───────────────────────┐
  │  Encircle API   │  │  Anthropic Claude API │  │  Microsoft Graph API  │
  │  v1/v2 REST     │  │  Vision (Haiku/Sonnet)│  │  OAuth2 PKCE          │
  │  Claims/rooms   │  │  8,192 token output   │  │  OneDrive/SharePoint  │
  │  Media/webhooks │  │  Base64 image batch   │  │  Token auto-refresh   │
  └─────────────────┘  └──────────────────────┘  └───────────────────────┘
```

**Request flow for an AI task (CPS report):**

1. User POSTs to `/cps-report/api/start/` → Django validates, fires `process_cps_session_task.delay()`
2. Celery worker fetches all claim media from Encircle (single paginated request, shared across rooms)
3. For each room: filter images by label prefix → batch 20 images → send to Claude Vision → parse JSON → persist items to DB
4. Frontend polls `/api/cps-report/api/session/<id>/status/` every 3 seconds
5. On completion, user downloads PDF or Excel — generated on-demand from DB

---

## Tech Stack

### Backend

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Framework | Django | 4.2.16 | Monolith, 13 apps |
| App Server | Gunicorn | 23.0 | gthread, multi-worker |
| Database | PostgreSQL | 15 | Primary datastore |
| Task Queue | Celery | 5.3.4 | Distributed async |
| Message Broker | Redis | 7 | Celery transport + results |
| Beat Scheduler | django-celery-beat | — | DB-backed periodic tasks |
| Auth | django-allauth | — | Email-based, verification, password reset |
| ORM | Django ORM | — | No raw SQL; parameterized throughout |

### AI & Vision

| Component | Model | Max Tokens | Use Case |
|-----------|-------|-----------|----------|
| CPS Schedule of Loss | claude-haiku-4-5 | 8,192 | Batch room photo analysis |
| Equipment Checker | claude-sonnet-4-6 | 8,096 | Multi-doc verification |
| Sensor Renamer | claude-sonnet-4-6 | 300 | Single-image reading extraction |
| Box Calculator | claude-sonnet-4-6 | varies | Room categorization |

### Document Generation

| Format | Library | Use Case |
|--------|---------|----------|
| PDF (programmatic) | ReportLab 4.4.2 | Schedule of Loss, box/wall labels |
| PDF (HTML→PDF) | WeasyPrint 65.1 | Scope checklists |
| Excel | openpyxl 3.1.5 | SoL export, data reports |
| Complex docs | LibreOffice UNO (headless) | Template population, PDF conversion |
| Merge/split | pypdf | Label PDF assembly |

### Infrastructure

| Component | Technology | Notes |
|-----------|-----------|-------|
| Reverse proxy | Nginx (Alpine) | SSL termination, static caching, HSTS |
| Containerization | Docker + Compose | 7 services |
| Browser automation | Selenium 4.21 + Chrome | Encircle tasks lacking API coverage |
| Image processing | Pillow 11.3 | Upload handling, format conversion |
| Cryptography | cryptography (Fernet) | OAuth token encryption at rest |

---

## Project Structure

```
mitigation_app_src/
├── app/
│   ├── mitigation_app/          # Django core — settings, root urls, celery config
│   │   ├── settings.py
│   │   ├── urls.py              # Root URL conf; each app registers its own urls.py
│   │   └── celery.py            # Celery app, autodiscover_tasks
│   │
│   ├── dashboard/               # Home page (app grid), stats, helpers
│   ├── claims/                  # Claim CRUD, room manager, file browser, Encircle push
│   ├── docsAppR/                # Core shared models + legacy views
│   │   ├── models.py            # CustomUser, Client, Room, WorkType, Lease, SentEmail…
│   │   ├── encircle_client.py   # EncircleAPIClient, DataProcessor, ExcelExporter
│   │   ├── onedrive_utils.py    # Microsoft Graph OAuth2 helpers
│   │   ├── tasks.py             # Label, folder-creation, template tasks
│   │   └── tests/               # Model, view, form, integration tests
│   │
│   ├── cps_report/              # AI Schedule of Loss — models, views, tasks, AI analyzer
│   │   ├── models.py            # CPSReportSession, CPSReportRoom, CPSReportItem
│   │   ├── views.py             # Home, start, status polling, export, signing
│   │   ├── tasks.py             # process_cps_session_task (Celery)
│   │   └── ai_analyzer.py       # Claude Vision pipeline
│   │
│   ├── box_calculator/          # Pack-out estimation — AI + pure calculator engine
│   │   ├── models.py            # BoxCalcSession, BoxCalcRoom, BoxCalcItem
│   │   ├── views.py             # Home, client rooms API, AI analyze, save, report
│   │   └── calculator.py        # Pure Python calculator (IICRC S500 box rules)
│   │
│   ├── encircle/                # Encircle live sync — dashboard, webhooks, automation
│   │   └── views.py             # Claims API proxy, sync, webhooks, room entry generator
│   │
│   ├── equipment_checker/       # AI equipment verification (owns its views + tasks)
│   │   ├── views.py             # Upload, status, CSV export
│   │   └── tasks.py             # process_equipment_check_task (Claude Vision)
│   │
│   ├── sensor_renamer/          # AI sensor image naming (owns its views + tasks)
│   │   ├── views.py             # Upload, status, ZIP download, browse, correct
│   │   └── tasks.py             # process_sensor_images_task (Claude Vision)
│   │
│   ├── labels/                  # Thermal label PDF generation (box + wall)
│   ├── scope_checklist/         # Room-by-room scope of work checklist
│   ├── email_manager/           # Email send, schedule, open-tracking pixel
│   ├── lease_manager/           # Lease document tracking + activity feed
│   ├── readings/                # Moisture reading image browser + upload
│   └── automations/             # OneDrive automation tasks (folder creation, templates)
│
├── nginx/
│   ├── nginx.conf               # SSL, proxy, caching, security headers
│   └── certs/                   # SSL certificates (not in repo)
│
├── docker-compose.yml           # 7-service orchestration
├── Dockerfile                   # Python 3.11-slim + Chrome + LibreOffice + uno
├── requirements.txt
└── .env                         # Secrets (not in repo)
```

---

## Feature Modules

### 1. Claims Manager (`claims/` + `docsAppR/`)

The core app. Manages the full lifecycle of a water or fire damage insurance claim.

**Routes:**

| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/claims/` | List all claims; create via 3-step wizard |
| GET/POST | `/claims/<id>/` | Claim detail + edit |
| POST | `/claims/<id>/push-to-encircle/` | Push claim metadata to Encircle |
| POST | `/claims/<id>/push-rooms-to-encircle/` | Generate and push room entries (8000-series) |
| GET | `/claims/<id>/folder-structure/` | OneDrive/server file browser |
| POST | `/claims/<id>/upload/` | Upload files to claim folder |
| GET | `/claims/<id>/files/` | Claim file browser UI |

**Key models:** `Client` (250+ fields covering property, insurance, contractor, ALE info), `Room`, `WorkType`, `RoomWorkTypeValue`

**Background tasks:**
- `create_server_folder_structure_task` — creates the full folder hierarchy when a claim is opened
- `copy_templates_to_server_task` — syncs document templates from the shared library
- `push_claim_to_encircle_task` — syncs claim metadata to Encircle
- `push_rooms_to_encircle_task` — generates and pushes room entries with 8000/9000/10000/70000-series line items

---

### 2. CPS Schedule of Loss (`cps_report/`)

The platform's highest-value feature. An AI pipeline that turns Encircle room photos into a submission-ready contents inventory with replacement values, depreciation percentages, and ACV calculations.

**Routes:**

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/cps-report/` | Session list grouped by claim |
| POST | `/cps-report/api/start/` | Start analysis session (fires Celery task) |
| GET | `/cps-report/api/session/<id>/status/` | Poll room-by-room progress |
| GET/POST | `/cps-report/session/<id>/` | Review and edit AI-generated items inline |
| POST | `/cps-report/session/<id>/export/` | Export Excel (24-col, Encircle-format) |
| POST | `/cps-report/session/<id>/export-pdf/` | Export ReportLab PDF |
| GET | `/cps-report/sign/<token>/` | Public client signature page (no auth required) |
| POST | `/cps-report/api/import-excel/` | Re-import a previously exported Excel |

**AI pipeline design:**

```python
# Single media fetch for the entire claim — avoids 40s API calls per room
all_claim_media = fetch_all_claim_media(session.encircle_claim_id)

for room in paired_rooms:
    # Room pairing: 300-series (overview) ↔ 400-series (PPR) by numeric suffix
    urls = filter_room_images(all_claim_media, room.room_number)

    # 20 images per Claude request; inter-batch sleep for rate-limit headroom
    result = analyze_room_for_cps(
        room_name=source_label,
        room_number=room.room_number,
        prefetched_media=all_claim_media,
    )
    # Items persisted to DB in real time — frontend polls for live progress
    persist_items(session, room, result['items'])
```

**Claude response schema (per room):**
```json
{
  "items": [
    {
      "description": "55-inch LED Smart TV",
      "brand": "Samsung",
      "condition": "Good",
      "qty": 1,
      "purchase_price_each": 650,
      "replacement_value_each": 699,
      "age_years": 3,
      "depreciation_category": "Electronics",
      "depreciation_pct": 45
    }
  ],
  "confidence": "high",
  "room_summary": "Master bedroom with full furniture set, electronics, and personal items"
}
```

**Design decisions:**
- `8,192 token responses` — prevents JSON truncation on large rooms (50+ items)
- `Room pairing` — Encircle uses 300-series for overview photos and 400-series for PPR; the system pairs them by matching numeric suffixes (301 ↔ 401 = same physical room) and analyzes both photo sets together
- `Single media fetch` — one paginated API call fetches all claim media (can be 5,000+ items); filtered per room in-memory using label-prefix matching
- `Real-time polling` — Celery task updates room status as it processes; frontend polls every 3s so the user sees progress without WebSockets

---

### 3. Equipment Checker (`equipment_checker/`)

Verifies field work documentation against job site photos. Upload photos (and/or an Encircle room-photo PDF report) plus a list of line items; Claude returns FOUND/PARTIAL/NOT FOUND status with notes for each item.

**Routes:**

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/equipment-checker/` | Upload interface |
| POST | `/equipment-checker/upload/` | Dispatch Celery verification task |
| GET | `/equipment-checker/status/` | Poll Celery task |
| POST | `/equipment-checker/export-csv/` | Download results as CSV |
| GET | `/equipment-checker/guide/` | Printable user guide |

**Input formats supported:**
- Individual job site photos (JPG, PNG, WEBP, HEIC)
- Encircle room-photo PDF export (preferred — Claude gets room context)
- Both simultaneously

**Line item format:** `ROOM NAME | Description` or just `Description`

---

### 4. Box Calculator (`box_calculator/`)

Room-by-room pack-out estimation following IICRC S500 workflows. AI classifies visible items by category; the pure Python calculator engine converts categories to box counts using standardized industry rules.

**Calculator engine (no Django dependencies):**
```python
rooms = [
    Room('Living Room', items=(
        Item(ItemCategory.ELECTRONICS, quantity=3),
        Item(ItemCategory.SOFA, quantity=1),          # → XL wrap (no box)
        Item(ItemCategory.DRESSER, quantity=1, compartments=6),  # → 1 XL + 6 medium
    )),
]
report = calculate_job(rooms)
# report.totals: BoxTotals(small=0, medium=6, large=0, dish_pack=0, wardrobe=0, xl=2)
```

**Box types and sizes:**
| Box | Cubic Feet | Used For |
|-----|-----------|---------|
| Small | 1.5 cu ft | Books, tools, dense heavy items |
| Medium | 3.0 cu ft | Kitchen, electronics, general |
| Large | 4.5 cu ft | Linens, lampshades, light bulky |
| Dish Pack | 5.2 cu ft | China, fragile kitchenware |
| Wardrobe | 10.0 cu ft | Hanging clothes (0.5 box/item) |
| XL Wrap | — | Furniture (no box; pad-wrapped, inventoried) |

---

### 5. Encircle Integration (`encircle/`)

Live sync dashboard. Pulls the full claim portfolio from the Encircle API, compares with local data, handles real-time webhooks, and automates room entry generation via Selenium for operations the Encircle API doesn't support.

**Key routes:**

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/encircle/` | Portfolio dashboard |
| GET | `/encircle/api/claims/` | Paginated claim list (all data) |
| GET | `/encircle/api/claims/<id>/structures/<sid>/rooms/` | Room structure for a claim |
| POST | `/encircle/webhooks/` | Webhook receiver (no auth — Encircle-signed) |
| POST | `/encircle/api/automate/` | Selenium-based room automation |

**EncircleAPIClient capabilities:**
- Full pagination support (handles 5,000+ item media pools)
- Room CRUD operations (create, update, delete)
- Media download (in-memory ZIP)
- Webhook subscription management
- Portfolio-level Excel export with styling

---

### 6. Sensor Image Renamer (`sensor_renamer/`)

AI-powered instrument reading extraction and standardized file naming. Upload sensor images → Claude reads the instrument display → files are sorted into sub-folders named by reading type and value.

**Output folders:**
- `RH_T_GPP/` → `RH65.3_T22.1_GPP450.7.jpg`
- `T_RH_GPP/` → `T22.1_RH65.3_GPP450.7.jpg`
- `GPP_RH_T/` → `GPP450.7_RH65.3_T22.1.jpg`
- `MC/` → `MC19.5.jpg`
- `NA_Review/` → Unreadable images requiring manual correction

**Manual correction endpoint:** `POST /sensor-renamer/correct/<session_id>/` accepts corrected values and moves the file from `NA_Review/` to the correct sub-folder without re-running Claude.

---

### 7. Labels (`labels/`)

Generates thermal-printer-ready PDFs for box labeling and room orientation.

**Box labels (4×3 inch):**
- Room name (large) + claim name + sequential box number
- Batched per room; supports per-room count selection

**Wall labels (4×6 inch):**
- Room name + compass orientation diagram (W=1/W=2/W=3/W=4 arrows)
- Work type reference grid (100/200/300/400/500/600/700 series + LOS/TRAVEL/DAMAGED status)
- Color-coded: red for LOS/DAMAGED, blue for orientation arrows

**Email delivery:** sends PDFs directly to Georgia or Ohio field teams plus custom recipients.

---

### 8. Email Manager (`email_manager/`)

Tracks client email delivery with open-event logging.

- **Tracking pixel:** 1×1 transparent GIF at `/emails/track/<uuid>/` — logs open events with IP and user-agent without requiring browser JavaScript
- **Scheduled delivery:** Celery Beat executes scheduled emails; supports one-time and recurring (daily/weekly/monthly/custom) intervals
- **Open notification:** sends admin alert email on first open if `notify_on_open=True`

---

### 9. Lease Manager (`lease_manager/`)

ALE (Additional Living Expenses) lease document management.

- Tracks lease agreements against insurance claims
- Activity feed per lease (document uploads, status changes, notes)
- Pipeline stage tracking (application, approved, active, completed)
- Document attachment with version history

---

## AI Pipelines

All three AI pipelines follow the same pattern: upload → Celery task → Claude API → persist → poll.

```
User Upload
    │
    ▼
Django View          ← validates inputs, creates session dir
    │
    ▼
Celery Task          ← dispatched with .delay(), returns task_id immediately
    │
    ├── Load media (base64-encode)
    ├── Build message content array
    ├── Call Claude API (with retry + rate-limit backoff)
    ├── Parse structured JSON response
    └── Persist results to DB in real time
         │
         ▼
Frontend polling ← GET /api/.../status/ every 3s
         │
         ▼
User reviews + exports
```

**Rate limit handling:**
- `RateLimitError` → exponential backoff (`min(60, 2^attempt)` seconds)
- `APIError` → fixed 3s retry, up to 4 attempts
- Inter-batch sleep between image groups (CPS pipeline)
- SDK-level auto-retry on transient errors

---

## Background Task System

All long-running operations run as Celery tasks against a Redis broker. The web layer returns immediately with a `task_id`; the frontend polls for completion.

| Task | Module | Trigger | Est. Duration | Notes |
|------|--------|---------|--------------|-------|
| `process_cps_session_task` | `cps_report.tasks` | Session start | 2–15 min | AI per room; real-time DB updates |
| `process_equipment_check_task` | `equipment_checker.tasks` | Upload | 30–90s | PDF + images → Claude |
| `process_sensor_images_task` | `sensor_renamer.tasks` | Upload | 5–60s | Concurrent thread pool |
| `create_server_folder_structure_task` | `docsAppR.tasks` | New claim | ~5s | Creates full folder hierarchy |
| `copy_templates_to_server_task` | `docsAppR.tasks` | Claim open | ~10s | Syncs shared template library |
| `populate_excel_task` | `docsAppR.tasks` | Doc request | ~30s | LibreOffice UNO template fill |
| `push_claim_to_encircle_task` | `docsAppR.tasks` | Manual push | ~15s | Claim metadata → Encircle API |
| `push_rooms_to_encircle_task` | `docsAppR.tasks` | Room push | ~30s | 8000/9000-series entries |
| `generate_and_email_labels_task` | `docsAppR.tasks` | Label request | ~10s | PDF + email |
| `renew-onedrive-subscriptions` | `automations.tasks` | Daily (Beat) | ~5s | Graph API webhook renewal |

**Celery Beat periodic tasks** are stored in PostgreSQL via `django-celery-beat` — they survive container restarts and can be managed from the Django admin without code changes.

---

## API Integrations

### Encircle API (v1/v2)

Full REST client with pagination, retry, and data processing layers.

```python
api = EncircleAPIClient()
claims = api.get_all_claims()          # auto-paginates
rooms  = api.get_all_structure_rooms(claim_id, structure_id)
media  = api.get_claim_media_paginated(claim_id)   # handles 5,000+ items
api.create_room(claim_id, structure_id, room_data)
api.webhook_subscribe(url, events)
```

**Room entry generation** — the system generates structured room entries in Encircle's line-item format. Each room gets entries in multiple series:
- 8000-series: mitigation scopes (WTR MIT, LOS, DEMO, etc.)
- 9000-series: equipment placement
- 10000-series: supplemental line items
- 70000-series: contents

### Anthropic Claude API

Direct SDK integration via `anthropic` Python package.

```python
# CPS pipeline — up to 20 base64-encoded images per request
resp = client.messages.create(
    model='claude-haiku-4-5-20251001',
    max_tokens=8192,
    messages=[{
        'role': 'user',
        'content': [
            *[{'type': 'image', 'source': {'type': 'base64', ...}} for img in batch],
            {'type': 'text', 'text': ANALYSIS_PROMPT},
        ]
    }],
)
```

**Token budget:** 8,192 output tokens enforced on CPS tasks to prevent truncation mid-JSON on rooms with 50+ items.

### Microsoft Graph API (OAuth2 PKCE)

Secure OneDrive/SharePoint integration using PKCE flow (public client model for server-side).

- Token refresh handled transparently using stored encrypted refresh token
- Supports shared drive navigation (not just personal OneDrive)
- Auto-creates claim folder hierarchies on first access
- Webhook subscription renewal via Celery Beat (subscriptions expire every 3 days)

---

## Document Generation

### Schedule of Loss — PDF (ReportLab)

Programmatic layout. No templates — full control over every element.

```
Cover page:
  ├── Claimetapp branding
  ├── Insured name, claim number, date of loss
  └── Adjuster contact information

Per-room sections:
  ├── Colored room header band
  ├── Line items table (Description | Brand | Qty | RV | Dep% | ACV)
  └── Room subtotal

Summary page:
  ├── Total RCV
  ├── Total depreciation
  └── Total ACV
```

### Schedule of Loss — Excel (openpyxl)

24-column workbook matching Encircle's native export format for direct import compatibility:

`Room | Box | Location | Description | Brand | Disposition | Condition | QTY | Model# | Serial# | Retailer | Replacement Source | Purchase Price | Age | Replacement Value | Depreciation % | ACV | Notes`

### Wall & Box Labels — PDF (ReportLab)

Thermal-printer-specific layouts:
- **Box labels:** 4×3 inch, two-column (room name + sequential box number)
- **Wall labels:** 4×6 inch, includes compass orientation diagram + work-type reference grid

### LibreOffice UNO Document Population

A headless LibreOffice instance runs as a persistent service, accepting connections over a TCP socket (port 2002). The Django app connects via UNO Python bridge to populate Excel templates and convert to PDF — no subprocess spawn per request, no temp file race conditions.

```python
# Socket-based IPC — LibreOffice stays alive between requests
context = uno.getComponentContext()
resolver = context.ServiceManager.createInstanceWithContext(
    'com.sun.star.bridge.UnoUrlResolver', context
)
ctx = resolver.resolve(f'uno:socket,host={UNO_HOST},port={UNO_PORT};...')
```

---

## Data Models

### Core Models (`docsAppR`)

```python
class Client(models.Model):
    # 250+ fields covering every aspect of a water damage claim
    pOwner          = CharField      # Insured name
    claimNumber     = CharField      # Insurance claim number
    encircle_claim_id = CharField    # Encircle integration ID
    dateOfLoss      = DateField
    causeOfLoss     = CharField
    # Insurance fields: company, adjuster, policy number, contact info
    # ALE fields: tenants, hotel, lease dates, amounts
    # Contractor fields: company, rep, TIN
    # 50+ more fields...

class Room(models.Model):
    id         = UUIDField(primary_key=True)
    client     = ForeignKey(Client)
    room_name  = CharField
    sequence   = IntegerField        # Display order
    # Modification tracking, work type values

class WorkType(models.Model):
    work_type_id = IntegerField       # 100/200/300/400/500/600/700/800/900 series
    name         = CharField

class RoomWorkTypeValue(models.Model):
    room       = ForeignKey(Room)
    work_type  = ForeignKey(WorkType)
    value_type = CharField            # LOS / TRAVEL / DAMAGED
```

### CPS Report Models (`cps_report`)

```python
class CPSReportSession(models.Model):
    client           = ForeignKey(Client)
    encircle_claim_id = CharField
    status           = CharField      # pending / processing / complete / error
    celery_task_id   = CharField
    share_token      = UUIDField      # Public signing link (no auth required)

class CPSReportRoom(models.Model):
    session                    = ForeignKey(CPSReportSession)
    room_name                  = CharField
    room_number                = CharField           # e.g. '301'
    encircle_room_id           = CharField
    encircle_room_id_secondary = CharField           # Paired 400-series room
    status                     = CharField           # pending / processing / complete / error

class CPSReportItem(models.Model):
    room                 = ForeignKey(CPSReportRoom)
    description          = CharField
    brand                = CharField
    qty                  = PositiveIntegerField
    replacement_value_each = DecimalField
    depreciation_pct     = DecimalField
    ai_suggested         = BooleanField              # Distinguishes AI vs. manually added
    # Computed properties: replacement_value_total, depreciation_amount, acv_each, acv_total
```

---

## Infrastructure & Deployment

### Docker Compose Services

```yaml
services:
  web:              # Django + Gunicorn on :8080
  db:               # PostgreSQL 15 (volume: postgres_data)
  redis:            # Redis 7 Alpine (volume: redis_data; AOF persistence)
  celery:           # Celery worker (4 concurrent processes)
  celery-beat:      # Periodic scheduler (DB-backed via django-celery-beat)
  libreoffice-uno:  # Headless LibreOffice on TCP :2002
  nginx:            # Reverse proxy on :80/:443
```

### Nginx Configuration

```nginx
# Security headers
add_header X-Frame-Options SAMEORIGIN;
add_header X-Content-Type-Options nosniff;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";

# Timeouts for long-running AI tasks
proxy_read_timeout 900;
proxy_send_timeout 900;

# Static/media caching
location /static/ { expires 1y; add_header Cache-Control "public, immutable"; }
location /media/  { expires 1d; }

# Upload limit for claim media
client_max_body_size 100M;
```

### Gunicorn

```bash
gunicorn \
  --bind 0.0.0.0:8080 \
  --workers $(($(nproc) * 2 + 1)) \
  --threads 4 \
  --worker-class gthread \
  --timeout 900 \
  --worker-connections 1000 \
  mitigation_app.wsgi:application
```

`gthread` worker class enables concurrent request handling within each worker without full async — appropriate for this I/O-heavy workload (DB queries, API calls, file I/O) that also has CPU-bound steps (PDF generation, image encoding).

### Dockerfile

```dockerfile
FROM python:3.11-slim
# System deps: Chrome + ChromeDriver (Selenium), LibreOffice + python3-uno, psql client
RUN apt-get install -y \
    google-chrome-stable chromium-driver \
    libreoffice python3-uno \
    libpq-dev gcc
COPY requirements.txt .
RUN pip install -r requirements.txt
```

---

## Security

| Layer | Control |
|-------|---------|
| Transport | HTTPS enforced at Nginx; HTTP → HTTPS redirect; TLS 1.2+ minimum |
| Authentication | django-allauth — email-based, email verification, secure password reset |
| Authorization | `@login_required` on all views except tracking pixel and public signing pages |
| CSRF | Django CSRF middleware on all state-changing endpoints |
| SQL Injection | Django ORM throughout; no raw SQL |
| Secrets | All credentials in environment variables; never in source code |
| Token Storage | OAuth refresh tokens encrypted at rest using Fernet (symmetric encryption) |
| Session Cookies | `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True` |
| Headers | `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, HSTS |
| File Uploads | Extension validation before save; files stored outside web root |
| Webhook Auth | Encircle webhooks validated by request origin + payload signature |

---

## Testing

Each Django app has its own `tests/` package with focused, independently runnable test modules.

```
app/
├── docsAppR/tests/
│   ├── test_models.py        # DocumentCategory, GeneratedDocument, EmailSchedule, SentEmail
│   ├── test_views.py         # Email view, tracking pixel, document list API, schedule view
│   ├── test_forms.py         # EmailForm, EmailScheduleForm validation
│   └── test_integration.py  # End-to-end email send → open-event workflow
│
├── sensor_renamer/tests/
│   ├── test_tasks.py         # _parse_response, result_has_na, build_filenames, safe_dest
│   └── test_views.py         # Auth guards, upload, status polling, correct endpoint
│
├── equipment_checker/tests/
│   ├── test_tasks.py         # _parse_items, _parse_response, SUPPORTED_EXTS
│   └── test_views.py         # Auth guards, upload, status, CSV export
│
├── cps_report/tests/
│   ├── test_models.py        # Session CRUD, total_replacement_value, room pairing
│   └── test_views.py         # Home grouping, status polling, item edit/delete
│
├── box_calculator/tests/
│   ├── test_models.py        # Session/Room/Item CRUD, full calculator engine
│   └── test_views.py         # Home, client rooms API, save session
│
├── claims/tests/
│   └── test_views.py         # List, detail, room CRUD, 404 handling
│
├── labels/tests/
│   └── test_views.py         # Auth, GET/POST, helper functions (safe_filename, print_area)
│
├── encircle/tests/
│   └── test_views.py         # Dashboard (mocked API), webhooks accept unauthenticated POST
│
├── scope_checklist/tests/
│   └── test_views.py         # Page, rooms API, save checklist
│
├── email_manager/tests/
│   └── test_views.py         # List, send, tracking pixel, schedule create
│
├── lease_manager/tests/
│   └── test_views.py         # Dashboard, filters, 404
│
├── readings/tests/
│   └── test_views.py         # Browser, upload
│
└── dashboard/tests/
    └── test_views.py         # Home, app grid context, auth guard
```

**Run tests:**
```bash
# All tests
python manage.py test

# Single app
python manage.py test sensor_renamer.tests

# Single module
python manage.py test sensor_renamer.tests.test_tasks

# With coverage
coverage run manage.py test && coverage report -m
```

**Test philosophy:**
- **No mocking of the database** — tests use the real Django test database (SQLite in CI)
- **Mock external APIs** — Claude, Encircle, Microsoft Graph all mocked via `unittest.mock.patch`
- **Pure function coverage** — parser helpers, calculator engine, filename builders tested without any Django setup
- **Auth guards verified on every protected endpoint**
- **JSON contract testing** — API endpoints assert response shape, not just status codes

---

## Local Development Setup

### Prerequisites

- Docker Desktop (or Docker Engine + Compose V2)
- Python 3.11 (for running tests locally outside Docker)

### Quick Start

```bash
git clone <repo>
cd mitigation_app_src

# 1. Copy and fill in env file
cp .env.example .env
# Edit .env — see Environment Variables below

# 2. Build and start all services
docker compose up --build

# 3. Run migrations
docker compose exec web python manage.py migrate

# 4. Create superuser
docker compose exec web python manage.py createsuperuser

# 5. Load initial work types
docker compose exec web python manage.py init_work_types
```

**Access the app:** https://localhost (Nginx handles SSL; use a self-signed cert in dev)

### Running Tests Locally

```bash
cd app
pip install -r ../requirements.txt

# Set test database (SQLite in dev)
export DJANGO_SETTINGS_MODULE=mitigation_app.settings
export DATABASE_URL=sqlite:///test.db

python manage.py test --keepdb
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | Yes | Django cryptographic secret |
| `DEBUG` | Yes | `False` in production |
| `ALLOWED_HOSTS` | Yes | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | Yes | Full origins for CSRF |
| `DATABASE_URL` | Yes | `postgres://user:pass@db:5432/dbname` |
| `REDIS_URL` | Yes | `redis://redis:6379/0` |
| `ANTHROPIC_API_KEY` | Yes | Claude Vision API key |
| `GRAPH_CLIENT_ID` | Yes | Azure app registration client ID |
| `GRAPH_REFRESH_TOKEN` | Yes | Encrypted OneDrive refresh token |
| `EMAIL_HOST` | Yes | SMTP relay host (Gmail) |
| `EMAIL_HOST_USER` | Yes | SMTP username |
| `EMAIL_HOST_PASSWORD` | Yes | SMTP app password |
| `DEFAULT_FROM_EMAIL` | Yes | From address for outbound email |
| `UNO_HOST` | Yes | LibreOffice UNO service hostname |
| `UNO_PORT` | Yes | LibreOffice UNO service port (2002) |
| `SECURE_SSL_REDIRECT` | Prod | `True` in production |
| `SESSION_COOKIE_SECURE` | Prod | `True` in production |

---

## Architectural Decisions

### Why Django monolith over microservices?

A single Django project with 13 apps gives strong module separation while sharing models, auth, admin, and the ORM without the operational overhead of service discovery, inter-service auth, and distributed tracing. The 13 apps are logically independent but share the `Client` model as a hub — splitting into services would require replicating or calling across a service boundary for nearly every operation.

### Why Celery + Redis over Django Q or background threads?

Long-running AI tasks (2–15 minutes per CPS session) cannot block a web worker. Celery provides durable task queuing with result persistence, retry policies, progress reporting, and horizontal scaling — all features we actively use. Redis is already present as the Celery broker, so the result backend costs nothing extra.

### Why Gunicorn gthread instead of async (uvicorn/ASGI)?

This workload is I/O-heavy but not concurrency-heavy on a per-request basis — most requests are quick DB reads. Long-running AI work is offloaded to Celery, not handled in-process. The `gthread` worker class gives us multi-threaded request handling within each worker without the complexity of a full ASGI migration. If WebSocket support becomes necessary (replacing the polling pattern), an ASGI migration is the next step.

### Why LibreOffice UNO service instead of a paid document API?

LibreOffice runs headless in a persistent container and accepts document requests over a TCP socket. This eliminates per-conversion subprocess startup overhead, avoids third-party API costs, and gives full control over template population. The only tradeoff is container size (+1.5GB) and the complexity of the UNO socket bridge.

### Why polling instead of WebSockets for AI progress?

The polling interval (3 seconds) is sufficient for progress updates on 2–15 minute tasks. WebSockets would add infrastructure complexity (channel layer, connection management, reconnect logic) without meaningfully improving UX for this task duration. If we add sub-second operations, the polling approach gets revisited.

### Why sensor_renamer and equipment_checker own their views and tasks?

Originally, these apps' view and task implementations lived in `docsAppR/` with the app directories acting as thin re-export shims. This created an invisible dependency — reading `sensor_renamer/views.py` showed nothing; the real code was in `docsAppR/sensor_views.py`. Each app now owns its full implementation. The `docsAppR/` files are backward-compatibility shims for any legacy imports.

---

## Project Scale

| Metric | Value |
|--------|-------|
| Django apps | 13 |
| Docker services | 7 |
| AI pipelines | 3 (CPS, Equipment Check, Sensor Renaming) |
| External APIs | 3 (Encircle, Anthropic, Microsoft Graph) |
| Document output formats | 4 (ReportLab PDF, WeasyPrint PDF, openpyxl Excel, LibreOffice UNO) |
| Celery tasks | 10 (3 AI, 7 operational) |
| Background task system | Celery 5 + Redis 7 + django-celery-beat |
| Authentication | Email-based via django-allauth |
| Deployment | Production VPS, Docker Compose, Nginx SSL |

---

*Solo full-stack project — designed, built, and maintained for production use by water mitigation contractors. Every line of AI integration, infrastructure configuration, and business logic written and owned end-to-end.*
