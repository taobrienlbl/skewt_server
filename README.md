# Skew-T Container

Dockerized service that:
- scans a mounted ingest folder for complete radiosonde launch upload sets
- stages per-launch delivery directories for Globus transfer
- can submit each launch directory to Globus before rendering
- generates Skew-T diagrams with `sounderpy` after transfer succeeds
- uses `site-config.yml` metadata in plot titles and web UI
- publishes images + downloadable source SHARPY files on a web UI
- runs processing on a cron interval configurable by environment variable

## Quick start

```bash
docker compose up --build
```

Then open `http://localhost:8080`.

## Quick start with WireGuard + FTP ingress

Use this path if your radiosonde receiver can only upload by legacy FTP and you want the upload path secured over WireGuard.

1. Preview the host and FTP configuration:

```bash
bash scripts/install_wireguard_host.sh \
  --endpoint your.host.example.org \
  --dry-run
```

2. Install WireGuard on the host and generate matching FTP artifacts:

```bash
sudo bash scripts/install_wireguard_host.sh \
  --endpoint your.host.example.org
```

3. Start the Skew-T stack with the generated FTP sidecar override:

```bash
docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml up -d
```

4. Load the generated client config from `/etc/wireguard/clients/` onto the receiver-side computer, connect the tunnel, and configure the receiver to upload by passive FTP to the host WireGuard IP, typically `10.44.0.1`.

5. Verify that uploaded files appear in `data/work` and then in the web UI.

Full operator documentation is in [`docs/wireguard-ftp-setup.md`](docs/wireguard-ftp-setup.md).

## Quick start with automatic HTTPS

If you want the site to behave like a normal URL on `http://` and `https://`, use the included Caddy reverse-proxy override.

The current hostname in [`Caddyfile`](Caddyfile) is:

- `usiub.hoosierwxandclimate.org`

Start the stack with:

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d
```

If you also want the WireGuard + FTP sidecar, use:

```bash
docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml -f docker-compose.caddy.yml up -d
```

Caddy will:

- listen on `80` and `443`
- obtain and renew HTTPS certificates automatically
- reverse-proxy requests to the app on `8080`

For this to work, your DNS for `usiub.hoosierwxandclimate.org` must point to the server's public IP, and the host firewall must allow `80/tcp` and `443/tcp`.

## Directory mounts

- `./data/ingest` -> `/data/ingest` (flat receiver upload drop)
- `./data/deliveries` -> `/data/deliveries` (per-launch Globus payload directories)
- `./data/work` -> `/data/work` (incoming `*SHARPY.txt`)
- `./data/output` -> `/data/output` (generated PNGs)
- `./data/web` -> `/data/web` (served image/text copies + manifest)
- `./data/state` -> `/data/state` (launch transfer state)
- `./site-config.yml` -> `/data/site-config.yml` (site metadata)

## Environment variables

- `SCAN_INTERVAL_MINUTES` (default `5`): cron interval for processing run. Integer `1-59`.
- `PROCESS_NICE` (default `10`): Unix scheduling niceness for the plotting processor. Integer `-20` to `19`; higher values are lower priority and help the web server stay responsive during plot generation.
- `INGEST_DIR` (default `/data/ingest`): flat upload directory populated by the receiver FTP software.
- `DELIVERY_DIR` (default `/data/deliveries`): per-launch package directory tree used as the Globus source path.
- `STATE_PATH` (default `/data/state/launches.json`): persistent launch and transfer state file.
- `UPLOAD_STABILITY_SECONDS` (default `120`): quiet period required before an uploaded launch is treated as complete.
- `ENABLE_GLOBUS_TRANSFER` (default `false`): when `true`, submit launch directories to Globus before rendering.
- `GLOBUS_CLIENT_ID`, `GLOBUS_CLIENT_SECRET`: Globus confidential app credentials used for transfer submission.
- `GLOBUS_SOURCE_COLLECTION_ID`: source collection rooted at `DELIVERY_DIR`.
- `GLOBUS_DEST_COLLECTION_ID`: destination collection ID.
- `GLOBUS_DEST_BASE_PATH` (default `/UCRP`): destination base path; launch folders are appended as `<site>/<YYYYMMDD_HHMM>/`.
- `LAUNCH_DIR_MINUTE_OFFSET` (default `0`): optional minute offset applied to the summary launch time when naming delivery directories.
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

## Receiver upload expectations

The ingest pipeline expects a flat upload directory containing one file set per launch:

- `*_SUMMARY.txt`
- `*_SHARPPY.txt`
- `*_TEMP.txt`
- four `*_BUFR*.bufr` files

The launch timestamp is parsed from the summary line:

`Launched (UTC)           : 3/6/2026 23:29:15`

Once all required files exist and have been unchanged for `UPLOAD_STABILITY_SECONDS`, the processor stages a delivery directory at:

`<DELIVERY_DIR>/<SITE>/<YYYYMMDD_HHMM>/`

That directory contains the Globus payload files only: `SHARPPY`, `TEMP`, and the four `BUFR` files.

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

## Testing workflow

1. Start stack: `docker compose up --build`
2. Copy one complete receiver upload set into `./data/ingest`
3. Wait one interval or force immediate run:
   - `docker compose exec skewt /opt/venv/bin/python -m app.processor`
4. Verify:
   - delivery directories appear under `./data/deliveries/<SITE>/<YYYYMMDD_HHMM>/`
   - `./data/state/launches.json` reflects transfer state
   - images appear under `./data/output` and `./data/web/images`
   - source files appear under `./data/web/sharpy`
   - browser shows latest sounding first at `http://localhost:8080`
   - launch date/time labels and transfer status are shown for each sounding
