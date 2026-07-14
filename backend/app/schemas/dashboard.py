from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DashboardQuestionItem(BaseModel):
    question: str
    count: int


class DashboardTrendPoint(BaseModel):
    date: date
    session_count: int
    message_count: int
    avg_latency_ms: float | None
    score: float | None


class DashboardServiceTrendPoint(BaseModel):
    date: date
    service_count: int


class DashboardKeywordCloudItem(BaseModel):
    word: str
    count: int
    weight: float
    source: str


class DashboardEmotionPoint(BaseModel):
    date: date
    happy: float
    neutral: float
    negative: float
    total: int
    score: float | None


class DashboardOverviewResponse(BaseModel):
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


class DashboardEmotionResponse(BaseModel):
    date_from: date
    date_to: date
    overall_sentiment: str
    emotion_counts: dict[str, int]
    trend: list[DashboardEmotionPoint]
    summary_text: str
