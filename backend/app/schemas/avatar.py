from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AvatarConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    is_active: bool
    model_path: str
    voice_id: str
    voice_profile_id: str | None
    response_language: Literal["zh", "en"]
    persona: str
    tts_reference_audio_path: str
    tts_reference_text: str
    tts_speed: float
    tts_emotion_enabled: bool
    created_at: datetime
    updated_at: datetime


class AvatarConfigUpdate(BaseModel):
    name: str | None = None
    model_path: str | None = None
    voice_id: str | None = None
    voice_profile_id: str | None = None
    response_language: Literal["zh", "en"] | None = None
    persona: str | None = None
    tts_reference_audio_path: str | None = None
    tts_reference_text: str | None = None
    tts_speed: float | None = Field(default=None, ge=0.5, le=1.5)
    tts_emotion_enabled: bool | None = None


class MessageResponse(BaseModel):
    message: str


class AvatarProfileSummary(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    model_path: str
    voice_id: str
    response_language: Literal["zh", "en"]
    updated_at: datetime


class AvatarProfileListResponse(BaseModel):
    items: list[AvatarProfileSummary]


class AvatarProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    model_path: str
    voice_id: str
    response_language: Literal["zh", "en"]
    voice_profile_id: str | None = None
    persona: str
    tts_reference_audio_path: str
    tts_reference_text: str
    tts_speed: float = Field(default=1.0, ge=0.5, le=1.5)
    tts_emotion_enabled: bool = True
    activate: bool = True
