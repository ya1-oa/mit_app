#!/bin/bash

# Set environment variables for Chrome automation
export CHROME_BIN="/usr/bin/google-chrome"
export CHROME_DRIVER_PATH="/usr/local/bin/chromedriver"

# Determine port (DigitalOcean sets PORT env var)
PORT=${PORT:-8080}

echo "Starting application on port $PORT..."

# Start the application
exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --threads 2 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile - \
    mitigation_app.wsgi:application
