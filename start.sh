#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="$REPO_ROOT/.flask_master_key"

if [[ -z "${FLASK_MASTER_KEY:-}" ]]; then
  if [[ -f "$KEY_FILE" ]]; then
    export FLASK_MASTER_KEY
    FLASK_MASTER_KEY="$(<"$KEY_FILE")"
  else
    if ! command -v python >/dev/null 2>&1; then
      echo "python is required to generate FLASK_MASTER_KEY" >&2
      exit 1
    fi
    FLASK_MASTER_KEY="$(python - <<'PY'
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
exec python -m flask run
