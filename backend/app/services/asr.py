from __future__ import annotations

import asyncio
from functools import lru_cache

import numpy as np

from app.core.config import Settings, get_settings


class ASRService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._model_error: str | None = None

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
        if not audio_bytes:
            return ""

        if self.settings.asr_engine == "mock":
            return self.settings.asr_mock_transcript

        await self._load_model()
        if self._model is None:
            return self.settings.asr_mock_transcript

        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return await asyncio.to_thread(self._transcribe_sync, audio_array, sample_rate)

    async def _load_model(self) -> None:
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


@lru_cache
def get_asr_service() -> ASRService:
    return ASRService(get_settings())
