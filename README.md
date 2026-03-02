# Skew-T Container

Dockerized service that:
- scans a mounted work folder for new `*SHARPY.txt` (also accepts common `*SHARPPY.txt`)
- generates Skew-T diagrams with `sounderpy`
- avoids regenerating existing images
- uses `site-config.yml` metadata in plot titles and web UI
- publishes images + downloadable source SHARPY files on a web UI
- runs processing on a cron interval configurable by environment variable
- optionally ingests SHARPY attachments from SMTP email

## Quick start

```bash
docker compose up --build
```

Then open `http://localhost:8080`.

## Directory mounts

- `./data/work` -> `/data/work` (incoming `*SHARPY.txt`)
- `./data/output` -> `/data/output` (generated PNGs)
- `./data/web` -> `/data/web` (served image/text copies + manifest)
- `./site-config.yml` -> `/data/site-config.yml` (site metadata)

## Environment variables

- `SCAN_INTERVAL_MINUTES` (default `5`): cron interval for processing run. Integer `1-59`.
- `ENABLE_SMTP_INGEST` (default `false`): enable SMTP receiver in container.
- `SMTP_PORT` (default `2525`): SMTP receiver port when enabled.
- `SITE_CONFIG_PATH` (default `/data/site-config.yml`): path to site metadata YAML.
- `TZ` (default `UTC`): container timezone.

## Site customization (`site-config.yml`)

Edit `site-config.yml`:

```yaml
site_code: USIUB
site_location: Bloomington, IN
site_latitude: 39.1653
site_longitude: -86.5264
site_long_name: Indiana University
```

These values are shown prominently on the web page and used in Skew-T titles.

## SHARPY file format expectations

The parser reads lines between `%RAW%` and `%END%` and expects comma-separated columns:
1. pressure (hPa)
2. height (m)
3. temperature (C)
4. dewpoint (C)
5. wind direction (deg)
6. wind speed (kt)

Files must end with `SHARPY.txt` (or `SHARPPY.txt`) to be discovered.
Launch date/time is parsed from filename pattern:

`<SITECODE>_<YYYYMMDD>_<HH>Z_<...>SHARPY.txt`

Example:
- `USIUB_20260222_21Z_SHARPPY.txt` -> `22 FEB 2026 | 2100Z`

## Optional SMTP ingest

Enable with:

```bash
ENABLE_SMTP_INGEST=true SMTP_PORT=2525 docker compose up --build
```

Send email attachments named like `XXXXSHARPY.txt` to localhost:2525.
Attachments are written into `/data/work` and picked up on the next scan interval.

## Testing workflow

1. Start stack: `docker compose up --build`
2. Copy one or more sample `*SHARPY.txt` files into `./data/work`
3. Wait one interval or force immediate run:
   - `docker compose exec skewt python -m app.processor`
4. Verify:
   - images appear under `./data/output` and `./data/web/images`
   - source files appear under `./data/web/sharpy`
   - browser shows latest sounding first at `http://localhost:8080`
   - launch date/time labels are shown for each sounding
5. Re-run processor and confirm existing outputs are skipped.

## Notes

- Cron and web server run in the same container.
- The startup script runs one initial processing pass immediately before cron begins.
