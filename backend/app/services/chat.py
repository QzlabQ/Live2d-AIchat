from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.emotion import EmotionAnalysis, get_emotion_analyzer
from app.services.rag import RetrievedChunk, get_rag_service

DISPLAY_PUNCTUATION_RE = re.compile(r"(?<=[。！？!?；;\n])")
TTS_STRONG_BOUNDARY_RE = re.compile(r"[。！？!?；;]")
TTS_SOFT_BOUNDARY_RE = re.compile(r"[，、,]")
TTS_FALLBACK_BOUNDARY_RE = re.compile(r"[\s、，,和及与并且然后再接着]")


def normalize_response_language(value: str | None) -> str:
    normalized = str(value or "zh").strip().lower()
    return "en" if normalized.startswith("en") else "zh"


def localized_text(response_language: str | None, zh_text: str, en_text: str) -> str:
    return en_text if normalize_response_language(response_language) == "en" else zh_text


@dataclass(slots=True)
class GeneratedReply:
    text: str
    emotion: str
    emotion_meta: EmotionAnalysis
    spoken_text: str | None = None
    sources: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    mode: str = "template"
    reply_kind: str = "answer"
    needs_followup: bool = False
    followup_question: str = ""
    missing_slots: list[str] = field(default_factory=list)
    confidence_note: str = "confirmed"


@dataclass(slots=True)
class ReplyStreamEvent:
    kind: str
    content: str = ""
    text: str = ""
    spoken_text: str = ""
    sources: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    mode: str = "template"
    reply_kind: str = "answer"
    needs_followup: bool = False
    followup_question: str = ""
    missing_slots: list[str] = field(default_factory=list)
    confidence_note: str = "confirmed"
    metrics: dict[str, int] = field(default_factory=dict)


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

        buffer_len = len(self.buffer)
        hard_window = min(buffer_len, self.hard_max_chars)
        strong_within_hard = self._last_boundary_before(TTS_STRONG_BOUNDARY_RE, hard_window)
        strong_any = self._last_boundary_before(TTS_STRONG_BOUNDARY_RE, buffer_len)

        # Prefer the latest sentence-ending boundary within the hard window, but
        # keep accumulating if the completed sentence is still too short. This
        # amortizes per-segment TTS startup on longer replies.
        if strong_within_hard is not None and strong_within_hard >= self.soft_min_chars:
            return strong_within_hard

        # Once the buffered reply exceeds the hard window we must choose a cut
        # inside that window. Looking at the whole buffer here would allow a
        # far-later comma to bypass hard_max_chars entirely.
        if buffer_len > self.hard_max_chars:
            soft_cut = self._last_boundary_before(TTS_SOFT_BOUNDARY_RE, self.hard_max_chars)
            if soft_cut is not None and soft_cut >= self.soft_min_chars:
                return soft_cut

            fallback_cut = self._last_boundary_before(TTS_FALLBACK_BOUNDARY_RE, self.hard_max_chars)
            if fallback_cut is not None and fallback_cut >= self.soft_min_chars // 2:
                return fallback_cut
            return self.hard_max_chars

        if buffer_len >= self.soft_min_chars:
            if force:
                soft_forced = self._last_boundary_before(TTS_SOFT_BOUNDARY_RE, buffer_len)
                if soft_forced is not None:
                    return soft_forced
                if strong_any is not None:
                    return strong_any
                return buffer_len

            if TTS_SOFT_BOUNDARY_RE.search(self.buffer[-2:]):
                return buffer_len

            if buffer_len >= self.soft_max_chars:
                soft_cut = self._last_boundary_before(TTS_SOFT_BOUNDARY_RE, buffer_len)
                if soft_cut is not None and soft_cut >= self.soft_min_chars:
                    return soft_cut

        if force:
            if strong_any is not None:
                return strong_any
            return buffer_len
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

    async def stream_reply(
        self,
        user_text: str,
        persona: str | None = None,
        response_language: str | None = None,
        *,
        query_text: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[ReplyStreamEvent]:
        generated = await self.generate_reply(
            user_text,
            persona=persona,
            response_language=response_language,
            query_text=query_text,
            history=history,
        )
        async for event in self._stream_from_pieces(
            self._iter_pieces(self.chunk_text(generated.spoken_text or generated.text)),
            sources=generated.sources,
            confidence=generated.confidence,
            mode=generated.mode,
            reply_kind=generated.reply_kind,
            needs_followup=generated.needs_followup,
            followup_question=generated.followup_question,
            missing_slots=generated.missing_slots,
            confidence_note=generated.confidence_note,
        ):
            yield event

    async def _stream_from_pieces(
        self,
        pieces: AsyncIterator[str],
        *,
        sources: list[RetrievedChunk],
        confidence: float,
        mode: str,
        reply_kind: str,
        needs_followup: bool,
        followup_question: str,
        missing_slots: list[str],
        confidence_note: str,
        fallback_text: str = "",
    ) -> AsyncIterator[ReplyStreamEvent]:
        display = DisplayChunker(flush_chars=self.settings.websocket_chunk_size)
        tts_segmenter = TTSSegmenter(
            soft_min_chars=self.settings.tts_segment_soft_min_chars,
            soft_max_chars=self.settings.tts_segment_soft_max_chars,
            hard_max_chars=self.settings.tts_segment_hard_max_chars,
        )
        full_parts: list[str] = []
        emitted_output = False
        iterator = pieces.__aiter__()

        while True:
            try:
                piece = await anext(iterator)
            except StopAsyncIteration:
                break
            except Exception:
                if fallback_text and not emitted_output:
                    display = DisplayChunker(flush_chars=self.settings.websocket_chunk_size)
                    tts_segmenter = TTSSegmenter(
                        soft_min_chars=self.settings.tts_segment_soft_min_chars,
                        soft_max_chars=self.settings.tts_segment_soft_max_chars,
                        hard_max_chars=self.settings.tts_segment_hard_max_chars,
                    )
                    full_parts = [fallback_text]
                    for chunk in display.feed(fallback_text):
                        emitted_output = True
                        yield ReplyStreamEvent(kind="text_delta", content=chunk)
                    for segment in tts_segmenter.feed(fallback_text):
                        emitted_output = True
                        yield ReplyStreamEvent(kind="tts_segment", content=segment)
                break

            if not piece:
                continue
            full_parts.append(piece)
            for chunk in display.feed(piece):
                emitted_output = True
                yield ReplyStreamEvent(kind="text_delta", content=chunk)
            for segment in tts_segmenter.feed(piece):
                emitted_output = True
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
            reply_kind=reply_kind,
            needs_followup=needs_followup,
            followup_question=followup_question,
            missing_slots=list(missing_slots),
            confidence_note=confidence_note,
        )

    async def _iter_pieces(self, pieces: Iterable[str]) -> AsyncIterator[str]:
        for piece in pieces:
            if piece:
                yield piece


