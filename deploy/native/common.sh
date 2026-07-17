#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${ROOT_DIR:-/opt/ai-chat-live2d}
APP_REPO_DIR="$ROOT_DIR/app"
BACKEND_DIR="$APP_REPO_DIR/backend"
FRONTEND_DIR="$APP_REPO_DIR/frontend"
DEPLOY_DIR="$ROOT_DIR/deploy"
DEPLOY_NATIVE_DIR="$DEPLOY_DIR/native"
DEPLOY_NGINX_DIR="$DEPLOY_DIR/nginx"
DATA_DIR="$ROOT_DIR/data"
LOG_DIR="$DATA_DIR/logs"
VENV_DIR="$ROOT_DIR/.venvs/backend"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ENV_FILE="$DEPLOY_DIR/backend.env"
POSTGRES_ENV_FILE="$DEPLOY_DIR/postgres.env"
NATIVE_NGINX_CONF_FILE="$DEPLOY_NGINX_DIR/native-nginx.conf"
NODE_BIN_DIR="$ROOT_DIR/tools/node20/bin"

print_step() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required command not found: $command_name" >&2
    exit 1
  fi
}

ensure_file() {
  local path="$1"
  local hint="$2"
  if [[ ! -f "$path" ]]; then
    echo "$hint" >&2
    exit 1
  fi
}

copy_if_missing() {
  local source_path="$1"
  local target_path="$2"
  if [[ ! -f "$target_path" ]]; then
    mkdir -p "$(dirname "$target_path")"
    cp "$source_path" "$target_path"
  fi
}

load_env_file() {
  local env_file="$1"
  ensure_file "$env_file" "env file not found: $env_file"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    local key=${line%%=*}
    local value=${line#*=}
    export "$key=$value"
  done < "$env_file"
}

ensure_backend_env() {
  load_env_file "$BACKEND_ENV_FILE"
}

ensure_postgres_env() {
  load_env_file "$POSTGRES_ENV_FILE"
}

prefer_node_path() {
  if [[ -d "$NODE_BIN_DIR" ]]; then
    export PATH="$NODE_BIN_DIR:$PATH"
  fi
}

bool_env_true() {
  local raw_value="${1:-}"
  case "${raw_value,,}" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

link_storage_dir() {
  local name="$1"
  local target_path="$2"
  mkdir -p "$(dirname "$BACKEND_DIR/storage/$name")"
  ln -sfn "$target_path" "$BACKEND_DIR/storage/$name"
}

sync_native_assets() {
  mkdir -p "$DEPLOY_NATIVE_DIR"
  if [[ "$THIS_DIR" != "$DEPLOY_NATIVE_DIR" ]]; then
    cp -a "$THIS_DIR"/. "$DEPLOY_NATIVE_DIR"/
  fi
  chmod +x "$DEPLOY_NATIVE_DIR"/*.sh 2>/dev/null || true
}
