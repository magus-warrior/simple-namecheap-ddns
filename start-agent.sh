#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${DDNS_PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "${PYTHON_BIN} is required to run the agent backend" >&2
  exit 1
fi

PYTHON_BIN="$(command -v "$PYTHON_BIN")"

cd "$REPO_ROOT"
exec "$PYTHON_BIN" -m agent.main
