#!/usr/bin/env bash
set -euo pipefail

# This script does two jobs:
# 1. configure a host-side WireGuard server and generate one client config
# 2. generate repo-local Docker Compose artifacts for the FTP sidecar
#
# The generated repo files let the FTP container bind only to the WireGuard IP
# and reuse the same FTP settings on future runs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_DIR="${REPO_ROOT}/config"
FTP_ENV_FILE="${CONFIG_DIR}/wireguard-ftp.env"
FTP_OVERRIDE_FILE="${REPO_ROOT}/docker-compose.ftp-wireguard.yml"

WG_IFACE="wg0"
WG_PORT="60000"
WG_SERVER_IP="10.44.0.1/24"
WG_CLIENT_IP="10.44.0.2/32"
WG_CLIENT_NAME="receiver-laptop"
WG_ENDPOINT=""

FTP_USER="radiosonde"
FTP_PASS=""
FTP_PASV_MIN_PORT="30000"
FTP_PASV_MAX_PORT="30009"

DRY_RUN=0

WG_DIR="/etc/wireguard"
WG_CLIENT_DIR="${WG_DIR}/clients"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_wireguard_host.sh [options]

Options:
  --endpoint HOSTNAME_OR_IP   Required. Public DNS name or IP for the host.
  --iface NAME                WireGuard interface name. Default: wg0
  --port PORT                 WireGuard UDP port. Default: 60000
  --server-ip CIDR            Host WireGuard IP/CIDR. Default: 10.44.0.1/24
  --client-ip CIDR            Client WireGuard IP/CIDR. Default: 10.44.0.2/32
  --client-name NAME          Client config name. Default: receiver-laptop
  --ftp-user NAME             FTP username. Default: radiosonde
  --ftp-pass PASSWORD         FTP password. Default: generated on first real install
  --ftp-pasv-min-port PORT    Passive FTP min port. Default: 30000
  --ftp-pasv-max-port PORT    Passive FTP max port. Default: 30009
  --dry-run                   Preview packages, paths, and configs without changes.
  --help                      Show this help text.

Examples:
  bash scripts/install_wireguard_host.sh --endpoint your.host.example.org --dry-run
  sudo bash scripts/install_wireguard_host.sh --endpoint your.host.example.org
EOF
}

# Parse a simple flag-based CLI so the script is easy to use over SSH and in docs.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --endpoint)
      WG_ENDPOINT="${2:-}"
      shift 2
      ;;
    --iface)
      WG_IFACE="${2:-}"
      shift 2
      ;;
    --port)
      WG_PORT="${2:-}"
      shift 2
      ;;
    --server-ip)
      WG_SERVER_IP="${2:-}"
      shift 2
      ;;
    --client-ip)
      WG_CLIENT_IP="${2:-}"
      shift 2
      ;;
    --client-name)
      WG_CLIENT_NAME="${2:-}"
      shift 2
      ;;
    --ftp-user)
      FTP_USER="${2:-}"
      shift 2
      ;;
    --ftp-pass)
      FTP_PASS="${2:-}"
      shift 2
      ;;
    --ftp-pasv-min-port)
      FTP_PASV_MIN_PORT="${2:-}"
      shift 2
      ;;
    --ftp-pasv-max-port)
      FTP_PASV_MAX_PORT="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${WG_ENDPOINT}" ]]; then
  echo "--endpoint is required." >&2
  echo >&2
  usage >&2
  exit 1
fi

for numeric_arg in WG_PORT FTP_PASV_MIN_PORT FTP_PASV_MAX_PORT; do
  value="${!numeric_arg}"
  if ! [[ "${value}" =~ ^[0-9]+$ ]] || [[ "${value}" -lt 1 ]] || [[ "${value}" -gt 65535 ]]; then
    echo "${numeric_arg} must be an integer between 1 and 65535." >&2
    exit 1
  fi
done

if [[ "${FTP_PASV_MIN_PORT}" -gt "${FTP_PASV_MAX_PORT}" ]]; then
  echo "--ftp-pasv-min-port must be less than or equal to --ftp-pasv-max-port." >&2
  exit 1
fi

if [[ -z "${FTP_USER}" ]]; then
  echo "--ftp-user must not be empty." >&2
  exit 1
fi

if [[ "${DRY_RUN}" -ne 1 && "${EUID}" -ne 0 ]]; then
  echo "Run as root, for example: sudo bash scripts/install_wireguard_host.sh --endpoint ${WG_ENDPOINT}" >&2
  exit 1
