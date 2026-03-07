# Deploying This System On Amazon Lightsail

This guide explains how to run this Skew-T system on `Amazon Lightsail` in the simplest cloud setup that still supports secure radiosonde uploads.

The intended reader is comfortable using Linux and editing configuration files, but may know very little about cloud services.

Useful AWS documentation:

- Lightsail getting started: <https://docs.aws.amazon.com/lightsail/latest/userguide/getting-started-with-amazon-lightsail.html>
- Lightsail pricing: <https://aws.amazon.com/lightsail/pricing/>
- Lightsail static IPs: <https://docs.aws.amazon.com/lightsail/latest/userguide/lightsail-create-static-ip.html>
- Lightsail static IP behavior: <https://docs.aws.amazon.com/en_us/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html>
- Lightsail firewall and port settings: <https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html>

## Why Amazon Lightsail is the recommended cloud option

If you are new to cloud platforms, `Amazon Lightsail` is the easiest AWS service to understand for this project.

In plain terms, Lightsail is a rented Linux computer in a data center with:

- a fixed monthly price
- a web console
- a public internet address
- simple firewall settings

That is a good match for this project because this repository needs:

- one Ubuntu server
- Docker and Docker Compose
- one VPN port open for WireGuard
- persistent storage for uploaded files and generated plots

This is simpler than using more advanced AWS services such as EC2, ECS, or App Runner.

## What this cloud deployment looks like

The basic design is:

1. create one Ubuntu Lightsail server
2. give it a static public IP address
3. install Docker and Docker Compose on that server
4. clone this repository onto the server
5. run the WireGuard setup helper from this repository
6. start the Docker stack
7. connect the receiver-side computer by WireGuard and upload by FTP through the VPN

This keeps the design close to a normal Linux server. That is why it is the easiest option for colleagues who do not want to learn a lot of cloud-specific tooling.

## A few cloud terms in plain language

Here are the only cloud words you really need:

- `instance`: the cloud provider's word for a virtual Linux server
- `static IP`: a public internet address that stays the same over time
- `firewall rule`: a setting that allows or blocks incoming network traffic
- `snapshot`: a saved backup image of the server disk
- `data transfer`: network traffic sent from the server to other machines

## What you need before starting

- an AWS account
- a public DNS name, or willingness to use the server's public IP address
- this repository available somewhere you can clone from the server
- a rough idea of whether the Skew-T website should be private or public

## Step 1: Create a Lightsail server

In the Lightsail web console:

1. create a new instance
2. choose `Linux/Unix`
3. choose `Ubuntu`
4. choose the smallest plan that is reasonable for Docker and plotting
5. give the server a clear name

For most users, starting small is fine. You can scale up later if needed.

If you want AWS's step-by-step page while doing this, use:

- <https://docs.aws.amazon.com/lightsail/latest/userguide/getting-started-with-amazon-lightsail.html>

## Step 2: Attach a static IP

This step is important.

Without a static IP, the server's public IP address may change if the instance is stopped and started again. That would break the WireGuard client configuration on the receiver-side computer.

In Lightsail:

1. create a static IP
2. attach it to your new instance

Use this static IP, or a DNS name pointing to it, as the `--endpoint` value when you run the WireGuard setup helper.

AWS documentation:

- create and attach a static IP: <https://docs.aws.amazon.com/lightsail/latest/userguide/lightsail-create-static-ip.html>
- understand static IP behavior and why it matters: <https://docs.aws.amazon.com/en_us/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html>

## Step 3: Open the required firewall ports

In the Lightsail networking or firewall section, open:

- `60000/udp` for WireGuard

If you want the web UI visible from outside the server, also open one of these:

- `8080/tcp` for the current simple setup
- or `80/tcp` and `443/tcp` later if you place a reverse proxy in front

If you only need private data ingestion and do not need the website publicly visible, you can leave the web port closed.

AWS documentation for firewall rules:

- <https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html>

## Step 4: Log into the server

Use the Lightsail browser terminal or SSH from your own machine.

Once logged in, update the system:

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

## Step 5: Install Docker and Docker Compose

If Docker is not already installed:

```bash
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Then log out and log back in so your shell sees the updated Docker group membership.

Verify:

```bash
docker --version
docker compose version
```

If you are unfamiliar with the Lightsail browser terminal or SSH access, the general getting-started page above is the best AWS reference while doing these steps.

## Step 6: Clone this repository

Choose a working directory and clone the repository:

```bash
git clone <REPOSITORY_URL>
cd skewt_server
```

If you are not using Git for deployment, copy the repository contents onto the server by another method and change into the repository directory.

## Step 7: Preview the WireGuard and FTP setup

Run the helper in dry-run mode first:

```bash
bash scripts/install_wireguard_host.sh \
  --endpoint your.static.ip.or.dns.name \
  --dry-run
