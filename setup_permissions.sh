#!/usr/bin/env bash
set -euo pipefail

DDNS_CONFIG_DIR="/etc/ddns-agent"
DDNS_CONFIG_FILE="${DDNS_CONFIG_DIR}/config.enc.json"
DDNS_ENV_FILE="${DDNS_CONFIG_DIR}/agent.env"
DDNS_DATA_DIR="/var/lib/ddns-agent"
FLASK_DB_PATH="${FLASK_DB_PATH:-${DDNS_DATA_DIR}/webapp.db}"
SUDOERS_FILE="/etc/sudoers.d/ddns-admin"

if ! id -u ddns-admin >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash ddns-admin
fi

if ! id -u ddns-agent >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin ddns-agent
fi

install -d -m 0750 -o root -g root "${DDNS_CONFIG_DIR}"
install -d -m 0750 -o ddns-agent -g ddns-agent "${DDNS_DATA_DIR}"

if [[ ! -f "${DDNS_CONFIG_FILE}" ]]; then
  install -m 0400 -o ddns-agent -g ddns-agent /dev/null "${DDNS_CONFIG_FILE}"
else
  chown ddns-agent:ddns-agent "${DDNS_CONFIG_FILE}"
  chmod 0400 "${DDNS_CONFIG_FILE}"
fi

if [[ ! -f "${DDNS_ENV_FILE}" ]]; then
  install -m 0400 -o root -g root /dev/null "${DDNS_ENV_FILE}"
else
  chown root:root "${DDNS_ENV_FILE}"
  chmod 0400 "${DDNS_ENV_FILE}"
fi

if [[ ! -f "${FLASK_DB_PATH}" ]]; then
  install -m 0640 -o ddns-admin -g ddns-admin /dev/null "${FLASK_DB_PATH}"
else
  chown ddns-admin:ddns-admin "${FLASK_DB_PATH}"
  chmod 0640 "${FLASK_DB_PATH}"
fi

cat > "${SUDOERS_FILE}" <<'EOF'
ddns-admin ALL=(root) NOPASSWD: /bin/systemctl reload ddns-agent
EOF
chmod 0440 "${SUDOERS_FILE}"