fi

SERVER_PRIV="${WG_DIR}/server_private.key"
SERVER_PUB="${WG_DIR}/server_public.key"
CLIENT_PRIV="${WG_CLIENT_DIR}/${WG_CLIENT_NAME}_private.key"
CLIENT_PUB="${WG_CLIENT_DIR}/${WG_CLIENT_NAME}_public.key"
WG_CONF="${WG_DIR}/${WG_IFACE}.conf"
CLIENT_CONF="${WG_CLIENT_DIR}/${WG_CLIENT_NAME}.conf"
SERVER_HOST_IP="$(printf '%s\n' "${WG_SERVER_IP}" | cut -d/ -f1)"

# Build a reproducible command line that reflects only the non-default values.
# This is shown during dry-run output so the user can copy the exact real command.
build_command_example() {
  local cmd="sudo bash scripts/install_wireguard_host.sh --endpoint ${WG_ENDPOINT}"
  [[ "${WG_IFACE}" != "wg0" ]] && cmd+=" --iface ${WG_IFACE}"
  [[ "${WG_PORT}" != "60000" ]] && cmd+=" --port ${WG_PORT}"
  [[ "${WG_SERVER_IP}" != "10.44.0.1/24" ]] && cmd+=" --server-ip ${WG_SERVER_IP}"
  [[ "${WG_CLIENT_IP}" != "10.44.0.2/32" ]] && cmd+=" --client-ip ${WG_CLIENT_IP}"
  [[ "${WG_CLIENT_NAME}" != "receiver-laptop" ]] && cmd+=" --client-name ${WG_CLIENT_NAME}"
  [[ "${FTP_USER}" != "radiosonde" ]] && cmd+=" --ftp-user ${FTP_USER}"
  [[ -n "${FTP_PASS}" ]] && cmd+=" --ftp-pass '${FTP_PASS}'"
  [[ "${FTP_PASV_MIN_PORT}" != "30000" ]] && cmd+=" --ftp-pasv-min-port ${FTP_PASV_MIN_PORT}"
  [[ "${FTP_PASV_MAX_PORT}" != "30009" ]] && cmd+=" --ftp-pasv-max-port ${FTP_PASV_MAX_PORT}"
  printf '%s\n' "${cmd}"
}

REAL_COMMAND_EXAMPLE="$(build_command_example)"

# Generate the env file that the FTP sidecar will consume at runtime.
# This file is intentionally repo-local so Docker Compose can use it later.
render_generated_env() {
  local ftp_password="$1"
  cat <<EOF
WIREGUARD_INTERFACE=${WG_IFACE}
WIREGUARD_HOST_IP=${SERVER_HOST_IP}
WIREGUARD_PORT=${WG_PORT}
FTP_BIND_IP=${SERVER_HOST_IP}
FTP_PASV_ADDRESS=${SERVER_HOST_IP}
FTP_PASV_MIN_PORT=${FTP_PASV_MIN_PORT}
FTP_PASV_MAX_PORT=${FTP_PASV_MAX_PORT}
PASV_ADDRESS=${SERVER_HOST_IP}
PASV_MIN_PORT=${FTP_PASV_MIN_PORT}
PASV_MAX_PORT=${FTP_PASV_MAX_PORT}
FTP_USER=${FTP_USER}
FTP_PASS=${ftp_password}
EOF
}

# Generate a Docker Compose override that adds the FTP sidecar with the correct
# bind IP and passive port range baked in for this host's WireGuard settings.
render_compose_override() {
  cat <<EOF
services:
  ftp:
    image: fauria/vsftpd
    container_name: skewt-ftp
    restart: unless-stopped
    env_file:
      - ./config/wireguard-ftp.env
    environment:
      PASV_ENABLE: "YES"
      PASV_ADDRESS: "${PASV_ADDRESS}"
      PASV_MIN_PORT: "${PASV_MIN_PORT}"
      PASV_MAX_PORT: "${PASV_MAX_PORT}"
    volumes:
      - ./data/work:/home/vsftpd/${FTP_USER}
    ports:
      - "${SERVER_HOST_IP}:21:21"
      - "${SERVER_HOST_IP}:${FTP_PASV_MIN_PORT}-${FTP_PASV_MAX_PORT}:${FTP_PASV_MIN_PORT}-${FTP_PASV_MAX_PORT}"
EOF
}

