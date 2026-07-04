from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AvatarConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_path: str
    voice_id: str
    persona: str
    tts_reference_audio_path: str
    tts_reference_text: str
    tts_speed: float
    tts_emotion_enabled: bool
    updated_at: datetime


class AvatarConfigUpdate(BaseModel):
    model_path: str | None = None
    voice_id: str | None = None
    persona: str | None = None
    tts_reference_audio_path: str | None = None
    tts_reference_text: str | None = None
    tts_speed: float | None = Field(default=None, ge=0.5, le=1.5)
    tts_emotion_enabled: bool | None = None


class MessageResponse(BaseModel):
    message: str
