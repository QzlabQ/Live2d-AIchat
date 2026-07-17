#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"

print_step "Sync native deployment assets"
sync_native_assets

print_step "Prepare directories"
mkdir -p \
  "$ROOT_DIR/models" \
  "$ROOT_DIR/vendor" \
  "$ROOT_DIR/.venvs" \
  "$DATA_DIR/postgres" \
  "$DATA_DIR/knowledge" \
  "$DATA_DIR/uploads" \
  "$LOG_DIR" \
  "$DEPLOY_NGINX_DIR"

copy_if_missing "$THIS_DIR/backend.env.example" "$BACKEND_ENV_FILE"
copy_if_missing "$THIS_DIR/postgres.env.example" "$POSTGRES_ENV_FILE"
copy_if_missing "$THIS_DIR/native-nginx.conf" "$NATIVE_NGINX_CONF_FILE"

print_step "Link backend storage workspace"
mkdir -p "$BACKEND_DIR/storage"
link_storage_dir "models" "$ROOT_DIR/models"
link_storage_dir "vendor" "$ROOT_DIR/vendor"
link_storage_dir "knowledge" "$DATA_DIR/knowledge"
link_storage_dir "uploads" "$DATA_DIR/uploads"

print_step "Load deployment env"
ensure_backend_env

print_step "Prepare backend venv"
require_command python3
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
(
  cd "$BACKEND_DIR"
  "$VENV_DIR/bin/python" -m pip install -r requirements.runtime.txt --no-build-isolation
)

if [[ "${TTS_COSYVOICE_ONNX_PROVIDER:-cpu}" == "cuda" ]] || bool_env_true "${TTS_COSYVOICE_LOAD_TRT:-false}"; then
  print_step "Pin GPU onnxruntime provider"
  (
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" -m pip uninstall -y onnxruntime onnxruntime-gpu || true
    "$VENV_DIR/bin/python" -m pip install onnxruntime-gpu==1.18.0 --no-build-isolation
  )
  "$VENV_DIR/bin/python" - <<'PY'
import onnxruntime as ort

providers = ort.get_available_providers()
print("onnxruntime_providers =", providers)
if "CUDAExecutionProvider" not in providers:
    raise SystemExit("CUDAExecutionProvider not available after native bootstrap.")
PY
fi

print_step "Build frontend"
"$THIS_DIR/build-frontend.sh"

print_step "Bootstrap completed"
cat <<EOF
Native deployment assets are ready.

Config files:
  $BACKEND_ENV_FILE
  $POSTGRES_ENV_FILE
  $NATIVE_NGINX_CONF_FILE

Next steps:
  1. Edit backend.env / postgres.env with real secrets.
  2. Make sure PostgreSQL 14/main is installed and the database/user exist.
  3. Optionally run: $DEPLOY_NATIVE_DIR/prewarm-trt.sh
  4. Start the stack: $DEPLOY_NATIVE_DIR/start-stack.sh
EOF
