#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="ddns-agent.service"
GUI_SERVICE_NAME="ddns-gui.service"
SYSTEMD_DIR="/etc/systemd/system"
SYSTEMD_SERVICE_PATH="${SYSTEMD_DIR}/${SERVICE_NAME}"
GUI_SYSTEMD_SERVICE_PATH="${SYSTEMD_DIR}/${GUI_SERVICE_NAME}"
REPO_SERVICE_FILE="${REPO_ROOT}/${SERVICE_NAME}"
GUI_REPO_SERVICE_FILE="${REPO_ROOT}/${GUI_SERVICE_NAME}"
START_FILE="${REPO_ROOT}/start.sh"
REQUIREMENTS_FILE="${REPO_ROOT}/requirements.txt"
CONFIG_DIR="${DDNS_CONFIG_DIR:-${REPO_ROOT}/.ddns}"
DATA_DIR="${DDNS_DATA_DIR:-${REPO_ROOT}/.ddns}"
AGENT_ENV_FILE="${CONFIG_DIR}/agent.env"
AGENT_CONFIG_FILE="${CONFIG_DIR}/config.enc.json"
AGENT_DB_FILE="${DATA_DIR}/agent.db"
SERVICE_USER="${DDNS_SERVICE_USER:-${SUDO_USER:-${USER:-ddns-agent}}}"
SUDO_BIN=""

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

confirm() {
  local prompt="$1"
  local response
  read -r -p "${prompt} [y/N]: " response
  [[ "${response,,}" == "y" ]]
}

ensure_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      SUDO_BIN="sudo"
    else
      error "This option must be run as root (sudo not available)."
      return 1
    fi
  fi
}

