# Skew-T Container

Dockerized service that:
- scans a mounted work folder for new `*SHARPY.txt` (also accepts common `*SHARPPY.txt`)
- generates Skew-T diagrams with `sounderpy`
- avoids regenerating existing images
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

## Directory mounts

- `./data/work` -> `/data/work` (incoming `*SHARPY.txt`)
- `./data/output` -> `/data/output` (generated PNGs)
- `./data/web` -> `/data/web` (served image/text copies + manifest)
- `./site-config.yml` -> `/data/site-config.yml` (site metadata)

## Environment variables

- `SCAN_INTERVAL_MINUTES` (default `5`): cron interval for processing run. Integer `1-59`.
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

## Testing workflow

1. Start stack: `docker compose up --build`
2. Copy one or more sample `*SHARPY.txt` files into `./data/work`
3. Wait one interval or force immediate run:
   - `docker compose exec skewt /opt/venv/bin/python -m app.processor`
4. Verify:
   - images appear under `./data/output` and `./data/web/images`
   - source files appear under `./data/web/sharpy`
   - browser shows latest sounding first at `http://localhost:8080`
   - launch date/time labels are shown for each sounding
5. Re-run processor and confirm existing outputs are skipped.

## Notes

- Cron and web server run in the same container.
- The startup script runs one initial processing pass immediately before cron begins.

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

## Public hosting on a desktop/server with Docker

Use this when you have a machine at home/office with Docker Desktop or Docker Engine and want internet access to the site.

1. Prepare host:
   - Install Docker + Docker Compose.
   - Open firewall for TCP `8080`.
2. Run service:
   - `docker compose up -d --build`
3. Persist data:
   - Keep `data/work`, `data/output`, `data/web`, and `site-config.yml` on local disk (already mounted by `docker-compose.yml`).
4. Expose publicly:
   - Configure router/NAT port-forward from public `80/443` (or `8080`) to this host.
   - Prefer a reverse proxy (`nginx`, `caddy`, or `traefik`) for TLS certificates and cleaner public URL.
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
