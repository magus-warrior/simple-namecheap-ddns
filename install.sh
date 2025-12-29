#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="ddns-agent.service"
SYSTEMD_DIR="/etc/systemd/system"
SYSTEMD_SERVICE_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"
AGENT_ENV_FILE="/etc/ddns-agent/agent.env"
REPO_SERVICE_FILE="${REPO_ROOT}/${SERVICE_NAME}"
START_FILE="${REPO_ROOT}/start.sh"
REQUIREMENTS_FILE="${REPO_ROOT}/requirements.txt"

color() {
  local code="$1"
  shift
  printf "\033[%sm%s\033[0m" "$code" "$*"
}

info() {
  echo "$(color 32 "[INFO]") $*"
}

warn() {
  echo "$(color 33 "[WARN]") $*" >&2
}

error() {
  echo "$(color 31 "[ERROR]") $*" >&2
}

ensure_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    error "This option must be run as root."
    return 1
  fi
}

find_python() {
  local python_bin
  python_bin="$(which python3 2>/dev/null || true)"
  if [[ -z "$python_bin" ]]; then
    python_bin="$(which python 2>/dev/null || true)"
  fi

  if [[ -z "$python_bin" ]]; then
    error "Unable to find python or python3 in PATH."
    return 1
  fi

  python_bin="$(readlink -f "$python_bin" 2>/dev/null || echo "$python_bin")"
  echo "$python_bin"
}

update_python_paths() {
  local python_bin
  python_bin="$(find_python)"

  if [[ -f "$REPO_SERVICE_FILE" ]]; then
    sed -i -E "s#^ExecStart=.*#ExecStart=/var/lib/ddns-agent/start-agent.sh#" "$REPO_SERVICE_FILE"
    info "Updated ${REPO_SERVICE_FILE} ExecStart."
  else
    warn "Missing ${REPO_SERVICE_FILE}; cannot update ExecStart."
  fi

  if [[ -f "$START_FILE" ]]; then
    sed -i -E "s#^PYTHON_BIN=.*#PYTHON_BIN=\"${python_bin}\"#" "$START_FILE"
    info "Updated ${START_FILE} PYTHON_BIN."
  else
    warn "Missing ${START_FILE}; cannot update PYTHON_BIN."
  fi
}

setup_permissions() {
  ensure_root

  local config_dir="/etc/ddns-agent"
  local config_file="${config_dir}/config.enc.json"
  local env_file="${config_dir}/agent.env"
  local data_dir="/var/lib/ddns-agent"
  local flask_db_path="${FLASK_DB_PATH:-${data_dir}/webapp.db}"
  local sudoers_file="/etc/sudoers.d/ddns-admin"

  if ! id -u ddns-admin >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash ddns-admin
    info "Created user ddns-admin."
  fi

  if ! id -u ddns-agent >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin ddns-agent
    info "Created user ddns-agent."
  fi

  install -d -m 0750 -o root -g root "${config_dir}"
  install -d -m 0750 -o ddns-agent -g ddns-agent "${data_dir}"

  if [[ ! -f "${config_file}" ]]; then
    install -m 0400 -o ddns-agent -g ddns-agent /dev/null "${config_file}"
  else
    chown ddns-agent:ddns-agent "${config_file}"
    chmod 0400 "${config_file}"
  fi

  if [[ ! -f "${env_file}" ]]; then
    install -m 0400 -o root -g root /dev/null "${env_file}"
  else
    chown root:root "${env_file}"
    chmod 0400 "${env_file}"
  fi

  if ! grep -q '^DDNS_WORKDIR=' "${env_file}"; then
    chmod 0600 "${env_file}"
    echo "DDNS_WORKDIR=${REPO_ROOT}" >> "${env_file}"
    chmod 0400 "${env_file}"
  fi

  if ! grep -q '^AGENT_MASTER_KEY=' "${env_file}"; then
    chmod 0600 "${env_file}"
    local agent_key
    agent_key="$(python3 - <<'PY'
import base64
import os

print(base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8"))
PY
)"
    echo "AGENT_MASTER_KEY=${agent_key}" >> "${env_file}"
    chmod 0400 "${env_file}"
    info "Generated AGENT_MASTER_KEY in ${env_file}."
  fi

  if [[ ! -f "${flask_db_path}" ]]; then
    install -m 0640 -o ddns-admin -g ddns-admin /dev/null "${flask_db_path}"
  else
    chown ddns-admin:ddns-admin "${flask_db_path}"
    chmod 0640 "${flask_db_path}"
  fi

  cat > "${sudoers_file}" <<'EOF'
ddns-admin ALL=(root) NOPASSWD: /bin/systemctl reload ddns-agent
EOF
  chmod 0440 "${sudoers_file}"
  info "Permissions and system users configured."
}

