from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateRequest(BaseModel):
    interest_tags: list[str] = Field(default_factory=list)
    device_type: Literal["mobile", "kiosk"] = "mobile"


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    interest_tags: list[str]
    device_type: str


class SessionInterestTagsUpdate(BaseModel):
    interest_tags: list[str] = Field(default_factory=list)


class VisitorSessionSummaryResponse(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    interest_tags: list[str]
    message_count: int
    last_message_preview: str


class VisitorSessionListResponse(BaseModel):
    items: list[VisitorSessionSummaryResponse]


class VisitorSessionMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class VisitorSessionMessageListResponse(BaseModel):
    items: list[VisitorSessionMessageResponse]
