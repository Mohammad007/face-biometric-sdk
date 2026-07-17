# ── DapperDev Biometric SDK — Railway deployment image ──────────────
# TensorFlow-based FastAPI service. Python pinned to 3.11 (TF 2.16 does
# not support 3.13).
FROM python:3.11-slim

# System libs needed by Pillow / TensorFlow / OpenCV-style ops
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    # Writable location for the SQLite DB on Railway's ephemeral disk /
    # mounted volume. Override with a volume mount for persistence.
    DATABASE_PATH=/app/data/biometric_data.db

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App source
COPY app ./app
COPY static ./static

# Data dir for the SQLite database
RUN mkdir -p /app/data

# Railway injects $PORT at runtime
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
