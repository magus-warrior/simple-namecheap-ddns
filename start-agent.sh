#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(which python3 2>/dev/null || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 is required to run the agent backend" >&2
  exit 1
fi

cd "$REPO_ROOT"
exec "$PYTHON_BIN" -m agent.main
