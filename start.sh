#!/bin/bash

# Set environment variables for Chrome automation
export CHROME_BIN="/usr/bin/google-chrome"
export CHROME_DRIVER_PATH="/usr/local/bin/chromedriver"

# Determine port (DigitalOcean sets PORT env var)
PORT=${PORT:-8080}

echo "Starting application on port $PORT..."

# Apply any pending database migrations before starting
echo "Running database migrations..."
python manage.py migrate --noinput
echo "Migrations complete."

# Keep the canonical lease templates (Engagement Agreement, Term Sheet,
# Month to Month Rental) in the DB in sync with the repo's static templates.
# The lease generator prefers the uploaded Document copy, so without this an
# edit to a static template (e.g. signature blocks) silently never takes effect.
# Idempotent and non-fatal — a failure here must never block startup.
echo "Syncing lease templates..."
python manage.py sync_lease_templates || echo "WARN: sync_lease_templates failed (continuing)"
echo "Lease templates synced."

# Start the application
exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --threads 2 \
    --timeout 800 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile - \
    mitigation_app.wsgi:application
