# Use Python 3.11 slim as base
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y \
    google-chrome-stable \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-core \
    uno-libs-private \
    ure \
    fonts-liberation \
    libgbm1 \
    libnss3 \
    libnspr4 \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
RUN CHROME_DRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE) \
    && wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${CHROME_DRIVER_VERSION}/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip -d /usr/bin/ \
    && chmod +x /usr/bin/chromedriver \
    && rm /tmp/chromedriver.zip

# Set environment variables
ENV CHROME_BIN=/usr/bin/google-chrome \
    CHROME_DRIVER_PATH=/usr/bin/chromedriver \
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
