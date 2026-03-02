#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${WORK_DIR}" "${OUTPUT_DIR}" "${WEB_IMAGES_DIR}" "${WEB_SHARPY_DIR}" "$(dirname "${MANIFEST_PATH}")"
touch /var/log/cron.log

INTERVAL="${SCAN_INTERVAL_MINUTES:-5}"
if ! [[ "${INTERVAL}" =~ ^[0-9]+$ ]] || [ "${INTERVAL}" -lt 1 ] || [ "${INTERVAL}" -gt 59 ]; then
  echo "Invalid SCAN_INTERVAL_MINUTES=${INTERVAL}; must be an integer in [1,59]. Falling back to 5."
  INTERVAL=5
fi

cat >/etc/cron.d/skewt-cron <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/venv/bin
*/${INTERVAL} * * * * root cd /app && python -m app.processor >> /var/log/cron.log 2>&1
CRON
chmod 0644 /etc/cron.d/skewt-cron
crontab /etc/cron.d/skewt-cron

# Process once at startup so fresh files appear immediately.
cd /app && python -m app.processor || true

cron

if [ "${ENABLE_SMTP_INGEST,,}" = "true" ]; then
  cd /app && python -m app.smtp_ingest &
fi

exec gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 2 "app.web:create_app()"
