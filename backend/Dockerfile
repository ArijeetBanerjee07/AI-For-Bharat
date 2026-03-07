# Use slim Python image to stay under Railway's 4GB limit
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install only the essential system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY backend/ .

# Install only the chromium browser (skip others to save space)
RUN playwright install chromium

# Expose port
EXPOSE 8080

# Run
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
