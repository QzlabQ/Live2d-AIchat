from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
import importlib
from io import BytesIO
from pathlib import Path
import re
import sys
import wave

from pypinyin import Style, lazy_pinyin

from app.core.config import Settings, get_settings

PUNCTUATION_RE = re.compile(r"[，。！？!?；;、,\s]+")
LATIN_VOWEL_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)
NON_ALPHA_RE = re.compile(r"[^a-z]")
COSYVOICE_ALIGNMENT_KEYS = ("alignment", "alignments", "phonemes", "phoneme_alignment")

MOUTH_POSES: dict[str, tuple[float, float]] = {
    "a": (0.92, 0.04),
    "i": (0.42, 0.82),
    "u": (0.62, -0.72),
    "e": (0.52, 0.25),
    "o": (0.72, -0.45),
    "N": (0.06, 0.0),
}


@dataclass(slots=True)
class TTSChunk:
    seq: int
    text: str
    audio_bytes: bytes
    phonemes: list[dict[str, float | str]]
    mime_type: str = "audio/mpeg"


class TTSService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine_error: str | None = None
        self._cosyvoice_model: object | None = None

    def status(self) -> str:
        if self.settings.tts_engine == "mock":
            return "mock"

        try:
            if self.settings.tts_engine == "cosyvoice":
                self._load_cosyvoice_model()
                return "ready"

            if self.settings.tts_engine == "edge-tts":
                import edge_tts  # noqa: F401

                return "ready"

            return f"degraded:Unsupported TTS engine: {self.settings.tts_engine}"
        except Exception as exc:  # pragma: no cover - environment dependent
            self._engine_error = str(exc)
            return f"degraded:{self._engine_error}"

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

        if self.settings.tts_engine == "cosyvoice":
            try:
                return self._synthesize_cosyvoice(cleaned_text, seq=seq, voice_id=voice_id)
            except Exception as exc:  # pragma: no cover - runtime dependency
                self._engine_error = str(exc)
                try:
                    return await self._synthesize_edge(cleaned_text, seq=seq, voice_id=voice_id)
                except Exception:
                    return TTSChunk(
                        seq=seq,
                        text=cleaned_text,
                        audio_bytes=b"",
                        phonemes=self._fallback_phonemes(cleaned_text),
                    )

        try:
            return await self._synthesize_edge(cleaned_text, seq=seq, voice_id=voice_id)
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._engine_error = str(exc)
            return TTSChunk(
                seq=seq,
                text=cleaned_text,
                audio_bytes=b"",
                phonemes=self._fallback_phonemes(cleaned_text),
            )

    async def _synthesize_edge(self, cleaned_text: str, seq: int, voice_id: str | None) -> TTSChunk:
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
            mime_type="audio/mpeg",
        )

    def _synthesize_cosyvoice(self, cleaned_text: str, seq: int, voice_id: str | None) -> TTSChunk:
        cosyvoice = self._load_cosyvoice_model()
        speaker = self._resolve_cosyvoice_speaker(voice_id)
        result = self._first_result(cosyvoice.inference_sft(cleaned_text, speaker, stream=False))
        if not isinstance(result, dict):
            raise RuntimeError("CosyVoice 返回格式异常，预期为 dict。")

        audio_payload = result.get("audio")
        if audio_payload is None:
            audio_payload = result.get("tts_speech")
        if audio_payload is None:
            audio_payload = result.get("speech")
        if audio_payload is None:
            raise RuntimeError("CosyVoice 未返回音频数据。")

        sample_rate = int(
            result.get("sample_rate")
            or result.get("tts_sample_rate")
            or result.get("sr")
            or self.settings.tts_cosyvoice_sample_rate
        )
        audio_bytes, duration_seconds = self._coerce_audio_payload(audio_payload, sample_rate)

        alignment = self._extract_alignment(result)
        phonemes = (
            self._phonemes_from_alignment(alignment)
            if alignment
            else self._fallback_phonemes(cleaned_text, total_duration=duration_seconds)
        )

        return TTSChunk(
            seq=seq,
            text=cleaned_text,
            audio_bytes=audio_bytes,
            phonemes=phonemes,
            mime_type="audio/wav",
        )

    def _load_cosyvoice_model(self) -> object:
        if self._cosyvoice_model is not None:
            return self._cosyvoice_model

        model_path = Path(self.settings.tts_cosyvoice_model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"CosyVoice 模型目录不存在：{model_path}. 请先下载本地模型后再启用 TTS_ENGINE=cosyvoice。"
            )

        device = self._resolve_cosyvoice_device()
        module = self._import_cosyvoice_module()
        factory = getattr(module, "CosyVoice2", None)
        if factory is None:
            raise RuntimeError("未找到 cosyvoice.cli.cosyvoice.CosyVoice2，请检查本地 CosyVoice 安装。")

        try:
            self._cosyvoice_model = factory(str(model_path), device=device)
        except TypeError:
            self._cosyvoice_model = factory(str(model_path))
            self._move_cosyvoice_runtime(self._cosyvoice_model, device)

        return self._cosyvoice_model

    def _import_cosyvoice_module(self):
        try:
            return importlib.import_module("cosyvoice.cli.cosyvoice")
        except ModuleNotFoundError as original_exc:
            code_path = Path(self.settings.tts_cosyvoice_code_path).resolve()
            if not code_path.exists():
                raise RuntimeError(
                    f"CosyVoice 代码目录不存在：{code_path}. 请先把官方仓库放到该目录，"
                    "或修改 TTS_COSYVOICE_CODE_PATH。"
                ) from original_exc

            if str(code_path) not in sys.path:
                sys.path.insert(0, str(code_path))
            matcha_path = code_path / "third_party" / "Matcha-TTS"
            if matcha_path.exists() and str(matcha_path) not in sys.path:
                sys.path.insert(0, str(matcha_path))

            try:
                return importlib.import_module("cosyvoice.cli.cosyvoice")
            except ModuleNotFoundError as patched_exc:
                raise RuntimeError(
                    "已找到 CosyVoice 代码目录，但仍无法导入 cosyvoice.cli.cosyvoice。"
                    "请确认仓库完整克隆（含 third_party 子模块）并已安装 CosyVoice 运行时依赖。"
                ) from patched_exc

    def _resolve_cosyvoice_device(self) -> str:
        requested = self.settings.tts_cosyvoice_device.strip().lower()

        try:
            import torch
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("CosyVoice 需要可用的 PyTorch 运行时。") from exc

        if requested in {"", "auto"}:
            return "cuda" if torch.cuda.is_available() else "cpu"

        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(
                "当前 conda 环境中的 torch 不支持 CUDA。请安装 GPU 版 PyTorch 后再使用 CosyVoice GPU。"
            )

        return requested

    def _move_cosyvoice_runtime(self, model: object, device: str) -> None:
        if device == "cpu":
            return

        for attr_name in ("model", "flow", "llm", "vocoder", "tts_model"):
            component = getattr(model, attr_name, None)
            if component is not None and hasattr(component, "to"):
                try:
                    component.to(device)
                except Exception:
                    continue

    def _resolve_cosyvoice_speaker(self, voice_id: str | None) -> str:
        candidate = (voice_id or "").strip()
        if candidate and "neural" not in candidate.lower() and not candidate.lower().startswith("zh-"):
            return candidate
        return self.settings.tts_cosyvoice_speaker

    def _extract_alignment(self, result: dict[str, object]) -> list[dict[str, object]]:
        for key in COSYVOICE_ALIGNMENT_KEYS:
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _phonemes_from_alignment(self, alignment: list[dict[str, object]]) -> list[dict[str, float | str]]:
        phonemes: list[dict[str, float | str]] = []
        for item in alignment:
            phoneme = str(item.get("ph") or item.get("phoneme") or item.get("text") or "").strip()
            if not phoneme:
                continue

            start = float(item.get("start") or item.get("begin") or item.get("offset") or 0.0)
            end = item.get("end")
            duration = item.get("duration")
            if end is None:
                end = start + float(duration or 0.12)

            phonemes.append(self._frame_from_shape(self._syllable_to_shape(phoneme), start, float(end)))

        if phonemes and phonemes[-1]["ph"] != "N":
            phonemes.append(self._frame_from_shape("N", float(phonemes[-1]["end"]), float(phonemes[-1]["end"]) + 0.08))
        return phonemes

    def _phonemes_from_boundaries(
        self, text: str, boundaries: list[dict[str, object]]
    ) -> list[dict[str, float | str]]:
        if not boundaries:
            return self._fallback_phonemes(text)

        phonemes: list[dict[str, float | str]] = []
        for item in boundaries:
            token = str(item.get("text", "")).strip()
            if not token:
                continue

            start = float(item.get("offset", 0)) / 10_000_000
            duration = max(float(item.get("duration", 0)) / 10_000_000, 0.12)
            shapes = self._token_to_shapes(token)
            unit_count = max(len(shapes), 1)
            slice_duration = duration / unit_count

            cursor = start
            for shape in shapes or ["N"]:
                phonemes.append(self._frame_from_shape(shape, cursor, cursor + slice_duration))
                cursor += slice_duration

        if phonemes:
            phonemes.append(self._frame_from_shape("N", float(phonemes[-1]["end"]), float(phonemes[-1]["end"]) + 0.08))
        return phonemes

    def _fallback_phonemes(
        self,
        text: str,
        total_duration: float | None = None,
    ) -> list[dict[str, float | str]]:
        shapes = self._extract_mouth_shapes(text)
        unit_count = max(len(shapes), 1)
        duration = max(total_duration or (0.14 * unit_count), 0.3)
        step = duration / unit_count

        phonemes: list[dict[str, float | str]] = []
        cursor = 0.0
        for shape in shapes or ["N"]:
            phonemes.append(self._frame_from_shape(shape, cursor, cursor + step))
            cursor += step

        phonemes.append(self._frame_from_shape("N", cursor, cursor + 0.08))
        return phonemes

    def _extract_mouth_shapes(self, text: str) -> list[str]:
        shapes: list[str] = []
        for token in [token for token in PUNCTUATION_RE.split(text) if token]:
            shapes.extend(self._token_to_shapes(token))
        return shapes or ["N"]

    def _token_to_shapes(self, token: str) -> list[str]:
        stripped = token.strip()
        if not stripped:
            return []

        syllables = lazy_pinyin(
            stripped,
            style=Style.NORMAL,
            strict=False,
            errors=lambda raw: list(raw),
        )

        shapes: list[str] = []
        for syllable in syllables:
            lowered = str(syllable).strip().lower()
            if not lowered:
                continue

            vowel_groups = LATIN_VOWEL_RE.findall(lowered)
            if vowel_groups:
                shapes.extend(self._syllable_to_shape(group) for group in vowel_groups)

        return shapes or ["N"]

    def _syllable_to_shape(self, syllable: str) -> str:
        normalized = syllable.lower().replace("ü", "v")
        normalized = NON_ALPHA_RE.sub("", normalized)
        if not normalized:
            return "N"

        if "a" in normalized:
            return "a"
        if "o" in normalized:
            return "o"
        if "u" in normalized or "v" in normalized or normalized.startswith("w"):
            return "u"
        if "i" in normalized or normalized.startswith("y"):
            return "i"
        if "e" in normalized or normalized.endswith("r"):
            return "e"
        return "N"

    def _frame_from_shape(self, shape: str, start: float, end: float) -> dict[str, float | str]:
        open_y, form = MOUTH_POSES.get(shape, MOUTH_POSES["N"])
        return {
            "ph": shape if shape in MOUTH_POSES else "N",
            "start": round(start, 3),
            "end": round(max(end, start + 0.04), 3),
            "openY": open_y,
            "form": form,
        }

    def _first_result(self, output: object) -> object:
        if isinstance(output, dict):
            return output
        if isinstance(output, Iterable) and not isinstance(output, (bytes, bytearray, str)):
            iterator = iter(output)
            return next(iterator, None)
        return output

    def _coerce_audio_payload(self, payload: object, sample_rate: int) -> tuple[bytes, float]:
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("CosyVoice 音频解码依赖 numpy，请先在当前环境中安装可用的 numpy。") from exc

        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload), 0.0

        if hasattr(payload, "detach"):
            payload = payload.detach()
        if hasattr(payload, "cpu"):
            payload = payload.cpu()
        if hasattr(payload, "numpy"):
            payload = payload.numpy()

        audio_array = np.asarray(payload).squeeze()
        if audio_array.ndim != 1:
            raise RuntimeError("CosyVoice 音频数据维度异常，预期为单声道数组。")

        if np.issubdtype(audio_array.dtype, np.integer):
            pcm = audio_array.astype(np.int16)
        else:
            pcm = (np.clip(audio_array.astype(np.float32), -1.0, 1.0) * 32767).astype(np.int16)

        audio_bytes = self._pcm16_to_wav_bytes(pcm, sample_rate)
        duration_seconds = float(len(pcm) / max(sample_rate, 1))
        return audio_bytes, duration_seconds

    def _pcm16_to_wav_bytes(self, pcm, sample_rate: int) -> bytes:
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return buffer.getvalue()


@lru_cache
def get_tts_service() -> TTSService:
    return TTSService(get_settings())
