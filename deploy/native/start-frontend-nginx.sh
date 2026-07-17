#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PID_FILE="$LOG_DIR/nginx.pid"
TMP_DIR="$DEPLOY_NGINX_DIR/tmp"
NGINX_GLOBALS='error_log stderr;'

require_command nginx
mkdir -p "$LOG_DIR"
mkdir -p \
  "$TMP_DIR/client_body" \
  "$TMP_DIR/proxy" \
  "$TMP_DIR/fastcgi" \
  "$TMP_DIR/uwsgi" \
  "$TMP_DIR/scgi"

ensure_file "$NATIVE_NGINX_CONF_FILE" "nginx config not found: $NATIVE_NGINX_CONF_FILE"
ensure_file "$FRONTEND_DIR/dist/index.html" "frontend build output not found. Run deploy/native/build-frontend.sh first."

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "nginx already running with pid $(cat "$PID_FILE")"
  exit 0
fi

nginx -g "$NGINX_GLOBALS" -p "$DEPLOY_NGINX_DIR" -c "$NATIVE_NGINX_CONF_FILE"
echo "nginx started"
