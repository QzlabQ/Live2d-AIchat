from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from functools import lru_cache
import importlib
from io import BytesIO
import logging
import os
from pathlib import Path
import queue
import re
import sys
import threading
from time import perf_counter
import wave

from pypinyin import Style, lazy_pinyin

from app.core.config import Settings, get_settings

PUNCTUATION_RE = re.compile(r"[，。！？!?；;、,\s]+")
LATIN_VOWEL_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)
NON_ALPHA_RE = re.compile(r"[^a-z]")
SPOKEN_GUIDANCE_RE = re.compile(
    r"用(?P<style>[^。！？!?；;]{0,36}?)(?:语言|语气|方式|口吻|话术)"
    r"(?:来)?(?:讲述|介绍|说明|解释|表达)(?P<object>[^。！？!?；;，,、]{0,80})"
)
VISITOR_PEDAGOGY_RE = re.compile(
    r"[，,、]\s*(?:让|帮助|引导|带领|激发|方便)(?:游客|孩子|小朋友|大家|观众|用户)"
    r"[^。！？!?；;]*"
)
GENERIC_TTS_OBJECTS = {"", "这段内容", "这句话", "一句话", "内容", "文本", "回答"}
COSYVOICE_ALIGNMENT_KEYS = ("alignment", "alignments", "phonemes", "phoneme_alignment")
BACKEND_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)

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


@dataclass(slots=True)
class StreamingTTSChunk:
    seq: int
    chunk_index: int
    text: str
    audio_bytes: bytes
    phonemes: list[dict[str, float | str]]
    offset_ms: int
    sample_rate: int
    channels: int = 1
    encoding: str = "pcm16le"
    is_final: bool = False
    model_chunk_ready_ms: int = 0


@dataclass(frozen=True, slots=True)
class TTSStreamProfile:
    name: str
    initial_token_hop_len: int
    growth_factor: float
    max_hop_multiplier: int


STREAM_PROFILES: dict[str, TTSStreamProfile] = {
    "stable": TTSStreamProfile(
        name="stable",
        initial_token_hop_len=25,
        growth_factor=2.0,
        max_hop_multiplier=4,
    ),
    "balanced": TTSStreamProfile(
        name="balanced",
        initial_token_hop_len=25,
        growth_factor=1.5,
        max_hop_multiplier=3,
    ),
    "low_latency": TTSStreamProfile(
        name="low_latency",
        initial_token_hop_len=25,
        growth_factor=1.0,
        max_hop_multiplier=1,
    ),
}


def resolve_stream_profile(settings: Settings) -> TTSStreamProfile:
    return STREAM_PROFILES.get(settings.tts_stream_profile, STREAM_PROFILES["stable"])


def resolve_stream_hop_limit(
    profile: TTSStreamProfile,
    *,
    base_token_hop_len: int,
    configured_max_hop_len: int,
) -> int:
    base_hop = max(int(base_token_hop_len), 1)
    profile_limit = base_hop * max(int(profile.max_hop_multiplier), 1)
    configured_limit = max(int(configured_max_hop_len), base_hop)
    if configured_limit <= base_hop:
        return profile_limit
    return min(configured_limit, profile_limit)


class LocalCosyVoiceProvider:
    def __init__(self, service: "TTSService") -> None:
        self.service = service

    async def stream_synthesize_reply(self, segments: AsyncIterator[tuple[int, str]], **kwargs):
        async for chunk in self.service._stream_synthesize_reply_local(segments, **kwargs):
            yield chunk


class RemoteTTSProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream_synthesize_reply(
        self,
        segments: AsyncIterator[tuple[int, str]],
        **kwargs,
    ) -> AsyncIterator[StreamingTTSChunk]:
        async def iter_segment_payloads():
            async for seq, text in segments:
                yield {"seq": seq, "text": text}

        payload = {
            "segments": iter_segment_payloads(),
            "voice_id": kwargs.get("voice_id"),
            "emotion": kwargs.get("emotion"),
            "reference_audio_path": kwargs.get("reference_audio_path"),
            "reference_text": kwargs.get("reference_text"),
            "speed": kwargs.get("speed"),
            "tts_emotion_enabled": kwargs.get("tts_emotion_enabled"),
        }
        async for event in self._iter_remote_events(payload):
            yield self._chunk_from_remote_event(event)

    async def _iter_remote_events(self, payload: dict[str, object]):
        del payload
        if not self.settings.tts_remote_url:
            raise RuntimeError("TTS_PROVIDER=remote requires TTS_REMOTE_URL.")
        raise NotImplementedError(
            f"TTS remote protocol {self.settings.tts_remote_protocol!r} is not implemented yet."
        )

    def _chunk_from_remote_event(self, event: dict[str, object]) -> StreamingTTSChunk:
        return StreamingTTSChunk(
            seq=int(event.get("seq", 0)),
            chunk_index=int(event.get("chunk_index", 0)),
            text=str(event.get("text", "")),
            audio_bytes=bytes(event.get("audio_bytes", b"")),
            phonemes=list(event.get("phonemes", [])),
            offset_ms=int(event.get("offset_ms", 0)),
            sample_rate=int(event.get("sample_rate", self.settings.tts_cosyvoice_sample_rate)),
            channels=int(event.get("channels", 1)),
            encoding=str(event.get("encoding", "pcm16le")),
            is_final=bool(event.get("is_final", False)),
            model_chunk_ready_ms=int(event.get("model_chunk_ready_ms", 0)),
        )


