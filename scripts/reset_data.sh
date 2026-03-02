#!/usr/bin/env bash
set -euo pipefail

find data/work -mindepth 1 ! -name '.gitkeep' -delete
find data/output -mindepth 1 ! -name '.gitkeep' -delete
find data/web/images -mindepth 1 ! -name '.gitkeep' -delete
find data/web/sharpy -mindepth 1 ! -name '.gitkeep' -delete
rm -f data/web/manifest.json

if docker compose ps -q skewt >/dev/null 2>&1 && [ -n "$(docker compose ps -q skewt)" ]; then
  docker compose exec skewt sh -lc ': > /var/log/cron.log' || true
fi

echo "Reset complete."
