#!/bin/bash

# Install LibreOffice on DigitalOcean App Platform
set -e

echo "➤ Installing LibreOffice..."
apt-get update
apt-get install -y --no-install-recommends libreoffice-writer libreoffice-calc

# Verify installation
echo "➤ Verifying LibreOffice installation..."
loffice --version || echo "LibreOffice verification failed"

# Clean up to reduce image size
echo "➤ Cleaning up..."
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "✓ LibreOffice installation complete"
