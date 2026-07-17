from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import re

import httpx

from app.core.config import Settings, get_settings

EMOTION_VALUES = ("neutral", "happy", "thinking", "excited", "sad")

EMOTION_HINTS: dict[str, tuple[str, ...]] = {
    "happy": ("欢迎", "高兴", "愉快", "适合", "推荐", "值得", "轻松", "美景"),
    "thinking": ("历史", "故事", "文化", "由来", "典故", "建设", "渊源", "背景"),
    "excited": ("路线", "出发", "先去", "一定要看", "马上", "精彩", "主线", "打卡"),
    "sad": ("遗憾", "抱歉", "不便", "暂时无法", "无法确认", "未开放", "没有找到"),
}


@dataclass(slots=True, frozen=True)
class EmotionAnalysis:
    label: str
    confidence: float
    keywords: list[str]
    reason: str
    source: str


class EmotionAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze_quick(self, user_text: str, reply_text: str = "") -> EmotionAnalysis:
        return self._analyze_with_heuristics(user_text=user_text, reply_text=reply_text)

    async def analyze(self, user_text: str, reply_text: str) -> EmotionAnalysis:
        if self.settings.dashscope_api_key:
            try:
                result = await self._analyze_with_llm(user_text=user_text, reply_text=reply_text)
                if result:
                    return result
            except Exception:
                pass
        return self._analyze_with_heuristics(user_text=user_text, reply_text=reply_text)

    async def _analyze_with_llm(self, user_text: str, reply_text: str) -> EmotionAnalysis | None:
        url = f"{self.settings.dashscope_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.dashscope_model,
            "temperature": 0.1,
            "max_tokens": 220,
            "enable_thinking": self.settings.dashscope_enable_thinking,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是数字人表情控制器。"
                        "请根据游客问题和导览员回答，判断当前回答更适合的表情。"
                        "只允许使用 neutral、happy、thinking、excited、sad 这五种情绪。"
                        "输出必须是 JSON 对象，包含 label、confidence、keywords、reason 四个字段。"
                        "confidence 范围 0 到 1，keywords 为数组。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"游客问题：{user_text.strip()}\n"
                        f"导览员回答：{reply_text.strip()}\n"
                        "请只返回 JSON。"
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds * 2) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            return None

        parsed = self._parse_llm_payload(content)
        if parsed is None:
            return None

        label = parsed.get("label", "neutral")
        confidence = float(parsed.get("confidence", 0.55))
        keywords = [str(item).strip() for item in parsed.get("keywords", []) if str(item).strip()]
        reason = str(parsed.get("reason", "")).strip() or "LLM 给出了当前回答的情绪判断。"
        return EmotionAnalysis(
            label=self._normalize_label(label),
            confidence=max(0.0, min(confidence, 1.0)),
            keywords=keywords[:4],
            reason=reason,
            source="llm",
        )

    def _analyze_with_heuristics(self, user_text: str, reply_text: str) -> EmotionAnalysis:
        combined = f"{user_text.strip()} {reply_text.strip()}"
        scores = {label: 0.0 for label in EMOTION_VALUES}
        matched_keywords: dict[str, list[str]] = {label: [] for label in EMOTION_VALUES}

        for label, hints in EMOTION_HINTS.items():
            for hint in hints:
                if hint in combined:
                    scores[label] += 0.24
                    matched_keywords[label].append(hint)

        if "？" in user_text or "怎么" in user_text or "如何" in user_text:
            scores["thinking"] += 0.08
        if any(token in combined for token in ("推荐", "路线", "游览", "主线")):
            scores["excited"] += 0.18
        if any(token in combined for token in ("欢迎", "你好", "很高兴", "适合")):
            scores["happy"] += 0.18
        if any(token in combined for token in ("抱歉", "无法", "暂时不能", "不便")):
            scores["sad"] += 0.16

        label = max(scores.items(), key=lambda item: item[1])[0]
        if scores[label] < 0.2:
            return EmotionAnalysis(
                label="neutral",
                confidence=0.45,
                keywords=[],
                reason="未命中特别明显的情绪关键词，保持中性导览语气。",
                source="heuristic",
            )

        keywords = self._dedupe_preserve_order(matched_keywords[label])[:4]
        reasons = {
            "happy": "回答包含欢迎、推荐等积极导览表达，更适合友好微笑表情。",
            "thinking": "回答偏历史、文化、典故说明，更适合思考型表情。",
            "excited": "回答聚焦路线与看点推荐，更适合更有动势的兴奋表情。",
            "sad": "回答包含无法确认或遗憾提示，使用较克制的表情更自然。",
            "neutral": "回答信息性较强，保持中性表情即可。",
        }
        return EmotionAnalysis(
            label=label,
            confidence=min(0.92, 0.48 + scores[label]),
            keywords=keywords,
            reason=reasons[label],
            source="heuristic",
        )

    def _parse_llm_payload(self, text: str) -> dict[str, object] | None:
        cleaned = text.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()
        elif not cleaned.startswith("{"):
            first = cleaned.find("{")
            last = cleaned.rfind("}")
            if first != -1 and last != -1 and last > first:
                cleaned = cleaned[first : last + 1]

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _normalize_label(self, label: str) -> str:
        normalized = label.strip().lower()
        if normalized not in EMOTION_VALUES:
            return "neutral"
        return normalized

    def _dedupe_preserve_order(self, items: list[str]) -> list[str]:
        seen = set()
        deduped: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped


@lru_cache
def get_emotion_analyzer() -> EmotionAnalyzer:
    return EmotionAnalyzer(get_settings())
