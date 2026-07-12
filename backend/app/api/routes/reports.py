from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.report import (
    DailyEmotionReportListResponse,
    DailyEmotionReportResponse,
    ReportRangeSummaryResponse,
)
from app.services.admin_auth import require_admin_auth
from app.services.reports import get_report_service

router = APIRouter(prefix="/admin/reports", dependencies=[Depends(require_admin_auth)])


@router.post("/daily/generate", response_model=DailyEmotionReportResponse)
async def generate_daily_report(
    report_date: date | None = Query(default=None),
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> DailyEmotionReportResponse:
    target_date = report_date or datetime.now().date()
    report = await get_report_service().generate_for_date_in_session(db, target_date, force=force)
    return DailyEmotionReportResponse.model_validate(report)


@router.get("/daily", response_model=DailyEmotionReportListResponse)
async def list_daily_reports(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=31, ge=1, le=366),
    db: AsyncSession = Depends(get_db),
) -> DailyEmotionReportListResponse:
    items = await get_report_service().list_reports(
        db,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return DailyEmotionReportListResponse(
        items=[DailyEmotionReportResponse.model_validate(item) for item in items]
    )


@router.get("/summary", response_model=ReportRangeSummaryResponse)
async def get_report_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ReportRangeSummaryResponse:
    target_to = date_to or datetime.now().date()
    target_from = date_from or (target_to - timedelta(days=6))
    reports = await get_report_service().list_reports(
        db,
        date_from=target_from,
        date_to=target_to,
        limit=366,
    )
    summary = await get_report_service().build_range_summary(
        db,
        date_from=target_from,
        date_to=target_to,
    )
    return ReportRangeSummaryResponse(
        date_from=target_from,
        date_to=target_to,
        report_count=len(reports),
        session_count=summary.session_count,
        message_count=summary.message_count,
        user_message_count=summary.user_message_count,
        assistant_message_count=summary.assistant_message_count,
        avg_assistant_latency_ms=summary.avg_assistant_latency_ms,
        emotion_counts=summary.emotion_counts,
        top_interest_tags=summary.top_interest_tags,
        top_keywords=summary.top_keywords,
        overall_sentiment=summary.overall_sentiment,
        summary_text=summary.summary_text,
    )
