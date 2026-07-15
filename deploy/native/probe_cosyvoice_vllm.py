#!/usr/bin/env python3
# Usage: python deploy/native/probe_cosyvoice_vllm.py [--model-dir /models/CosyVoice2-0.5B] [--vllm-model-dir /models/CosyVoice2-0.5B/vllm]
# Purpose: validate the opt-in CosyVoice2 + TRT + vLLM path on a native GPU server without starting the backend.

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import sys
import time


DEPLOY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WARMUP_TEXT = "\u4f60\u597d\u3002"
DEFAULT_STREAM_TEXT = (
    "\u6b22\u8fce\u6765\u5230\u666f\u533a\u3002"
    "\u6211\u4eec\u73b0\u5728\u4ece\u5165\u53e3\u5e7f\u573a\u51fa\u53d1\uff0c"
    "\u5148\u4e3a\u4f60\u7b80\u8981\u4ecb\u7ecd\u4e3b\u8981\u6e38\u89c8\u8def\u7ebf\uff0c"
    "\u518d\u63d0\u9192\u4f60\u54ea\u4e9b\u5c55\u533a\u66f4\u9002\u5408\u5e26\u5b69\u5b50\u4e00\u8d77\u53c2\u89c2\uff0c"
    "\u5982\u679c\u4f60\u60f3\u770b\u65e5\u843d\uff0c\u53ef\u4ee5\u63d0\u524d\u4e8c\u5341\u5206\u949f\u8d76\u5230\u89c2\u666f\u53f0\u3002"
)
DEFAULT_INSTRUCTION = "\u8bf7\u7528\u6e29\u548c\u81ea\u7136\u7684\u8bed\u6c14\u8bb2\u89e3\u3002"
VLLM_COSYVOICE_PLUGIN_NAME = "ai_chat_cosyvoice"
VLLM_COSYVOICE_CODE_PATH_ENV = "AI_CHAT_COSYVOICE_CODE_PATH"


class ProbeError(RuntimeError):
    pass


def checkpoint_ok(name: str, detail: str = "") -> None:
    if detail:
        print(f"[PASS] {name}: {detail}")
    else:
        print(f"[PASS] {name}")


def fail(name: str, detail: str) -> "NoReturn":
    print(f"[FAIL] {name}: {detail}", file=sys.stderr)
    raise ProbeError(f"{name}: {detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe CosyVoice2 TRT + vLLM support on a native GPU server."
    )
    parser.add_argument(
        "--model-dir",
        default=os.environ.get("TTS_COSYVOICE_MODEL_PATH", str(DEPLOY_ROOT / "models" / "CosyVoice2-0.5B")),
        help="CosyVoice2 base model directory.",
    )
    parser.add_argument(
        "--code-dir",
        default=os.environ.get("TTS_COSYVOICE_CODE_PATH", str(DEPLOY_ROOT / "vendor" / "CosyVoice")),
        help="CosyVoice source checkout directory.",
    )
    parser.add_argument(
        "--vllm-model-dir",
        default=os.environ.get(
            "TTS_COSYVOICE_VLLM_MODEL_PATH",
            str(DEPLOY_ROOT / "models" / "CosyVoice2-0.5B" / "vllm"),
        ),
        help="CosyVoice vLLM model directory.",
    )
    parser.add_argument(
        "--reference-audio",
        default=os.environ.get(
            "DEFAULT_TTS_REFERENCE_AUDIO_PATH",
            str(DEPLOY_ROOT / "vendor" / "CosyVoice" / "asset" / "zero_shot_prompt.wav"),
        ),
        help="Reference wav for inference_instruct2.",
    )
    parser.add_argument(
        "--warmup-text",
        default=DEFAULT_WARMUP_TEXT,
        help="Short text for the non-streaming warmup pass.",
    )
    parser.add_argument(
        "--stream-text",
        default=DEFAULT_STREAM_TEXT,
        help="Longer text for the streaming validation pass.",
    )
    parser.add_argument(
        "--instruction",
        default=DEFAULT_INSTRUCTION,
        help="Instruction text passed into inference_instruct2.",
    )
    parser.add_argument(
        "--onnx-provider",
        default=os.environ.get("TTS_COSYVOICE_ONNX_PROVIDER", "cuda"),
        help="Value to export as COSYVOICE_ONNX_PROVIDER before import.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=float(os.environ.get("DEFAULT_TTS_SPEED", "1.0")),
        help="Speech speed.",
    )
    parser.add_argument(
        "--trt-concurrent",
        type=int,
        default=int(os.environ.get("TTS_COSYVOICE_TRT_CONCURRENT", "1")),
        help="TRT concurrency passed into CosyVoice2.",
    )
    parser.add_argument(
        "--vllm-gpu-memory-utilization",
        type=float,
        default=float(os.environ.get("TTS_COSYVOICE_VLLM_GPU_MEMORY_UTILIZATION", "0.2")),
        help="vLLM GPU memory utilization fraction.",
    )
    parser.add_argument(
        "--vllm-dtype",
        default=os.environ.get("TTS_COSYVOICE_VLLM_DTYPE", "fp16"),
        choices=("fp16", "bf16"),
        help="vLLM dtype.",
    )
    return parser.parse_args()