class TTSService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine_error: str | None = None
        self._cosyvoice_model: object | None = None
        self._prompt_feature_cache: dict[tuple[str, str], dict[str, object]] = {}
        self._local_provider = LocalCosyVoiceProvider(self)
        self._remote_provider = RemoteTTSProvider(settings)

    @property
    def supports_reply_streaming(self) -> bool:
        return self.settings.tts_provider == "remote" or self.settings.tts_engine == "cosyvoice"

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

    def _sanitize_synthesis_text(self, text: str) -> str:
        def replace_directive(match: re.Match[str]) -> str:
            obj = match.group("object").strip(" ：:，,、")
            if obj in GENERIC_TTS_OBJECTS:
                return ""
            return obj

        cleaned = str(text or "").replace("<|endofprompt|>", "").strip()
        previous = None
        while previous != cleaned:
            previous = cleaned
            cleaned = SPOKEN_GUIDANCE_RE.sub(replace_directive, cleaned)
            cleaned = VISITOR_PEDAGOGY_RE.sub("", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if re.fullmatch(r"[。！？!?；;，,、.:\s：]+", cleaned):
            return ""
        return cleaned

    def warmup(self) -> None:
        if self.settings.tts_engine != "cosyvoice":
            return

        cosyvoice = self._load_cosyvoice_model()
        prompt_wav = self._resolve_reference_audio_path(None)
        result = self._first_result(
            cosyvoice.inference_instruct2(
                "你好。",
                self._build_cosyvoice_instruction("neutral", emotion_enabled=False),
                prompt_wav,
                stream=False,
                speed=1.0,
            )
        )
        if not isinstance(result, dict):
            raise RuntimeError("CosyVoice warmup returned an unexpected result format.")

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
        self._configure_cosyvoice_runtime_environment()
        module = self._import_cosyvoice_module()
        factory = getattr(module, "CosyVoice2", None)
        if factory is None:
            raise RuntimeError("未找到 cosyvoice.cli.cosyvoice.CosyVoice2，请检查本地 CosyVoice 安装。")

        try:
            self._cosyvoice_model = factory(
                str(model_path),
                load_jit=self.settings.tts_cosyvoice_load_jit,
                fp16=self.settings.tts_cosyvoice_fp16,
            )
        except TypeError:
            self._cosyvoice_model = factory(str(model_path))

        self._move_cosyvoice_runtime(self._cosyvoice_model, device)

        return self._cosyvoice_model

    def _configure_cosyvoice_runtime_environment(self) -> None:
        provider = self.settings.tts_cosyvoice_onnx_provider.strip().lower()
        if provider not in {"cpu", "cuda", "auto"}:
            provider = "cpu"
        os.environ["COSYVOICE_ONNX_PROVIDER"] = provider

    def _import_cosyvoice_module(self):
        try:
            module = importlib.import_module("cosyvoice.cli.cosyvoice")
            self._patch_cosyvoice_runtime_support(module)
            return module
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
                module = importlib.import_module("cosyvoice.cli.cosyvoice")
                self._patch_cosyvoice_runtime_support(module)
                return module
            except ModuleNotFoundError as patched_exc:
                raise RuntimeError(
                    "已找到 CosyVoice 代码目录，但仍无法导入 cosyvoice.cli.cosyvoice。"
                    "请确认仓库完整克隆（含 third_party 子模块）并已安装 CosyVoice 运行时依赖。"
                ) from patched_exc

    def _patch_cosyvoice_runtime_support(self, cosyvoice_module: object) -> None:
        profile = resolve_stream_profile(self.settings)
        frontend_module = importlib.import_module("cosyvoice.cli.frontend")
        frontend_class = getattr(frontend_module, "CosyVoiceFrontEnd", None)
        if frontend_class is not None and not hasattr(frontend_class, "iter_text_normalize"):
            def iter_text_normalize(self, text_generator, text_frontend=True):
                for text in text_generator:
                    for normalized in self.text_normalize(text, split=True, text_frontend=text_frontend):
                        if normalized:
                            yield normalized

            setattr(frontend_class, "iter_text_normalize", iter_text_normalize)

        def inference_instruct2_reply(
            self,
            text_iterator,
            instruct_text,
            prompt_wav,
            zero_shot_spk_id='',
            stream=False,
            speed=1.0,
            text_frontend=True,
        ):
            normalize = getattr(self.frontend, "iter_text_normalize", None)
            if callable(normalize):
                text_iterator = normalize(text_iterator, text_frontend=text_frontend)
            model_input = self.frontend.frontend_instruct2(
                text_iterator,
                instruct_text,
                prompt_wav,
                self.sample_rate,
                zero_shot_spk_id,
            )
            for model_output in self.model.tts(**model_input, stream=stream, speed=speed):
                yield model_output

        for class_name in ("CosyVoice2", "CosyVoice3"):
            cosyvoice_class = getattr(cosyvoice_module, class_name, None)
            if cosyvoice_class is not None and not hasattr(cosyvoice_class, "inference_instruct2_reply"):
                setattr(cosyvoice_class, "inference_instruct2_reply", inference_instruct2_reply)

        model_module = importlib.import_module("cosyvoice.cli.model")

        def patch_reply_stream_tts(model_class_name: str) -> None:
            model_class = getattr(model_module, model_class_name, None)
            if model_class is None or getattr(model_class, "_ai_chat_reply_stream_patch", False):
                return

            original_tts = model_class.tts

            def patched_tts(self, *args, **kwargs):
                stream = kwargs.get("stream", False)
                if stream is not True:
                    yield from original_tts(self, *args, **kwargs)
                    return

                import uuid
                import numpy as np
                import time
                import torch

                text = kwargs.get("text", torch.zeros(1, 0, dtype=torch.int32))
                flow_embedding = kwargs.get("flow_embedding", torch.zeros(0, 192))
                llm_embedding = kwargs.get("llm_embedding", torch.zeros(0, 192))
                prompt_text = kwargs.get("prompt_text", torch.zeros(1, 0, dtype=torch.int32))
                llm_prompt_speech_token = kwargs.get("llm_prompt_speech_token", torch.zeros(1, 0, dtype=torch.int32))
                flow_prompt_speech_token = kwargs.get("flow_prompt_speech_token", torch.zeros(1, 0, dtype=torch.int32))
                prompt_speech_feat = kwargs.get("prompt_speech_feat", torch.zeros(1, 0, 80))
                source_speech_token = kwargs.get("source_speech_token", torch.zeros(1, 0, dtype=torch.int32))
                this_uuid = str(uuid.uuid1())
                with self.lock:
                    self.tts_speech_token_dict[this_uuid], self.llm_end_dict[this_uuid] = [], False
                    self.hift_cache_dict[this_uuid] = None

                if source_speech_token.shape[1] == 0:
                    producer = threading.Thread(
                        target=self.llm_job,
                        args=(text, prompt_text, llm_prompt_speech_token, llm_embedding, this_uuid),
                    )
                else:
                    producer = threading.Thread(target=self.vc_job, args=(source_speech_token, this_uuid))
                producer.start()

                try:
                    token_offset = 0
                    base_token_hop_len = int(getattr(self, "token_hop_len", profile.initial_token_hop_len))
                    token_hop_len = base_token_hop_len
                    configured_max_hop_len = int(getattr(self, "token_max_hop_len", base_token_hop_len))
                    token_max_hop_len = resolve_stream_hop_limit(
                        profile,
                        base_token_hop_len=base_token_hop_len,
                        configured_max_hop_len=configured_max_hop_len,
                    )
                    stream_scale_factor = max(float(profile.growth_factor), 1.0)
                    prompt_token_pad = int(
                        np.ceil(flow_prompt_speech_token.shape[1] / max(base_token_hop_len, 1)) * base_token_hop_len
                        - flow_prompt_speech_token.shape[1]
                    )
                    while True:
                        time.sleep(0.05)
                        this_token_hop_len = token_hop_len + prompt_token_pad if token_offset == 0 else token_hop_len
                        if len(self.tts_speech_token_dict[this_uuid]) - token_offset >= this_token_hop_len + self.flow.pre_lookahead_len:
                            this_tts_speech_token = torch.tensor(
                                self.tts_speech_token_dict[this_uuid][: token_offset + this_token_hop_len + self.flow.pre_lookahead_len]
                            ).unsqueeze(dim=0)
                            this_tts_speech = self.token2wav(
                                token=this_tts_speech_token,
                                prompt_token=flow_prompt_speech_token,
                                prompt_feat=prompt_speech_feat,
                                embedding=flow_embedding,
                                token_offset=token_offset,
                                uuid=this_uuid,
                                stream=stream,
                                finalize=False,
                            )
                            token_offset += this_token_hop_len
                            next_hop = int(round(token_hop_len * stream_scale_factor))
                            token_hop_len = min(token_max_hop_len, max(base_token_hop_len, next_hop))
                            yield {"tts_speech": this_tts_speech.cpu()}
                        if (
                            self.llm_end_dict[this_uuid] is True
                            and len(self.tts_speech_token_dict[this_uuid]) - token_offset
                            < this_token_hop_len + self.flow.pre_lookahead_len
                        ):
                            break
                    producer.join()
                    this_tts_speech_token = torch.tensor(self.tts_speech_token_dict[this_uuid]).unsqueeze(dim=0)
                    this_tts_speech = self.token2wav(
                        token=this_tts_speech_token,
                        prompt_token=flow_prompt_speech_token,
                        prompt_feat=prompt_speech_feat,
                        embedding=flow_embedding,
                        token_offset=token_offset,
                        uuid=this_uuid,
                        finalize=True,
                    )
                    yield {"tts_speech": this_tts_speech.cpu()}
                finally:
                    with self.lock:
                        self.tts_speech_token_dict.pop(this_uuid, None)
                        self.llm_end_dict.pop(this_uuid, None)
                        self.hift_cache_dict.pop(this_uuid, None)
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.current_stream().synchronize()

            setattr(model_class, "tts", patched_tts)
            setattr(model_class, "_ai_chat_reply_stream_patch", True)

        patch_reply_stream_tts("CosyVoice2Model")
        patch_reply_stream_tts("CosyVoice3Model")

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

    def _pcm16_to_bytes(self, pcm) -> bytes:
        return pcm.tobytes() if hasattr(pcm, "tobytes") else bytes(pcm)

    def _coerce_cosyvoice_pcm_payload(self, payload: object, sample_rate: int):
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("CosyVoice audio decoding requires numpy.") from exc

        if hasattr(payload, "detach"):
            payload = payload.detach()
        if hasattr(payload, "cpu"):
            payload = payload.cpu()
        if hasattr(payload, "numpy"):
            payload = payload.numpy()

        audio_array = np.asarray(payload).squeeze()
        if audio_array.ndim != 1:
            raise RuntimeError("CosyVoice audio data must be mono.")
        if np.issubdtype(audio_array.dtype, np.integer):
            pcm = audio_array.astype(np.int16)
        else:
            pcm = (np.clip(audio_array.astype(np.float32), -1.0, 1.0) * 32767).astype(np.int16)
        duration_seconds = float(len(pcm) / max(sample_rate, 1))
        return pcm, self._pcm16_to_bytes(pcm), duration_seconds

    def _trim_pcm_silence(
        self,
        pcm: object,
        sample_rate: int,
        *,
        leading_ms: int = 20,
        trailing_ms: int = 20,
        threshold_ratio: float = 0.01,
    ):
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise RuntimeError("Silence trimming requires numpy.") from exc

        audio = np.asarray(pcm).astype(np.int16).squeeze()
        if audio.size == 0:
            return audio, {"trimmed_leading_ms": 0.0, "trimmed_trailing_ms": 0.0}

        threshold = max(int(32767 * threshold_ratio), 64)
        active = np.flatnonzero(np.abs(audio) >= threshold)
        if active.size == 0:
            return audio, {"trimmed_leading_ms": 0.0, "trimmed_trailing_ms": 0.0}

        leading_pad = int(sample_rate * leading_ms / 1000)
        trailing_pad = int(sample_rate * trailing_ms / 1000)
        start = max(int(active[0]) - leading_pad, 0)
        end = min(int(active[-1]) + trailing_pad + 1, len(audio))
        trimmed = audio[start:end]
        return trimmed, {
            "trimmed_leading_ms": round(start * 1000 / max(sample_rate, 1), 3),
            "trimmed_trailing_ms": round((len(audio) - end) * 1000 / max(sample_rate, 1), 3),
        }

    def _get_cached_prompt_features(
        self,
        frontend: object,
        prompt_wav: str,
        reference_text: str | None,
    ) -> dict[str, object]:
        cache_key = (str(Path(prompt_wav).resolve()), (reference_text or "").strip())
        cached = self._prompt_feature_cache.get(cache_key)
        if cached is not None:
            logger.info("tts_prompt_cache prompt_cache_hit=1 prompt_cache_build_ms=0.0")
            return cached

        started_at = perf_counter()
        cached = {
            "speech_feat": frontend._extract_speech_feat(prompt_wav),
            "speech_token": frontend._extract_speech_token(prompt_wav),
            "embedding": frontend._extract_spk_embedding(prompt_wav),
        }
        build_ms = round((perf_counter() - started_at) * 1000, 3)
        self._prompt_feature_cache[cache_key] = cached
        logger.info("tts_prompt_cache prompt_cache_hit=0 prompt_cache_build_ms=%s", build_ms)
        return cached

    def _bind_prompt_feature_cache(
        self,
        frontend: object,
        prompt_wav: str,
        reference_text: str | None,
    ):
        if not all(
            hasattr(frontend, attr)
            for attr in ("_extract_speech_feat", "_extract_speech_token", "_extract_spk_embedding")
        ):
            return lambda: None

        cached = self._get_cached_prompt_features(frontend, prompt_wav, reference_text)
        resolved_prompt = str(Path(prompt_wav).resolve())
        original_feat = frontend._extract_speech_feat
        original_token = frontend._extract_speech_token
        original_embedding = frontend._extract_spk_embedding

        def matches(candidate: str) -> bool:
            return str(Path(candidate).resolve()) == resolved_prompt

        def cached_feat(candidate: str):
            if matches(candidate):
                return cached["speech_feat"]
            return original_feat(candidate)

        def cached_token(candidate: str):
            if matches(candidate):
                return cached["speech_token"]
            return original_token(candidate)

        def cached_embedding(candidate: str):
            if matches(candidate):
                return cached["embedding"]
            return original_embedding(candidate)

        frontend._extract_speech_feat = cached_feat
        frontend._extract_speech_token = cached_token
        frontend._extract_spk_embedding = cached_embedding

        def restore() -> None:
            frontend._extract_speech_feat = original_feat
            frontend._extract_speech_token = original_token
            frontend._extract_spk_embedding = original_embedding

        return restore

    def _extract_cosyvoice_audio_result(
        self,
        result: dict[str, object],
        *,
        sample_rate_fallback: int,
    ) -> tuple[object, int] | None:
        audio_payload = result.get("audio")
        if audio_payload is None:
            audio_payload = result.get("tts_speech")
        if audio_payload is None:
            audio_payload = result.get("speech")
        if audio_payload is None:
            return None

        sample_rate = int(
            result.get("sample_rate")
            or result.get("tts_sample_rate")
            or result.get("sr")
            or sample_rate_fallback
        )
        return audio_payload, sample_rate

    def _build_streaming_chunk_from_result(
        self,
        *,
        seq: int,
        chunk_index: int,
        text: str,
        result: dict[str, object],
        offset_ms: int,
        stream_started_at: float,
    ) -> tuple[StreamingTTSChunk | None, int]:
        extracted = self._extract_cosyvoice_audio_result(
            result,
            sample_rate_fallback=self.settings.tts_cosyvoice_sample_rate,
        )
        if extracted is None:
            return None, offset_ms

        audio_payload, sample_rate = extracted
        pcm, _, _ = self._coerce_cosyvoice_pcm_payload(audio_payload, sample_rate)
        # Only the first chunk carries model warm-up padding worth trimming.
        # Interior chunks are sample-contiguous continuous audio: trimming their
        # leading/trailing silence would delete the model's own prosodic pauses
        # and shrink each chunk below real-time, starving the frontend buffer.
        if chunk_index == 0:
            trimmed_pcm, trim_info = self._trim_pcm_silence(
                pcm,
                sample_rate=sample_rate,
                leading_ms=60,
                trailing_ms=0,
            )
        else:
            trimmed_pcm = pcm
            trim_info = {"trimmed_leading_ms": 0.0, "trimmed_trailing_ms": 0.0}
        audio_bytes = self._pcm16_to_bytes(trimmed_pcm)
        phonemes = self._phonemes_from_waveform(trimmed_pcm, sample_rate) if len(trimmed_pcm) else []
        current_chunk = StreamingTTSChunk(
            seq=seq,
            chunk_index=chunk_index,
            text=text,
            audio_bytes=audio_bytes,
            phonemes=phonemes,
            offset_ms=offset_ms,
            sample_rate=sample_rate,
            is_final=False,
            model_chunk_ready_ms=int((perf_counter() - stream_started_at) * 1000),
        )
        next_offset_ms = offset_ms + int(round(len(trimmed_pcm) * 1000 / max(sample_rate, 1)))
        logger.info(
            "tts_stream_chunk seq=%s idx=%s model_chunk_ready_ms=%s trim_leading_ms=%s trim_trailing_ms=%s",
            seq,
            chunk_index,
            current_chunk.model_chunk_ready_ms,
            trim_info["trimmed_leading_ms"],
            trim_info["trimmed_trailing_ms"],
        )
        return current_chunk, next_offset_ms

    async def _iter_clean_reply_segments(
        self,
        segments: AsyncIterator[tuple[int, str]],
    ) -> AsyncIterator[tuple[int, str]]:
        async for seq, text in segments:
            cleaned = self._sanitize_synthesis_text(text)
            if cleaned:
                yield seq, cleaned

    async def _iter_cosyvoice_reply_results_async(
        self,
        segments: AsyncIterator[tuple[int, str]],
        *,
        emotion: str | None,
        reference_audio_path: str | None,
        reference_text: str | None,
        speed: float | None,
        emotion_enabled: bool,
    ) -> AsyncIterator[tuple[int, str, dict[str, object]]]:
        iterator = self._iter_clean_reply_segments(segments).__aiter__()
        try:
            first_segment = await anext(iterator)
        except StopAsyncIteration:
            return

        cosyvoice = self._load_cosyvoice_model()
        prompt_wav = self._resolve_reference_audio_path(reference_audio_path)
        instruct_text = self._build_cosyvoice_instruction(emotion, emotion_enabled=emotion_enabled)
        output_queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        input_queue: queue.Queue[object] = queue.Queue()
        input_done = object()
        loop = asyncio.get_running_loop()
        active_segment: dict[str, object] = {
            "seq": first_segment[0],
            "text": first_segment[1],
        }
        first_result_pending = {"value": True}

        def text_iterator():
            while True:
                item = input_queue.get()
                if item is input_done:
                    return
                seq, text = item
                active_segment["seq"] = seq
                active_segment["text"] = text
                yield text

        def worker() -> None:
            restore = self._bind_prompt_feature_cache(
                getattr(cosyvoice, "frontend", object()),
                prompt_wav,
                reference_text,
            )
            try:
                inference = getattr(cosyvoice, "inference_instruct2_reply", None)
                if inference is None:
                    inference = getattr(cosyvoice, "inference_instruct2")
                for result in inference(
                    text_iterator(),
                    instruct_text,
                    prompt_wav,
                    stream=True,
                    speed=float(speed or 1.0),
                ):
                    if first_result_pending["value"]:
                        payload = (first_segment[0], first_segment[1], result)
                        first_result_pending["value"] = False
                    else:
                        payload = (
                            int(active_segment["seq"]),
                            str(active_segment["text"]),
                            result,
                        )
                    loop.call_soon_threadsafe(output_queue.put_nowait, ("data", payload))
                loop.call_soon_threadsafe(output_queue.put_nowait, ("done", None))
            except Exception as exc:  # pragma: no cover - runtime dependency
                loop.call_soon_threadsafe(output_queue.put_nowait, ("error", exc))
            finally:
                restore()

        async def feed_segments() -> None:
            try:
                input_queue.put(first_segment)
                async for segment in iterator:
                    input_queue.put(segment)
            finally:
                input_queue.put(input_done)

        feeder_task = asyncio.create_task(feed_segments())
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        try:
            while True:
                event_type, payload = await output_queue.get()
                if event_type == "data":
                    seq, text, result = payload
                    if isinstance(result, dict):
                        yield seq, text, result
                        continue
                    raise RuntimeError("CosyVoice returned an unexpected result format.")
                if event_type == "error":
                    raise payload  # type: ignore[misc]
                break
        finally:
            if not feeder_task.done():
                feeder_task.cancel()
            await asyncio.gather(feeder_task, return_exceptions=True)
            thread.join(timeout=0.2)

    async def _iter_cosyvoice_results_async(
        self,
        cleaned_text: str,
        *,
        emotion: str | None,
        reference_audio_path: str | None,
        reference_text: str | None,
        speed: float | None,
        emotion_enabled: bool,
    ):
        cosyvoice = self._load_cosyvoice_model()
        prompt_wav = self._resolve_reference_audio_path(reference_audio_path)
        instruct_text = self._build_cosyvoice_instruction(emotion, emotion_enabled=emotion_enabled)
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def worker() -> None:
            restore = self._bind_prompt_feature_cache(
                getattr(cosyvoice, "frontend", object()),
                prompt_wav,
                reference_text,
            )
            try:
                for result in cosyvoice.inference_instruct2(
                    cleaned_text,
                    instruct_text,
                    prompt_wav,
                    stream=True,
                    speed=float(speed or 1.0),
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, ("data", result))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:  # pragma: no cover - runtime dependency
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
            finally:
                restore()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        try:
            while True:
                event_type, payload = await queue.get()
                if event_type == "data":
                    yield payload
                    continue
                if event_type == "error":
                    raise payload  # type: ignore[misc]
                break
        finally:
            thread.join(timeout=0.2)

    async def stream_synthesize_segment(
        self,
        text: str,
        seq: int,
        voice_id: str | None = None,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        speed: float | None = None,
        tts_emotion_enabled: bool = True,
    ):
        del voice_id
        cleaned_text = self._sanitize_synthesis_text(text)
        if not cleaned_text:
            return

        if self.settings.tts_engine != "cosyvoice":
            chunk = await self.synthesize_chunk(
                cleaned_text,
                seq=seq,
                emotion=emotion,
                reference_audio_path=reference_audio_path,
                speed=speed,
                tts_emotion_enabled=tts_emotion_enabled,
            )
            if chunk.audio_bytes or chunk.phonemes:
                yield StreamingTTSChunk(
                    seq=seq,
                    chunk_index=0,
                    text=cleaned_text,
                    audio_bytes=b"",
                    phonemes=chunk.phonemes,
                    offset_ms=0,
                    sample_rate=self.settings.tts_cosyvoice_sample_rate,
                    is_final=True,
                )
            return

        segment_started_at = perf_counter()
        last_chunk: StreamingTTSChunk | None = None
        offset_ms = 0
        chunk_index = 0
        async for result in self._iter_cosyvoice_results_async(
            cleaned_text,
            emotion=emotion,
            reference_audio_path=reference_audio_path,
            reference_text=reference_text,
            speed=speed,
            emotion_enabled=tts_emotion_enabled,
        ):
            if not isinstance(result, dict):
                raise RuntimeError("CosyVoice returned an unexpected result format.")

            current_chunk, offset_ms = self._build_streaming_chunk_from_result(
                seq=seq,
                chunk_index=chunk_index,
                text=cleaned_text,
                result=result,
                offset_ms=offset_ms,
                stream_started_at=segment_started_at,
            )
            if current_chunk is None:
                continue

            chunk_index += 1
            last_chunk = current_chunk
            yield current_chunk

        if last_chunk is not None:
            last_chunk.is_final = True

    async def _stream_synthesize_reply_local(
        self,
        segments: AsyncIterator[tuple[int, str]],
        *,
        voice_id: str | None = None,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        speed: float | None = None,
        tts_emotion_enabled: bool = True,
    ) -> AsyncIterator[StreamingTTSChunk]:
        del voice_id

        if self.settings.tts_engine != "cosyvoice":
            async for seq, segment in self._iter_clean_reply_segments(segments):
                async for chunk in self.stream_synthesize_segment(
                    segment,
                    seq=seq,
                    emotion=emotion,
                    reference_audio_path=reference_audio_path,
                    reference_text=reference_text,
                    speed=speed,
                    tts_emotion_enabled=tts_emotion_enabled,
                ):
                    yield chunk
            return

        reply_started_at = perf_counter()
        last_chunk: StreamingTTSChunk | None = None
        offset_ms = 0
        chunk_index = 0
        async for seq, text, result in self._iter_cosyvoice_reply_results_async(
            segments,
            emotion=emotion,
            reference_audio_path=reference_audio_path,
            reference_text=reference_text,
            speed=speed,
            emotion_enabled=tts_emotion_enabled,
        ):
            current_chunk, offset_ms = self._build_streaming_chunk_from_result(
                seq=seq,
                chunk_index=chunk_index,
                text=text,
                result=result,
                offset_ms=offset_ms,
                stream_started_at=reply_started_at,
            )
            if current_chunk is None:
                continue

            chunk_index += 1
            last_chunk = current_chunk
            yield current_chunk

        if last_chunk is not None:
            last_chunk.is_final = True

    async def stream_synthesize_reply(
        self,
        segments: AsyncIterator[tuple[int, str]],
        *,
        voice_id: str | None = None,
        emotion: str | None = None,
        reference_audio_path: str | None = None,
        reference_text: str | None = None,
        speed: float | None = None,
        tts_emotion_enabled: bool = True,
    ) -> AsyncIterator[StreamingTTSChunk]:
        provider = self._remote_provider if self.settings.tts_provider == "remote" else self._local_provider
        async for chunk in provider.stream_synthesize_reply(
            segments,
            voice_id=voice_id,
            emotion=emotion,
            reference_audio_path=reference_audio_path,
            reference_text=reference_text,
            speed=speed,
            tts_emotion_enabled=tts_emotion_enabled,
        ):
            yield chunk

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
        cleaned_text = self._sanitize_synthesis_text(text)
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
        del voice_id
        cleaned_text = self._sanitize_synthesis_text(cleaned_text)
        if not cleaned_text:
            return TTSChunk(seq=seq, text="", audio_bytes=b"", phonemes=[])

        cosyvoice = self._load_cosyvoice_model()
        prompt_wav = self._resolve_reference_audio_path(reference_audio_path)
        instruct_text = self._build_cosyvoice_instruction(emotion, emotion_enabled=emotion_enabled)
        restore = self._bind_prompt_feature_cache(
            getattr(cosyvoice, 'frontend', object()),
            prompt_wav,
            reference_text,
        )
        try:
            result = self._first_result(
                cosyvoice.inference_instruct2(
                    cleaned_text,
                    instruct_text,
                    prompt_wav,
                    stream=False,
                    speed=float(speed or 1.0),
                )
            )
        finally:
            restore()
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
