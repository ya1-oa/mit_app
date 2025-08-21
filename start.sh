#!/bin/bash

# Memory optimization for Chrome in low-memory environment (1GB RAM)
export CHROME_OPTIONS="--disable-dev-shm-usage --no-sandbox --disable-gpu --single-process --memory-pressure-off"

echo "🚀 Starting Chrome-based automation environment..."
echo "💻 Memory optimization: 1GB RAM detected"

# Check Chrome availability
if command -v google-chrome > /dev/null 2>&1; then
    CHROME_VERSION=$(google-chrome --version 2>/dev/null || echo "version unknown")
    echo "✅ Chrome found: $CHROME_VERSION"
else
    echo "❌ Chrome not found!"
    echo "🔍 Searching for Chrome in common locations:"
    ls -la /usr/bin/google-chrome* /usr/bin/chromium* 2>/dev/null || echo "No Chrome binaries found"
    exit 1
fi

# Check ChromeDriver availability
if [ -x "/usr/local/bin/chromedriver" ]; then
    CHROME_DRIVER_VERSION=$(/usr/local/bin/chromedriver --version 2>/dev/null || echo "version unknown")
    echo "✅ ChromeDriver found: $CHROME_DRIVER_VERSION"
else
    echo "❌ ChromeDriver not found or not executable!"
    echo "🔍 Searching for ChromeDriver:"
    ls -la /usr/local/bin/chromedriver* 2>/dev/null || echo "No ChromeDriver found"
    exit 1
fi

# Check essential Chrome dependencies
echo "🔍 Checking Chrome dependencies..."
if ldconfig -p | grep -q libnss3; then
    echo "✅ libnss3: found"
else
    echo "❌ libnss3: missing (essential for Chrome)"
fi

if ldconfig -p | grep -q libnspr4; then
    echo "✅ libnspr4: found"
else
    echo "❌ libnspr4: missing (essential for Chrome)"
fi

# Display Chrome configuration
echo "🔧 Chrome configuration:"
echo "   CHROME_BIN: ${CHROME_BIN:-/usr/bin/google-chrome}"
echo "   CHROME_DRIVER_PATH: ${CHROME_DRIVER_PATH:-/usr/local/bin/chromedriver}"
echo "   Chrome options: $CHROME_OPTIONS"

# Memory status
echo "💾 Memory status:"
free -h || echo "free command not available"

# Start your Django application with optimized gunicorn for low memory
echo "🚀 Starting Django application with memory-optimized gunicorn..."
echo "📋 Command: gunicorn --worker-tmp-dir /dev/shm --workers 2 --threads 2 --worker-class gthread mitigation_app.wsgi:application --log-file -"

# Execute the optimized gunicorn command
exec gunicorn \
    --worker-tmp-dir /dev/shm \
    --workers 2 \
    --threads 2 \
    --worker-class gthread \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout 120 \
    --keepalive 5 \
    mitigation_app.wsgi:application \
    --log-file -