def ensure_path(name: str, raw_path: str, *, file_ok: bool) -> Path:
    path = Path(raw_path).expanduser()
    if file_ok:
        if not path.is_file():
            fail(name, f"{path} is missing. Check your mount or pass --{name.replace('_', '-')}.")
    else:
        if not path.is_dir():
            fail(name, f"{path} is missing. Check your mount or pass --{name.replace('_', '-')}.")
    checkpoint_ok(name, str(path))
    return path


def prepare_vllm_model_dir(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        if not path.is_dir():
            fail("vllm_model_dir", f"{path} exists but is not a directory.")
        checkpoint_ok("vllm_model_dir", f"reusing existing export dir {path}")
        return path
    parent = path.parent
    if not parent.is_dir():
        fail("vllm_model_dir", f"{path} does not exist and parent directory {parent} is missing.")
    checkpoint_ok("vllm_model_dir", f"will export into {path}")
    return path


def add_cosyvoice_paths(code_dir: Path) -> None:
    candidate_paths = [code_dir]
    matcha_dir = code_dir / "third_party" / "Matcha-TTS"
    if matcha_dir.is_dir():
        candidate_paths.append(matcha_dir)

    for candidate in candidate_paths:
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)

    existing_pythonpath = [entry for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep) if entry]
    prepended = [str(candidate) for candidate in candidate_paths if str(candidate) not in existing_pythonpath]
    ordered_pythonpath = prepended + [entry for entry in existing_pythonpath if entry not in prepended]
    if ordered_pythonpath:
        os.environ["PYTHONPATH"] = os.pathsep.join(ordered_pythonpath)
    checkpoint_ok("python_path", f"code_dir={code_dir}")


def configure_vllm_plugin_environment(code_dir: Path) -> None:
    os.environ[VLLM_COSYVOICE_CODE_PATH_ENV] = str(code_dir.expanduser().resolve())

    existing_plugins = [entry.strip() for entry in os.environ.get("VLLM_PLUGINS", "").split(",") if entry.strip()]
    if VLLM_COSYVOICE_PLUGIN_NAME not in existing_plugins:
        existing_plugins.append(VLLM_COSYVOICE_PLUGIN_NAME)
    os.environ["VLLM_PLUGINS"] = ",".join(existing_plugins)
    checkpoint_ok(
        "vllm_plugin_env",
        f"VLLM_PLUGINS={os.environ['VLLM_PLUGINS']} {VLLM_COSYVOICE_CODE_PATH_ENV}={os.environ[VLLM_COSYVOICE_CODE_PATH_ENV]}",
    )


def first_result(result_or_iterable: object) -> dict[str, object]:
    if isinstance(result_or_iterable, dict):
        return result_or_iterable
    iterator = iter(result_or_iterable)
    try:
        result = next(iterator)
    except StopIteration as exc:
        fail("warmup_output", "CosyVoice returned no results for the warmup request.")
        raise AssertionError("unreachable") from exc
    if not isinstance(result, dict):
        fail("warmup_output", f"Expected dict results, got {type(result).__name__}.")
    return result


