from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import Message, Session


@dataclass(slots=True)
class DashboardQuestionItem:
    question: str
    count: int


@dataclass(slots=True)
class DashboardTrendPoint:
    date: date
    session_count: int
    message_count: int
    avg_latency_ms: float | None
    score: float | None


@dataclass(slots=True)
class DashboardServiceTrendPoint:
    date: date
    service_count: int


@dataclass(slots=True)
class DashboardKeywordCloudItem:
    word: str
    count: int
    weight: float
    source: str


@dataclass(slots=True)
class DashboardEmotionPoint:
    date: date
    happy: float
    neutral: float
    negative: float
    total: int
    score: float | None


@dataclass(slots=True)
class DashboardOverview:
    period: str
    date_from: date
    date_to: date
    service_count: int
    session_count: int
    message_count: int
    user_message_count: int
    assistant_message_count: int
    realtime_online_count: int
    avg_satisfaction: float | None
    avg_latency_ms: float | None
    overall_sentiment: str
    top_questions: list[DashboardQuestionItem]
    service_trend: list[DashboardServiceTrendPoint]
    satisfaction_trend: list[DashboardTrendPoint]
    top_interest_tags: list[str]
    top_keywords: list[str]
    keyword_cloud: list[DashboardKeywordCloudItem]
    emotion_counts: dict[str, int]
    summary_text: str


@dataclass(slots=True)
class DashboardEmotionSummary:
    date_from: date
    date_to: date
    overall_sentiment: str
    emotion_counts: dict[str, int]
    trend: list[DashboardEmotionPoint]
    summary_text: str


QUESTION_PREFIX_RE = re.compile(
    r"^(请问一下|请问|麻烦|帮我|想问一下|想问|能不能|可以|告诉我|我想知道|请帮我)\s*"
)
TRAILING_PARTICLES_RE = re.compile(r"[。！？!?；;,.，、\s]+$")
STOP_WORDS = {
    "请问",
    "麻烦",
    "帮我",
    "可以",
    "告诉我",
    "一下",
    "什么",
    "怎么",
    "是否",
    "能不能",
    "这个",
    "那个",
    "我们",
    "你们",
}
EMOTION_SCORE = {
    "happy": 4.6,
    "excited": 4.8,
    "neutral": 3.6,
    "thinking": 3.5,
    "sad": 2.4,
}


