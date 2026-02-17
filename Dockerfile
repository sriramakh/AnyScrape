# Use an official Python runtime as a parent image
# python:3.11-slim-bookworm is a good balance of size and compatibility
FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Set a default value for headless mode, can be overridden
ENV ANYSCRAPE_HEADLESS_DEFAULT=true

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for Playwright and general build tools
RUN apt-get update && apt-get install -y \
    build-essential \
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

# create a non-root user for security (optional but recommended for some playwright scenarios)
# However, for a simple CLI container, root is often fine. 
# We'll stick to root for simplicity unless strictly required.

# Entrypoint allows running the container as an executable
ENTRYPOINT ["python", "-m", "anyscrape.cli"]

# Default command if no arguments are provided
CMD ["--help"]
