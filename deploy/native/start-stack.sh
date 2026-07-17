#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/start-postgres.sh"
"$SCRIPT_DIR/start-backend.sh"
"$SCRIPT_DIR/start-frontend-nginx.sh"
