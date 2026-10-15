#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash one-click-deploy.sh" >&2
  exit 1
fi
exec bash "$SCRIPT_DIR/deploy.vps"
