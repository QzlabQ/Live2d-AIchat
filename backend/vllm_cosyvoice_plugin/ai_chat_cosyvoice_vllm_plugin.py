from __future__ import annotations

import os
from pathlib import Path
import sys

PLUGIN_NAME = "ai_chat_cosyvoice"
CODE_PATH_ENV = "AI_CHAT_COSYVOICE_CODE_PATH"
MODEL_ARCH = "CosyVoice2ForCausalLM"
MODEL_REFERENCE = "cosyvoice.vllm.cosyvoice2:CosyVoice2ForCausalLM"


def _candidate_paths(code_path: Path) -> list[Path]:
    candidates = [code_path]
    matcha_path = code_path / "third_party" / "Matcha-TTS"
    if matcha_path.is_dir():
        candidates.append(matcha_path)
    return candidates


def _prepend_python_paths(code_path: Path) -> None:
    if not code_path.exists():
        return

    candidates = _candidate_paths(code_path)
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


def register() -> None:
    code_path = os.environ.get(CODE_PATH_ENV)
    if code_path:
        _prepend_python_paths(Path(code_path).expanduser())

    from vllm import ModelRegistry

    try:
        ModelRegistry.register_model(MODEL_ARCH, MODEL_REFERENCE)
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise
