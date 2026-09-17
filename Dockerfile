# ==========================================
# ReWoo Production Multi-Stage Docker Build
# ==========================================
# Stage 1: Build dependencies
# Stage 2: Production runtime (minimal)
# Stage 3: Celery worker

# ---- Build Stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml README.md ./

# Install dependencies to a separate directory
RUN uv pip install --system --no-cache-dir .

# ---- API Server Stage ----
FROM python:3.12-slim AS api

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r rewoo \
    && useradd -r -g rewoo -d /app -s /sbin/nologin rewoo

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY rewoo/ rewoo/

# Create necessary directories
RUN mkdir -p /app/data && chown -R rewoo:rewoo /app

# Switch to non-root user
USER rewoo

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

EXPOSE ${PORT}

# Run with uvicorn for production
CMD ["uvicorn", "rewoo.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools", "--log-level", "info", "--access-log"]

# ---- Celery Worker Stage ----
FROM python:3.12-slim AS worker

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r rewoo \
    && useradd -r -g rewoo -d /app -s /sbin/nologin rewoo

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY rewoo/ rewoo/

RUN mkdir -p /app/data && chown -R rewoo:rewoo /app
USER rewoo

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["celery", "-A", "rewoo.tasks.executor:celery_app", "worker", "--loglevel=info", "--concurrency=4", "--max-tasks-per-child=100"]

# ---- Celery Beat Stage ----
FROM worker AS beat

CMD ["celery", "-A", "rewoo.tasks.executor:celery_app", "beat", "--loglevel=info"]
