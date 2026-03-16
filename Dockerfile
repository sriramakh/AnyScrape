# Use an official Python runtime as a parent image
# python:3.11-slim-bookworm is a good balance of size and compatibility
FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Set a default value for headless mode, can be overridden
ENV ANYSCRAPE_HEADLESS_DEFAULT=true
# Virtual display for headless=False retry on servers without a monitor
ENV DISPLAY=:99

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for Playwright, xvfb, and general build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and system dependencies
# We only install chromium to keep the image size smaller,
# as crawl4ai primarily uses it.
# Remove "chromium" if you need firefox/webkit support.
RUN playwright install --with-deps chromium

# Copy the current directory contents into the container at /app
COPY . .

# Start xvfb in the background, then run the web API server
ENTRYPOINT ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &  uvicorn anyscrape.web_app:app --host 0.0.0.0 --port 8000"]
