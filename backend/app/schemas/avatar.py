from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AvatarConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_path: str
    voice_id: str
    persona: str
    updated_at: datetime


class AvatarConfigUpdate(BaseModel):
    model_path: str | None = None
    voice_id: str | None = None
    persona: str | None = None


class MessageResponse(BaseModel):
    message: str
