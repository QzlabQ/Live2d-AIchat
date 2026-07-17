#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

require_command pg_ctlcluster
require_command pg_lsclusters

sudo pg_ctlcluster 14 main stop
pg_lsclusters
