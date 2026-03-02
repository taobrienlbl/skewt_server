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
      sounderpy \
      metpy \
      numpy

COPY app /app/app
COPY templates /app/templates
COPY static /app/static
COPY scripts /app/scripts

ENV PATH="/opt/venv/bin:${PATH}" \
    WORK_DIR=/data/work \
    OUTPUT_DIR=/data/output \
    WEB_ROOT=/data/web \
    WEB_IMAGES_DIR=/data/web/images \
    WEB_SHARPY_DIR=/data/web/sharpy \
    MANIFEST_PATH=/data/web/manifest.json \
    SITE_CONFIG_PATH=/data/site-config.yml \
    SCAN_INTERVAL_MINUTES=5

EXPOSE 8080
VOLUME ["/data/work", "/data/output", "/data/web"]

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
