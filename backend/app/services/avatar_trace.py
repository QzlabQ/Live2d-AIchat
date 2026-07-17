from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

UTC = timezone.utc

_DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "avatar_trace.log"


@dataclass(slots=True)
class ReplyTrace:
    reply_id: str
    session_id: str
    streaming: bool
    chat_mode: str
    tts_engine: str
    tts_synthesis_strategy: str | None = None
    tts_vendor_session_count: int = 0
    prompt_cache_hit: bool | None = None
    prompt_cache_build_ms: float | None = None
    torch_cuda_available: bool | None = None
    torch_device_name: str | None = None
    requested_onnx_provider: str | None = None
    available_onnx_providers: list[str] = field(default_factory=list)
    tts_stream_profile: str | None = None
    tts_cosyvoice_fp16: bool | None = None
    tts_cosyvoice_load_jit: bool | None = None
    tts_cosyvoice_load_trt: bool | None = None
    tts_cosyvoice_trt_concurrent: int | None = None
    tts_ar_backend: str | None = None
    tts_flow_backend: str | None = None
    tts_trt_engine_expected: bool | None = None
    tts_trt_engine_loaded: bool | None = None
    tts_segment_soft_min_chars: int | None = None
    tts_segment_soft_max_chars: int | None = None
    tts_segment_hard_max_chars: int | None = None
    tts_prefetch_enabled: bool | None = None
    tts_prefetch_started_count: int = 0
    tts_prefetch_hit_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metrics: dict[str, int] = field(default_factory=dict)
    segment_count: int = 0
    audio_chunk_count: int = 0
    max_chunk_gap_ms: int = 0
    tts_chunks: list[dict[str, int | float]] = field(default_factory=list)
    _last_audio_chunk_at_ms: int | None = field(default=None, init=False, repr=False)
    _last_audio_chunk_duration_ms: int | None = field(default=None, init=False, repr=False)
    _tts_vendor_session_seqs: set[int] = field(default_factory=set, init=False, repr=False)

    def mark(self, name: str, at_ms: int) -> None:
        if name not in self.metrics:
            self.metrics[name] = int(at_ms)

    def set_metric(self, name: str, value_ms: int) -> None:
        self.metrics[name] = int(value_ms)

    def set_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.torch_cuda_available = snapshot.get("torch_cuda_available")  # type: ignore[assignment]
        self.torch_device_name = snapshot.get("torch_device_name")  # type: ignore[assignment]
        self.requested_onnx_provider = snapshot.get("requested_onnx_provider")  # type: ignore[assignment]
        providers = snapshot.get("available_onnx_providers")
        self.available_onnx_providers = list(providers) if isinstance(providers, list) else []
        self.tts_stream_profile = snapshot.get("tts_stream_profile")  # type: ignore[assignment]
        self.tts_cosyvoice_fp16 = snapshot.get("tts_cosyvoice_fp16")  # type: ignore[assignment]
        self.tts_cosyvoice_load_jit = snapshot.get("tts_cosyvoice_load_jit")  # type: ignore[assignment]
        self.tts_cosyvoice_load_trt = snapshot.get("tts_cosyvoice_load_trt")  # type: ignore[assignment]
        self.tts_cosyvoice_trt_concurrent = snapshot.get("tts_cosyvoice_trt_concurrent")  # type: ignore[assignment]
        self.tts_ar_backend = snapshot.get("tts_ar_backend")  # type: ignore[assignment]
        self.tts_flow_backend = snapshot.get("tts_flow_backend")  # type: ignore[assignment]
        self.tts_trt_engine_expected = snapshot.get("tts_trt_engine_expected")  # type: ignore[assignment]
        self.tts_trt_engine_loaded = snapshot.get("tts_trt_engine_loaded")  # type: ignore[assignment]
        self.tts_segment_soft_min_chars = snapshot.get("tts_segment_soft_min_chars")  # type: ignore[assignment]
        self.tts_segment_soft_max_chars = snapshot.get("tts_segment_soft_max_chars")  # type: ignore[assignment]
        self.tts_segment_hard_max_chars = snapshot.get("tts_segment_hard_max_chars")  # type: ignore[assignment]
        self.tts_synthesis_strategy = snapshot.get("tts_synthesis_strategy")  # type: ignore[assignment]
        self.tts_prefetch_enabled = snapshot.get("tts_prefetch_enabled")  # type: ignore[assignment]

    def set_prompt_cache_snapshot(self, *, hit: bool | None, build_ms: float | None) -> None:
        self.prompt_cache_hit = hit
        self.prompt_cache_build_ms = build_ms

    def observe_audio_chunk(self, at_ms: int) -> None:
        observed_at = int(at_ms)
        self.audio_chunk_count += 1
        if self._last_audio_chunk_at_ms is not None:
            self.max_chunk_gap_ms = max(
                self.max_chunk_gap_ms,
                observed_at - self._last_audio_chunk_at_ms,
            )
        self._last_audio_chunk_at_ms = observed_at

    def observe_tts_chunk(
        self,
        *,
        seq: int,
        chunk_index: int,
        sent_at_ms: int,
        audio_duration_ms: int,
        model_ready_ms: int,
        send_lag_ms: int,
        token_wait_ms: int = 0,
        token2wav_ms: int = 0,
        hop_len: int = 0,
        token_offset: int = 0,
        is_final: bool = False,
        llm_done_ms: int | None = None,
        final_decode_enter_ms: int | None = None,
        prefetch_enabled: bool | None = None,
        prefetch_started_count_delta: int = 0,
        prefetch_hit_count_delta: int = 0,
    ) -> None:
        observed_at = int(sent_at_ms)
        gap_ms = 0
        self.audio_chunk_count += 1
        if self._last_audio_chunk_at_ms is not None:
            gap_ms = observed_at - self._last_audio_chunk_at_ms
            self.max_chunk_gap_ms = max(self.max_chunk_gap_ms, gap_ms)
        previous_audio_ms = self._last_audio_chunk_duration_ms or 0
        self._last_audio_chunk_at_ms = observed_at
        observed_seq = int(seq)
        if observed_seq not in self._tts_vendor_session_seqs:
            self._tts_vendor_session_seqs.add(observed_seq)
            self.tts_vendor_session_count += 1
        duration_ms = max(int(audio_duration_ms), 0)
        self._last_audio_chunk_duration_ms = duration_ms
        chunk_token_wait_ms = max(int(token_wait_ms), 0)
        chunk_token2wav_ms = max(int(token2wav_ms), 0)
        chunk_generate_ms = chunk_token_wait_ms + chunk_token2wav_ms
        ready_ratio = round(float(model_ready_ms) / duration_ms, 3) if duration_ms > 0 else 0.0
        real_rtf = round(float(duration_ms) / chunk_generate_ms, 3) if chunk_generate_ms > 0 else 0.0
        chunk_supply_lag_ms = int(gap_ms - previous_audio_ms) if self.tts_chunks else 0
        self.metrics["tts_total_token_wait_ms"] = self.metrics.get("tts_total_token_wait_ms", 0) + chunk_token_wait_ms
        self.metrics["tts_total_token2wav_ms"] = (
            self.metrics.get("tts_total_token2wav_ms", 0) + chunk_token2wav_ms
        )
        if llm_done_ms is not None:
            self.metrics["tts_llm_done_ms"] = int(llm_done_ms)
        if final_decode_enter_ms is not None:
            self.metrics["tts_final_decode_enter_ms"] = int(final_decode_enter_ms)
        if prefetch_enabled is not None:
            self.tts_prefetch_enabled = bool(prefetch_enabled)
        self.tts_prefetch_started_count += max(int(prefetch_started_count_delta), 0)
        self.tts_prefetch_hit_count += max(int(prefetch_hit_count_delta), 0)
        self.tts_chunks.append(
            {
                "seq": int(seq),
                "chunk_index": int(chunk_index),
                "sent_at_ms": observed_at,
                "tts_chunk_audio_ms": duration_ms,
                "tts_model_ready_ms": int(model_ready_ms),
                "tts_ws_send_lag_ms": int(send_lag_ms),
                "tts_chunk_gap_ms": int(max(gap_ms, 0)),
                "tts_chunk_rtf": ready_ratio,
                "tts_chunk_ready_ratio": ready_ratio,
                "tts_chunk_real_rtf": real_rtf,
                "token_wait_ms": chunk_token_wait_ms,
                "token2wav_ms": chunk_token2wav_ms,
                "hop_len": int(max(hop_len, 0)),
                "token_offset": int(max(token_offset, 0)),
                "chunk_supply_lag_ms": chunk_supply_lag_ms,
                "is_final": bool(is_final),
            }
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "reply_id": self.reply_id,
            "session_id": self.session_id,
            "streaming": self.streaming,
            "chat_mode": self.chat_mode,
            "tts_engine": self.tts_engine,
            "tts_synthesis_strategy": self.tts_synthesis_strategy,
            "tts_vendor_session_count": self.tts_vendor_session_count,
            "prompt_cache_hit": self.prompt_cache_hit,
            "prompt_cache_build_ms": self.prompt_cache_build_ms,
            "torch_cuda_available": self.torch_cuda_available,
            "torch_device_name": self.torch_device_name,
            "requested_onnx_provider": self.requested_onnx_provider,
            "available_onnx_providers": list(self.available_onnx_providers),
            "tts_stream_profile": self.tts_stream_profile,
            "tts_cosyvoice_fp16": self.tts_cosyvoice_fp16,
            "tts_cosyvoice_load_jit": self.tts_cosyvoice_load_jit,
            "tts_cosyvoice_load_trt": self.tts_cosyvoice_load_trt,
            "tts_cosyvoice_trt_concurrent": self.tts_cosyvoice_trt_concurrent,
            "tts_ar_backend": self.tts_ar_backend,
            "tts_flow_backend": self.tts_flow_backend,
            "tts_trt_engine_expected": self.tts_trt_engine_expected,
            "tts_trt_engine_loaded": self.tts_trt_engine_loaded,
            "tts_segment_soft_min_chars": self.tts_segment_soft_min_chars,
            "tts_segment_soft_max_chars": self.tts_segment_soft_max_chars,
            "tts_segment_hard_max_chars": self.tts_segment_hard_max_chars,
            "tts_prefetch_enabled": self.tts_prefetch_enabled,
            "tts_prefetch_started_count": self.tts_prefetch_started_count,
            "tts_prefetch_hit_count": self.tts_prefetch_hit_count,
            "segment_count": self.segment_count,
            "audio_chunk_count": self.audio_chunk_count,
            "max_chunk_gap_ms": self.max_chunk_gap_ms,
            "tts_chunks": list(self.tts_chunks),
            "metrics": dict(self.metrics),
        }


