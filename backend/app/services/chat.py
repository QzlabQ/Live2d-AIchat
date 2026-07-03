from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.emotion import EmotionAnalysis, get_emotion_analyzer
from app.services.rag import RetrievedChunk, get_rag_service

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


@dataclass(slots=True)
class GeneratedReply:
    text: str
    emotion: str
    emotion_meta: EmotionAnalysis
    spoken_text: str | None = None
    sources: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    mode: str = "template"


class BaseGuideChatService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chunk_text(self, text: str) -> list[str]:
        segments = [item.strip() for item in SENTENCE_SPLIT_RE.split(text) if item.strip()]
        if not segments:
            return [text]

        chunked: list[str] = []
        for segment in segments:
            if len(segment) <= self.settings.websocket_chunk_size:
                chunked.append(segment)
                continue

            start = 0
            while start < len(segment):
                chunked.append(segment[start : start + self.settings.websocket_chunk_size])
                start += self.settings.websocket_chunk_size
        return chunked

    async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
        return await get_emotion_analyzer().analyze(user_text=user_text, reply_text=reply_text)


class TemplateGuideChatService(BaseGuideChatService):
    async def generate_reply(self, user_text: str, persona: str | None = None) -> GeneratedReply:
        text = " ".join(user_text.strip().split())
        if not text:
            reply = "我刚刚没有听清，你可以再说一次吗？"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("你好", "hello", "hi", "嗨")):
            reply = "你好，我是景区数字导览助手。你可以问我景点介绍、游览路线，或者直接说出你想去的地方。"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("历史", "故事", "由来", "文化")):
            reply = (
                "这个景区通常会围绕当地历史、人文故事和代表性景点来展开讲解。"
                "当前 Phase 1 先打通语音和数字人链路，后续接入知识库后我会给出更准确的史实回答。"
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("路线", "怎么逛", "推荐", "先去")):
            reply = (
                "如果你是第一次来，建议先从核心景点开始，再去人少一些的区域慢慢逛。"
                "后续版本会结合你的兴趣标签，自动生成更细的游览路线。"
            )
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        if any(token in text for token in ("时间", "营业", "开放", "几点")):
            reply = "开放时间这类信息后续会接入知识库和后台配置。现在你也可以继续问我景点简介或参观建议。"
            emotion = await self.analyze_emotion(user_text, reply)
            return GeneratedReply(reply, emotion.label, emotion)

        persona_hint = ""
        if persona:
            persona_hint = "我会按照导览员的口吻继续为你讲解。"

        reply = (
            "我已经收到你的问题。"
            f"{persona_hint}"
            "当前后端已支持文本、语音识别、语音合成和流式 WebSocket 返回，"
            "下一阶段接入知识库后，回答会更贴合具体景区内容。"
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


def get_chat_service():
    settings = get_settings()
    mode = settings.chat_mode.strip().lower()
    if mode == "rag":
        return RAGGuideChatService(settings)
    return TemplateGuideChatService(settings)
