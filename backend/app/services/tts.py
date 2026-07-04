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
BACKEND_ROOT = Path(__file__).resolve().parents[2]

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

    def _load_cosyvoice_model(self) -> object:
        if self._cosyvoice_model is not None:
            return self._cosyvoice_model

        model_path = self._resolve_backend_path(self.settings.tts_cosyvoice_model_path)
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
            code_path = self._resolve_backend_path(self.settings.tts_cosyvoice_code_path)
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

    def _resolve_backend_path(self, value: str) -> Path:
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()

        backend_candidate = BACKEND_ROOT / candidate
        if backend_candidate.exists():
            return backend_candidate.resolve()

        cwd_candidate = Path.cwd() / candidate
        if cwd_candidate.exists():
            return cwd_candidate.resolve()

        return backend_candidate.resolve()

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

    def _pcm16_to_wav_bytes(self, pcm, sample_rate: int) -> bytes:
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return buffer.getvalue()

    async def synthesize_chunk(
        self,
        text: str,
        seq: int,
        voice_id: str | None = None,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        speed: float | None = None,
        tts_emotion_enabled: bool = True,
    ) -> TTSChunk:
        cleaned_text = text.strip()
        if not cleaned_text:
            return TTSChunk(seq=seq, text=text, audio_bytes=b'', phonemes=[])

        if self.settings.tts_engine == 'mock':
            return TTSChunk(seq=seq, text=cleaned_text, audio_bytes=b'', phonemes=self._fallback_phonemes(cleaned_text))

        if self.settings.tts_engine == 'cosyvoice':
            try:
                return self._synthesize_cosyvoice(
                    cleaned_text,
                    seq=seq,
                    voice_id=voice_id,
                    emotion=emotion,
                    reference_audio_path=reference_audio_path,
                    reference_text=reference_text,
                    speed=speed,
                    emotion_enabled=tts_emotion_enabled,
                )
            except Exception as exc:  # pragma: no cover - runtime dependency
                self._engine_error = str(exc)
                try:
                    return await self._synthesize_edge(cleaned_text, seq=seq, voice_id=voice_id)
                except Exception:
                    return TTSChunk(seq=seq, text=cleaned_text, audio_bytes=b'', phonemes=self._fallback_phonemes(cleaned_text))

        try:
            return await self._synthesize_edge(cleaned_text, seq=seq, voice_id=voice_id)
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            self._engine_error = str(exc)
            return TTSChunk(seq=seq, text=cleaned_text, audio_bytes=b'', phonemes=self._fallback_phonemes(cleaned_text))

    def _build_cosyvoice_instruction(self, emotion: str | None, emotion_enabled: bool = True) -> str:
        mapping = {
            'happy': '\u7528\u6109\u5feb\u3001\u4eb2\u5207\u3001\u81ea\u7136\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>',
            'excited': '\u7528\u70ed\u60c5\u3001\u5174\u594b\u3001\u611f\u67d3\u529b\u5f3a\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>',
            'thinking': '\u7528\u5e73\u9759\u3001\u601d\u8003\u611f\u66f4\u5f3a\u3001\u7565\u5e26\u505c\u987f\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>',
            'sad': '\u7528\u6e29\u548c\u3001\u514b\u5236\u3001\u7565\u4f4e\u6c89\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>',
            'neutral': '\u7528\u81ea\u7136\u3001\u53cb\u597d\u3001\u6e05\u6670\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>',
        }
        if not emotion_enabled:
            return mapping['neutral']
        return mapping.get((emotion or 'neutral').strip().lower(), mapping['neutral'])

    def _synthesize_cosyvoice(
        self,
        cleaned_text: str,
        seq: int,
        voice_id: str | None,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        speed: float | None = None,
        emotion_enabled: bool = True,
    ) -> TTSChunk:
        del voice_id, reference_text
        cosyvoice = self._load_cosyvoice_model()
        prompt_wav = self._resolve_reference_audio_path(reference_audio_path)
        instruct_text = self._build_cosyvoice_instruction(emotion, emotion_enabled=emotion_enabled)
        result = self._first_result(
            cosyvoice.inference_instruct2(
                cleaned_text,
                instruct_text,
                prompt_wav,
                stream=False,
                speed=float(speed or 1.0),
            )
        )
        if not isinstance(result, dict):
            raise RuntimeError('CosyVoice returned an unexpected result format.')

        audio_payload = result.get('audio')
        if audio_payload is None:
            audio_payload = result.get('tts_speech')
        if audio_payload is None:
            audio_payload = result.get('speech')
        if audio_payload is None:
            raise RuntimeError('CosyVoice did not return audio data.')

        sample_rate = int(result.get('sample_rate') or result.get('tts_sample_rate') or result.get('sr') or self.settings.tts_cosyvoice_sample_rate)
        audio_bytes, duration_seconds, pcm = self._coerce_cosyvoice_audio_payload(audio_payload, sample_rate)
        phonemes = self._phonemes_from_result_timing(result, cleaned_text)
        if not phonemes and pcm is not None:
            phonemes = self._phonemes_from_waveform(pcm, sample_rate)
        if not phonemes:
            phonemes = self._fallback_phonemes(cleaned_text, total_duration=duration_seconds)

        return TTSChunk(seq=seq, text=cleaned_text, audio_bytes=audio_bytes, phonemes=phonemes, mime_type='audio/wav')

    def _resolve_reference_audio_path(self, reference_audio_path: str | None) -> str:
        candidate = self._resolve_backend_path(reference_audio_path or self.settings.default_tts_reference_audio_path)
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f'TTS reference audio does not exist: {candidate}')
        return str(candidate.resolve())

    def _coerce_cosyvoice_audio_payload(self, payload: object, sample_rate: int):
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError('CosyVoice audio decoding requires numpy.') from exc

        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload), 0.0, None

        if hasattr(payload, 'detach'):
            payload = payload.detach()
        if hasattr(payload, 'cpu'):
            payload = payload.cpu()
        if hasattr(payload, 'numpy'):
            payload = payload.numpy()

        audio_array = np.asarray(payload).squeeze()
        if audio_array.ndim != 1:
            raise RuntimeError('CosyVoice audio data must be mono.')
        if np.issubdtype(audio_array.dtype, np.integer):
            pcm = audio_array.astype(np.int16)
        else:
            pcm = (np.clip(audio_array.astype(np.float32), -1.0, 1.0) * 32767).astype(np.int16)
        return self._pcm16_to_wav_bytes(pcm, sample_rate), float(len(pcm) / max(sample_rate, 1)), pcm

    def _phonemes_from_result_timing(self, result: dict[str, object], text: str) -> list[dict[str, float | str]]:
        alignment = self._extract_alignment(result)
        if alignment:
            return self._phonemes_from_alignment(alignment)

        duration = result.get('duration')
        if not isinstance(duration, list):
            return []

        shapes = self._extract_mouth_shapes(text)
        units: list[dict[str, object]] = []
        for index, item in enumerate(duration):
            if isinstance(item, dict):
                units.append(item)
            else:
                units.append({'ph': shapes[index % max(len(shapes), 1)], 'duration': item})
        return self._phonemes_from_duration_units(units)

    def _phonemes_from_duration_units(self, units: list[dict[str, object]]) -> list[dict[str, float | str]]:
        phonemes: list[dict[str, float | str]] = []
        cursor = 0.0
        for unit in units:
            phoneme = str(unit.get('ph') or unit.get('phoneme') or unit.get('text') or 'N')
            duration = max(float(unit.get('duration') or 0.08), 0.04)
            start = float(unit.get('start') or unit.get('begin') or cursor)
            end = unit.get('end')
            if end is None:
                end = start + duration
            phonemes.append(self._frame_from_shape(self._syllable_to_shape(phoneme), start, float(end)))
            cursor = float(end)

        if phonemes and phonemes[-1]['ph'] != 'N':
            phonemes.append(self._frame_from_shape('N', float(phonemes[-1]['end']), float(phonemes[-1]['end']) + 0.08))
        return phonemes

    def _phonemes_from_waveform(self, pcm: object, sample_rate: int, fps: int = 50) -> list[dict[str, float | str]]:
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError('Waveform lip-sync fallback requires numpy.') from exc

        audio = np.asarray(pcm).astype(np.float32).squeeze()
        if audio.size == 0:
            return []
        if np.max(np.abs(audio)) > 1.5:
            audio = audio / 32768.0

        frame_size = max(int(sample_rate / fps), 1)
        energies: list[float] = []
        for start in range(0, len(audio), frame_size):
            window = audio[start : start + frame_size]
            if window.size == 0:
                continue
            energies.append(float(np.sqrt(np.mean(np.square(window)))))
        if not energies:
            return []

        max_energy = max(max(energies), 1e-6)
        frames: list[dict[str, float | str]] = []
        for index, energy in enumerate(energies):
            normalized = max(0.0, min(1.0, energy / max_energy))
            smoothed = normalized ** 0.6
            if smoothed > 0.55:
                shape = 'a'
            elif smoothed > 0.18:
                shape = 'e'
            else:
                shape = 'N'
            start = index / fps
            end = min((index + 1) / fps, len(audio) / max(sample_rate, 1))
            frame = self._frame_from_shape(shape, start, end)
            frame['openY'] = round(max(float(frame['openY']), smoothed), 3)
            frames.append(frame)

        if frames and frames[-1]['ph'] != 'N':
            frames.append(self._frame_from_shape('N', float(frames[-1]['end']), float(frames[-1]['end']) + 0.08))
        return frames


@lru_cache
def get_tts_service() -> TTSService:
    return TTSService(get_settings())
