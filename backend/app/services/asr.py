from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

import numpy as np
from opencc import OpenCC

from app.core.config import Settings, get_settings


@dataclass(slots=True)
class ASRTranscriptionResult:
    text: str
    model_load_ms: int = 0
    asr_transcribe_ms: int = 0
    asr_total_ms: int = 0


class ASRService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._model_error: str | None = None
        self._load_lock = asyncio.Lock()

    def status(self) -> str:
        if self.settings.asr_engine == "mock":
            return "mock"
        if self._model_error:
            return f"degraded:{self._model_error}"
        if self._model is not None:
            return "ready"
        try:
            import faster_whisper  # noqa: F401
        except Exception as exc:  # pragma: no cover - environment dependent
            self._model_error = str(exc)
            return f"degraded:{self._model_error}"
        return "ready"

    async def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        result = await self.transcribe_with_metrics(audio_bytes, sample_rate=sample_rate)
        return result.text

    async def transcribe_with_metrics(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> ASRTranscriptionResult:
        if not audio_bytes:
            return ASRTranscriptionResult(text="")

        if self.settings.asr_engine == "mock":
            return ASRTranscriptionResult(text=self._normalize_transcript_text(self.settings.asr_mock_transcript))

        total_started_at = perf_counter()
        model_load_ms = await self.ensure_model_loaded()
        if self._model is None:
            return ASRTranscriptionResult(
                text=self._normalize_transcript_text(self.settings.asr_mock_transcript),
                model_load_ms=model_load_ms,
                asr_total_ms=int((perf_counter() - total_started_at) * 1000),
            )

        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        transcribe_started_at = perf_counter()
        text = await asyncio.to_thread(self._transcribe_sync, audio_array, sample_rate)
        transcribe_ms = int((perf_counter() - transcribe_started_at) * 1000)
        total_ms = int((perf_counter() - total_started_at) * 1000)
        return ASRTranscriptionResult(
            text=self._normalize_transcript_text(text),
            model_load_ms=model_load_ms,
            asr_transcribe_ms=transcribe_ms,
            asr_total_ms=total_ms,
        )

    async def warmup(self) -> int:
        if self.settings.asr_engine == "mock":
            return 0
        return await self.ensure_model_loaded()

    async def ensure_model_loaded(self) -> int:
        if self._model is not None or self._model_error is not None:
            return 0

        async with self._load_lock:
            if self._model is not None or self._model_error is not None:
                return 0
            started_at = perf_counter()
            await asyncio.to_thread(self._load_model_sync)
            return int((perf_counter() - started_at) * 1000)

    def _load_model_sync(self) -> None:
        if self._model is not None or self._model_error is not None:
            return

        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.settings.asr_model_name,
                device=self.settings.asr_device,
                compute_type=self.settings.asr_compute_type,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._model_error = str(exc)

    def _transcribe_sync(self, audio_array: np.ndarray, sample_rate: int) -> str:
        segments, _ = self._model.transcribe(
            audio_array,
            language=self.settings.asr_language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 200},
        )
        text = "".join(segment.text for segment in segments).strip()
        return text or self.settings.asr_mock_transcript

    @staticmethod
    def _normalize_transcript_text(text: str) -> str:
        normalized = text.strip()
        if not normalized:
            return normalized
        return _get_opencc_t2s().convert(normalized)


@lru_cache
def get_asr_service() -> ASRService:
    return ASRService(get_settings())


@lru_cache
def _get_opencc_t2s() -> OpenCC:
    return OpenCC("t2s")
