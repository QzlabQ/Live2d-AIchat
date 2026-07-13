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
    display_scale: float
    display_offset_x: float
    display_offset_y: float
    stage_height: int
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
    display_scale: float | None = Field(default=None, ge=0.6, le=1.8)
    display_offset_x: float | None = Field(default=None, ge=-0.5, le=0.5)
    display_offset_y: float | None = Field(default=None, ge=-0.5, le=0.5)
    stage_height: int | None = Field(default=None, ge=320, le=760)


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
    display_scale: float
    display_offset_x: float
    display_offset_y: float
    stage_height: int
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
    display_scale: float = Field(default=1.0, ge=0.6, le=1.8)
    display_offset_x: float = Field(default=0.0, ge=-0.5, le=0.5)
    display_offset_y: float = Field(default=0.0, ge=-0.5, le=0.5)
    stage_height: int = Field(default=420, ge=320, le=760)
    activate: bool = True
