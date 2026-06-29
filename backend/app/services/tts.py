from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import itertools
import re

from app.core.config import Settings, get_settings

PUNCTUATION_RE = re.compile(r"[，。！？!?；;、,\s]+")
MOUTH_SHAPES = ("a", "i", "u", "e", "o")


@dataclass(slots=True)
class TTSChunk:
    seq: int
    text: str
    audio_bytes: bytes
    phonemes: list[dict[str, float | str]]


class TTSService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine_error: str | None = None

    def status(self) -> str:
        if self.settings.tts_engine == "mock":
            return "mock"
        if self._engine_error:
            return f"degraded:{self._engine_error}"
        try:
            import edge_tts  # noqa: F401
        except Exception as exc:  # pragma: no cover - environment dependent
            self._engine_error = str(exc)
            return f"degraded:{self._engine_error}"
        return "ready"

    async def synthesize_chunk(self, text: str, seq: int, voice_id: str | None = None) -> TTSChunk:
        cleaned_text = text.strip()
        if not cleaned_text:
            return TTSChunk(seq=seq, text=text, audio_bytes=b"", phonemes=[])

        if self.settings.tts_engine == "mock":
            return TTSChunk(
                seq=seq,
                text=cleaned_text,
                audio_bytes=b"",
                phonemes=self._fallback_phonemes(cleaned_text),
            )

        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                cleaned_text,
                voice=voice_id or self.settings.tts_voice,
                rate=self.settings.tts_rate,
                pitch=self.settings.tts_pitch,
            )

            audio_buffer = bytearray()
            boundaries: list[dict[str, object]] = []
            async for message in communicate.stream():
                message_type = message.get("type")
                if message_type == "audio":
                    audio_buffer.extend(message["data"])
                elif message_type == "WordBoundary":
                    boundaries.append(message)

            phonemes = self._phonemes_from_boundaries(cleaned_text, boundaries)
            return TTSChunk(
                seq=seq,
                text=cleaned_text,
                audio_bytes=bytes(audio_buffer),
                phonemes=phonemes,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._engine_error = str(exc)
            return TTSChunk(
                seq=seq,
                text=cleaned_text,
                audio_bytes=b"",
                phonemes=self._fallback_phonemes(cleaned_text),
            )

    def _phonemes_from_boundaries(
        self, text: str, boundaries: list[dict[str, object]]
    ) -> list[dict[str, float | str]]:
        if not boundaries:
            return self._fallback_phonemes(text)

        phonemes: list[dict[str, float | str]] = []
        mouth_shape_cycle = itertools.cycle(MOUTH_SHAPES)
        for item in boundaries:
            token = str(item.get("text", "")).strip()
            if not token:
                continue

            start = float(item.get("offset", 0)) / 10_000_000
            duration = max(float(item.get("duration", 0)) / 10_000_000, 0.12)
            units = [piece for piece in PUNCTUATION_RE.split(token) if piece]
            unit_count = max(sum(len(unit) for unit in units), 1)
            slice_duration = duration / unit_count

            cursor = start
            for _ in range(unit_count):
                phonemes.append(
                    {
                        "ph": next(mouth_shape_cycle),
                        "start": round(cursor, 3),
                        "end": round(cursor + slice_duration, 3),
                    }
                )
                cursor += slice_duration

        if phonemes:
            phonemes.append(
                {
                    "ph": "N",
                    "start": round(phonemes[-1]["end"], 3),
                    "end": round(phonemes[-1]["end"] + 0.08, 3),
                }
            )
        return phonemes

    def _fallback_phonemes(self, text: str) -> list[dict[str, float | str]]:
        tokens = [token for token in PUNCTUATION_RE.split(text) if token]
        token_length = max(sum(len(token) for token in tokens), 1)
        total_duration = max(0.14 * token_length, 0.3)
        step = total_duration / token_length

        phonemes: list[dict[str, float | str]] = []
        cursor = 0.0
        for index in range(token_length):
            phonemes.append(
                {
                    "ph": MOUTH_SHAPES[index % len(MOUTH_SHAPES)],
                    "start": round(cursor, 3),
                    "end": round(cursor + step, 3),
                }
            )
            cursor += step

        phonemes.append({"ph": "N", "start": round(cursor, 3), "end": round(cursor + 0.08, 3)})
        return phonemes


@lru_cache
def get_tts_service() -> TTSService:
    return TTSService(get_settings())