install_service() {
  ensure_root

  if [[ ! -f "$REPO_SERVICE_FILE" ]]; then
    error "Missing ${REPO_SERVICE_FILE}."
    return 1
  fi

  install -m 0644 "$REPO_SERVICE_FILE" "$SYSTEMD_SERVICE_PATH"
  systemctl daemon-reload
  info "Installed ${SERVICE_NAME} to ${SYSTEMD_SERVICE_PATH}."

  if systemctl is-enabled --quiet "$SERVICE_NAME"; then
    info "${SERVICE_NAME} is already enabled."
  else
    read -r -p "Enable ${SERVICE_NAME} on boot? [y/N]: " enable_choice
    if [[ "${enable_choice,,}" == "y" ]]; then
      systemctl enable "$SERVICE_NAME"
      info "Enabled ${SERVICE_NAME}."
    fi
  fi

  read -r -p "Start/restart ${SERVICE_NAME} now? [y/N]: " start_choice
  if [[ "${start_choice,,}" == "y" ]]; then
    systemctl restart "$SERVICE_NAME"
    info "Restarted ${SERVICE_NAME}."
  fi
}

install_dependencies() {
  local python_bin
  python_bin="$(find_python)"

  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    warn "Missing ${REQUIREMENTS_FILE}; nothing to install."
    return 0
  fi

  if ! "$python_bin" -m pip --version >/dev/null 2>&1; then
    info "pip not found, attempting to bootstrap with ensurepip."
    "$python_bin" -m ensurepip --upgrade
  fi

  "$python_bin" -m pip install --upgrade pip
  "$python_bin" -m pip install -r "$REQUIREMENTS_FILE"
  info "Python dependencies installed."
}

verify_paths() {
  local python_bin
  if ! python_bin="$(find_python)"; then
    return 1
  fi

  info "Python detected: ${python_bin}"

  if [[ -f "$START_FILE" ]]; then
    local start_python
    start_python="$(rg -n '^PYTHON_BIN=' "$START_FILE" | sed -E 's/^PYTHON_BIN="?(.*)"?$/\1/')"
    info "start.sh PYTHON_BIN: ${start_python:-"(not set)"}"
  else
    warn "Missing ${START_FILE}."
  fi

  if [[ -f "$REPO_SERVICE_FILE" ]]; then
    local repo_exec
    repo_exec="$(rg -n '^ExecStart=' "$REPO_SERVICE_FILE" | sed -E 's/^ExecStart=//')"
    info "Repo service ExecStart: ${repo_exec:-"(not set)"}"
  else
    warn "Missing ${REPO_SERVICE_FILE}."
  fi

  if [[ -f "$SYSTEMD_SERVICE_PATH" ]]; then
    local system_exec
    system_exec="$(rg -n '^ExecStart=' "$SYSTEMD_SERVICE_PATH" | sed -E 's/^ExecStart=//')"
    info "Systemd ExecStart: ${system_exec:-"(not set)"}"
  else
    warn "Systemd service not installed at ${SYSTEMD_SERVICE_PATH}."
  fi

  if [[ -f "$AGENT_ENV_FILE" ]]; then
    local workdir
    workdir="$(rg -n '^DDNS_WORKDIR=' "$AGENT_ENV_FILE" | sed -E 's/^DDNS_WORKDIR=//')"
    info "DDNS_WORKDIR: ${workdir:-"(not set)"}"
    if [[ -n "$workdir" && "$workdir" != "$REPO_ROOT" ]]; then
      warn "DDNS_WORKDIR does not match repo root (${REPO_ROOT})."
    fi
    local agent_key
    agent_key="$(rg -n '^AGENT_MASTER_KEY=' "$AGENT_ENV_FILE" | sed -E 's/^AGENT_MASTER_KEY=//')"
    if [[ -z "$agent_key" ]]; then
      warn "AGENT_MASTER_KEY missing in ${AGENT_ENV_FILE}."
    else
      info "AGENT_MASTER_KEY: (set)"
    fi
  else
    warn "Missing ${AGENT_ENV_FILE}."
  fi
}

update_repo() {
  if ! command -v git >/dev/null 2>&1; then
    error "git is required to update the repository."
    return 1
  fi

  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    error "${REPO_ROOT} is not a git repository."
    return 1
  fi

  local status
  status="$(git -C "$REPO_ROOT" status --porcelain)"
  if [[ -n "$status" ]]; then
    warn "Working tree has uncommitted changes. Update may fail."
  fi

  git -C "$REPO_ROOT" pull --rebase
  info "Repository updated."
}

print_menu() {
  cat <<'EOF'
Simple Namecheap DDNS Installer
================================
1) Verify paths and environment
2) Update python paths in service/start scripts
3) Install/update Python dependencies
4) Configure system users and permissions (root)
5) Install/update systemd service (root)
6) Update repository (git pull)
q) Quit
EOF
}

main() {
  while true; do
    print_menu
    read -r -p "Select an option: " choice
    case "${choice,,}" in
      1)
        verify_paths
        ;;
      2)
        update_python_paths
        ;;
      3)
        install_dependencies
        ;;
      4)
        setup_permissions
        ;;
      5)
        install_service
        ;;
      6)
        update_repo
        ;;
      q)
        info "Exiting installer."
        break
        ;;
      *)
        warn "Unknown option: ${choice}"
        ;;
    esac
    echo
  done
}

main "$@"
