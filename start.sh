#!/bin/bash

# Start Xvfb virtual display (required for Firefox headless)
echo "🚀 Starting Xvfb virtual display..."
echo "📋 Display will be set to :99 with resolution 1920x1080x24"

# Start Xvfb in the background
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!

# Wait for Xvfb to start
echo "⏳ Waiting for Xvfb to initialize..."
sleep 3

# Check if Xvfb started successfully
if ps -p $XVFB_PID > /dev/null; then
    echo "✅ Xvfb started successfully with PID: $XVFB_PID"
    echo "📊 Xvfb process details:"
    ps -f -p $XVFB_PID
    
    # Test if the display is working
    echo "🧪 Testing Xvfb display..."
    if xdpyinfo -display :99 > /dev/null 2>&1; then
        echo "✅ Xvfb display test passed - display :99 is working"
        echo "📏 Display info:"
        xdpyinfo -display :99 | grep -E "(dimensions|resolution|version)" | head -5
    else
        echo "❌ Xvfb display test failed - check /tmp/xvfb.log for details"
        echo "📄 Xvfb log contents:"
        cat /tmp/xvfb.log
    fi
else
    echo "❌ Xvfb failed to start!"
    echo "📄 Xvfb log contents:"
    cat /tmp/xvfb.log
    echo "⚠️ Continuing without Xvfb - Chrome may still work..."
fi

# Export DISPLAY environment variable
export DISPLAY=:99
echo "🌐 Set DISPLAY environment variable to: $DISPLAY"

# Display current environment for debugging
echo "🔍 Current environment variables:"
env | grep -E "(DISPLAY|GECKO|CHROME|PATH)" | sort

# Check if browsers are available
echo "🔍 Checking browser availability:"
if command -v firefox > /dev/null 2>&1; then
    echo "✅ Firefox found: $(firefox --version 2>/dev/null || echo 'version unknown')"
else
    echo "❌ Firefox not found"
fi

if command -v google-chrome > /dev/null 2>&1; then
    echo "✅ Chrome found: $(google-chrome --version 2>/dev/null || echo 'version unknown')"
else
    echo "❌ Chrome not found"
fi

# Check if drivers are available
echo "🔍 Checking driver availability:"
if [ -x "$GECKO_DRIVER_PATH" ]; then
    echo "✅ Geckodriver found: $($GECKO_DRIVER_PATH --version 2>/dev/null || echo 'version unknown')"
else
    echo "❌ Geckodriver not found or not executable at: $GECKO_DRIVER_PATH"
fi

if [ -x "$CHROME_DRIVER_PATH" ]; then
    echo "✅ Chromedriver found: $($CHROME_DRIVER_PATH --version 2>/dev/null || echo 'version unknown')"
else
    echo "❌ Chromedriver not found or not executable at: $CHROME_DRIVER_PATH"
fi

# Start your Django application with gunicorn
echo "🚀 Starting Django application with gunicorn..."
echo "📋 Command: gunicorn --worker-tmp-dir /dev/shm mitigation_app.wsgi:application --log-file -"

# Execute the original gunicorn command
exec gunicorn --worker-tmp-dir /dev/shm mitigation_app.wsgi:application --log-file -
