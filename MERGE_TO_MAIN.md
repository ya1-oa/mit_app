# Runbook: merge `feature/contractor-bid-hub` → `main`

Purpose: get the feature branch's work onto `main` **without breaking production or
losing data**, and adopt a clean "feature branch → main" workflow afterward.

> ⚠️ Read the **Decisions** section before running anything. The risky parts are the
> **database backend** and the **migration history** — not the merge itself.

---

## 0. How deploy works (know this first)

`.github/workflows/deploy.yml` triggers on **every push to `main`**. It SSHes into the
server and runs:

```bash
cd ~/mitigation_app_src/app
git fetch origin main
git reset --hard origin/main          # server code = whatever is on main
cd ~/mitigation_app_src
docker compose down --timeout 30 || true
docker compose up -d --build          # rebuild + restart
docker compose exec -T web python manage.py sync_lease_templates
```

**Implication:** the second anything lands on `main`, production redeploys and runs
migrations. A broken merge = broken/empty live site. So we reconcile on the feature
branch first, verify, *then* push to main.

---

## 1. Current state (facts, as of this writing)

- `main` is the deploy branch. The server currently runs the **feature branch** code
  (manually checked out), on **SQLite** (`app/db.sqlite3`). All real claims/leases
  created so far live in that SQLite file.
- `feature/contractor-bid-hub` is **127 commits ahead** of `main`.
- `main` has **6 commits the feature branch does NOT have**:
  - `fix: correct box_calculator URL name, DEBUG env var, and DATABASES typo`
  - `fix: merge conflicting box_calculator migrations`
  - `fix: reorder migration 0016 to add lease FK before index`
  - `fix: replace SQLite-only migration 0017 with no-op for PostgreSQL`
  - `feat: add missing Excel Hub and Box Calculator cards to home app grid`
  - `Fix start.sh permission denied on github actions auto deploy flow`
- `main` is **missing entire apps** the feature branch added: `dev_hub`, `contractor_hub`
  (plus ~30 migrations).

---

## 2. The three blockers

### 🔴 A. Database backend is opposite on the two branches
| | feature (prod now) | main |
|---|---|---|
| `DEBUG` | hardcoded `True` | from env (default `False`) |
| `DEVELOPMENT_MODE` | hardcoded `True` | from env (default `False`) |
| Backend | **SQLite** (`db.sqlite3`) | **Postgres** (the `db` compose service) |
| Settings var | `DATABASE` (typo — broken) | `DATABASES` (fixed) |

If main's config deploys, the app reads **Postgres** instead of SQLite → your existing
data appears **gone** (still in the sqlite file, but unused). This is the single biggest
risk.

### 🔴 B. Migration histories diverged
- main lacks ~30 migrations + 2 apps' migrations.
- BOTH branches modified `docsAppR/migrations/0016*` and `0017*` differently.
- main already has a `box_calculator/migrations/0004_merge_*` (it resolved its own conflict).
- Merging will likely produce multiple migration leaves → `migrate` fails unless reconciled.

### 🔴 C. main's 6 fixes must be preserved
Don't overwrite main with the feature tree wholesale — you'd lose the Postgres fixes,
the DATABASES typo fix, and the start.sh permission fix.

---

## 3. Decisions YOU must make (before step 4)

### Decision 1 — Production database: **Postgres (recommended) or stay on SQLite?**
- **Postgres (recommended).** main already targets it, and SQLite caused the
  "database is locked" failures we hit (migrations silently failing, Celery pileups).
  Cost: you must migrate existing SQLite data into Postgres (one-time, see step 4.5).
- **Stay SQLite (short term).** Lower effort now, but you keep the locking problems and
  you'd have to override main's config to force SQLite. Not recommended long-term.

> Recommendation: **Postgres.** Decide now — it changes steps 4.4 and 4.5.

### Decision 2 — `DEBUG` in production
Must be **`False`** in prod (the current `DEBUG=True` exposes tracebacks/settings publicly).
Keep main's env-driven version and set `DEBUG=False` (or unset) in the server `.env`.

### Decision 3 — Where does the canonical `.env` live / who owns the secrets?
The server `.env` must contain `DATABASE_URL` (Postgres), `DEBUG`, `DEVELOPMENT_MODE`,
the email vars, `LEASE_EMAIL_*`, etc. Confirm it's complete before the first main deploy.

