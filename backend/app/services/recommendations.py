from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

CANONICAL_TAG_ALIASES: dict[str, tuple[str, ...]] = {
    "历史文化": ("历史文化", "history", "culture", "history-culture"),
    "亲子": ("亲子", "family", "family-friendly", "kids", "children"),
    "夜游": ("夜游", "night-tour", "night tour", "night"),
    "轻松": ("轻松", "relaxed", "relax", "easygoing"),
    "拍照打卡": ("拍照打卡", "拍照", "打卡", "photo", "photo-stop"),
    "省力": ("省力", "easy", "effort-saving", "low-energy", "accessible"),
}


class ChatCompletionsClient(Protocol):
    async def complete(self, messages: list[dict[str, str]]) -> str:
        ...


@dataclass(slots=True)
class RecommendationRequest:
    session_id: str
    interest_tags: list[str]
    device_type: str
    visitor_profile: str | None = None


@dataclass(slots=True)
class RecommendationResult:
    route_title: str
    intro: str
    highlights: list[str]
    suggested_questions: list[str]
    applied_interest_tags: list[str]


class RecommendationGenerationError(Exception):
    pass


class VisitorRecommendationService:
    def __init__(
        self,
        settings: Settings | None = None,
        llm: ChatCompletionsClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._llm = llm

    async def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        try:
            result = await self._complete_structured(request)
        except RecommendationGenerationError as exc:
            logger.warning(
                "Structured recommendation fallback for session %s: %s",
                request.session_id,
                exc,
            )
            return self._fallback_payload(request)

        if not self._is_complete(result):
            return self._fallback_payload(request)
        return result

    async def _complete_structured(self, request: RecommendationRequest) -> RecommendationResult:
        try:
            raw = await self._get_llm().complete(self._build_messages(request))
        except Exception as exc:
            raise RecommendationGenerationError("LLM completion failed.") from exc

        payload = self._parse_json_object(raw)
        if payload is None:
            raise RecommendationGenerationError("Recommendation payload is not valid JSON.")

        result = self._coerce_result(payload, request)
        if not self._is_complete(result):
            raise RecommendationGenerationError("Recommendation payload is incomplete.")
        return result

    def _build_messages(self, request: RecommendationRequest) -> list[dict[str, str]]:
        tags = "、".join(self._normalize_interest_tags(request.interest_tags))
        visitor_profile = (request.visitor_profile or "").strip() or "未提供"
        return [
            {
                "role": "system",
                "content": (
                    "你是景区导览助手。"
                    "请只输出 JSON，并返回结构化路线推荐。"
                    "字段固定为 route_title, intro, highlights, suggested_questions, applied_interest_tags。"
                    "highlights 和 suggested_questions 必须为非空数组。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"session_id: {request.session_id}\n"
                    f"device_type: {request.device_type}\n"
                    f"interest_tags: {tags}\n"
                    f"visitor_profile: {visitor_profile}\n\n"
                    "请返回一条适合游客的推荐路线。"
                ),
            },
        ]

    def _coerce_result(
        self,
        payload: dict[str, object],
        request: RecommendationRequest,
    ) -> RecommendationResult:
        normalized_request_tags = self._normalize_interest_tags(request.interest_tags)
        route_title = self._clean_text(payload.get("route_title"))
        intro = self._clean_text(payload.get("intro"))
        highlights = self._clean_list(payload.get("highlights"))
        suggested_questions = self._clean_list(payload.get("suggested_questions"))
        applied_interest_tags = self._sanitize_applied_interest_tags(
            payload.get("applied_interest_tags"),
            normalized_request_tags,
        )
        if not applied_interest_tags:
            applied_interest_tags = list(normalized_request_tags)

        return RecommendationResult(
            route_title=route_title,
            intro=intro,
            highlights=highlights,
            suggested_questions=suggested_questions,
            applied_interest_tags=applied_interest_tags,
        )

    def _fallback_payload(self, request: RecommendationRequest) -> RecommendationResult:
        tags = self._normalize_interest_tags(request.interest_tags)
        profile = (request.visitor_profile or "").strip()

        if self._has_canonical_tag(tags, "亲子"):
            route_title = "亲子轻松体验路线"
            intro = "先走更容易进入状态的核心点位，再安排适合边走边聊和短暂停留的体验段。"
            highlights = ["从核心地标起步", "优先平缓路线", "预留拍照和休息时间"]
            suggested_questions = ["哪一段最适合带孩子慢慢逛？", "如果只玩半天应该删掉哪一站？"]
        elif self._has_canonical_tag(tags, "历史文化"):
            route_title = "历史文化漫游路线"
            intro = "先看代表性地标，再顺着故事线理解景区背景，适合第一次系统了解景区。"
            highlights = ["优先核心地标", "按故事线安排顺序", "适合边走边听讲解"]
            suggested_questions = ["这条路线里哪一站最值得先听讲解？", "如果更想看历史细节，可以加哪一站？"]
        elif self._has_canonical_tag(tags, "夜游"):
            route_title = "夜游氛围体验路线"
            intro = "优先安排夜景效果更好的区域，把傍晚到入夜的节奏利用起来。"
            highlights = ["优先夜景点位", "兼顾灯光变化", "适合边走边拍"]
            suggested_questions = ["哪一段最适合等亮灯？", "如果只看夜景核心点，建议保留哪几站？"]
        elif self._has_canonical_tag(tags, "拍照打卡"):
            route_title = "拍照打卡优先路线"
            intro = "先串联标志性场景和更容易出片的点位，方便集中完成拍照打卡。"
            highlights = ["优先视觉标志点", "减少来回折返", "适合集中拍摄"]
            suggested_questions = ["哪一站最适合先拍标志性照片？", "如果想避开人流，建议先去哪一段？"]
        elif self._has_canonical_tag(tags, "轻松") or self._has_canonical_tag(tags, "省力"):
            route_title = "轻松省力游览路线"
            intro = "尽量先走更省体力、停留更舒适的路线，适合放慢节奏游览。"
            highlights = ["减少高强度往返", "优先舒适停留点", "便于按体力灵活收尾"]
            suggested_questions = ["如果想更省力，哪一站可以直接跳过？", "这条路线哪里最适合中途休息？"]
        else:
            route_title = "经典游览推荐路线"
            intro = "先覆盖游客最常关心的核心区域，再根据现场体力和时间灵活调整。"
            highlights = ["先看代表性景点", "留出机动时间", "适合第一次到访快速建立印象"]
            suggested_questions = ["如果时间不够，哪一站可以先跳过？", "这条路线适合什么时候开始走？"]

        if profile:
            intro = f"{intro} 已结合游客画像：{profile}。"

        return RecommendationResult(
            route_title=route_title,
            intro=intro,
            highlights=highlights,
            suggested_questions=suggested_questions,
            applied_interest_tags=list(tags),
        )

    def _get_llm(self) -> ChatCompletionsClient:
        if self._llm is None:
            from app.services.rag import DashScopeChatCompletionsClient

            self._llm = DashScopeChatCompletionsClient(self.settings)
        return self._llm

    def _is_complete(self, result: RecommendationResult) -> bool:
        return all(
            [
                bool(result.route_title.strip()),
                bool(result.intro.strip()),
                bool(result.highlights),
                bool(result.suggested_questions),
                bool(result.applied_interest_tags),
            ]
        )

    def _normalize_interest_tags(self, tags: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen = set()
        for tag in tags:
            value = self._clean_text(tag)
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        return cleaned

    def _has_canonical_tag(self, tags: list[str], canonical_tag: str) -> bool:
        aliases = {alias.lower() for alias in CANONICAL_TAG_ALIASES.get(canonical_tag, ())}
        for tag in tags:
            if tag.lower() in aliases:
                return True
        return False

    def _clean_text(self, value: object) -> str:
        return " ".join(str(value or "").strip().split())

    def _clean_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in (self._clean_text(entry) for entry in value) if item]

    def _sanitize_applied_interest_tags(
        self,
        value: object,
        normalized_request_tags: list[str],
    ) -> list[str]:
        allowed = set(normalized_request_tags)
        filtered: list[str] = []
        for tag in self._clean_list(value):
            if tag not in allowed or tag in filtered:
                continue
            filtered.append(tag)
        return filtered

    def _parse_json_object(self, raw_text: str) -> dict[str, object] | None:
        cleaned = raw_text.strip()
        if not cleaned:
            return None

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()
        elif not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None


@lru_cache
def get_visitor_recommendation_service() -> VisitorRecommendationService:
    return VisitorRecommendationService(get_settings())
