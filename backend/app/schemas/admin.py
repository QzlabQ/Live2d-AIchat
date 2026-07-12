from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminMeResponse(BaseModel):
    username: str


class KnowledgeUploadResponse(BaseModel):
    doc_id: str
    status: str
    message: str


class Live2DModelOption(BaseModel):
    path: str
    label: str


class Live2DModelListResponse(BaseModel):
    items: list[Live2DModelOption]


class VoiceProfileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    source_filename: str
    audio_path: str
    reference_text: str
    duration_ms: int
    mime_type: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class VoiceProfileListResponse(BaseModel):
    items: list[VoiceProfileItem]


class VoiceProfileUploadResponse(BaseModel):
    item: VoiceProfileItem
    message: str = "音色资源已上传。"
