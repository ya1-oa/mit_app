# Use Python 3.11 slim as base
FROM python:3.11-slim

# Install system dependencies for Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chrome dependencies (CRITICAL - all the missing libraries)
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libcups2 \
    libdbus-1-3 \
    # Chrome browser and utilities
    wget \
    gnupg \
    ca-certificates \
    unzip \
    libpq-dev \
    gcc \
    curl \
    jq \
    # LibreOffice dependencies
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-core \
    python3-uno \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Replace the entire ChromeDriver installation section with:
RUN echo "=== Installing ChromeDriver using Chrome for Testing ===" \
    && CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1-3) \
    && echo "Detected Chrome major version: $CHROME_VERSION" \
    # Fetch all versions
    && curl -s "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json" > /tmp/versions.json \
    # Find the latest patch version that matches our major version
    && CHROMEDRIVER_URL=$(jq -r --arg version "$CHROME_VERSION" \
        '.versions[] | select(.version | startswith($version)) | .downloads.chromedriver[]? | select(.platform == "linux64") | .url' \
        /tmp/versions.json | tail -1) \
    && echo "Matching ChromeDriver URL: $CHROMEDRIVER_URL" \
    # Fallback to latest stable
    && if [ -z "$CHROMEDRIVER_URL" ] || [ "$CHROMEDRIVER_URL" = "null" ]; then \
        echo "Matching version not found, using latest stable..." \
        && curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" > /tmp/latest.json \
        && CHROMEDRIVER_URL=$(jq -r '.channels.Stable.downloads.chromedriver[]? | select(.platform == "linux64") | .url' /tmp/latest.json); \
    fi \
    # Download and install
    && echo "Downloading ChromeDriver from: $CHROMEDRIVER_URL" \
    && wget --no-verbose --tries=3 --timeout=30 "$CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && find /tmp -name "chromedriver" -type f -exec cp {} /usr/local/bin/chromedriver \; \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver* /tmp/*.json \
    && echo "=== Versions ===" \
    && google-chrome --version \
    && /usr/local/bin/chromedriver --version

# Set environment variables
ENV CHROME_DRIVER_PATH=/usr/local/bin/chromedriver \
    CHROME_BIN=/usr/bin/google-chrome \
    LIBREOFFICE_PATH=/usr/bin/libreoffice \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/usr/lib/python3/dist-packages"

# Create and set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files (if using Django)
RUN python manage.py collectstatic --noinput

# Create startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Use the startup script
CMD ["/app/start.sh"]
