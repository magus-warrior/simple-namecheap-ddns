#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$REPO_ROOT/.flask_master_key"
PYTHON_BIN="python"

export DDNS_WORKDIR="${DDNS_WORKDIR:-$REPO_ROOT}"
export AGENT_DB_PATH="${AGENT_DB_PATH:-$DDNS_WORKDIR/.ddns/agent.db}"

if [[ -z "${FLASK_MASTER_KEY:-}" ]]; then
  if [[ -f "$KEY_FILE" ]]; then
    export FLASK_MASTER_KEY
    FLASK_MASTER_KEY="$(<"$KEY_FILE")"
  else
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      echo "python is required to generate FLASK_MASTER_KEY" >&2
      exit 1
    fi
    FLASK_MASTER_KEY="$("$PYTHON_BIN" - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode("utf-8"))
PY
)"
    printf '%s' "$FLASK_MASTER_KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    export FLASK_MASTER_KEY
    echo "Generated FLASK_MASTER_KEY and saved to $KEY_FILE" >&2
  fi
fi

export FLASK_APP="${FLASK_APP:-app}"
export FLASK_RUN_PORT="${FLASK_RUN_PORT:-8001}"
export FLASK_RUN_HOST="${FLASK_RUN_HOST:-0.0.0.0}"

cd "$REPO_ROOT"
exec "$PYTHON_BIN" -m flask run
