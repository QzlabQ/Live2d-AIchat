from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AvatarConfig
from app.db.session import get_db
from app.schemas.avatar import AvatarConfigResponse, AvatarConfigUpdate, MessageResponse

BACKEND_ROOT = Path(__file__).resolve().parents[3]

router = APIRouter(prefix="/admin/avatar")


async def fetch_avatar_config(db: AsyncSession) -> AvatarConfig:
    result = await db.execute(select(AvatarConfig).limit(1))
    avatar = result.scalar_one_or_none()
    if avatar is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avatar configuration is not initialized.",
        )
    return avatar


def validate_reference_audio_path(value: str) -> str:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = BACKEND_ROOT / candidate
    resolved = candidate.resolve()
    root = BACKEND_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='TTS reference audio must be inside the backend workspace.',
        )
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='TTS reference audio file does not exist.',
        )
    return str(resolved)


@router.get("/config", response_model=AvatarConfigResponse)
async def get_avatar_config(db: AsyncSession = Depends(get_db)) -> AvatarConfig:
    return await fetch_avatar_config(db)


@router.put("/config", response_model=MessageResponse)
async def update_avatar_config(
    payload: AvatarConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    avatar = await fetch_avatar_config(db)

    if payload.model_path is not None:
        avatar.model_path = payload.model_path
    if payload.voice_id is not None:
        avatar.voice_id = payload.voice_id
    if payload.persona is not None:
        avatar.persona = payload.persona
    if payload.tts_reference_audio_path is not None:
        avatar.tts_reference_audio_path = validate_reference_audio_path(payload.tts_reference_audio_path)
    if payload.tts_reference_text is not None:
        avatar.tts_reference_text = payload.tts_reference_text
    if payload.tts_speed is not None:
        avatar.tts_speed = payload.tts_speed
    if payload.tts_emotion_enabled is not None:
        avatar.tts_emotion_enabled = payload.tts_emotion_enabled

    await db.commit()
    await db.refresh(avatar)
    return MessageResponse(message="配置已更新")