class DashboardService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.session_factory = session_factory
        self.settings = settings

    def _resolve_period(self, period: str) -> tuple[date, date]:
        today = datetime.now().date()
        normalized = (period or "today").strip().lower()
        if normalized == "week":
            return today - timedelta(days=6), today
        if normalized == "month":
            return today - timedelta(days=29), today
        return today, today

    def _range_bounds(self, date_from: date, date_to: date) -> tuple[datetime, datetime]:
        start_at = datetime.combine(date_from, time.min)
        end_at = datetime.combine(date_to + timedelta(days=1), time.min)
        return start_at, end_at

    async def build_overview(self, db: AsyncSession, *, period: str = "today") -> DashboardOverview:
        date_from, date_to = self._resolve_period(period)
        start_at, end_at = self._range_bounds(date_from, date_to)
        stats = await self._collect_stats(db, start_at=start_at, end_at=end_at)
        active_threshold = datetime.now() - timedelta(minutes=10)
        active_stmt = select(func.count(Session.id)).where(Session.updated_at >= active_threshold)
        realtime_online_count = int((await db.execute(active_stmt)).scalar_one() or 0)

        summary_text = self._build_summary_text(
            date_from=date_from,
            date_to=date_to,
            session_count=stats["session_count"],
            message_count=stats["message_count"],
            avg_latency_ms=stats["avg_latency_ms"],
            top_questions=stats["top_questions"],
            top_interest_tags=stats["top_interest_tags"],
            overall_sentiment=stats["overall_sentiment"],
        )

        return DashboardOverview(
            period=period,
            date_from=date_from,
            date_to=date_to,
            service_count=stats["session_count"],
            session_count=stats["session_count"],
            message_count=stats["message_count"],
            user_message_count=stats["user_message_count"],
            assistant_message_count=stats["assistant_message_count"],
            realtime_online_count=realtime_online_count,
            avg_satisfaction=stats["avg_satisfaction"],
            avg_latency_ms=stats["avg_latency_ms"],
            overall_sentiment=stats["overall_sentiment"],
            top_questions=stats["top_questions"],
            service_trend=stats["service_trend"],
            satisfaction_trend=stats["satisfaction_trend"],
            top_interest_tags=stats["top_interest_tags"],
            top_keywords=stats["top_keywords"],
            keyword_cloud=stats["keyword_cloud"],
            emotion_counts=stats["emotion_counts"],
            summary_text=summary_text,
        )

    async def build_emotion_summary(
        self,
        db: AsyncSession,
        *,
        date_from: date,
        date_to: date,
    ) -> DashboardEmotionSummary:
        start_at, end_at = self._range_bounds(date_from, date_to)
        stats = await self._collect_stats(db, start_at=start_at, end_at=end_at)
        trend = [
            DashboardEmotionPoint(
                date=item.date,
                happy=item.happy_ratio,
                neutral=item.neutral_ratio,
                negative=item.negative_ratio,
                total=item.total,
                score=item.score,
            )
            for item in stats["emotion_trend"]
        ]
        summary_text = self._build_summary_text(
            date_from=date_from,
            date_to=date_to,
            session_count=stats["session_count"],
            message_count=stats["message_count"],
            avg_latency_ms=stats["avg_latency_ms"],
            top_questions=stats["top_questions"],
            top_interest_tags=stats["top_interest_tags"],
            overall_sentiment=stats["overall_sentiment"],
        )
        return DashboardEmotionSummary(
            date_from=date_from,
            date_to=date_to,
            overall_sentiment=stats["overall_sentiment"],
            emotion_counts=stats["emotion_counts"],
            trend=trend,
            summary_text=summary_text,
        )

    async def _collect_stats(self, db: AsyncSession, *, start_at: datetime, end_at: datetime) -> dict[str, object]:
        stmt = (
            select(Message, Session)
            .join(Session, Session.id == Message.session_id)
            .where(Message.created_at >= start_at, Message.created_at < end_at)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        rows = (await db.execute(stmt)).all()

        session_ids: set[str] = set()
        user_message_count = 0
        assistant_message_count = 0
        latencies: list[float] = []
        emotion_counts: Counter[str] = Counter()
        question_counter: Counter[str] = Counter()
        keyword_counter: Counter[str] = Counter()
        tag_counter: Counter[str] = Counter()
        daily_session_ids: dict[date, set[str]] = defaultdict(set)
        daily_message_count: Counter[date] = Counter()
        daily_latency_values: dict[date, list[float]] = defaultdict(list)
        daily_emotion_counts: dict[date, Counter[str]] = defaultdict(Counter)

        for message, session_obj in rows:
            message_day = message.created_at.date()
            session_ids.add(session_obj.id)
            daily_session_ids[message_day].add(session_obj.id)
            daily_message_count[message_day] += 1
            if session_obj.interest_tags:
                tag_counter.update([str(tag).strip() for tag in session_obj.interest_tags if str(tag).strip()])

            if message.role == "user":
                user_message_count += 1
                question = self._normalize_question(message.content)
                if question:
                    question_counter.update([question])
                keyword_counter.update(self._extract_keywords(message.content))
                continue

            if message.role == "assistant":
                assistant_message_count += 1
                emotion = (message.emotion or "neutral").strip().lower() or "neutral"
                emotion_counts.update([emotion])
                daily_emotion_counts[message_day].update([emotion])
                if message.latency_ms is not None:
                    latency = float(message.latency_ms)
                    latencies.append(latency)
                    daily_latency_values[message_day].append(latency)

        avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else None
        overall_sentiment = self._sentiment_from_emotions(dict(emotion_counts))
        avg_satisfaction = self._satisfaction_score(dict(emotion_counts))

        service_trend: list[DashboardServiceTrendPoint] = []
        satisfaction_trend: list[DashboardTrendPoint] = []
        for day in self._iter_days(start_at.date(), end_at.date() - timedelta(days=1)):
            values = daily_latency_values.get(day, [])
            service_trend.append(
                DashboardServiceTrendPoint(
                    date=day,
                    service_count=len(daily_session_ids.get(day, set())),
                )
            )
            satisfaction_trend.append(
                DashboardTrendPoint(
                    date=day,
                    session_count=len(daily_session_ids.get(day, set())),
                    message_count=int(daily_message_count.get(day, 0)),
                    avg_latency_ms=round(sum(values) / len(values), 1) if values else None,
                    score=self._satisfaction_score(dict(daily_emotion_counts.get(day, Counter()))),
                )
            )
        emotion_trend = [
            _EmotionTrendRow(
                date=day,
                happy_ratio=self._emotion_ratio(dict(daily_emotion_counts.get(day, Counter())), {"happy", "excited"}),
                neutral_ratio=self._emotion_ratio(dict(daily_emotion_counts.get(day, Counter())), {"neutral", "thinking"}),
                negative_ratio=self._emotion_ratio(dict(daily_emotion_counts.get(day, Counter())), {"sad"}),
                total=sum(daily_emotion_counts.get(day, Counter()).values()),
                score=self._satisfaction_score(dict(daily_emotion_counts.get(day, Counter()))),
            )
            for day in self._iter_days(start_at.date(), end_at.date() - timedelta(days=1))
        ]

        top_questions = [
            DashboardQuestionItem(question=item, count=count)
            for item, count in question_counter.most_common(10)
        ]
        top_interest_tags = [item for item, _ in tag_counter.most_common(8)]
        top_keywords = [item for item, _ in keyword_counter.most_common(8)]
        keyword_cloud = self._build_keyword_cloud(keyword_counter, tag_counter)

        return {
            "session_count": len(session_ids),
            "message_count": len(rows),
            "user_message_count": user_message_count,
            "assistant_message_count": assistant_message_count,
            "avg_latency_ms": avg_latency_ms,
            "emotion_counts": dict(emotion_counts),
            "overall_sentiment": overall_sentiment,
            "avg_satisfaction": avg_satisfaction,
            "top_questions": top_questions,
            "top_interest_tags": top_interest_tags,
            "top_keywords": top_keywords,
            "keyword_cloud": keyword_cloud,
            "service_trend": service_trend,
            "satisfaction_trend": satisfaction_trend,
            "emotion_trend": emotion_trend,
        }

    def _iter_days(self, start: date, end: date):
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    def _normalize_question(self, text: str) -> str:
        cleaned = re.sub(r"\s+", "", str(text).strip())
        cleaned = QUESTION_PREFIX_RE.sub("", cleaned)
        cleaned = TRAILING_PARTICLES_RE.sub("", cleaned)
        cleaned = cleaned.strip("呢吧呀嘛么啊哦")
        if len(cleaned) > 24:
            cleaned = cleaned[:24]
        return cleaned

    def _extract_keywords(self, text: str) -> list[str]:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", str(text).lower())
        results: list[str] = []
        for segment in normalized.split():
            candidate = QUESTION_PREFIX_RE.sub("", segment)
            candidate = candidate.strip().strip("。！？!?；;,.，、")
            if len(candidate) < 2:
                continue
            if candidate in STOP_WORDS:
                continue
            results.append(candidate[:16])
        return results[:4]

    def _build_keyword_cloud(
        self,
        keyword_counter: Counter[str],
        tag_counter: Counter[str],
    ) -> list[DashboardKeywordCloudItem]:
        merged: dict[str, tuple[int, str]] = {}
        for word, count in keyword_counter.items():
            merged[word] = (int(count), "question")
        for word, count in tag_counter.items():
            if word in merged:
                existing_count, _ = merged[word]
                merged[word] = (existing_count + int(count), "mixed")
                continue
            merged[word] = (int(count), "tag")

        ranked = sorted(merged.items(), key=lambda item: (-item[1][0], item[0]))[:18]
        if not ranked:
            return []

        max_count = max(count for _, (count, _) in ranked) or 1
        return [
            DashboardKeywordCloudItem(
                word=word,
                count=count,
                weight=round(0.85 + (count / max_count) * 0.75, 2),
                source=source,
            )
            for word, (count, source) in ranked
        ]

    def _emotion_ratio(self, emotion_counts: dict[str, int], keys: set[str]) -> float:
        total = sum(int(value) for value in emotion_counts.values())
        if total == 0:
            return 0.0
        selected = sum(int(emotion_counts.get(key, 0)) for key in keys)
        return round(selected / total, 4)

    def _satisfaction_score(self, emotion_counts: dict[str, int]) -> float | None:
        total = sum(int(value) for value in emotion_counts.values())
        if total == 0:
            return None
        weighted = 0.0
        for emotion, count in emotion_counts.items():
            weighted += EMOTION_SCORE.get(emotion, 3.4) * int(count)
        return round(weighted / total, 2)

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

    def _build_summary_text(
        self,
        *,
        date_from: date,
        date_to: date,
        session_count: int,
        message_count: int,
        avg_latency_ms: float | None,
        top_questions: list[DashboardQuestionItem],
        top_interest_tags: list[str],
        overall_sentiment: str,
    ) -> str:
        fragments = [
            f"{date_from.isoformat()} 至 {date_to.isoformat()} 共 {session_count} 个会话、{message_count} 条消息。",
        ]
        if avg_latency_ms is not None:
            fragments.append(f"平均响应 {avg_latency_ms:.1f} ms。")
        if top_questions:
            fragments.append(f"最常见问题是“{top_questions[0].question}”。")
        if top_interest_tags:
            fragments.append(f"关注点集中在 { '、'.join(top_interest_tags[:3]) }。")
        if overall_sentiment == "positive":
            fragments.append("整体交流偏积极。")
        elif overall_sentiment == "negative":
            fragments.append("当前情绪偏保守，需要继续关注。")
        else:
            fragments.append("整体情绪较平稳。")
        return "".join(fragments)


@lru_cache
def get_dashboard_service() -> DashboardService:
    from app.db.session import AsyncSessionFactory

    return DashboardService(AsyncSessionFactory, get_settings())


@dataclass(slots=True)
class _EmotionTrendRow:
    date: date
    happy_ratio: float
    neutral_ratio: float
    negative_ratio: float
    total: int
    score: float | None