class TemplateGuideChatService(BaseGuideChatService):
    async def generate_reply(
        self,
        user_text: str,
        persona: str | None = None,
        response_language: str | None = None,
        *,
        query_text: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> GeneratedReply:
        text = " ".join(user_text.strip().split())
        if not text:
            reply = localized_text(
                response_language,
                "我刚才没有听清，你可以再说一遍吗？",
                "I didn't catch that clearly. Could you say it again?",
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text.lower() for token in ("hello", "hi")) or "你好" in text:
            reply = localized_text(
                response_language,
                "你好，我是景区数字导览助手。你可以问我景点介绍、游览路线，或者直接说出你想去的地方。",
                "Hi, I'm your scenic-area virtual guide. You can ask about highlights, routes, or just tell me where you'd like to go.",
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("历史", "故事", "由来", "文化")):
            reply = localized_text(
                response_language,
                "这里的讲解通常会围绕景区历史、人文故事和代表性景点展开。如果你愿意，我可以先从最经典的一处景点开始介绍。",
                "I can walk you through the area's history, local stories, and signature spots. If you want, I can start with the most iconic one.",
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("路线", "怎么逛", "推荐", "先去")):
            reply = localized_text(
                response_language,
                "如果你是第一次来，建议先从核心景点主线开始，再根据体力和兴趣补充周边区域，这样体验会更完整也更轻松。",
                "If it's your first visit, I'd start with the main highlight route, then add nearby stops based on your energy and interests.",
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("时间", "营业", "开放", "几点")):
            reply = localized_text(
                response_language,
                "开放时间这类信息接入知识库后会更准确。你也可以继续问我某个景点的介绍，或者我先给你推荐一条游览路线。",
                "Opening-hour questions become much more accurate with the knowledge base enabled. You can also ask about a specific spot, or I can suggest a route first.",
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        persona_hint = localized_text(
            response_language,
            "我会按照导览员的口吻继续为你讲解。" if persona else "",
            "I'll keep the guide persona in the reply." if persona else "",
        )
        reply = localized_text(
            response_language,
            (
                "我已经收到你的问题。"
                f"{persona_hint}"
                "当前系统已经支持文本、语音识别、语音合成和流式 WebSocket 返回。"
                "接入知识库后，回答会更贴合具体景区内容。"
            ),
            (
                "I got your question. "
                f"{persona_hint}"
                "The system already supports text chat, speech recognition, speech synthesis, and streaming WebSocket replies. "
                "Once the knowledge base is connected, the answers become much more specific to the scenic area."
            ),
        )
        emotion = await self.analyze_emotion(user_text, reply)
        return GeneratedReply(reply, emotion.label, emotion)


class RAGGuideChatService(BaseGuideChatService):
    async def generate_reply(
        self,
        user_text: str,
        persona: str | None = None,
        response_language: str | None = None,
        *,
        query_text: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> GeneratedReply:
        answer = await get_rag_service().answer(
            query_text or user_text,
            persona=persona,
            history=history or [],
            response_language=response_language,
        )
        emotion = await self.analyze_emotion(user_text, answer.spoken_text or answer.answer_text)
        return GeneratedReply(
            text=answer.answer_text,
            spoken_text=answer.spoken_text,
            emotion=emotion.label,
            emotion_meta=emotion,
            sources=answer.sources,
            confidence=answer.confidence,
            mode="rag",
            reply_kind=answer.reply_kind,
            needs_followup=answer.needs_followup,
            followup_question=answer.followup_question,
            missing_slots=answer.missing_slots,
            confidence_note=answer.confidence_note,
        )

    async def stream_reply(
        self,
        user_text: str,
        persona: str | None = None,
        response_language: str | None = None,
        *,
        query_text: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[ReplyStreamEvent]:
        rag_service = get_rag_service()
        prepared = await rag_service.prepare_stream_answer(
            query_text or user_text,
            persona=persona,
            history=history or [],
            response_language=response_language,
        )
        fallback_text = prepared.answer_text or prepared.fallback_text or prepared.spoken_text
        if prepared.metrics:
            yield ReplyStreamEvent(kind="metrics", metrics=dict(prepared.metrics))

        if prepared.llm_messages:
            llm_client = getattr(rag_service, "llm", None)
            if llm_client is not None and hasattr(llm_client, "stream_complete"):
                async for event in self._stream_from_pieces(
                    llm_client.stream_complete(prepared.llm_messages),
                    sources=prepared.sources,
                    confidence=prepared.confidence,
                    mode="rag",
                    reply_kind=prepared.reply_kind,
                    needs_followup=prepared.needs_followup,
                    followup_question=prepared.followup_question,
                    missing_slots=prepared.missing_slots,
                    confidence_note=prepared.confidence_note,
                    fallback_text=fallback_text,
                ):
                    yield event
                return

        async for event in self._stream_from_pieces(
            self._iter_pieces(self.chunk_text(fallback_text)),
            sources=prepared.sources,
            confidence=prepared.confidence,
            mode="rag",
            reply_kind=prepared.reply_kind,
            needs_followup=prepared.needs_followup,
            followup_question=prepared.followup_question,
            missing_slots=prepared.missing_slots,
            confidence_note=prepared.confidence_note,
        ):
            yield event


def get_chat_service():
    settings = get_settings()
    mode = settings.chat_mode.strip().lower()
    if mode == "rag":
        return RAGGuideChatService(settings)
    return TemplateGuideChatService(settings)
