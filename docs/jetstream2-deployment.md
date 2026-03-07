# Deploying This System On Jetstream2

This guide explains how to run this Skew-T system on `Jetstream2` as research infrastructure.

The intended reader is comfortable using Linux and editing configuration files, but may know very little about cloud services or about Jetstream2 specifically.

## Why Jetstream2 is a good fit for this project

Jetstream2 is a research cloud. In plain terms, it gives you a Linux server that you can control, much like a normal virtual machine on a commercial cloud service.

That matches this project well because this repository needs:

- one Linux server
- Docker and Docker Compose
- one incoming VPN port for WireGuard
- persistent storage for uploaded files and generated plots

This is a good fit for a radiosonde workflow because:

- you can run the Docker stack on one server
- you can run WireGuard on the server host
- you can keep FTP private by exposing it only over the WireGuard VPN

## Important note about access

Jetstream2 is free to eligible U.S. researchers and educators through `ACCESS`, but it is not automatic.

You should expect to need:

1. an `ACCESS ID`
2. a valid Jetstream2 allocation

If you are faculty or research staff at a U.S. university, you are likely eligible. But you still need to go through the account and allocation process.

Useful Jetstream2 and ACCESS documentation:

- Jetstream2 getting started: <https://jetstream-cloud.org/get-started/index.html>
- Jetstream2 allocations overview: <https://docs.jetstream-cloud.org/alloc/overview/>
- ACCESS user registration: <https://identity.access-ci.org/new-user>
- ACCESS allocations overview: <https://allocations.access-ci.org/overview>

## A few terms in plain language

These are the only Jetstream2-related terms you really need:

- `ACCESS ID`: the account you use to access Jetstream2 and request allocations
- `allocation`: the approved amount of Jetstream2 resources you are allowed to use
- `instance`: Jetstream2's word for a Linux virtual machine
- `Exosphere`: the easiest web interface for launching and managing Jetstream2 instances
- `floating IP`: Jetstream2's public internet address for a server
- `security group`: a firewall rule set controlling which ports can be reached

## What you need before starting

- an ACCESS ID
- a Jetstream2 allocation that you can use for a persistent server
- a domain name if you want a friendly hostname for the web interface
- this repository available somewhere you can clone from the Jetstream2 server
- a plan for whether the web UI should be public or private

For a real service, do not rely on the Jetstream2 trial allocation. The trial allocation is intentionally small and temporary.

Jetstream2 documentation for trial allocations:

- <https://docs.jetstream-cloud.org/alloc/trial/>

## What this deployment looks like

The simplest Jetstream2 design is:

1. request or confirm a Jetstream2 allocation
2. create one Ubuntu instance in Exosphere
3. associate a public IP address with that instance
4. install Docker and Docker Compose
5. clone this repository
6. run the WireGuard helper script from this repository
7. start the Docker stack
8. configure the receiver-side computer to connect over WireGuard and upload by FTP

This keeps the entire design close to a single Linux server, which is the easiest way to reason about it.

## Step 1: Get access to Jetstream2

If you do not already have an ACCESS ID, create one:

- <https://identity.access-ci.org/new-user>

Then make sure you have a usable Jetstream2 allocation:

- <https://docs.jetstream-cloud.org/alloc/overview/>

The Jetstream2 getting-started page is:

- <https://jetstream-cloud.org/get-started/index.html>

## Step 2: Log in to Jetstream2

The simplest interface for most users is `Exosphere`.

Jetstream2 login:

- <https://jetstream2.exosphere.app>

When you log in, select the allocation you want to use for this server.

## Step 3: Create an Ubuntu instance

Use Exosphere to create one Ubuntu instance.

If you are unsure what to choose:

- choose the newest Ubuntu version
- keep most options at their defaults
- give the instance a clear, descriptive name

Jetstream2 instance creation guide:

- <https://docs.jetstream-cloud.org/ui/exo/create_instance/>

Important practical notes from Jetstream2 documentation:

- the smallest size is fine for exploration, but larger sizes consume your allocation more quickly
- the default disk size may be too small if you plan to keep a growing collection of sounding files and images
- most users can ignore the advanced options at first

For this project, choose a size that is comfortably large enough for:

- Docker
- plotting
- some persistent storage growth

## Step 4: Be careful with Jetstream2 network defaults

This is the most important Jetstream2-specific warning.

Jetstream2 documentation says that in `Exosphere`, the default security group allows all inbound access.

That means you should not assume the server is locked down automatically.

Jetstream2 security documentation:

- <https://docs.jetstream-cloud.org/faq/security/>

You should take a defense-in-depth approach:

1. limit incoming ports with Jetstream2 security groups if possible
2. also use a host-based firewall such as `ufw`
3. only expose the minimum set of ports needed

For this project, that usually means:

- `51820/udp` for WireGuard
- optionally `8080/tcp` for the web UI
- do not expose FTP publicly

Example `ufw` commands on the Jetstream2 host:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 51820/udp
sudo ufw allow 8080/tcp
sudo ufw enable
sudo ufw status
```

If you do not want the web UI public, omit the `8080/tcp` rule.

Do not open FTP ports such as `21/tcp` or the passive FTP port range on the public interface. In this design, FTP should only be reachable over WireGuard.

## Step 5: Associate a public IP address

Your Jetstream2 instance needs a public IP so the receiver-side computer can find the WireGuard server.

Jetstream2 often calls this a `floating IP`.

This is the address you will use as the WireGuard endpoint, either directly or through a DNS name.

The instance creation guide and Exosphere interface will help you create and attach the public IP.

Instance creation guide:

- <https://docs.jetstream-cloud.org/ui/exo/create_instance/>

## Step 6: Connect to the instance

Once the instance is online, connect by SSH or use the web console if available.

Update the system:

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

## Step 7: Install Docker and Docker Compose

If Docker is not already installed:

```bash
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Then log out and log back in so your shell recognizes the updated Docker group membership.

Verify:

```bash
docker --version
docker compose version
```

Jetstream2 documentation notes that Jetstream featured images include Docker. Even so, it is still reasonable to verify the local installation on your chosen Ubuntu image.

Jetstream2 Docker documentation:

- <https://docs.jetstream-cloud.org/general/docker/>

## Step 8: Clone this repository

Clone the repository onto the Jetstream2 instance:

```bash
git clone <REPOSITORY_URL>
cd skewt_server
```

If you are not deploying by Git, copy the repository contents onto the instance and change into the repository directory.

## Step 9: Preview the WireGuard and FTP setup

Run the helper in dry-run mode first:

```bash
bash scripts/install_wireguard_host.sh \
  --endpoint your.public.ip.or.dns.name \
  --dry-run
```

Read the output carefully.

It will show:

- which packages will be installed
- which host files will be written
- which repository files will be written
- the generated FTP settings
- the generated Docker Compose override

This is the safest way to review the setup before making changes.

## Step 10: Run the real setup

If the dry run looks correct:

```bash
sudo bash scripts/install_wireguard_host.sh \
  --endpoint your.public.ip.or.dns.name
```

This will:

- install WireGuard
- create the host WireGuard configuration
- create a client WireGuard configuration for the receiver-side computer
- create `config/wireguard-ftp.env`
- create `docker-compose.ftp-wireguard.yml`

It will also print the generated FTP username and password.

## Step 11: Start the Docker stack

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml up -d
```

This starts:

- the existing Skew-T processor and website
- the FTP sidecar container used for uploads over the WireGuard VPN

## Step 12: Configure the receiver-side computer

Copy the generated client config from:

- `/etc/wireguard/clients/`

to the receiver-side computer.

Install a WireGuard client there and import that configuration.

Then configure the receiver to upload by passive FTP to the host's WireGuard IP, usually:

- `10.44.0.1`

Use the FTP username and password written in:

- `config/wireguard-ftp.env`

## Step 13: Test one upload

Before treating the system as operational, test one representative upload.

Check:

1. the receiver-side computer can bring up the WireGuard tunnel
2. the receiver can reach FTP on the WireGuard IP
3. the uploaded file appears in `data/work`
4. the generated image appears in `data/output`
5. the web UI shows the new sounding

Useful commands on the server:

```bash
sudo wg show
docker compose ps
docker compose logs skewt
docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml logs ftp
```

## Optional: make the web UI easier to reach

Jetstream2 documents how to run a web server with automatic HTTPS and a custom domain name.

You do not need that for basic operation, but it can make the web UI easier to share.

Jetstream2 web server documentation:

- <https://docs.jetstream-cloud.org/general/webserver/>

If you later want a cleaner public URL, the usual next step would be:

1. point a DNS name at the Jetstream2 instance
2. add a reverse proxy such as Caddy in front of the web UI
3. serve the site over HTTPS

## Resource and quota caution

Jetstream2 is not billed like a commercial cloud account, but it is still limited by your allocation.

That means you should think about resource use even if you are not getting a monthly invoice.

Practical cautions:

- larger instances consume your allocation more quickly
- bigger disks and longer runtimes use more of your available resources
- trial allocations are too small for a real long-running service

You should treat allocation usage the same way you would treat cost on a commercial cloud:

- start small
- confirm the workflow works
- scale only if needed

## Common gotchas

### I can log into the server, but WireGuard does not connect

Check:

- the public IP or DNS name in the client config is correct
- `51820/udp` is allowed
- the server is actually running WireGuard

Useful commands:

```bash
sudo systemctl status wg-quick@wg0
sudo wg show
```

### The website works, but FTP upload does not

Check:

- the stack was started with `docker-compose.ftp-wireguard.yml`
- the receiver is configured for passive FTP
- the receiver is connecting to the WireGuard IP, not the public IP
- FTP was not accidentally exposed publicly instead of only over WireGuard

### The server is unexpectedly exposed to the internet

This is often caused by broad Jetstream2 security-group settings or no host firewall.

Remember:

- Jetstream2 documentation says Exosphere defaults can allow all inbound traffic
- you should explicitly restrict access

## Minimal recommended Jetstream2 deployment pattern

For this project, the simplest good Jetstream2 pattern is:

1. one Ubuntu instance
2. one public IP
3. WireGuard on the host
4. Docker Compose running this repository
5. one FTP sidecar container bound only to the WireGuard IP
6. minimum necessary open ports

That gives you a research-cloud version of a single Linux server, which is the easiest mental model for colleagues to understand.