class TraceLoggerWorker:
    def __init__(self, log_path: Path | str = _DEFAULT_LOG_PATH) -> None:
        self.log_path = Path(log_path)
        self._queue: asyncio.Queue[ReplyTrace | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="avatar-trace-logger")

    async def stop(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        await self._task
        self._task = None

    def enqueue(self, trace: ReplyTrace) -> None:
        self._queue.put_nowait(trace)

    async def _run(self) -> None:
        while True:
            trace = await self._queue.get()
            try:
                if trace is None:
                    return
                await asyncio.to_thread(self._append_trace, trace)
            except Exception:
                logger.exception("Failed to write avatar trace.")
            finally:
                self._queue.task_done()

    def _append_trace(self, trace: ReplyTrace) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(trace.to_payload(), ensure_ascii=False, sort_keys=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class AvatarTraceService:
    def __init__(self, worker: TraceLoggerWorker | None = None) -> None:
        self.worker = worker or TraceLoggerWorker()

    async def start(self) -> None:
        await self.worker.start()

    async def stop(self) -> None:
        await self.worker.stop()

    def enqueue_trace(self, trace: ReplyTrace) -> None:
        self.worker.enqueue(trace)


_avatar_trace_service: AvatarTraceService | None = None


def get_avatar_trace_service() -> AvatarTraceService:
    global _avatar_trace_service
    if _avatar_trace_service is None:
        _avatar_trace_service = AvatarTraceService()
    return _avatar_trace_service
