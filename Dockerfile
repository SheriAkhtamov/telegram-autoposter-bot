# Dockerfile for Telegram Autoposter Bot

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create media storage directory
RUN mkdir -p /app/media_storage

# Expose panel port
EXPOSE 8080

# Run the bot
CMD ["python", "main.py"]
