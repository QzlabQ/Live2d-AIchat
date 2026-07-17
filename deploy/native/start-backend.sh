#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PID_FILE="$LOG_DIR/backend.pid"
LOG_FILE="$LOG_DIR/backend.log"
PYTHON_BIN="$VENV_DIR/bin/python"

ensure_backend_env
mkdir -p "$LOG_DIR"
ensure_file "$PYTHON_BIN" "backend venv not found: $PYTHON_BIN. Run deploy/native/bootstrap.sh first."

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "backend already running with pid $(cat "$PID_FILE")"
  exit 0
fi

cd "$BACKEND_DIR"
setsid -f /bin/sh -c "echo \$$ > \"$PID_FILE\"; cd \"$BACKEND_DIR\"; exec \"$PYTHON_BIN\" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>\"$LOG_FILE\" 2>&1"

sleep 1
if [[ ! -f "$PID_FILE" ]] || ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "backend failed to start"
  exit 1
fi

echo "backend started with pid $(cat "$PID_FILE")"
