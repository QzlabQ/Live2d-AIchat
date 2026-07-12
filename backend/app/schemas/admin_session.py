from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AdminSessionSummaryResponse(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    last_message_preview: str


class AdminSessionListResponse(BaseModel):
    items: list[AdminSessionSummaryResponse]


class AdminSessionMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    emotion: str | None = None
    latency_ms: int | None = None


class AdminSessionDetailResponse(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    items: list[AdminSessionMessageResponse]
