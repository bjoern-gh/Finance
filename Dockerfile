# Single image used by both the Streamlit and API services.
# The CMD is overridden per-service in docker-compose.yml.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps needed for curl-cffi (yfinance) and numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        liblzma-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first — this layer is cached as long as requirements.txt doesn't change
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# portfolios/ is a Docker volume mount — ensure the directory exists in the image
# so the volume mounts cleanly even on first run
RUN mkdir -p /app/portfolios

# Non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Default: run Streamlit (overridden for the API service in docker-compose.yml)
EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
