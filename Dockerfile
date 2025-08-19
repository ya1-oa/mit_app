# Use Python 3.11 slim as base
FROM python:3.11-slim

# Install system dependencies for both Firefox and Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Firefox for automation (primary)
    firefox-esr \
    # Chrome (fallback)
    wget \
    gnupg \
    ca-certificates \
    # LibreOffice dependencies
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-base \
    libreoffice-core \
    uno-libs-private \
    ure \
    fonts-liberation \
    # Additional dependencies
    libgbm1 \
    libnss3 \
    libnspr4 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgtk-3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install GeckoDriver (Firefox driver) - primary
RUN GECKODRIVER_VERSION=$(wget -qO- https://api.github.com/repos/mozilla/geckodriver/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/') \
    && wget -O /tmp/geckodriver.tar.gz https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-linux64.tar.gz \
    && tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ \
    && chmod +x /usr/local/bin/geckodriver \
    && rm /tmp/geckodriver.tar.gz

# Install ChromeDriver (fallback) - simplified approach
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
    && CHROME_MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d. -f1) \
    && { \
        CHROME_DRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION} 2>/dev/null || \
        wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE) || echo "139.0.7258.127"; \
    } \
    && wget --no-verbose --tries=3 \
       https://chromedriver.storage.googleapis.com/${CHROME_DRIVER_VERSION}/chromedriver_linux64.zip -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm /tmp/chromedriver.zip

# Set environment variables
ENV GECKO_DRIVER_PATH=/usr/local/bin/geckodriver \
    CHROME_DRIVER_PATH=/usr/local/bin/chromedriver \
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

# Run gunicorn
CMD ["gunicorn", "--worker-tmp-dir", "/dev/shm", "mitigation_app.wsgi:application", "--log-file", "-"]
