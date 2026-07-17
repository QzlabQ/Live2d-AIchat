#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_command pg_lsclusters
require_command pg_ctlcluster

if pg_lsclusters --no-header | awk '$1 == "14" && $2 == "main" { print $4 }' | grep -qx 'online'; then
  echo "postgres cluster 14/main already running"
else
  sudo pg_ctlcluster 14 main start
fi

pg_lsclusters
