#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PID_FILE="$LOG_DIR/nginx.pid"
NGINX_GLOBALS='error_log stderr;'

require_command nginx

if [[ -f "$PID_FILE" ]]; then
  nginx -g "$NGINX_GLOBALS" -p "$DEPLOY_NGINX_DIR" -c "$NATIVE_NGINX_CONF_FILE" -s quit || true
  rm -f "$PID_FILE"
fi

echo "nginx stopped"
