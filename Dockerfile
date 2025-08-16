# Use Python 3.9 slim as base
FROM python:3.10-slim

# Install system dependencies in separate layers for better caching
# First - Chrome/Selenium dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    libgbm1 \
    libnss3 \
    libnspr4 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Second - LibreOffice with minimal dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-base \
    libreoffice-core \
    uno-libs-private \
    ure \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROME_DRIVER_PATH=/usr/bin/chromedriver \
    LIBREOFFICE_PATH=/usr/bin/libreoffice

# Create and set working directory
WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files (if using Django)
RUN python manage.py collectstatic --noinput

# Run gunicorn
CMD ["gunicorn", "--worker-tmp-dir", "/dev/shm", "mitigation_app.wsgi:application", "--log-file", "-"]