needs_root() {
  if [[ "${CONFIG_DIR}" == /etc/* || "${CONFIG_DIR}" == /var/* || "${DATA_DIR}" == /etc/* || "${DATA_DIR}" == /var/* ]]; then
    return 0
  fi
  return 1
}

find_python() {
  local python_bin
  if [[ -n "${DDNS_PYTHON_BIN:-}" ]]; then
    if [[ -x "${DDNS_PYTHON_BIN}" ]]; then
      echo "${DDNS_PYTHON_BIN}"
      return 0
    fi
    warn "DDNS_PYTHON_BIN is set but not executable: ${DDNS_PYTHON_BIN}"
  fi

  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "${VIRTUAL_ENV}/bin/python"
    return 0
  fi

  if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    echo "${CONDA_PREFIX}/bin/python"
    return 0
  fi

  if [[ "${EUID:-$(id -u)}" -eq 0 && -n "${SUDO_USER:-}" ]]; then
    python_bin="$(${SUDO_BIN:-sudo} -u "$SUDO_USER" -H bash -lc 'command -v python3 || command -v python' 2>/dev/null || true)"
  else
    python_bin="$(which python3 2>/dev/null || true)"
  fi
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
    sed -i -E "s#^Environment=AGENT_CONFIG_PATH=.*#Environment=AGENT_CONFIG_PATH=${AGENT_CONFIG_FILE}#" "$REPO_SERVICE_FILE"
    sed -i -E "s#^Environment=AGENT_DB_PATH=.*#Environment=AGENT_DB_PATH=${AGENT_DB_FILE}#" "$REPO_SERVICE_FILE"
    sed -i -E "s#^Environment=DDNS_PYTHON_BIN=.*#Environment=DDNS_PYTHON_BIN=${python_bin}#" "$REPO_SERVICE_FILE"
    sed -i -E "s#^EnvironmentFile=.*#EnvironmentFile=${AGENT_ENV_FILE}#" "$REPO_SERVICE_FILE"
    sed -i -E "s#^WorkingDirectory=.*#WorkingDirectory=${REPO_ROOT}#" "$REPO_SERVICE_FILE"
    sed -i -E "s#^ExecStart=.*#ExecStart=${REPO_ROOT}/start-agent.sh#" "$REPO_SERVICE_FILE"
    sed -i -E "s#^User=.*#User=${SERVICE_USER}#" "$REPO_SERVICE_FILE"
    info "Updated ${REPO_SERVICE_FILE} service paths."
  else
    warn "Missing ${REPO_SERVICE_FILE}; cannot update ExecStart."
  fi

  if [[ -f "$GUI_REPO_SERVICE_FILE" ]]; then
    sed -i -E "s#^Environment=DDNS_WORKDIR=.*#Environment=DDNS_WORKDIR=${REPO_ROOT}#" "$GUI_REPO_SERVICE_FILE"
    sed -i -E "s#^Environment=AGENT_CONFIG_PATH=.*#Environment=AGENT_CONFIG_PATH=${AGENT_CONFIG_FILE}#" "$GUI_REPO_SERVICE_FILE"
    sed -i -E "s#^Environment=AGENT_DB_PATH=.*#Environment=AGENT_DB_PATH=${AGENT_DB_FILE}#" "$GUI_REPO_SERVICE_FILE"
    sed -i -E "s#^EnvironmentFile=.*#EnvironmentFile=${AGENT_ENV_FILE}#" "$GUI_REPO_SERVICE_FILE"
    sed -i -E "s#^WorkingDirectory=.*#WorkingDirectory=${REPO_ROOT}#" "$GUI_REPO_SERVICE_FILE"
    sed -i -E "s#^ExecStart=.*#ExecStart=${REPO_ROOT}/start.sh#" "$GUI_REPO_SERVICE_FILE"
    sed -i -E "s#^User=.*#User=${SERVICE_USER}#" "$GUI_REPO_SERVICE_FILE"
    info "Updated ${GUI_REPO_SERVICE_FILE} service paths."
  else
    warn "Missing ${GUI_REPO_SERVICE_FILE}; cannot update ExecStart."
  fi

  if [[ -f "$START_FILE" ]]; then
    sed -i -E "s#^PYTHON_BIN=.*#PYTHON_BIN=\"${python_bin}\"#" "$START_FILE"
    info "Updated ${START_FILE} PYTHON_BIN."
  else
    warn "Missing ${START_FILE}; cannot update PYTHON_BIN."
  fi
}

ensure_env_workdir() {
  if needs_root; then
    ensure_root
  fi

  local env_mode="0400"
  if [[ "${DDNS_SYSTEM_WIDE:-}" == "1" ]]; then
    env_mode="0440"
  fi

  if [[ ! -f "${AGENT_ENV_FILE}" ]]; then
    if needs_root; then
      ${SUDO_BIN} install -d -m 0750 -o root -g root "${CONFIG_DIR}"
      ${SUDO_BIN} install -m "${env_mode}" -o root -g root /dev/null "${AGENT_ENV_FILE}"
    else
      mkdir -p "${CONFIG_DIR}"
      install -m 0600 /dev/null "${AGENT_ENV_FILE}"
    fi
    info "Created ${AGENT_ENV_FILE}."
  fi

  local temp_file
  temp_file="$(mktemp)"
  awk -v workdir="DDNS_WORKDIR=${REPO_ROOT}" '
    BEGIN { found = 0 }
    /^DDNS_WORKDIR=/ { print workdir; found = 1; next }
    { print }
    END { if (!found) print workdir }
  ' "${AGENT_ENV_FILE}" > "${temp_file}"

  ${SUDO_BIN} chmod 0600 "${AGENT_ENV_FILE}"
  ${SUDO_BIN} tee "${AGENT_ENV_FILE}" >/dev/null < "${temp_file}"
  rm -f "${temp_file}"
  ${SUDO_BIN} chmod "${env_mode}" "${AGENT_ENV_FILE}"
  info "Updated DDNS_WORKDIR in ${AGENT_ENV_FILE}."
}

setup_permissions() {
  local flask_db_path="${FLASK_DB_PATH:-${DATA_DIR}/webapp.db}"
  local sudoers_file="/etc/sudoers.d/ddns-admin"
  local allow_system_wide="${DDNS_SYSTEM_WIDE:-}"

  if needs_root; then
    ensure_root
  fi

  if needs_root; then
    if [[ "${allow_system_wide}" == "1" ]]; then
      if ! id -u ddns-admin >/dev/null 2>&1; then
        ${SUDO_BIN} useradd --create-home --shell /bin/bash ddns-admin
        info "Created user ddns-admin."
      fi

      if ! id -u ddns-agent >/dev/null 2>&1; then
        ${SUDO_BIN} useradd --system --no-create-home --shell /usr/sbin/nologin ddns-agent
        info "Created user ddns-agent."
      fi

      ${SUDO_BIN} install -d -m 0750 -o ddns-admin -g ddns-agent "${CONFIG_DIR}"
      ${SUDO_BIN} install -d -m 0750 -o ddns-agent -g ddns-agent "${DATA_DIR}"

      if [[ ! -f "${AGENT_CONFIG_FILE}" ]]; then
        ${SUDO_BIN} install -m 0640 -o ddns-admin -g ddns-agent /dev/null "${AGENT_CONFIG_FILE}"
      else
        ${SUDO_BIN} chown ddns-admin:ddns-agent "${AGENT_CONFIG_FILE}"
        ${SUDO_BIN} chmod 0640 "${AGENT_CONFIG_FILE}"
      fi

      if [[ ! -f "${AGENT_ENV_FILE}" ]]; then
        ${SUDO_BIN} install -m 0440 -o ddns-admin -g ddns-agent /dev/null "${AGENT_ENV_FILE}"
      else
        ${SUDO_BIN} chown ddns-admin:ddns-agent "${AGENT_ENV_FILE}"
        ${SUDO_BIN} chmod 0440 "${AGENT_ENV_FILE}"
      fi
    else
      warn "DDNS_SYSTEM_WIDE not set; skipping system user and sudoers setup."
      ${SUDO_BIN} install -d -m 0750 -o root -g root "${CONFIG_DIR}"
      ${SUDO_BIN} install -d -m 0750 -o root -g root "${DATA_DIR}"

      if [[ ! -f "${AGENT_CONFIG_FILE}" ]]; then
        ${SUDO_BIN} install -m 0400 -o root -g root /dev/null "${AGENT_CONFIG_FILE}"
      else
        ${SUDO_BIN} chown root:root "${AGENT_CONFIG_FILE}"
        ${SUDO_BIN} chmod 0400 "${AGENT_CONFIG_FILE}"
      fi

      if [[ ! -f "${AGENT_ENV_FILE}" ]]; then
        ${SUDO_BIN} install -m 0400 -o root -g root /dev/null "${AGENT_ENV_FILE}"
      else
        ${SUDO_BIN} chown root:root "${AGENT_ENV_FILE}"
        ${SUDO_BIN} chmod 0400 "${AGENT_ENV_FILE}"
      fi
    fi
  else
    mkdir -p "${CONFIG_DIR}" "${DATA_DIR}"
    install -m 0600 /dev/null "${AGENT_CONFIG_FILE}"
    install -m 0600 /dev/null "${AGENT_ENV_FILE}"
  fi

  ensure_env_workdir

  if ! grep -q '^AGENT_MASTER_KEY=' "${AGENT_ENV_FILE}"; then
    ${SUDO_BIN} chmod 0600 "${AGENT_ENV_FILE}"
    local agent_key
    agent_key="$(python3 - <<'PY'
import base64
import os

print(base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8"))
PY
)"
    echo "AGENT_MASTER_KEY=${agent_key}" | ${SUDO_BIN} tee -a "${AGENT_ENV_FILE}" >/dev/null
    ${SUDO_BIN} chmod 0400 "${AGENT_ENV_FILE}"
    info "Generated AGENT_MASTER_KEY in ${AGENT_ENV_FILE}."
  fi

  if [[ ! -f "${flask_db_path}" ]]; then
    if needs_root; then
      if [[ "${allow_system_wide}" == "1" ]]; then
        ${SUDO_BIN} install -m 0640 -o ddns-admin -g ddns-admin /dev/null "${flask_db_path}"
      else
        ${SUDO_BIN} install -m 0640 -o root -g root /dev/null "${flask_db_path}"
      fi
    else
      install -m 0640 /dev/null "${flask_db_path}"
    fi
  else
    if needs_root; then
      if [[ "${allow_system_wide}" == "1" ]]; then
        ${SUDO_BIN} chown ddns-admin:ddns-admin "${flask_db_path}"
      else
        ${SUDO_BIN} chown root:root "${flask_db_path}"
      fi
      ${SUDO_BIN} chmod 0640 "${flask_db_path}"
    else
      chmod 0640 "${flask_db_path}"
    fi
  fi

  if needs_root; then
    if [[ "${allow_system_wide}" == "1" ]]; then
      ${SUDO_BIN} tee "${sudoers_file}" >/dev/null <<'EOF'
ddns-admin ALL=(root) NOPASSWD: /bin/systemctl reload ddns-agent
EOF
      ${SUDO_BIN} chmod 0440 "${sudoers_file}"
      info "Permissions and system users configured."
    else
      info "Permissions configured without system users or sudoers."
    fi
  else
    info "Permissions configured for local project directories."
  fi
}

install_service() {
  ensure_root

  ensure_env_workdir
  update_python_paths

  local missing_service=0

  install_service_file() {
    local service_name="$1"
    local repo_service_file="$2"
    local systemd_service_path="$3"

    if [[ ! -f "$repo_service_file" ]]; then
      warn "Missing ${repo_service_file}."
      missing_service=1
      return 0
    fi

    ${SUDO_BIN} install -m 0644 "$repo_service_file" "$systemd_service_path"
    ${SUDO_BIN} systemctl daemon-reload
    info "Installed ${service_name} to ${systemd_service_path}."

    if ${SUDO_BIN} systemctl is-enabled --quiet "$service_name"; then
      info "${service_name} is already enabled."
    else
      read -r -p "Enable ${service_name} on boot? [y/N]: " enable_choice
      if [[ "${enable_choice,,}" == "y" ]]; then
        ${SUDO_BIN} systemctl enable "$service_name"
        info "Enabled ${service_name}."
      fi
    fi

    read -r -p "Start/restart ${service_name} now? [y/N]: " start_choice
    if [[ "${start_choice,,}" == "y" ]]; then
      ${SUDO_BIN} systemctl restart "$service_name"
      info "Restarted ${service_name}."
    fi
  }

  install_service_file "$SERVICE_NAME" "$REPO_SERVICE_FILE" "$SYSTEMD_SERVICE_PATH"
  install_service_file "$GUI_SERVICE_NAME" "$GUI_REPO_SERVICE_FILE" "$GUI_SYSTEMD_SERVICE_PATH"

  if [[ "$missing_service" -ne 0 ]]; then
    error "One or more service files are missing."
    return 1
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
    start_python="$(sed -n -E 's/^PYTHON_BIN="?([^"]*)"?$/\1/p' "$START_FILE")"
    info "start.sh PYTHON_BIN: ${start_python:-"(not set)"}"
  else
    warn "Missing ${START_FILE}."
  fi

  if [[ -f "$REPO_SERVICE_FILE" ]]; then
    local repo_exec
    repo_exec="$(sed -n -E 's/^ExecStart=//p' "$REPO_SERVICE_FILE")"
    info "Repo service ExecStart: ${repo_exec:-"(not set)"}"
  else
    warn "Missing ${REPO_SERVICE_FILE}."
  fi

  if [[ -f "$SYSTEMD_SERVICE_PATH" ]]; then
    local system_exec
    system_exec="$(sed -n -E 's/^ExecStart=//p' "$SYSTEMD_SERVICE_PATH")"
    info "Systemd ExecStart: ${system_exec:-"(not set)"}"
  else
    warn "Systemd service not installed at ${SYSTEMD_SERVICE_PATH}."
  fi

  if [[ -f "$GUI_REPO_SERVICE_FILE" ]]; then
    local gui_repo_exec
    gui_repo_exec="$(sed -n -E 's/^ExecStart=//p' "$GUI_REPO_SERVICE_FILE")"
    info "GUI repo service ExecStart: ${gui_repo_exec:-"(not set)"}"
  else
    warn "Missing ${GUI_REPO_SERVICE_FILE}."
  fi

  if [[ -f "$GUI_SYSTEMD_SERVICE_PATH" ]]; then
    local gui_system_exec
    gui_system_exec="$(sed -n -E 's/^ExecStart=//p' "$GUI_SYSTEMD_SERVICE_PATH")"
    info "GUI systemd ExecStart: ${gui_system_exec:-"(not set)"}"
  else
    warn "GUI systemd service not installed at ${GUI_SYSTEMD_SERVICE_PATH}."
  fi

  if [[ -f "$AGENT_ENV_FILE" ]]; then
    local workdir
    workdir="$(sed -n -E 's/^DDNS_WORKDIR=//p' "$AGENT_ENV_FILE")"
    info "DDNS_WORKDIR: ${workdir:-"(not set)"}"
    if [[ -n "$workdir" && "$workdir" != "$REPO_ROOT" ]]; then
      warn "DDNS_WORKDIR does not match repo root (${REPO_ROOT})."
    fi
    local agent_key
    agent_key="$(sed -n -E 's/^AGENT_MASTER_KEY=//p' "$AGENT_ENV_FILE")"
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

guided_install() {
  info "Starting guided first-time install."
  update_python_paths
  install_dependencies
  setup_permissions
  install_service
  verify_paths
  info "Guided install complete."
}

full_reinstall() {
  warn "Full reinstall will stop the service, remove systemd unit, and delete config/data."
  if ! confirm "Proceed with full reinstall"; then
    info "Full reinstall canceled."
    return 0
  fi

  if needs_root || [[ -d "$SYSTEMD_DIR" ]]; then
    ensure_root
  fi

  if command -v systemctl >/dev/null 2>&1; then
    if ${SUDO_BIN} systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
      ${SUDO_BIN} systemctl disable "$SERVICE_NAME" || true
    fi
    if ${SUDO_BIN} systemctl is-enabled --quiet "$GUI_SERVICE_NAME" 2>/dev/null; then
      ${SUDO_BIN} systemctl disable "$GUI_SERVICE_NAME" || true
    fi
    if ${SUDO_BIN} systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
      ${SUDO_BIN} systemctl stop "$SERVICE_NAME" || true
    fi
    if ${SUDO_BIN} systemctl is-active --quiet "$GUI_SERVICE_NAME" 2>/dev/null; then
      ${SUDO_BIN} systemctl stop "$GUI_SERVICE_NAME" || true
    fi
  fi

  if [[ -f "$SYSTEMD_SERVICE_PATH" ]]; then
    ${SUDO_BIN} rm -f "$SYSTEMD_SERVICE_PATH"
    ${SUDO_BIN} systemctl daemon-reload || true
    info "Removed systemd service ${SYSTEMD_SERVICE_PATH}."
  fi

  if [[ -f "$GUI_SYSTEMD_SERVICE_PATH" ]]; then
    ${SUDO_BIN} rm -f "$GUI_SYSTEMD_SERVICE_PATH"
    ${SUDO_BIN} systemctl daemon-reload || true
    info "Removed systemd service ${GUI_SYSTEMD_SERVICE_PATH}."
  fi

  if [[ -d "$CONFIG_DIR" ]]; then
    ${SUDO_BIN} rm -rf "$CONFIG_DIR"
    info "Removed config directory ${CONFIG_DIR}."
  fi

  if [[ -d "$DATA_DIR" ]]; then
    ${SUDO_BIN} rm -rf "$DATA_DIR"
    info "Removed data directory ${DATA_DIR}."
  fi

  guided_install
}

print_menu() {
  cat <<'EOF'
Simple Namecheap DDNS Installer
================================
1) Verify paths and environment
2) Update python paths in service/start scripts
3) Install/update Python dependencies
4) Configure system users and permissions (root)
5) Install/update systemd services (root)
6) Update repository (git pull)
7) Guided install (first time)
8) Full reinstall (wipe config/data)
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
      7)
        guided_install
        ;;
      8)
        full_reinstall
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
