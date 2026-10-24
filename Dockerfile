FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed to build asyncpg/psycopg2 wheels on some platforms.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

# Runs as a non-root user in production.
RUN useradd --create-home --shell /bin/bash flowdesk \
    && chown -R flowdesk:flowdesk /app
USER flowdesk

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command runs the server only. Migrations should be run as a
# separate step (e.g., via `docker compose run backend alembic upgrade head`
# or as a Kubernetes initContainer) to avoid concurrent migration races
# in multi-replica deployments.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
