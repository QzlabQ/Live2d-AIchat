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
