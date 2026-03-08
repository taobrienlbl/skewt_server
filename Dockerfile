FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    ca-certificates \
    curl \
    build-essential \
    libproj-dev \
    proj-data \
    proj-bin \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml /app/

RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python \
      flask \
      gunicorn \
      globus-sdk \
      sounderpy \
      metpy \
      numpy

COPY app /app/app
COPY templates /app/templates
COPY static /app/static
COPY scripts /app/scripts

ENV PATH="/opt/venv/bin:${PATH}" \
    INGEST_DIR=/data/ingest \
    DELIVERY_DIR=/data/deliveries \
    WORK_DIR=/data/work \
    OUTPUT_DIR=/data/output \
    WEB_ROOT=/data/web \
    WEB_IMAGES_DIR=/data/web/images \
    WEB_SHARPY_DIR=/data/web/sharpy \
    MANIFEST_PATH=/data/web/manifest.json \
    STATE_PATH=/data/state/launches.json \
    SITE_CONFIG_PATH=/data/site-config.yml \
    SCAN_INTERVAL_MINUTES=5 \
    UPLOAD_STABILITY_SECONDS=120 \
    ENABLE_GLOBUS_TRANSFER=false \
    GLOBUS_DEST_BASE_PATH=/UCRP

EXPOSE 8080
VOLUME ["/data/ingest", "/data/deliveries", "/data/work", "/data/output", "/data/web", "/data/state"]

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
