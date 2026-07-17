#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PID_FILE="$LOG_DIR/trt_prewarm.pid"
LOG_FILE="$LOG_DIR/trt_prewarm.log"

mkdir -p "$LOG_DIR"
ensure_file "$VENV_DIR/bin/python" "backend venv not found: $VENV_DIR/bin/python. Run deploy/native/bootstrap.sh first."

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "trt prewarm already running with pid $(cat "$PID_FILE")"
  exit 0
fi

rm -f "$ROOT_DIR/models/CosyVoice2-0.5B/flow.decoder.estimator.fp16.mygpu.plan"

setsid -f /bin/bash -lc "
  echo \$$ > '$PID_FILE'
  cd '$BACKEND_DIR'
  '$VENV_DIR/bin/python' - <<'PY' >>'$LOG_FILE' 2>&1
import sys
from pathlib import Path

code_path = Path('/opt/ai-chat-live2d/vendor/CosyVoice')
matcha_path = code_path / 'third_party' / 'Matcha-TTS'
sys.path.insert(0, str(code_path))
if matcha_path.exists():
    sys.path.insert(0, str(matcha_path))

from cosyvoice.cli.cosyvoice import CosyVoice2

CosyVoice2('/opt/ai-chat-live2d/models/CosyVoice2-0.5B', load_trt=True, fp16=True)
print('trt_prewarm_ok', True)
PY
"

sleep 1
if [[ ! -f "$PID_FILE" ]] || ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "trt prewarm failed to start"
  exit 1
fi

echo "trt prewarm started with pid $(cat "$PID_FILE")"
