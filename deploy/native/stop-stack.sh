#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/stop-frontend-nginx.sh"
"$SCRIPT_DIR/stop-backend.sh"
"$SCRIPT_DIR/stop-postgres.sh"
