# AGENTS.md

Guidance for coding agents working in `/home/obrienta/projects/skewt_server`.

## Project Overview

This repository hosts a small containerized Skew-T processing service:

- `app/processor.py` scans `data/work` for `*SHARPY.txt` and `*SHARPPY.txt` files.
- Matching files are parsed into sounding profiles, rendered to PNG with `sounderpy`, and copied into web-facing directories under `data/web`.
- `app/web.py` serves a Flask UI that reads `data/web/manifest.json` and exposes the generated images and source text files.
- `scripts/entrypoint.sh` runs one processing pass at startup, installs a cron job, and launches Gunicorn.

The system is file-driven. There is no database, background queue, or API beyond the Flask UI.

## Repository Layout

- `app/web.py`: Flask application and file-serving routes.
- `app/processor.py`: SHARPY discovery, parsing, plotting, copying, and manifest generation.
- `app/site_config.py`: Site metadata loading from `site-config.yml`.
- `templates/index.html`: Main UI template.
- `static/styles.css`: Site styling.
- `scripts/entrypoint.sh`: Container startup, cron wiring, and Gunicorn launch.
- `scripts/reset_data.sh`: Local reset helper for mounted data directories.
- `data/work`: Incoming SHARPY text files.
- `data/output`: Generated PNGs.
- `data/web/images`: Web-served PNG copies.
- `data/web/sharpy`: Downloadable source text copies.
- `data/web/manifest.json`: Generated manifest consumed by the UI.
- `site-config.yml`: User-editable site metadata.

## Core Workflows

### Start the stack

```bash
docker compose up --build
```

App is served on `http://localhost:8080`.

### Force one processing run

If the container is already running:

```bash
docker compose exec skewt /opt/venv/bin/python -m app.processor
```

If working directly in a local Python environment:

```bash
python -m app.processor
```

### Reset generated data

```bash
bash scripts/reset_data.sh
```

This deletes generated files under `data/` while preserving `.gitkeep`.

## Environment And Configuration

Important environment variables used by the app:

- `WORK_DIR`
- `OUTPUT_DIR`
- `WEB_IMAGES_DIR`
- `WEB_SHARPY_DIR`
- `MANIFEST_PATH`
- `SITE_CONFIG_PATH`
- `SCAN_INTERVAL_MINUTES`
- `TZ`

Defaults are set in the `Dockerfile`. Runtime overrides are supplied in `docker-compose.yml`.

Site metadata is loaded from `site-config.yml`. `app/site_config.py` supports PyYAML if available and otherwise falls back to a minimal line-based parser, so keep this file simple.

## Development Conventions

- Prefer minimal, targeted changes. This repository is small and has a simple runtime model.
- Preserve the file-based contract between processor output and Flask UI.
- Keep output paths and manifest fields stable unless the task explicitly requires changing them.
- Treat the mounted `data/` directories as part of the operational interface. Changes there can affect local runs and deployed containers.
- Use ASCII unless an existing file already requires non-ASCII.

## Processor-Specific Notes

- Discovery is recursive under `WORK_DIR` and only accepts filenames matching `SHARP+Y.txt`.
- Filenames are expected to contain `<SITECODE>_<YYYYMMDD>_<HH>Z_...` for launch-time parsing. If a filename does not match, the manifest falls back to `"Unknown launch time"`.
- Parsing only reads lines between `%RAW%` and `%END%`.
- The processor skips re-rendering if the target PNG already exists, but still refreshes web copies when source or output mtimes are newer.
- `manifest.json` is regenerated on every run and sorted with most recent launch first.

When changing processor logic, verify both image generation and manifest ordering.

## Validation

There is no formal automated test suite in this repository today. Validate changes with the real workflow:

1. Start the stack with `docker compose up --build`.
2. Add one or more representative `*SHARPY.txt` files to `data/work`.
3. Run `docker compose exec skewt /opt/venv/bin/python -m app.processor` if you need an immediate pass.
4. Confirm:
   - PNGs appear in `data/output` and `data/web/images`
   - source files appear in `data/web/sharpy`
   - `data/web/manifest.json` is valid and ordered correctly
   - `http://localhost:8080` renders the latest sounding and downloads work
5. Re-run the processor to check idempotent skip behavior.

If you change only static assets or templates, a browser check is usually sufficient.

## Editing Guidance

- `templates/index.html` and `static/styles.css` are tightly coupled. Keep selectors and template structure aligned.
- `app/web.py` assumes the manifest shape emitted by `app/processor.py`; update both sides together if fields change.
- `scripts/entrypoint.sh` writes to `/etc/cron.d/skewt-cron` and `/var/log/cron.log`; do not change startup behavior casually because the container relies on both cron and Gunicorn running together.
- Avoid introducing heavyweight infrastructure or abstractions unless the task requires it.

## Known Gaps

- No unit tests or integration tests are present.
- No linting or formatting configuration is checked in.
- The Docker image installs dependencies directly rather than locking them from a pinned requirements file.

If you add tooling, keep it lightweight and consistent with the repository’s current size.