def extract_audio_payload(result: dict[str, object]) -> object | None:
    for key in ("audio", "tts_speech", "speech"):
        payload = result.get(key)
        if payload is not None:
            return payload
    return None


def extract_sample_rate(result: dict[str, object], fallback: int = 24000) -> int:
    for key in ("sample_rate", "tts_sample_rate", "sr"):
        value = result.get(key)
        if value is not None:
            return int(value)
    return fallback


def infer_sample_count(audio_payload: object) -> int:
    shape = getattr(audio_payload, "shape", None)
    if shape:
        return int(shape[-1])
    if isinstance(audio_payload, (bytes, bytearray)):
        return int(len(audio_payload) // 2)
    if isinstance(audio_payload, list):
        if audio_payload and isinstance(audio_payload[0], list):
            return len(audio_payload[0])
        return len(audio_payload)
    if hasattr(audio_payload, "__len__"):
        return int(len(audio_payload))  # type: ignore[arg-type]
    return 0


def extract_audio_duration_ms(result: dict[str, object], fallback_sr: int = 24000) -> float:
    audio_payload = extract_audio_payload(result)
    if audio_payload is None:
        fail("audio_payload", "CosyVoice result did not include audio/tts_speech/speech.")
    sample_rate = max(extract_sample_rate(result, fallback=fallback_sr), 1)
    sample_count = max(infer_sample_count(audio_payload), 0)
    return sample_count * 1000.0 / sample_rate


def probe_cuda() -> object:
    try:
        import torch
    except ModuleNotFoundError as exc:
        fail("torch_import", "PyTorch is not installed in this runtime.")
        raise AssertionError("unreachable") from exc
    if not torch.cuda.is_available():
        fail(
            "cuda_runtime",
            "torch.cuda.is_available() is False. Check NVIDIA driver, CUDA runtime, and GPU container access.",
        )
    device_name = torch.cuda.get_device_name(0)
    checkpoint_ok("cuda_runtime", f"device={device_name}")
    return torch


def register_vllm_model() -> None:
    try:
        import vllm
        from vllm import ModelRegistry
    except ModuleNotFoundError as exc:
        fail("vllm_import", "vllm is not installed in this runtime.")
        raise AssertionError("unreachable") from exc

    checkpoint_ok("vllm_import", f"version={getattr(vllm, '__version__', 'unknown')}")
    model_reference = "cosyvoice.vllm.cosyvoice2:CosyVoice2ForCausalLM"
    try:
        ModelRegistry.register_model("CosyVoice2ForCausalLM", model_reference)
    except Exception as exc:
        message = str(exc)
        if "already" not in message.lower():
            fail("model_registry", f"ModelRegistry.register_model failed: {message}")
        checkpoint_ok("model_registry", "CosyVoice2ForCausalLM already registered")
        return
    checkpoint_ok("model_registry", f"registered {model_reference}")


def load_cosyvoice_factory() -> object:
    cosyvoice_module = importlib.import_module("cosyvoice.cli.cosyvoice")
    factory = getattr(cosyvoice_module, "CosyVoice2", None)
    if factory is None:
        fail("cosyvoice_import", "cosyvoice.cli.cosyvoice.CosyVoice2 is missing from the vendor checkout.")
    checkpoint_ok("cosyvoice_import", "CosyVoice2 factory loaded")
    return factory


def main() -> int:
    args = parse_args()
    os.environ["COSYVOICE_ONNX_PROVIDER"] = args.onnx_provider.strip().lower()
    if args.trt_concurrent <= 0:
        fail("trt_concurrent", "--trt-concurrent must be a positive integer.")
    if args.vllm_gpu_memory_utilization <= 0.0 or args.vllm_gpu_memory_utilization > 1.0:
        fail(
            "vllm_gpu_memory_utilization",
            "--vllm-gpu-memory-utilization must be within (0, 1].",
        )

    model_dir = ensure_path("model_dir", args.model_dir, file_ok=False)
    code_dir = ensure_path("code_dir", args.code_dir, file_ok=False)
    vllm_model_dir = prepare_vllm_model_dir(args.vllm_model_dir)
    reference_audio = ensure_path("reference_audio", args.reference_audio, file_ok=True)

    torch = probe_cuda()
    add_cosyvoice_paths(code_dir)
    configure_vllm_plugin_environment(code_dir)
    register_vllm_model()
    factory = load_cosyvoice_factory()

    init_started_at = time.perf_counter()
    try:
        cosyvoice = factory(
            str(model_dir),
            load_trt=True,
            load_vllm=True,
            fp16=True,
            trt_concurrent=args.trt_concurrent,
            vllm_model_dir=str(vllm_model_dir),
            vllm_gpu_memory_utilization=args.vllm_gpu_memory_utilization,
            vllm_dtype=args.vllm_dtype,
        )
    except TypeError as exc:
        fail(
            "cosyvoice_init",
            "CosyVoice2 rejected TRT/vLLM init args. Update the vendor runtime to a build that supports load_vllm/load_trt.",
        )
        raise AssertionError("unreachable") from exc
    except Exception as exc:
        fail("cosyvoice_init", f"CosyVoice2 init failed: {exc}")
    init_elapsed_ms = (time.perf_counter() - init_started_at) * 1000.0
    checkpoint_ok("cosyvoice_init", f"elapsed_ms={init_elapsed_ms:.1f}")

    warmup_started_at = time.perf_counter()
    try:
        warmup_result = first_result(
            cosyvoice.inference_instruct2(
                args.warmup_text,
                args.instruction,
                str(reference_audio),
                stream=False,
                speed=args.speed,
            )
        )
    except Exception as exc:
        fail("warmup_inference", f"Warmup inference failed: {exc}")
    warmup_elapsed_ms = (time.perf_counter() - warmup_started_at) * 1000.0
    warmup_audio_ms = extract_audio_duration_ms(warmup_result)
    warmup_rtf = warmup_elapsed_ms / warmup_audio_ms if warmup_audio_ms > 0 else 0.0
    checkpoint_ok(
        "warmup_inference",
        f"elapsed_ms={warmup_elapsed_ms:.1f} audio_ms={warmup_audio_ms:.1f} rtf={warmup_rtf:.3f}",
    )

    stream_started_at = time.perf_counter()
    first_chunk_ms: float | None = None
    total_stream_audio_ms = 0.0
    chunk_count = 0
    try:
        for result in cosyvoice.inference_instruct2(
            args.stream_text,
            args.instruction,
            str(reference_audio),
            stream=True,
            speed=args.speed,
        ):
            chunk_count += 1
            if not isinstance(result, dict):
                fail("streaming_output", f"Expected dict chunk, got {type(result).__name__}.")
            chunk_audio_ms = extract_audio_duration_ms(result)
            total_stream_audio_ms += chunk_audio_ms
            elapsed_ms = (time.perf_counter() - stream_started_at) * 1000.0
            if first_chunk_ms is None:
                first_chunk_ms = elapsed_ms
                checkpoint_ok("streaming_first_chunk", f"first_chunk_ms={first_chunk_ms:.1f}")
    except Exception as exc:
        fail("streaming_inference", f"Streaming inference failed: {exc}")

    if chunk_count == 0:
        fail("streaming_inference", "Streaming inference produced zero chunks.")
    if chunk_count < 2:
        fail(
            "streaming_inference",
            "Streaming inference only produced one chunk. Re-run with a longer --stream-text to validate multi-chunk streaming.",
        )

    stream_elapsed_ms = (time.perf_counter() - stream_started_at) * 1000.0
    throughput_x = total_stream_audio_ms / stream_elapsed_ms if stream_elapsed_ms > 0 else 0.0
    stream_rtf = stream_elapsed_ms / total_stream_audio_ms if total_stream_audio_ms > 0 else 0.0
    checkpoint_ok(
        "streaming_inference",
        "chunks=%s elapsed_ms=%.1f audio_ms=%.1f throughput_x=%.3f rtf=%.3f"
        % (chunk_count, stream_elapsed_ms, total_stream_audio_ms, throughput_x, stream_rtf),
    )

    checkpoint_ok(
        "probe_complete",
        "CosyVoice2 TRT + vLLM path is runnable in isolation on this server.",
    )

    if torch.cuda.is_available():
        try:
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError:
        raise SystemExit(1)
