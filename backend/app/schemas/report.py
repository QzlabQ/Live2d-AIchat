from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DailyEmotionReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_date: date
    status: str
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
    generated_at: datetime
    updated_at: datetime


class DailyEmotionReportListResponse(BaseModel):
    items: list[DailyEmotionReportResponse]


class ReportRangeSummaryResponse(BaseModel):
    date_from: date
    date_to: date
    report_count: int
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