# Dry-run output shows exactly what will be generated on the host and in the repo.
# This avoids making users guess what the real install will touch.
render_configs() {
  local server_private_key="$1"
  local server_public_key="$2"
  local client_private_key="$3"
  local client_public_key="$4"
  local ftp_password="$5"

  cat <<EOF
Planned package installation:
  - wireguard
  - qrencode

Note:
  - The script will install the \`wg\` command by installing the \`wireguard\` package.

Planned host directories:
  - ${WG_DIR}
  - ${WG_CLIENT_DIR}

Planned host files:
  - ${SERVER_PRIV}
  - ${SERVER_PUB}
  - ${CLIENT_PRIV}
  - ${CLIENT_PUB}
  - ${WG_CONF}
  - ${CLIENT_CONF}

Planned repository files:
  - ${FTP_ENV_FILE}
  - ${FTP_OVERRIDE_FILE}

Server settings:
  - interface: ${WG_IFACE}
  - listen port: ${WG_PORT}
  - VPN address: ${WG_SERVER_IP}
  - public endpoint: ${WG_ENDPOINT}

Client settings:
  - client name: ${WG_CLIENT_NAME}
  - VPN address: ${WG_CLIENT_IP}

FTP settings:
  - username: ${FTP_USER}
  - password: ${ftp_password}
  - bind IP: ${SERVER_HOST_IP}
  - passive address: ${SERVER_HOST_IP}
  - passive ports: ${FTP_PASV_MIN_PORT}-${FTP_PASV_MAX_PORT}

Rendered server config:
[Interface]
Address = ${WG_SERVER_IP}
ListenPort = ${WG_PORT}
PrivateKey = ${server_private_key}
SaveConfig = false

[Peer]
PublicKey = ${client_public_key}
AllowedIPs = ${WG_CLIENT_IP}
PersistentKeepalive = 25

Rendered client config:
[Interface]
Address = ${WG_CLIENT_IP}
PrivateKey = ${client_private_key}
DNS = 1.1.1.1

[Peer]
PublicKey = ${server_public_key}
Endpoint = ${WG_ENDPOINT}:${WG_PORT}
AllowedIPs = ${SERVER_HOST_IP}/32
PersistentKeepalive = 25

Rendered FTP env file:
$(render_generated_env "${ftp_password}")

Rendered Compose override:
$(render_compose_override)

Example real install command with the current options:
  ${REAL_COMMAND_EXAMPLE}

Example stack startup with generated files:
  docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml up -d
EOF
}

# If `wg` is already installed, generate throwaway preview keys so the dry run
# looks like a real config. If it is not installed yet, use placeholders instead.
generate_preview_keys() {
  if command -v wg >/dev/null 2>&1; then
    local server_private_key server_public_key client_private_key client_public_key
    server_private_key="$(wg genkey)"
    server_public_key="$(printf '%s' "${server_private_key}" | wg pubkey)"
    client_private_key="$(wg genkey)"
    client_public_key="$(printf '%s' "${client_private_key}" | wg pubkey)"
    render_configs \
      "${server_private_key}" \
      "${server_public_key}" \
      "${client_private_key}" \
      "${client_public_key}" \
      "${FTP_PASS:-<ftp-password will be generated during install>}"
  else
    render_configs \
      "<server-private-key will be generated during install>" \
      "<server-public-key will be derived during install>" \
      "<client-private-key will be generated during install>" \
      "<client-public-key will be derived during install>" \
      "${FTP_PASS:-<ftp-password will be generated during install>}"
  fi
}

# Generate a reasonably strong alphanumeric FTP password from a finite amount of
# random data.
#
# The previous implementation used:
#   base64 </dev/urandom | tr -dc 'A-Za-z0-9' | cut -c1-24
# That can stall because `tr -dc` removes newlines, creating one endless line,
# and `cut -c1-24` is line-oriented: it can wait forever for end-of-line or EOF.
#
# This implementation feeds a finite chunk of random data through the pipeline
# and then uses `head -c 24`, which is byte-oriented and exits as soon as it has
# enough characters.
generate_password() {
  head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24
}

# Write the repo-local files that make the FTP sidecar match the host's
# WireGuard configuration. When run via sudo, hand the generated files back to
# the invoking user so they are easy to inspect and edit later.
write_repo_files() {
  local ftp_password="$1"
  install -d -m 755 "${CONFIG_DIR}"
  render_generated_env "${ftp_password}" >"${FTP_ENV_FILE}"
  render_compose_override >"${FTP_OVERRIDE_FILE}"
  chmod 600 "${FTP_ENV_FILE}"
  chmod 644 "${FTP_OVERRIDE_FILE}"
  if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
    chown "${SUDO_UID}:${SUDO_GID}" "${CONFIG_DIR}" "${FTP_ENV_FILE}" "${FTP_OVERRIDE_FILE}"
  fi
}

if [[ "${DRY_RUN}" -eq 1 ]]; then
  generate_preview_keys
  echo
  echo "Dry run only. No packages were installed, no files were written, and no services were started."
  exit 0
fi

apt-get update
apt-get install -y wireguard qrencode

# Create the WireGuard directory structure with root-only permissions before
# generating keys or configs.
install -d -m 700 "${WG_DIR}" "${WG_CLIENT_DIR}"

umask 077

# Reuse existing keys if present so rerunning the script does not silently rotate
# the server or client identity.
if [[ ! -f "${SERVER_PRIV}" ]]; then
  wg genkey >"${SERVER_PRIV}"
fi
wg pubkey <"${SERVER_PRIV}" >"${SERVER_PUB}"

if [[ ! -f "${CLIENT_PRIV}" ]]; then
  wg genkey >"${CLIENT_PRIV}"
fi
wg pubkey <"${CLIENT_PRIV}" >"${CLIENT_PUB}"

SERVER_PRIVATE_KEY="$(<"${SERVER_PRIV}")"
SERVER_PUBLIC_KEY="$(<"${SERVER_PUB}")"
CLIENT_PRIVATE_KEY="$(<"${CLIENT_PRIV}")"
CLIENT_PUBLIC_KEY="$(<"${CLIENT_PUB}")"

# Reuse a previously generated FTP password unless the user explicitly passed
# `--ftp-pass`. That keeps receiver-side configuration stable across reruns.
if [[ -z "${FTP_PASS}" ]]; then
  if [[ -f "${FTP_ENV_FILE}" ]]; then
    EXISTING_FTP_PASS="$(sed -n 's/^FTP_PASS=//p' "${FTP_ENV_FILE}" | head -n 1)"
    FTP_PASS="${EXISTING_FTP_PASS}"
  fi
  if [[ -z "${FTP_PASS}" ]]; then
    FTP_PASS="$(generate_password)"
  fi
fi

# Write the host-side WireGuard server config and the matching client config.
cat >"${WG_CONF}" <<EOF
[Interface]
Address = ${WG_SERVER_IP}
ListenPort = ${WG_PORT}
PrivateKey = ${SERVER_PRIVATE_KEY}
SaveConfig = false

[Peer]
PublicKey = ${CLIENT_PUBLIC_KEY}
AllowedIPs = ${WG_CLIENT_IP}
PersistentKeepalive = 25
EOF

cat >"${CLIENT_CONF}" <<EOF
[Interface]
Address = ${WG_CLIENT_IP}
PrivateKey = ${CLIENT_PRIVATE_KEY}
DNS = 1.1.1.1

[Peer]
PublicKey = ${SERVER_PUBLIC_KEY}
Endpoint = ${WG_ENDPOINT}:${WG_PORT}
AllowedIPs = ${SERVER_HOST_IP}/32
PersistentKeepalive = 25
EOF

chmod 600 "${WG_CONF}" "${SERVER_PRIV}" "${SERVER_PUB}" "${CLIENT_PRIV}" "${CLIENT_PUB}" "${CLIENT_CONF}"

write_repo_files "${FTP_PASS}"

# Enable the WireGuard interface immediately so the generated client config can
# be tested right away.
systemctl enable --now "wg-quick@${WG_IFACE}"

echo
echo "WireGuard server config written to: ${WG_CONF}"
echo "Client config written to: ${CLIENT_CONF}"
echo "FTP env file written to: ${FTP_ENV_FILE}"
echo "Compose override written to: ${FTP_OVERRIDE_FILE}"
echo
echo "Installed packages:"
echo "  - wireguard"
echo "  - qrencode"
echo
echo "FTP credentials:"
echo "  - username: ${FTP_USER}"
echo "  - password: ${FTP_PASS}"
echo
echo "Open UDP ${WG_PORT} on the host firewall if needed."
echo "Next step: start the stack with:"
echo "  docker compose -f docker-compose.yml -f docker-compose.ftp-wireguard.yml up -d"
echo
echo "Example rerun command for these same options:"
echo "  ${REAL_COMMAND_EXAMPLE}"
echo
echo "Client configuration:"
qrencode -t ansiutf8 <"${CLIENT_CONF}" || true
