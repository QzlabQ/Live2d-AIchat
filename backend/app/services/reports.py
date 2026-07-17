from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import DailyEmotionReport, Message, Session

logger = logging.getLogger(__name__)

REPORT_SENTIMENT_VALUES = {"positive", "neutral", "negative"}
STOP_PHRASES = {
    "请问",
    "这里",
    "这个",
    "那个",
    "一下",
    "可以",
    "帮我",
    "我们",
    "你们",
    "什么",
    "怎么",
    "是否",
}


@dataclass(slots=True)
class DailyReportComputation:
    report_date: date
    session_count: int
    message_count: int
    user_message_count: int
    assistant_message_count: int
    avg_assistant_latency_ms: float | None
    emotion_counts: dict[str, int]
    top_interest_tags: list[str]
    top_keywords: list[str]
    overall_sentiment: str
    summary_text: str
    source: str


class DailyEmotionReportService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.settings.analytics_scheduler_enabled or self._task is not None:
            return

        self._stop_event.clear()
        await self.generate_recent_missing_reports()
        self._task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.settings.analytics_scheduler_interval_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    await self.generate_recent_missing_reports()
                except Exception:
                    logger.exception("Daily analytics scheduler tick failed.")

    async def generate_recent_missing_reports(self) -> None:
        today = datetime.now().date()
        days = max(1, int(self.settings.analytics_scheduler_catchup_days))
        for offset in reversed(range(days)):
            target = today - timedelta(days=offset)
            try:
                await self.generate_for_date(target, force=False)
            except Exception:
                logger.exception("Failed to generate report for %s", target.isoformat())

    async def generate_for_date(self, report_date: date, *, force: bool = False) -> DailyEmotionReport:
        async with self.session_factory() as db:
            return await self.generate_for_date_in_session(db, report_date, force=force)

    async def generate_for_date_in_session(
        self,
        db: AsyncSession,
        report_date: date,
        *,
        force: bool = False,
    ) -> DailyEmotionReport:
        existing = await self._get_report_by_date(db, report_date)
        if existing is not None and not force and not await self._report_needs_refresh(db, existing):
            return existing
        if existing is not None:
            await db.delete(existing)
            await db.flush()

        computation = await self._compute_report(db, report_date)
        report = DailyEmotionReport(
            report_date=computation.report_date,
            status="ready",
            session_count=computation.session_count,
            message_count=computation.message_count,
            user_message_count=computation.user_message_count,
            assistant_message_count=computation.assistant_message_count,
            avg_assistant_latency_ms=computation.avg_assistant_latency_ms,
            emotion_counts=computation.emotion_counts,
            top_interest_tags=computation.top_interest_tags,
            top_keywords=computation.top_keywords,
            overall_sentiment=computation.overall_sentiment,
            summary_text=computation.summary_text,
            source=computation.source,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report

    async def list_reports(
        self,
        db: AsyncSession,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 31,
        reconcile: bool = False,
    ) -> list[DailyEmotionReport]:
        stmt = select(DailyEmotionReport).order_by(DailyEmotionReport.report_date.desc())
        if reconcile and date_from is not None and date_to is not None:
            await self.reconcile_reports_in_range(db, date_from=date_from, date_to=date_to)
        if date_from is not None:
            stmt = stmt.where(DailyEmotionReport.report_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(DailyEmotionReport.report_date <= date_to)
        if limit > 0:
            stmt = stmt.limit(limit)
        return list((await db.execute(stmt)).scalars())

    async def reconcile_reports_in_range(
        self,
        db: AsyncSession,
        *,
        date_from: date,
        date_to: date,
    ) -> None:
        target = date_from
        today = datetime.now().date()
        upper_bound = min(date_to, today)
        while target <= upper_bound:
            await self.generate_for_date_in_session(db, target, force=False)
            target += timedelta(days=1)

    async def build_range_summary(
        self,
        db: AsyncSession,
        *,
        date_from: date,
        date_to: date,
    ) -> DailyReportComputation:
        reports = await self.list_reports(db, date_from=date_from, date_to=date_to, limit=366)
        if not reports:
            return DailyReportComputation(
                report_date=date_to,
                session_count=0,
                message_count=0,
                user_message_count=0,
                assistant_message_count=0,
                avg_assistant_latency_ms=None,
                emotion_counts={},
                top_interest_tags=[],
                top_keywords=[],
                overall_sentiment="neutral",
                summary_text="当前时间范围内还没有生成日报分析。",
                source="heuristic",
            )

        emotion_counter: Counter[str] = Counter()
        tag_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        latency_values: list[float] = []
        summary_fragments: list[str] = []

        for item in reports:
            emotion_counter.update(item.emotion_counts or {})
            tag_counter.update(item.top_interest_tags or [])
            keyword_counter.update(item.top_keywords or [])
            if item.avg_assistant_latency_ms is not None:
                latency_values.append(float(item.avg_assistant_latency_ms))
            if item.summary_text:
                summary_fragments.append(item.summary_text.strip())

        dominant_sentiment = self._sentiment_from_emotions(dict(emotion_counter))
        report_count = len(reports)
        avg_latency = (
            round(sum(latency_values) / len(latency_values), 1) if latency_values else None
        )
        summary_text = (
            f"共覆盖 {report_count} 天、{sum(item.session_count for item in reports)} 个会话、"
            f"{sum(item.message_count for item in reports)} 条消息。"
        )
        if summary_fragments:
            summary_text += f" 近期观察：{summary_fragments[0]}"

        return DailyReportComputation(
            report_date=date_to,
            session_count=sum(item.session_count for item in reports),
            message_count=sum(item.message_count for item in reports),
            user_message_count=sum(item.user_message_count for item in reports),
            assistant_message_count=sum(item.assistant_message_count for item in reports),
            avg_assistant_latency_ms=avg_latency,
            emotion_counts=dict(emotion_counter),
            top_interest_tags=[item for item, _ in tag_counter.most_common(6)],
            top_keywords=[item for item, _ in keyword_counter.most_common(8)],
            overall_sentiment=dominant_sentiment,
            summary_text=summary_text,
            source="heuristic",
        )

    async def _get_report_by_date(self, db: AsyncSession, report_date: date) -> DailyEmotionReport | None:
        stmt = select(DailyEmotionReport).where(DailyEmotionReport.report_date == report_date).limit(1)
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _report_needs_refresh(self, db: AsyncSession, report: DailyEmotionReport) -> bool:
        start_at = datetime.combine(report.report_date, time.min)
        end_at = start_at + timedelta(days=1)
        stats_stmt = (
            select(
                func.count(Message.id),
                func.count(func.distinct(Message.session_id)),
                func.count(Message.id).filter(Message.role == "user"),
                func.count(Message.id).filter(Message.role == "assistant"),
            )
            .where(Message.created_at >= start_at, Message.created_at < end_at)
        )
        message_count, session_count, user_count, assistant_count = (
            await db.execute(stats_stmt)
        ).one()
        return any(
            [
                int(session_count or 0) != int(report.session_count or 0),
                int(message_count or 0) != int(report.message_count or 0),
                int(user_count or 0) != int(report.user_message_count or 0),
                int(assistant_count or 0) != int(report.assistant_message_count or 0),
            ]
        )

    async def _compute_report(self, db: AsyncSession, report_date: date) -> DailyReportComputation:
        start_at = datetime.combine(report_date, time.min)
        end_at = start_at + timedelta(days=1)
        stmt = (
            select(Message, Session)
            .join(Session, Session.id == Message.session_id)
            .where(Message.created_at >= start_at, Message.created_at < end_at)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        rows = (await db.execute(stmt)).all()

        session_ids: set[str] = set()
        user_messages: list[Message] = []
        assistant_messages: list[Message] = []
        tag_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        emotion_counter: Counter[str] = Counter()
        session_dialogues: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for message, session_obj in rows:
            session_ids.add(session_obj.id)
            if session_obj.interest_tags:
                tag_counter.update(session_obj.interest_tags)
            session_dialogues[session_obj.id].append((message.role, message.content))

            if message.role == "user":
                user_messages.append(message)
                keyword_counter.update(self._extract_keywords(message.content))
                continue

            if message.role == "assistant":
                assistant_messages.append(message)
                emotion_counter.update([(message.emotion or "neutral").strip().lower() or "neutral"])

        avg_latency = self._compute_average_latency(assistant_messages)
        top_interest_tags = [item for item, _ in tag_counter.most_common(6)]
        top_keywords = [item for item, _ in keyword_counter.most_common(8)]
        sample_dialogues = self._build_dialogue_samples(session_dialogues)
        overall_sentiment, summary_text, source = await self._summarize_report(
            report_date=report_date,
            session_count=len(session_ids),
            message_count=len(rows),
            user_message_count=len(user_messages),
            assistant_message_count=len(assistant_messages),
            avg_assistant_latency_ms=avg_latency,
            emotion_counts=dict(emotion_counter),
            top_interest_tags=top_interest_tags,
            top_keywords=top_keywords,
            sample_dialogues=sample_dialogues,
        )

        return DailyReportComputation(
            report_date=report_date,
            session_count=len(session_ids),
            message_count=len(rows),
            user_message_count=len(user_messages),
            assistant_message_count=len(assistant_messages),
            avg_assistant_latency_ms=avg_latency,
            emotion_counts=dict(emotion_counter),
            top_interest_tags=top_interest_tags,
            top_keywords=top_keywords,
            overall_sentiment=overall_sentiment,
            summary_text=summary_text,
            source=source,
        )

    def _compute_average_latency(self, assistant_messages: list[Message]) -> float | None:
        values = [int(item.latency_ms) for item in assistant_messages if item.latency_ms is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 1)

    def _build_dialogue_samples(self, session_dialogues: dict[str, list[tuple[str, str]]]) -> list[str]:
        samples: list[str] = []
        limit = max(1, int(self.settings.analytics_report_sample_sessions))
        for _, entries in list(session_dialogues.items())[:limit]:
            turns: list[str] = []
            for role, content in entries[:4]:
                speaker = "游客" if role == "user" else "导览助手"
                turns.append(f"{speaker}：{self._truncate_text(content, 96)}")
            if turns:
                samples.append(" | ".join(turns))
        return samples

    async def _summarize_report(
        self,
        *,
        report_date: date,
        session_count: int,
        message_count: int,
        user_message_count: int,
        assistant_message_count: int,
        avg_assistant_latency_ms: float | None,
        emotion_counts: dict[str, int],
        top_interest_tags: list[str],
        top_keywords: list[str],
        sample_dialogues: list[str],
    ) -> tuple[str, str, str]:
        if message_count == 0:
            return "neutral", "当天暂无有效对话数据。", "heuristic"

        if self.settings.dashscope_api_key:
            llm_result = await self._summarize_with_llm(
                report_date=report_date,
                session_count=session_count,
                message_count=message_count,
                user_message_count=user_message_count,
                assistant_message_count=assistant_message_count,
                avg_assistant_latency_ms=avg_assistant_latency_ms,
                emotion_counts=emotion_counts,
                top_interest_tags=top_interest_tags,
                top_keywords=top_keywords,
                sample_dialogues=sample_dialogues,
            )
            if llm_result is not None:
                return llm_result[0], llm_result[1], "llm"

        dominant = self._sentiment_from_emotions(emotion_counts)
        summary_parts = [
            f"{report_date.isoformat()} 共记录 {session_count} 个会话、{message_count} 条消息。"
        ]
        if top_keywords:
            summary_parts.append(f"游客关注点主要集中在：{'、'.join(top_keywords[:4])}。")
        if top_interest_tags:
            summary_parts.append(f"活跃兴趣标签：{'、'.join(top_interest_tags[:3])}。")
        if avg_assistant_latency_ms is not None:
            summary_parts.append(f"导览助手平均响应耗时约 {avg_assistant_latency_ms:.1f} ms。")
        if dominant == "negative":
            summary_parts.append("当天对话里存在较多受阻或无法确认场景，建议复核知识覆盖和回复策略。")
        elif dominant == "positive":
            summary_parts.append("整体交流偏积极顺畅，推荐与讲解类问题反馈更好。")
        else:
            summary_parts.append("整体交流较平稳，仍可继续优化高频问题的回答自然度与速度。")
        return dominant, "".join(summary_parts), "heuristic"

    async def _summarize_with_llm(
        self,
        *,
        report_date: date,
        session_count: int,
        message_count: int,
        user_message_count: int,
        assistant_message_count: int,
        avg_assistant_latency_ms: float | None,
        emotion_counts: dict[str, int],
        top_interest_tags: list[str],
        top_keywords: list[str],
        sample_dialogues: list[str],
    ) -> tuple[str, str] | None:
        url = f"{self.settings.dashscope_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.dashscope_model,
            "temperature": 0.2,
            "max_tokens": 260,
            "enable_thinking": self.settings.dashscope_enable_thinking,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是景区数字人运营分析助手。"
                        "请根据每日会话统计，输出一段简短运营摘要。"
                        "只返回 JSON，字段为 overall_sentiment 和 summary_text。"
                        "overall_sentiment 只能是 positive、neutral、negative。"
                        "summary_text 控制在 120 个中文字符以内，强调游客关注点和是否需要优化。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "report_date": report_date.isoformat(),
                            "session_count": session_count,
                            "message_count": message_count,
                            "user_message_count": user_message_count,
                            "assistant_message_count": assistant_message_count,
                            "avg_assistant_latency_ms": avg_assistant_latency_ms,
                            "emotion_counts": emotion_counts,
                            "top_interest_tags": top_interest_tags,
                            "top_keywords": top_keywords,
                            "sample_dialogues": sample_dialogues,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds * 2) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            parsed = self._parse_llm_json(str(content))
            if parsed is None:
                return None
            sentiment = str(parsed.get("overall_sentiment", "neutral")).strip().lower()
            if sentiment not in REPORT_SENTIMENT_VALUES:
                sentiment = "neutral"
            summary_text = str(parsed.get("summary_text", "")).strip()
            if not summary_text:
                return None
            return sentiment, summary_text[:180]
        except Exception as exc:
            logger.warning("Failed to generate daily report summary with LLM: %s", exc)
            return None

    def _parse_llm_json(self, text: str) -> dict[str, object] | None:
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

    def _extract_keywords(self, text: str) -> list[str]:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.strip().lower())
        segments = [item.strip() for item in normalized.split() if item.strip()]
        results: list[str] = []
        for item in segments:
            candidate = re.sub(r"^(请问|我想问|我想了解|想问一下|帮我看看|能不能|可以|这里的|这里|景区的)", "", item)
            candidate = re.sub(r"(吗|呢|呀|啊|吧|一下)$", "", candidate)
            candidate = candidate.strip()
            if len(candidate) < 2:
                continue
            if candidate in STOP_PHRASES:
                continue
            results.append(candidate[:16])
        return results[:4]

    def _sentiment_from_emotions(self, emotion_counts: dict[str, int]) -> str:
        positive = int(emotion_counts.get("happy", 0)) + int(emotion_counts.get("excited", 0))
        negative = int(emotion_counts.get("sad", 0))
        thinking = int(emotion_counts.get("thinking", 0))
        total = sum(int(value) for value in emotion_counts.values())
        if total == 0:
            return "neutral"
        if negative / total >= 0.25:
            return "negative"
        if positive / total >= 0.45 and negative == 0:
            return "positive"
        if thinking / total >= 0.5:
            return "neutral"
        return "neutral"

    def _truncate_text(self, text: str, limit: int) -> str:
        cleaned = " ".join(str(text).split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 1].rstrip() + "…"


@lru_cache
def get_report_service() -> DailyEmotionReportService:
    from app.db.session import AsyncSessionFactory

    return DailyEmotionReportService(AsyncSessionFactory, get_settings())
