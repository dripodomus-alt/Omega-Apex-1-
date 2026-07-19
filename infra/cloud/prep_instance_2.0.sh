#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APEX_OMEGA_DIR:-/opt/apex-omega}"
REPO_URL="${APEX_REPO_URL:-}"
BRANCH="${APEX_REPO_BRANCH:-main}"
OPEN_DASHBOARD_PORT="${APEX_OPEN_DASHBOARD_PORT:-true}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./prep_instance_2.0.sh" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git ufw fail2ban gnupg lsb-release

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker
systemctl enable --now fail2ban || true

if [[ -n "${REPO_URL}" ]]; then
  if [[ -d "${APP_DIR}/.git" ]]; then
    git -C "${APP_DIR}" fetch origin "${BRANCH}"
    git -C "${APP_DIR}" checkout "${BRANCH}"
    git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
  else
    rm -rf "${APP_DIR}"
    git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
  fi
else
  mkdir -p "${APP_DIR}"
  if [[ ! -f "${APP_DIR}/docker-compose.yml" ]]; then
    echo "No APEX_REPO_URL provided and ${APP_DIR}/docker-compose.yml is absent." >&2
    echo "Upload this repo to ${APP_DIR} or rerun with APEX_REPO_URL=https://..." >&2
    exit 2
  fi
fi

cd "${APP_DIR}"
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    chmod 600 .env
    echo "Created ${APP_DIR}/.env from .env.example. Populate signer/RPC secrets before enabling live execution."
  else
    touch .env
    chmod 600 .env
    echo "Created blank ${APP_DIR}/.env. Populate signer/RPC secrets before enabling live execution."
  fi
fi

mkdir -p out cache logs
chmod 700 out cache logs || true

ufw allow OpenSSH || true
if [[ "${OPEN_DASHBOARD_PORT}" == "true" ]]; then
  ufw allow 8080/tcp || true
fi
ufw --force enable || true

docker compose build omega
docker compose up -d redis omega

echo ""
echo "Apex-Omega cloud stack submitted."
echo "Dashboard: http://<server-ip>:8080/"
echo "Health:    http://<server-ip>:8080/health"
echo "Status:    http://<server-ip>:8080/api/runtime/status"
echo "Logs:      cd ${APP_DIR} && docker compose logs -f omega"
echo "Mobile tunnel: set CLOUDFLARED_TOKEN in .env, then docker compose --profile mobile-tunnel up -d cloudflared"
