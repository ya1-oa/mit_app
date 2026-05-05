# Claimetapp — Home Mitigation Claims Management Platform

A full-stack, production-deployed SaaS platform for mitigation contractors and insurance claim professionals. Built to automate the most time-consuming parts of the claims workflow: claim creation, room documentation, contents scheduling, equipment verification, document generation, and Encircle integration — all from a single web application.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [AI Integration](#ai-integration)
- [Feature Modules](#feature-modules)
- [Infrastructure & Deployment](#infrastructure--deployment)
- [API Integrations](#api-integrations)
- [Document Generation](#document-generation)
- [Background Task System](#background-task-system)
- [Security](#security)

---

## Overview

Claimetapp eliminates hours of manual data entry for mitigation contractors. A technician walks through a fire- or water-damaged home, takes photos in Encircle, and the platform handles everything else:

Currently Implementing fully custom picture taking implementation removed ALL need for third party industry software.

- Generates a full **Contents Personal Property Schedule (CPS)** with AI-estimated replacement values
- Produces professional **Schedule of Loss PDFs and Excel exports** ready to submit to insurance carriers
- Verifies **equipment documentation** against job site photos
- Estimates **pack-out box requirements** per room
- Syncs claim structure and room entries **directly to Encircle** via API
- Manages the entire claim **document lifecycle on OneDrive/SharePoint**

The system is fully containerized, runs on a production VPS, and handles real paying clients.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Internet                                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTPS
                    ┌───────────▼───────────┐
                    │      Nginx            │
                    │  (SSL, proxy, cache)  │
                    └───────────┬───────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │            Gunicorn                  │
              │     (multi-worker, gthread)          │
              │         Django 4.2                   │
              └──┬────────────────────────┬─────────┘
                 │                        │
    ┌────────────▼────────┐   ┌──────────▼──────────┐
    │     PostgreSQL 15   │   │      Redis 7         │
    │     (primary DB)    │   │  (Celery broker)     │
    └─────────────────────┘   └──────────┬──────────┘
                                         │
              ┌──────────────────────────┼──────────────┐
              │                          │              │
   ┌──────────▼──────┐      ┌────────────▼──────┐  ┌───▼──────────┐
   │  Celery Worker  │      │  Celery Beat       │  │  LibreOffice │
   │  (4 concurrent) │      │  (scheduled jobs)  │  │  UNO Service │
   └─────────────────┘      └───────────────────┘  └──────────────┘
```

**Seven Docker containers** orchestrated via Compose, each with a single responsibility. Nginx terminates SSL and serves static/media files directly, keeping Django free for application logic.

---

## Tech Stack

### Backend
| Layer | Technology |
|-------|-----------|
| Framework | Django 4.2.16 |
| App Server | Gunicorn 23.0 (gthread, multi-worker) |
| Database | PostgreSQL 15 |
| Task Queue | Celery 5.3.4 |
| Message Broker | Redis 7 |
| Scheduled Tasks | django-celery-beat (DB scheduler) |
| Authentication | django-allauth (email-based, verification, password reset) |

### AI & Machine Learning
| Component | Technology |
|-----------|-----------|
| Vision AI | Anthropic Claude (claude-haiku-4-5-20251001) |
| Document AI | Claude with base64-encoded image batches |
| Use Cases | Schedule of Loss, box estimation, equipment verification |

### Document Generation
| Format | Library |
|--------|---------|
| PDF (reports) | ReportLab 4.4.2 (programmatic layout) |
| PDF (HTML) | WeasyPrint 65.1, xhtml2pdf |
| Excel | openpyxl 3.1.5 |
| Complex Docs | LibreOffice UNO (headless, socket-based) |
| SVG | svglib |

### Infrastructure
| Component | Technology |
|-----------|-----------|
| Reverse Proxy | Nginx (SSL/TLS 1.2+, security headers, 100MB uploads) |
| Containerization | Docker + Docker Compose |
| Browser Automation | Selenium 4.21 + Headless Chrome |
| Image Processing | Pillow 11.3 |

### External APIs
- **Encircle** — Water mitigation claims platform (REST v1/v2)
- **Anthropic** — Claude Vision API
- **Microsoft Graph** — OneDrive/SharePoint document management (OAuth2 PKCE)

---

## AI Integration

This is where the platform's core value is delivered. Three distinct AI-powered pipelines, each solving a real problem in the claims workflow.

### 1. CPS Schedule of Loss Generator

The most complex pipeline. A Celery task fetches all claim media from Encircle (~5,000+ items for large claims), filters images per room by label matching, downloads them, and sends them to Claude Vision in batches of 20.

```python
# Each room: fetch → filter → batch → analyze → persist
all_claim_media = fetch_all_claim_media(session.encircle_claim_id)

for room in rooms:
    urls = filter_room_images(all_claim_media, room.room_number)
    result = analyze_room_for_cps(
        room_name=source_label,
        room_number=room.room_number,
        prefetched_media=all_claim_media,
    )
```

Claude returns structured JSON per room:
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

The session processes rooms sequentially (Celery task), persisting items to the DB in real time so the frontend can poll for progress. When complete, the user downloads a submission-ready PDF or Excel.

**Design decisions:**
- Claim media fetched **once per session** (single API call, shared across all rooms) — avoids redundant 40-second fetches
- **Label-prefix matching** to correctly isolate one room's photos from a 5,000-item media pool
- **8,192 token responses** to prevent JSON truncation on large rooms
- **Batching** with inter-batch sleep to respect API rate limits

### 2. Box Calculator (Pack-Out Estimation)

Analyzes room photos and returns categorized item lists with quantity and compartment estimates — used to pre-calculate box and packing material needs before a pack-out begins.

```python
# Categories: books, fragile_kitchen, hanging_clothes, dresser, electronics, ...
result = analyze_room_with_ai(room_name, encircle_claim_id, image_urls)
```

### 3. Equipment Checker

Verifies field work against reference documentation. Claude receives a job site photo and a reference equipment list PDF, then returns a structured verification result — confirming whether documented work matches what's visible in the photos. Used to catch billing gaps before submitting to insurance.

---

## Feature Modules

### Claims Management (`docsAppR`)
The core app. Manages the full claim lifecycle:
- Create/edit claims with client, property, and insurance details
- Generate and push room entries to Encircle via API
- File browser backed by OneDrive/SharePoint (navigate, upload, download, template sync)
- Email tracking with open event logging
- Claim duplication and room migration utilities

### CPS Report (`cps_report`)
End-to-end Schedule of Loss generation:
1. User selects a claim and starts a session
2. System fetches 300s/400s CPS rooms from Encircle and pairs them by numeric suffix (301↔401 = same physical room)
3. Celery task processes all rooms via Claude Vision
4. Frontend polls progress in real time
5. User reviews and edits AI-generated items inline
6. Export to PDF (ReportLab) or Excel (openpyxl)

**Room pairing logic:** Encircle organizes photos by series (300s = overview, 400s = PPR). The system automatically identifies paired rooms by matching numeric suffixes and analyzes both photo sets together, combining items into a single line item list per room.

### Equipment Checker (`equipment_checker`)
Upload job site photos, select reference documentation, get a room-by-room verification report. Outputs a color-coded PDF showing FOUND/PARTIAL/NOT FOUND status for each work item.

### Box Calculator (`box_calculator`)
Room-by-room pack-out estimation. AI classifies every visible item by packing category, estimates quantities, and calculates box and material requirements. Exportable to Excel.

### Encircle Dashboard (`encircle`)
Live sync dashboard. Pulls claim portfolio, room structures, and readings from the Encircle API. Includes webhook handling for real-time updates, room automation via Selenium, and portfolio-level analytics.

### Document Management (`claims`, `docsAppR`)
OneDrive-backed file management with claim-scoped folder structures. Automatically creates the folder hierarchy when a claim is opened, syncs templates from a shared library, and presents a full file browser UI in the app.

### Scope Checklist (`scope_checklist`)
Room-by-room scope of work checklist. Generates a PDF report of all checklist items per room and delivers it by email.

### Labels (`labels`)
Generates barcode/QR label PDFs for boxes and walls. Auto-emailable.

### Lease Manager (`lease_manager`)
Lease document management with activity tracking.

### Sensor Renamer (`sensor_renamer`)
AI-assisted sensor image renaming tool. Identifies sensor type and location from photos, generates standardized filenames.

---

## Infrastructure & Deployment

### Docker Compose Services

```yaml
services:
  web:          # Django/Gunicorn on :8080
  db:           # PostgreSQL 15
  redis:        # Redis 7 (Celery broker)
  celery:       # Worker (4 concurrent processes)
  celery-beat:  # Periodic scheduler (DB-backed)
  libreoffice-uno:  # Headless LibreOffice on socket :2002
  nginx:        # Reverse proxy + SSL on :80/:443
```

### Nginx

- HTTP → HTTPS redirect
- SSL/TLS 1.2+ with strong cipher suite
- 100MB upload limit (large claim media)
- 900s proxy/body timeouts (long-running AI tasks)
- Static and media file serving with cache headers
- Security headers: X-Frame-Options, X-Content-Type-Options, HSTS

### Gunicorn

- `gthread` worker class (sync + threads)
- Workers: `(cpu_count × 2) + 1`
- 4 threads per worker
- 1000 worker connections
- 120s timeout (configurable via env)

### LibreOffice UNO

A headless LibreOffice instance runs as a persistent service, accepting document generation requests over a Unix socket. Used to populate Excel templates and convert documents to PDF — bypassing the need for any paid document API.

---

## API Integrations

### Encircle API (v1/v2)

Full REST client with pagination support, data processors, and an Excel exporter:

```python
api = EncircleAPIClient()
all_rooms = api.get_all_structure_rooms(claim_id, structure_id)
media = api.get_room_media(claim_id, structure_id, room_id)
```

Key capabilities:
- Claim CRUD and structure management
- Room entry generation (8000/9000/10000/70000 series line items)
- Media download (in-memory ZIP)
- Webhook subscription management
- Paginated media browsing (handles 5,000+ item claims)

### Microsoft Graph API

OAuth2 PKCE flow for secure OneDrive/SharePoint integration:
- Navigate shared folder structures
- Upload/download files
- Auto-create claim folder hierarchies
- Sync document templates across claims
- Token refresh handled transparently

### Anthropic Claude API

Direct SDK integration with image batching:
- Base64-encoded images sent as vision messages
- Structured JSON output enforced via prompt
- 8,192 token responses for complete room analysis
- Rate limit handling (inter-batch sleep + SDK auto-retry)
- Multiple concurrent sessions supported via Celery

---

## Document Generation

### Schedule of Loss PDF (ReportLab)
Programmatic PDF layout — no templates, full control:
- Cover page with claim details and branding
- Per-room sections with colored headers
- Line item tables (description, brand, qty, replacement value, ACV)
- Grand total summary with depreciation breakdown
- Insurance-carrier-standard format

### Schedule of Loss Excel (openpyxl)
24-column workbook matching Encircle's export format:
- Columns: Room, Box, Location, Description, Brand, Disposition, Condition, QTY, Model#, Serial#, Retailer, Replacement Source, Purchase Price, Age, Replacement Value, Depreciation %, ACV, Notes
- Professional styling, borders, frozen header row
- Ready to submit or import into claim management systems

### Scope Checklist PDF (WeasyPrint)
HTML-to-PDF via WeasyPrint — room-by-room scope items with checkboxes. Emailed directly from the app.

---

## Background Task System

All long-running operations run as Celery tasks, keeping the web layer responsive:

| Task | Trigger | Duration |
|------|---------|---------|
| `process_cps_session_task` | Session start | 2–15 min (AI analysis) |
| `create_server_folder_structure_task` | New claim | ~5s |
| `copy_templates_to_server_task` | Claim creation | ~10s |
| `populate_excel_task` | Document request | ~30s |
| `push_claim_to_encircle_task` | Claim push | ~15s |
| `push_rooms_to_encircle_task` | Room push | ~30s |
| `generate_and_email_labels_task` | Label request | ~10s |
| `renew-onedrive-subscriptions` | Daily (beat) | ~5s |

The frontend polls `/api/session/<id>/status/` for live progress during AI processing. Each room updates its status independently as it completes.

---

## Security

- **HTTPS enforced** at Nginx — all HTTP redirected to HTTPS
- **Email-based auth** via django-allauth with verification requirements
- **CSRF protection** on all state-changing endpoints
- **Encrypted token storage** (cryptography library) for OAuth refresh tokens
- **Environment-based secrets** — no credentials in source
- **Django ORM** — parameterized queries throughout, no raw SQL
- **Session cookies** — secure flag, HttpOnly
- **AllowedHosts** validation
- **Security headers** — X-Frame-Options DENY, X-Content-Type-Options nosniff, HSTS

---

## Project Scale

- **13 Django apps** covering the full claims management workflow
- **7 Docker services** in production
- **3 AI-powered pipelines** (Schedule of Loss, box estimation, equipment verification)
- **3 external API integrations** (Encircle, Anthropic, Microsoft Graph)
- **4 document output formats** (PDF/reportlab, PDF/weasyprint, Excel, LibreOffice)
- **Selenium automation** for Encircle workflow tasks that lack API endpoints
- **Real-time progress** via Celery + polling
- **Production deployment** on a VPS with SSL, multi-worker Gunicorn, and Nginx

---

*Built and maintained as a solo full-stack project for production use by water mitigation contractors.*