```

Read the output carefully.

It will show:

- which packages will be installed
- which files will be written on the host
- which files will be written in the repository
- the generated FTP settings
- the generated Docker Compose override

This is the safest way to review the planned setup before making changes.

## Step 8: Run the real setup

If the dry run looks correct:

```bash
sudo bash scripts/install_wireguard_host.sh \
  --endpoint your.static.ip.or.dns.name
```

This will:

- install WireGuard
- create the host WireGuard configuration
- create a client WireGuard configuration for the receiver-side computer
- create `config/wireguard-ftp.env`
- create `docker-compose.ftp-wireguard.yml`

It will also print the generated FTP username and password.

## Step 9: Start the Docker stack

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml up -d
```

This starts:

- the existing Skew-T processor and website
- the FTP sidecar container used for uploads over the WireGuard VPN

## Step 10: Configure the receiver-side computer

Copy the generated client config from:

- `/etc/wireguard/clients/`

to the receiver-side computer.

Install a WireGuard client there and import that configuration.

Then configure the receiver to upload by passive FTP to the host's WireGuard IP, usually:

- `10.44.0.1`

Use the FTP username and password written in:

- `config/wireguard-ftp.env`

## Step 11: Test one upload

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

## Cost control notes

This is the part that often surprises people when they are new to cloud platforms.

AWS pricing page:

- <https://aws.amazon.com/lightsail/pricing/>

### 1. The server costs money as long as it exists

Even if nobody is using it, a cloud server usually costs money while it exists.

If you want the system always available, that is expected. Just treat it as a standing monthly service cost.

### 2. Static IPs are not something to create and forget

A static IP is useful and recommended here.

But if you create a static IP and then leave it unattached to a server, cloud providers may charge for that.

Rule of thumb:

- keep one static IP attached to the actual server
- delete any unused extra static IPs

AWS documentation:

- <https://docs.aws.amazon.com/en_us/lightsail/latest/userguide/understanding-static-ip-addresses-in-amazon-lightsail.html>

### 3. Backups can quietly add cost

Snapshots and backups are useful, but each one uses storage.

If you create many snapshots and never clean them up, monthly costs can slowly rise.

Rule of thumb:

- keep only the backups you really need
- delete old snapshots you no longer plan to use

### 4. Public website traffic can increase cost

If many people load the Skew-T website and download lots of images, the server sends more data out to the internet.

That outgoing traffic is often called `data transfer`.

For a small internal or research-facing site, this is often modest. But if the site becomes widely used, it can matter.

Rule of thumb:

- if the site is mainly for a small team, costs are likely modest
- if the site becomes public and popular, review monthly usage

### 5. Bigger servers cost more

Start with a smaller Lightsail plan unless you already know you need more CPU or memory.

You can scale up later if:

- plotting is too slow
- memory is too tight
- the server feels overloaded

### 6. Set a billing alert early

If AWS offers a billing alert or budget notification in your account, set it up early.

That way, if you accidentally create extra resources or usage grows unexpectedly, you will hear about it sooner.

## Recommended conservative cost strategy

For most users, a careful starting strategy is:

1. create one small Ubuntu Lightsail instance
2. attach one static IP
3. open only the ports you need
4. do not create extra disks, extra servers, or extra static IPs unless necessary
5. keep snapshots to a minimum
6. watch the monthly bill for the first month

## Common gotchas

### The server public IP changed

This usually means a static IP was not attached.

Fix:

- attach a static IP
- update the WireGuard endpoint if needed

### WireGuard does not connect from the receiver-side computer

Check:

- `60000/udp` is open in Lightsail
- the server is running
- the endpoint in the client config matches the static IP or DNS name
- the receiver-side computer actually started its WireGuard client

### The website works, but FTP upload does not

Check:

- the stack was started with `docker-compose.ftp-wireguard.yml`
- the receiver is configured for passive FTP
- the receiver is sending to the WireGuard IP, not the public IP

### Costs are higher than expected

Check for:

- unused snapshots
- extra instances
- unattached static IPs
- unexpectedly high public traffic to the site

## Minimal recommended Lightsail deployment pattern

For this project, the simplest good cloud pattern is:

1. one Ubuntu Lightsail server
2. one attached static IP
3. one open UDP port for WireGuard
4. optionally one open web port for the UI
5. Docker Compose running this repository
6. WireGuard on the host
7. FTP running only on the WireGuard IP

That gives you the cloud equivalent of a single Linux server, which is the easiest mental model for colleagues to understand.
