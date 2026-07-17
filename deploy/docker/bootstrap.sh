#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

BACKEND_TEMPLATE="$TEMPLATE_BACKEND_ENV"
if [[ "${1:-}" == "--v100" ]]; then
  BACKEND_TEMPLATE="$TEMPLATE_BACKEND_V100_ENV"
fi

print_step "Prepare Docker deployment directories"
mkdir -p \
  "$LIVE_DEPLOY_DIR" \
  "$LIVE_NGINX_DIR" \
  "$ROOT_DIR/models" \
  "$ROOT_DIR/vendor" \
  "$DATA_DIR/postgres" \
  "$DATA_DIR/knowledge" \
  "$DATA_DIR/uploads" \
  "$LOG_DIR"

print_step "Sync repo-managed Docker assets"
cp "$TEMPLATE_DEPLOY_DIR/docker-compose.yml" "$COMPOSE_FILE"
cp "$TEMPLATE_NGINX_CONF" "$LIVE_NGINX_CONF"
copy_if_missing "$BACKEND_TEMPLATE" "$BACKEND_ENV_FILE"
copy_if_missing "$TEMPLATE_POSTGRES_ENV" "$POSTGRES_ENV_FILE"

print_step "Bootstrap completed"
cat <<EOF
Docker deployment assets are ready.

Managed files refreshed from the repo:
  $COMPOSE_FILE
  $LIVE_NGINX_CONF

Config files kept or created:
  $BACKEND_ENV_FILE
  $POSTGRES_ENV_FILE

Next steps:
  1. Edit backend.env / postgres.env with real secrets.
  2. Upload models, vendor/CosyVoice, and data assets if they are not present yet.
  3. Start the stack with: $SCRIPT_DIR/up.sh

Tip:
  - Use: $SCRIPT_DIR/bootstrap.sh --v100
    when you want the V100-oriented backend.env template on first setup.
EOF