### Decision 4 — Cutover timing
First push to main = immediate redeploy. Pick a low-traffic window and have the rollback
(section 6) ready.

---

## 4. Reconciliation runbook (do this on the feature branch, NOT main)

```bash
# 0. Fresh clone (WSL)
git clone https://github.com/ya1-oa/mit_app.git && cd mit_app
git checkout feature/contractor-bid-hub
git fetch origin

# 1. Make a safety branch so you can't lose the current feature state
git checkout -b merge/main-reconcile

# 2. Pull main's 6 fixes INTO the feature line (conflicts surface here, safely)
git merge origin/main
```

### 4.3 Resolve conflicts
Expect conflicts in at least:
- `mitigation_app/settings.py` — **keep main's** `DATABASES` (not `DATABASE`), env-driven
  `DEBUG`/`DEVELOPMENT_MODE`; re-apply the feature branch's logging config + `LEASE_EMAIL_*`
  + `docsAppR`/`dev_hub` in `INSTALLED_APPS`.
- `start.sh` — keep main's permission fix **and** the feature branch's
  `sync_lease_templates` line (or rely on the deploy.yml's sync — don't duplicate).
- `docsAppR/migrations/0016*`, `0017*` — keep the **Postgres-safe** versions from main;
  make sure later feature migrations still apply on top.
- `home`/dashboard templates (the "Excel Hub / Box Calculator cards") — keep both sets.

### 4.4 Reconcile migrations
```bash
# Identify multiple leaf migrations and auto-create merge migrations
python manage.py makemigrations --merge

# Nothing should be missing:
python manage.py makemigrations --check --dry-run     # expect "No changes detected"

# Dry-run the plan against a COPY of prod data (never the live DB first):
python manage.py migrate --plan
```
If `0016/0017` or box_calculator still conflict, resolve by hand: the migration that
production has **already applied** wins on operations; later migrations must depend on it.

### 4.5 (If Decision 1 = Postgres) move the data
```bash
# On the server, while still on SQLite, export everything except noisy tables:
python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.permission -e admin.logentry -e sessions.session \
  > data.json

# Point settings at Postgres (DATABASE_URL in .env), build schema, then load:
python manage.py migrate
python manage.py loaddata data.json
```
Verify row counts (claims, leases, signature requests) match the SQLite source.

### 4.6 Verify the app actually runs
Bring the stack up locally/staging on the reconciled branch and smoke-test:
claim creation, lease detail, signature send, PDF download, dev_hub weekly report.
Fix anything before touching main.

### 4.7 Land it on main
```bash
git checkout main
git pull origin main
git merge merge/main-reconcile        # should be clean now
git push origin main                  # 🚀 THIS triggers the production deploy
```
Watch the GitHub Actions run + the server: `docker compose logs -f web celery`.

---

## 5. After the first deploy — verify prod
- Site loads, no debug tracebacks (DEBUG=False).
- Data present (claims/leases visible) — confirms the DB cutover worked.
- Migrations applied: `docker compose exec web python manage.py showmigrations | grep -i "\[ \]"`
  (should be empty).
- Send a test signature + generate a PDF.

---

## 6. Rollback plan
If the deploy breaks production:
```bash
# On the server: pin main back to the last-good commit and redeploy
cd ~/mitigation_app_src/app
git reset --hard <LAST_GOOD_MAIN_SHA>
cd ~/mitigation_app_src && docker compose up -d --build
```
- Record `<LAST_GOOD_MAIN_SHA>` (current `origin/main` tip) BEFORE pushing.
- If you switched to Postgres and it's wrong, the SQLite file is untouched — flip
  `.env` back to SQLite config and redeploy to restore the old data view.

---

## 7. Going-forward workflow (the point of all this)
1. `git checkout main && git pull`
2. `git checkout -b feature/<small-thing>`
3. Build it, commit in small steps.
4. Push the branch, open a **PR → main** on GitHub (lets you see conflicts + diff).
5. Merge the PR → auto-deploys.
6. Keep branches **short-lived** so they never drift 127 commits from main again.

Never develop long-term on one mega-branch — that drift is exactly what made this merge hard.
