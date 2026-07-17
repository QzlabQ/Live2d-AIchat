#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_command docker
ensure_file "$COMPOSE_FILE" "docker compose file not found: $COMPOSE_FILE. Run deploy/docker/bootstrap.sh first."
load_env_file "$BACKEND_ENV_FILE"

cd "$LIVE_DEPLOY_DIR"
docker compose up -d --build "$@"
