#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=${ROOT_DIR:-/opt/ai-chat-live2d}
APP_REPO_DIR="$ROOT_DIR/app"
TEMPLATE_DEPLOY_DIR="$APP_REPO_DIR/deploy"
LIVE_DEPLOY_DIR="$ROOT_DIR/deploy"
LIVE_NGINX_DIR="$LIVE_DEPLOY_DIR/nginx"
DATA_DIR="$ROOT_DIR/data"
LOG_DIR="$DATA_DIR/logs"
COMPOSE_FILE="$LIVE_DEPLOY_DIR/docker-compose.yml"
BACKEND_ENV_FILE="$LIVE_DEPLOY_DIR/backend.env"
POSTGRES_ENV_FILE="$LIVE_DEPLOY_DIR/postgres.env"
TEMPLATE_BACKEND_ENV="$TEMPLATE_DEPLOY_DIR/backend.env.example"
TEMPLATE_BACKEND_V100_ENV="$TEMPLATE_DEPLOY_DIR/backend.env.v100.example"
TEMPLATE_POSTGRES_ENV="$TEMPLATE_DEPLOY_DIR/postgres.env.example"
TEMPLATE_NGINX_CONF="$TEMPLATE_DEPLOY_DIR/nginx/default.conf"
LIVE_NGINX_CONF="$LIVE_NGINX_DIR/default.conf"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
