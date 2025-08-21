#!/bin/bash

# Start Xvfb virtual display (required for Firefox headless)
echo "Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!

# Wait for Xvfb to start
sleep 3

# Check if Xvfb started successfully
if ! ps -p $XVFB_PID > /dev/null; then
    echo "Xvfb failed to start. Check /tmp/xvfb.log for details."
    echo "Continuing without Xvfb - Chrome may still work..."
fi

echo "Xvfb started successfully with PID: $XVFB_PID"

# Export DISPLAY environment variable
export DISPLAY=:99

# Start your Django application with gunicorn (your original command)
echo "Starting Django application with gunicorn..."
exec gunicorn --worker-tmp-dir /dev/shm mitigation_app.wsgi:application --log-file -
