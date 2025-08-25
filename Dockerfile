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
    curl \
    jq \
    # LibreOffice dependencies
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-core \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver using Chrome for Testing API (NEW METHOD)
RUN echo "=== Installing ChromeDriver using Chrome for Testing ===" \
    && CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
    && echo "Detected Chrome version: $CHROME_VERSION" \
    # Fetch the Chrome for Testing JSON API to get the correct download URL
    && echo "Fetching Chrome for Testing versions..." \
    && curl -s "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json" > /tmp/versions.json \
    # Extract the ChromeDriver download URL for our exact Chrome version
    && CHROMEDRIVER_URL=$(jq -r --arg version "$CHROME_VERSION" \
        '.versions[] | select(.version == $version) | .downloads.chromedriver[]? | select(.platform == "linux64") | .url' \
        /tmp/versions.json) \
    && echo "ChromeDriver URL: $CHROMEDRIVER_URL" \
    # If exact version not found, get the latest stable
    && if [ -z "$CHROMEDRIVER_URL" ] || [ "$CHROMEDRIVER_URL" = "null" ]; then \
        echo "Exact version not found, using latest stable..." \
        && curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" > /tmp/latest.json \
        && CHROMEDRIVER_URL=$(jq -r '.channels.Stable.downloads.chromedriver[]? | select(.platform == "linux64") | .url' /tmp/latest.json) \
        && echo "Latest stable ChromeDriver URL: $CHROMEDRIVER_URL"; \
    fi \
    # Download and install ChromeDriver
    && if [ -n "$CHROMEDRIVER_URL" ] && [ "$CHROMEDRIVER_URL" != "null" ]; then \
        echo "Downloading ChromeDriver from: $CHROMEDRIVER_URL" \
        && wget --no-verbose --tries=3 --timeout=30 "$CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
        && echo "Extracting ChromeDriver..." \
        && unzip /tmp/chromedriver.zip -d /tmp/ \
        && find /tmp -name "chromedriver" -type f -exec cp {} /usr/local/bin/chromedriver \; \
        && chmod +x /usr/local/bin/chromedriver \
        && rm -rf /tmp/chromedriver* /tmp/*.json \
        && echo "=== ChromeDriver Installation Successful ===" \
        && /usr/local/bin/chromedriver --version \
        && echo "=== Chrome and ChromeDriver Versions ===" \
        && google-chrome --version \
        && /usr/local/bin/chromedriver --version; \
    else \
        echo "ERROR: Failed to find ChromeDriver download URL" && exit 1; \
    fi

# Set environment variables
ENV CHROME_DRIVER_PATH=/usr/local/bin/chromedriver \
    CHROME_BIN=/usr/bin/google-chrome \
    LIBREOFFICE_PATH=/usr/bin/libreoffice \
    PYTHONUNBUFFERED=1

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