5. Re-run processor and confirm existing outputs are skipped.

## Notes

- Cron and web server run in the same container.
- The startup script runs one initial processing pass immediately before cron begins.
- Plot generation runs at reduced CPU priority by default (`PROCESS_NICE=10`) so the web server is less likely to stall on small hosts while a new image is rendered.

## Secure FTP Ingress Over WireGuard

If your radiosonde receiver can only upload via legacy FTP, the recommended approach is:

1. install WireGuard on the host running this stack
2. connect the receiver computer to that host over WireGuard
3. run an FTP service bound only to the host's WireGuard address
4. write uploads into `data/work`

Detailed instructions are in [`docs/wireguard-ftp-setup.md`](docs/wireguard-ftp-setup.md).
A helper script for bootstrapping the host-side WireGuard interface and generating matching Docker Compose artifacts is in [`scripts/install_wireguard_host.sh`](scripts/install_wireguard_host.sh).
An example of the generated FTP env file is in [`config/wireguard-ftp.env.example`](config/wireguard-ftp.env.example).
An example of the generated Compose override is in [`docker-compose.ftp-wireguard.yml.example`](docker-compose.ftp-wireguard.yml.example).
The WireGuard guide is written for technically proficient Linux users who may not already know VPN or Docker details, and is intended to be shareable with colleagues running radiosonde stations.
For the simplest cloud hosting path, see the Lightsail guide in [`docs/lightsail-deployment.md`](docs/lightsail-deployment.md).
For Jetstream2 as research infrastructure, see [`docs/jetstream2-deployment.md`](docs/jetstream2-deployment.md).

## Public hosting on a desktop/server with Docker

Use this when you have a machine at home/office with Docker Desktop or Docker Engine and want internet access to the site.

1. Prepare host:
   - Install Docker + Docker Compose.
   - Open firewall for TCP `80` and `443` if using Caddy.
   - Open firewall for TCP `8080` only if you plan to expose the app directly without Caddy.
2. Run service:
   - Directly on `8080`: `docker compose up -d --build`
   - With automatic HTTPS via Caddy: `docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build`
3. Persist data:
   - Keep `data/work`, `data/output`, `data/web`, and `site-config.yml` on local disk (already mounted by `docker-compose.yml`).
4. Expose publicly:
   - Configure router/NAT port-forward from public `80/443` to this host if using Caddy.
   - Configure router/NAT port-forward from public `8080` only if you are intentionally exposing the app directly.
   - Prefer the included Caddy reverse proxy for TLS certificates and a cleaner public URL.
5. DNS:
   - Point a domain/subdomain (for example `skewt.example.com`) to your public IP.
6. Security hardening:
   - Keep OS and Docker patched.
   - Consider HTTP auth or IP allow-list if the site should be private.

## Cloud deployment (AWS and Azure)

You can run this as a single container service with persistent mounted storage.

### AWS options

1. `EC2 + Docker Compose` (simplest to match local behavior):
   - Launch EC2 VM, install Docker/Compose, copy repo, run `docker compose up -d --build`.
   - Use EBS volume for persistent `data/` directories.
   - Put an Application Load Balancer or nginx/caddy in front for TLS on `443`.
2. `ECS/Fargate` (managed containers):
   - Build/push image to ECR.
   - Run as ECS service.
   - Mount EFS for `/data/work`, `/data/output`, `/data/web`.
   - Use ALB for public HTTPS.

### Azure options

1. `Azure VM + Docker Compose` (closest to local):
   - Provision Ubuntu VM, install Docker/Compose, deploy repo and run compose.
   - Persist with managed disk.
2. `Azure Container Apps` (managed):
   - Push image to ACR.
   - Deploy container app with mounted Azure Files for `/data/...`.
   - Configure ingress on `443` and custom domain/TLS.

### Cloud notes

- Set environment variables in platform config rather than editing image.
- Keep `site-config.yml` in mounted storage or convert to env/secret management.
- Validate timezone (`TZ`) and clock sync, since timestamps are user-visible.

## Authorship note

This repository includes code and documentation co-authored with AI assistance.
