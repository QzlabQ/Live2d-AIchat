from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.dashboard import DashboardEmotionResponse, DashboardOverviewResponse
from app.services.admin_auth import require_admin_auth
from app.services.dashboard import get_dashboard_service

router = APIRouter(prefix="/admin/dashboard", dependencies=[Depends(require_admin_auth)])


@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    period: str = Query(default="today", pattern="^(today|week|month)$"),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewResponse:
    overview = await get_dashboard_service().build_overview(db, period=period)
    return DashboardOverviewResponse(
        period=overview.period,
        date_from=overview.date_from,
        date_to=overview.date_to,
        service_count=overview.service_count,
        session_count=overview.session_count,
        message_count=overview.message_count,
        user_message_count=overview.user_message_count,
        assistant_message_count=overview.assistant_message_count,
        realtime_online_count=overview.realtime_online_count,
        avg_satisfaction=overview.avg_satisfaction,
        avg_latency_ms=overview.avg_latency_ms,
        overall_sentiment=overview.overall_sentiment,
        top_questions=[
            {"question": item.question, "count": item.count}
            for item in overview.top_questions
        ],
        service_trend=[
            {
                "date": item.date,
                "service_count": item.service_count,
            }
            for item in overview.service_trend
        ],
        satisfaction_trend=[
            {
                "date": item.date,
                "session_count": item.session_count,
                "message_count": item.message_count,
                "avg_latency_ms": item.avg_latency_ms,
                "score": item.score,
            }
            for item in overview.satisfaction_trend
        ],
        top_interest_tags=overview.top_interest_tags,
        top_keywords=overview.top_keywords,
        keyword_cloud=[
            {
                "word": item.word,
                "count": item.count,
                "weight": item.weight,
                "source": item.source,
            }
            for item in overview.keyword_cloud
        ],
        emotion_counts=overview.emotion_counts,
        summary_text=overview.summary_text,
    )


@router.get("/emotion", response_model=DashboardEmotionResponse)
async def get_dashboard_emotion(
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> DashboardEmotionResponse:
    target_end = end or datetime.now().date()
    target_start = start or (target_end - timedelta(days=6))
    summary = await get_dashboard_service().build_emotion_summary(
        db,
        date_from=target_start,
        date_to=target_end,
    )
    return DashboardEmotionResponse(
        date_from=summary.date_from,
        date_to=summary.date_to,
        overall_sentiment=summary.overall_sentiment,
        emotion_counts=summary.emotion_counts,
        trend=[
            {
                "date": item.date,
                "happy": item.happy,
                "neutral": item.neutral,
                "negative": item.negative,
                "total": item.total,
                "score": item.score,
            }
            for item in summary.trend
        ],
        summary_text=summary.summary_text,
    )
