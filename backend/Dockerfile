# Use official Microsoft Playwright image (includes all browser deps)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory
WORKDIR /app

# Install FFmpeg for audio processing
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy requirements (made consistent for Railway)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# IMPORTANT: Tell Playwright to use the pre-installed browsers from the image
# This skips the 5+ minute download step entirely
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Expose the port FastAPI will run on
EXPOSE 8080

# Command to run the application
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
