#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ensure_backend_env
prefer_node_path
require_command node
require_command npm

cd "$FRONTEND_DIR"

if command -v pnpm >/dev/null 2>&1; then
  pnpm install --no-frozen-lockfile
  pnpm run build
else
  npx pnpm@9.15.4 install --no-frozen-lockfile
  npx pnpm@9.15.4 run build
fi
