#!/usr/bin/env bash
# setup_libreoffice_uno.sh
#
# Installs LibreOffice, python3-uno bridge, and configures the persistent
# UNO listener service for the claims management system.
#
# Usage:
#   sudo bash setup_libreoffice_uno.sh [APP_USER] [CLAIMS_ROOT]
#
# Examples:
#   sudo bash setup_libreoffice_uno.sh www-data /srv/claims
#   sudo bash setup_libreoffice_uno.sh django /home/django/media/claims

set -euo pipefail

APP_USER="${1:-www-data}"
CLAIMS_ROOT="${2:-/srv/claims}"

echo "=== LibreOffice UNO Setup ==="
echo "App user:    $APP_USER"
echo "Claims root: $CLAIMS_ROOT"
echo ""

# --- 1. Install LibreOffice + UNO bridge ---
echo "[1/5] Installing LibreOffice and python3-uno..."
apt-get update -qq
apt-get install -y -qq libreoffice-calc python3-uno

# Verify
echo "  Checking UNO import..."
if /usr/bin/python3 -c "import uno; print('  OK: uno importable')" 2>/dev/null; then
    echo "  python3-uno bridge: OK"
else
    echo "  ERROR: python3-uno not importable. Check your Python version."
    echo "  LibreOffice ships UNO for the system Python only."
    echo "  If using a virtualenv, recreate it with --system-site-packages"
    exit 1
fi

# --- 2. Create service user home directory ---
echo "[2/5] Setting up service profile directory..."
mkdir -p /var/lib/libreoffice-uno/.config/libreoffice
chown -R "$APP_USER":"$APP_USER" /var/lib/libreoffice-uno

# --- 3. Install systemd service ---
echo "[3/5] Installing systemd service..."

# Read the template and patch in the actual user + claims root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SRC="$SCRIPT_DIR/libreoffice-uno.service"

if [[ ! -f "$SERVICE_SRC" ]]; then
    echo "  ERROR: libreoffice-uno.service not found at $SERVICE_SRC"
    echo "  Place the .service file next to this script."
    exit 1
fi

# Patch User/Group and ReadWritePaths
sed -e "s|^User=.*|User=$APP_USER|" \
    -e "s|^Group=.*|Group=$APP_USER|" \
    -e "s|ReadWritePaths=/path/to/your/claims/root|ReadWritePaths=$CLAIMS_ROOT|" \
    "$SERVICE_SRC" > /etc/systemd/system/libreoffice-uno.service

systemctl daemon-reload

# --- 4. Enable and start ---
echo "[4/5] Enabling and starting service..."
systemctl enable libreoffice-uno.service
systemctl start libreoffice-uno.service

# Wait for it to come up
sleep 3
if systemctl is-active --quiet libreoffice-uno.service; then
    echo "  Service running: OK"
else
    echo "  WARNING: Service failed to start. Check: journalctl -u libreoffice-uno.service"
fi

# --- 5. Verify UNO connection ---
echo "[5/5] Testing UNO connection..."
# Give LO a moment to initialize the listener socket
sleep 2

TEST_RESULT=$(/usr/bin/python3 -c "
import uno
local_ctx = uno.getComponentContext()
resolver = local_ctx.ServiceManager.createInstanceWithContext(
    'com.sun.star.bridge.UnoUrlResolver', local_ctx)
try:
    ctx = resolver.resolve(
        'uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext')
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext('com.sun.star.frame.Desktop', ctx)
    print('CONNECTED' if desktop else 'NO_DESKTOP')
except Exception as e:
    print(f'FAILED: {e}')
" 2>&1)

if [[ "$TEST_RESULT" == "CONNECTED" ]]; then
    echo "  UNO connection: OK"
    echo ""
    echo "=== Setup complete ==="
    echo ""
    echo "The LibreOffice UNO listener is running on 127.0.0.1:2002"
    echo "Your Django/Celery app will automatically use it for Excel population."
    echo ""
    echo "If using a virtualenv, ensure it was created with --system-site-packages:"
    echo "  python3 -m venv --system-site-packages /path/to/venv"
    echo ""
    echo "Set these env vars if you need non-default config:"
    echo "  UNO_HOST=127.0.0.1  UNO_PORT=2002"
else
    echo "  WARNING: UNO connection test returned: $TEST_RESULT"
    echo "  The service may still be starting. Retry in a few seconds:"
    echo "    python3 -c 'from docsAppR.lo_uno_service import is_available; print(is_available())'"
fi
