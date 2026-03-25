FROM python:3.12-slim

# System dependencies for Playwright + Postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates \
    # Playwright browser deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 libpangocairo-1.0-0 \
    libdrm2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright chromium browser
RUN playwright install chromium

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
