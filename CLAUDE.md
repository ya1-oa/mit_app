# CLAUDE.md — ClaiMetApp (`mit_app`)

Guidance for any agent/dev working in this repo. **Read the Strict Rules before writing code.**

---

## What this is

ClaiMetApp (claimetapp.com) — a property-restoration / insurance-claims **mitigation SaaS**.
Server-rendered Django monolith with async processing and heavy document generation. It is
incrementally **replacing a legacy Encircle + Excel "30-Master" workflow** with native features.

---

## Stack (verified)

- **Language/Framework:** Python **3.11**, Django **4.2.16** (server-rendered templates; no SPA, no JS build step)
- **DB:** PostgreSQL 15 is the production target (`psycopg2-binary`). ⚠️ The repo currently has a
  **SQLite⇄Postgres split** between branches — see Rule 5 and `MERGE_TO_MAIN.md`.
- **Async:** Celery **5.3** + Redis **5** (broker = Redis DB 0, Django cache = DB 1),
  `django-celery-beat` (scheduled jobs, DB scheduler), `django-celery-results`
- **Web:** Gunicorn (gthread) behind nginx
- **Containers:** Docker Compose — services: `web`, `db` (postgres), `redis`, `celery`,
  `celery-beat`, `nginx`, `libreoffice-uno`
- **Documents:** WeasyPrint **65** (HTML→PDF), ReportLab (some PDFs), openpyxl + **LibreOffice UNO**
  headless (port 2002) for Excel template population
- **Auth:** `django-allauth`
- **AI:** Anthropic SDK (`claude-haiku-4-5`) for room analysis
- **Optional:** Twilio (SMS OTP — falls back to email if unconfigured)
- **Frontend:** Django templates + **Bootstrap 5** + bootstrap-icons; CDN libs (`signature_pad`, `driver.js`)
- **External:** Encircle API (**being phased out** — goal is full independence)

---

## App layout (Django apps)

- **`docsAppR`** — core: `Client` (= a claim), `Room`, `WorkType`, `RoomWorkTypeValue`, `Document`
  (doc templates), Encircle sync, lease models, Celery tasks (`tasks.py`)
- **`lease_manager`** — leases, ALE, e-signature flow, lease email sender (`email_utils.py`)
- **`dev_hub`** — internal dev tooling (modules, weekly progress reports)
- Others: `dashboard`, `claims`, `scope_checklist`, `email_manager`, `labels`, `readings`,
  `sensor_renamer`, `equipment_checker`, `claim_images`, `encircle`, `box_calculator`,
  `cps_report`, `contractor_hub`, `tasks`

### Domain concepts you must know
- **Client = a claim.** Rooms belong to a Client; work types are 100–700 ("basic") + readings series.
- **Encircle entries** are pre-generated as `Room` rows with `is_encircle_entry=True` at claim Step 2.
- **Room templates:** `basic` (100–700s) is the **primary/default** list. `readings_8000` → MIT
  sub-claim, `readings_9000` → RHT sub-claim, `siding_10000` → siding. See Rule 9.
- **Lease signing:** `LeaseSignatureRequest` (per-party token, OTP verification, signature image,
  role = tenant/landlord/re_company), `LeaseDocument`, `LeaseActivity`.

---

## Running commands (important)

- **Do NOT run `manage.py` on the host** — the Windows host cannot load Django settings. Use the container:
  ```bash
  docker compose exec web python manage.py <command>
  ```
- **Python syntax check only** (host): `C:\Users\okaak\AppData\Local\Python\bin\python.exe -m py_compile <file>`
  (the bare `python` / `python3` are Windows Store stubs and fail).
- **`.env` changes need a recreate, not a restart:** `docker compose up -d --force-recreate <svc>`
  (`docker compose restart` keeps the old environment).

---

## Deploy

`.github/workflows/deploy.yml` runs on **push to `main`**: SSH → `git reset --hard origin/main`
→ `docker compose up -d --build` → `migrate` → `sync_lease_templates`.

> **Pushing to `main` deploys to production immediately.** There is no manual gate.

---

## STRICT development rules

1. **Never `git add -A` / `git add .`.** Stage explicit paths only (`git add app/foo.py`). Unrelated
   work-in-progress is frequently left in the working tree and must not be swept into commits.
2. **One feature per branch, branched from `main`.** Open a PR → `main`. Keep branches short-lived;
   never let a branch drift far from `main` (that drift is what made the current merge hard).
3. **Treat `main` as production.** Don't push to it casually — it auto-deploys. Verify build +
   migrations first, and record the last-good `main` SHA for rollback before any merge.
4. **Secrets only in `.env`** (env vars). Never hardcode credentials, API keys, or tokens.
   `DEBUG` must be `False` in production; `DEBUG`/`DEVELOPMENT_MODE` are env-driven, not hardcoded.
5. **Database = Postgres in prod.** Migrations must be Postgres-safe (no SQLite-only operations).
   Never silently switch DB backends. The settings var is **`DATABASES`** (plural) — do not
   reintroduce the `DATABASE` typo.
6. **Migrations:** generate them in the container; never edit an already-applied migration;
   reconcile multiple leaves with `makemigrations --merge`; check `migrate --plan` before deploy.
7. **Lease/signature email** must go through `lease_manager/email_utils.py`
   (`get_lease_from_email()` + `get_lease_email_connection()`), not the default mail backend.
8. **Lease document templates:** the generator prefers the **uploaded `Document.file`** over the
   static repo template. After editing a static lease template (`account/short_term.html`,
   `term_sheet.html`, `lease.html`) you MUST run `sync_lease_templates` (already wired into
   `start.sh` and `deploy.yml`) or the edit won't take effect.
9. **8000s/9000s readings must NEVER appear in the primary/default room list** — only when their
   template (`readings_8000` / `readings_9000`) is explicitly selected, on their own sub-claims.
   Default template list is `['basic']`. Don't reintroduce `['basic', 'readings']` defaults.
10. **Match the surrounding code.** Server-rendered templates + Bootstrap. No new frontend
    frameworks, build steps, or heavy dependencies without discussion.
11. **Logging:** app code logs under the `docsAppR` / app loggers; keep them configured in
    `LOGGING` — the web (gunicorn) process silently drops records from unconfigured loggers.
12. **Verify by running the app, not the test suite.** Exercise the actual feature in the
    container / on the running app; a green test run is not verification of behavior.

---

## In flight / being phased out

- **Encircle** (external API) — moving toward full independence.
- **30-Master** Excel workflow — porting into native apps (document creation, scope/completion
  checklists, per-claim progress, dashboard gauges).
- **SQLite → Postgres** production cutover — see **`MERGE_TO_MAIN.md`** for the runbook and the
  decisions that must be made first.
