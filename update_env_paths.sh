#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python_bin="$(command -v python3 || true)"
if [[ -z "$python_bin" ]]; then
  python_bin="$(command -v python || true)"
fi

if [[ -z "$python_bin" ]]; then
  echo "Unable to find python or python3 in PATH." >&2
  exit 1
fi

python_bin="$(readlink -f "$python_bin")"

service_file="$REPO_ROOT/ddns-agent.service"
start_file="$REPO_ROOT/start.sh"

if [[ -f "$service_file" ]]; then
  sed -i -E "s#^ExecStart=.* -m agent\.main#ExecStart=${python_bin} -m agent.main#" "$service_file"
fi

if [[ -f "$start_file" ]]; then
  sed -i -E "s#^PYTHON_BIN=.*#PYTHON_BIN=\"${python_bin}\"#" "$start_file"
fi

echo "Updated python path to ${python_bin}"
