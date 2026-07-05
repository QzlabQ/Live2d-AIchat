from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.emotion import EmotionAnalysis, get_emotion_analyzer
from app.services.rag import RetrievedChunk, get_rag_service

DISPLAY_PUNCTUATION_RE = re.compile(r"[。！？；!?;\n]")
TTS_STRONG_BOUNDARY_RE = re.compile(r"[。！？；!?;]")
TTS_SOFT_BOUNDARY_RE = re.compile(r"[，、,]")
TTS_FALLBACK_BOUNDARY_RE = re.compile(r"[\s、，,和及与并且然后再接着]")


@dataclass(slots=True)
class GeneratedReply:
    text: str
    emotion: str
    emotion_meta: EmotionAnalysis
    spoken_text: str | None = None
    sources: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    mode: str = "template"


@dataclass(slots=True)
class ReplyStreamEvent:
    kind: str
    content: str = ""
    text: str = ""
    spoken_text: str = ""
    sources: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    mode: str = "template"


class DisplayChunker:
    def __init__(self, flush_chars: int = 24) -> None:
        self.flush_chars = max(flush_chars, 4)
        self.buffer = ""

    def feed(self, text: str) -> list[str]:
        if not text:
            return []

        self.buffer += text
        chunks: list[str] = []
        while True:
            cut = self._next_cut()
            if cut is None:
                break
            chunk = self.buffer[:cut].strip()
            self.buffer = self.buffer[cut:]
            if chunk:
                chunks.append(chunk)
        return chunks

    def flush(self) -> list[str]:
        chunk = self.buffer.strip()
        self.buffer = ""
        return [chunk] if chunk else []

    def _next_cut(self) -> int | None:
        match = DISPLAY_PUNCTUATION_RE.search(self.buffer)
        if match and match.end() >= min(self.flush_chars, 8):
            return match.end()
        if len(self.buffer) >= self.flush_chars:
            return self.flush_chars
        return None


class TTSSegmenter:
    def __init__(
        self,
        soft_min_chars: int = 12,
        soft_max_chars: int = 20,
        hard_max_chars: int = 28,
    ) -> None:
        self.soft_min_chars = soft_min_chars
        self.soft_max_chars = soft_max_chars
        self.hard_max_chars = hard_max_chars
        self.buffer = ""

    def feed(self, text: str) -> list[str]:
        if not text:
            return []

        self.buffer += text
        return self._collect_segments(force=False)

    def flush(self) -> list[str]:
        return self._collect_segments(force=True)

    def _collect_segments(self, force: bool) -> list[str]:
        segments: list[str] = []
        while True:
            cut = self._next_cut(force=force)
            if cut is None:
                break
            segment = self.buffer[:cut].strip()
            self.buffer = self.buffer[cut:].lstrip()
            if segment:
                segments.append(segment)
            if force and not self.buffer.strip():
                self.buffer = ""
                break
        return segments

    def _next_cut(self, force: bool) -> int | None:
        if not self.buffer.strip():
            return None

        strong = TTS_STRONG_BOUNDARY_RE.search(self.buffer)
        strong_end = strong.end() if strong else None

        if strong_end is not None and strong_end <= self.soft_max_chars:
            return strong_end

        if len(self.buffer) >= self.soft_min_chars:
            if strong_end is not None and strong_end > self.soft_max_chars:
                soft_before_strong = self._last_boundary_before(
                    TTS_SOFT_BOUNDARY_RE,
                    min(strong_end, self.soft_max_chars),
                )
                if soft_before_strong is not None and soft_before_strong >= self.soft_min_chars:
                    return soft_before_strong

            if force:
                soft_forced = self._last_boundary_before(TTS_SOFT_BOUNDARY_RE, len(self.buffer))
                if soft_forced is not None:
                    return soft_forced
                if strong_end is not None:
                    return strong_end
                return len(self.buffer)

            if TTS_SOFT_BOUNDARY_RE.search(self.buffer[-2:]):
                return len(self.buffer)

            if len(self.buffer) >= self.soft_max_chars:
                soft_cut = self._last_boundary_before(TTS_SOFT_BOUNDARY_RE, len(self.buffer))
                if soft_cut is not None and soft_cut >= self.soft_min_chars:
                    return soft_cut

        if len(self.buffer) > self.hard_max_chars:
            soft_cut = self._last_boundary_before(TTS_SOFT_BOUNDARY_RE, self.hard_max_chars)
            if soft_cut is not None and soft_cut >= self.soft_min_chars:
                return soft_cut

            fallback_cut = self._last_boundary_before(TTS_FALLBACK_BOUNDARY_RE, self.hard_max_chars)
            if fallback_cut is not None and fallback_cut >= self.soft_min_chars // 2:
                return fallback_cut
            return self.hard_max_chars

        if strong_end is not None:
            return strong_end

        if force:
            return len(self.buffer)
        return None

    def _last_boundary_before(self, pattern: re.Pattern[str], limit: int) -> int | None:
        last: int | None = None
        for match in pattern.finditer(self.buffer[:limit]):
            last = match.end()
        return last


