# ---------- Backend Dockerfile ----------
# Multi-stage: deps layer (cached) → app layer
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps: ffmpeg (for video pipeline), pg client libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libpq-dev \
        gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- deps stage (cached as long as requirements.txt unchanged) ----------
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- app stage ----------
FROM deps AS app
COPY . .

# Collect static files (CSS, JS from Django admin etc.)
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Create non-root user for runtime
RUN useradd -m -r -s /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default: run gunicorn. Override in docker-compose for celery worker.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