class BaseGuideChatService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chunk_text(self, text: str) -> list[str]:
        chunker = DisplayChunker(flush_chars=self.settings.websocket_chunk_size)
        chunks = chunker.feed(text)
        chunks.extend(chunker.flush())
        return chunks or [text]

    async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
        return await get_emotion_analyzer().analyze(user_text=user_text, reply_text=reply_text)

    async def stream_reply(self, user_text: str, persona: str | None = None) -> AsyncIterator[ReplyStreamEvent]:
        generated = await self.generate_reply(user_text, persona=persona)
        async for event in self._stream_from_pieces(
            self._iter_pieces(self.chunk_text(generated.spoken_text or generated.text)),
            sources=generated.sources,
            confidence=generated.confidence,
            mode=generated.mode,
        ):
            yield event

    async def _stream_from_pieces(
        self,
        pieces: AsyncIterator[str],
        *,
        sources: list[RetrievedChunk],
        confidence: float,
        mode: str,
    ) -> AsyncIterator[ReplyStreamEvent]:
        display = DisplayChunker(flush_chars=self.settings.websocket_chunk_size)
        tts_segmenter = TTSSegmenter(
            soft_min_chars=self.settings.tts_segment_soft_min_chars,
            soft_max_chars=self.settings.tts_segment_soft_max_chars,
            hard_max_chars=self.settings.tts_segment_hard_max_chars,
        )
        full_parts: list[str] = []

        async for piece in pieces:
            if not piece:
                continue
            full_parts.append(piece)
            for chunk in display.feed(piece):
                yield ReplyStreamEvent(kind="text_delta", content=chunk)
            for segment in tts_segmenter.feed(piece):
                yield ReplyStreamEvent(kind="tts_segment", content=segment)

        for chunk in display.flush():
            yield ReplyStreamEvent(kind="text_delta", content=chunk)
        for segment in tts_segmenter.flush():
            yield ReplyStreamEvent(kind="tts_segment", content=segment)

        final_text = "".join(full_parts).strip()
        yield ReplyStreamEvent(
            kind="final",
            text=final_text,
            spoken_text=final_text,
            sources=sources,
            confidence=confidence,
            mode=mode,
        )

    async def _iter_pieces(self, pieces: Iterable[str]) -> AsyncIterator[str]:
        for piece in pieces:
            if piece:
                yield piece


class TemplateGuideChatService(BaseGuideChatService):
    async def generate_reply(self, user_text: str, persona: str | None = None) -> GeneratedReply:
        text = " ".join(user_text.strip().split())
        if not text:
            reply = "我刚刚没有听清，你可以再说一次吗？"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text.lower() for token in ("hello", "hi")) or "你好" in text:
            reply = "你好，我是景区数字导览助手。你可以问我景点介绍、游览路线，或者直接说出你想去的地方。"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("历史", "故事", "由来", "文化")):
            reply = "这里的讲解通常会围绕景区历史、人文故事和代表性景点展开。如果你愿意，我可以先从最经典的一处景点开始介绍。"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("路线", "怎么逛", "推荐", "先去")):
            reply = "如果你是第一次来，建议先从核心景点主线开始，再根据体力和兴趣补充周边区域。这样体验会更完整也更轻松。"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("时间", "营业", "开放", "几点")):
            reply = "开放时间这类信息后续会接入景区知识库和后台配置。现在你也可以继续问我景点简介或参观建议。"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        persona_hint = "我会按照导览员的口吻继续为你讲解。" if persona else ""
        reply = (
            "我已经收到你的问题。"
            f"{persona_hint}"
            "当前系统已经支持文本、语音识别、语音合成和流式 WebSocket 返回。"
            "接入知识库后，回答会更贴合具体景区内容。"
        )
        emotion = await self.analyze_emotion(user_text, reply)
        return GeneratedReply(reply, emotion.label, emotion)


class RAGGuideChatService(BaseGuideChatService):
    async def generate_reply(self, user_text: str, persona: str | None = None) -> GeneratedReply:
        answer = await get_rag_service().answer(user_text, persona=persona)
        emotion = await self.analyze_emotion(user_text, answer.spoken_text or answer.answer_text)
        return GeneratedReply(
            text=answer.answer_text,
            spoken_text=answer.spoken_text,
            emotion=emotion.label,
            emotion_meta=emotion,
            sources=answer.sources,
            confidence=answer.confidence,
            mode="rag",
        )

    async def stream_reply(self, user_text: str, persona: str | None = None) -> AsyncIterator[ReplyStreamEvent]:
        rag_service = get_rag_service()
        prepared = await rag_service.prepare_stream_answer(user_text, persona=persona)
        if prepared.llm_messages:
            try:
                async for event in self._stream_from_pieces(
                    rag_service.llm.stream_complete(prepared.llm_messages),
                    sources=prepared.sources,
                    confidence=prepared.confidence,
                    mode="rag",
                ):
                    yield event
                return
            except Exception:
                pass

        fallback_text = prepared.fallback_text or prepared.spoken_text or prepared.answer_text

        async for event in self._stream_from_pieces(
            self._iter_pieces(self.chunk_text(fallback_text)),
            sources=prepared.sources,
            confidence=prepared.confidence,
            mode="rag",
        ):
            yield event


def get_chat_service():
    settings = get_settings()
    mode = settings.chat_mode.strip().lower()
    if mode == "rag":
        return RAGGuideChatService(settings)
    return TemplateGuideChatService(settings)
