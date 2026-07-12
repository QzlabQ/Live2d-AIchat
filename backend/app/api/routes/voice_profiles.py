from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AvatarConfig, VoiceProfile
from app.db.session import get_db
from app.schemas.admin import VoiceProfileItem, VoiceProfileListResponse, VoiceProfileUploadResponse
from app.schemas.avatar import MessageResponse
from app.services.admin_auth import require_admin_auth
from app.services.voice_profiles import (
    build_voice_profile_storage_path,
    read_upload_limited,
    validate_voice_profile_audio,
)

router = APIRouter(prefix="/admin/voice-profiles", dependencies=[Depends(require_admin_auth)])
settings = get_settings()


def serialize_voice_profile(profile: VoiceProfile) -> VoiceProfileItem:
    return VoiceProfileItem.model_validate(profile)


@router.get("", response_model=VoiceProfileListResponse)
async def list_voice_profiles(db: AsyncSession = Depends(get_db)) -> VoiceProfileListResponse:
    items = list((await db.execute(select(VoiceProfile).order_by(VoiceProfile.updated_at.desc()))).scalars())
    return VoiceProfileListResponse(items=[serialize_voice_profile(item) for item in items])


@router.post("", response_model=VoiceProfileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_voice_profile(
    file: UploadFile = File(...),
    name: str = Form(...),
    reference_text: str = Form(...),
    description: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> VoiceProfileUploadResponse:
    filename = Path(file.filename or "voice.wav").name
    if not name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="音色名称不能为空。")
    if not reference_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="参考文本不能为空。")

    try:
        payload = await read_upload_limited(file, settings.admin_voice_max_bytes)
    finally:
        await file.close()

    _, duration_ms, mime_type = validate_voice_profile_audio(filename, payload)
    profile_id = str(uuid4())
    stored_path = build_voice_profile_storage_path(settings, profile_id, filename)
    stored_path.write_bytes(payload)

    profile = VoiceProfile(
        id=profile_id,
        name=name.strip(),
        description=description.strip(),
        source_filename=filename,
        audio_path=str(stored_path),
        reference_text=reference_text.strip(),
        duration_ms=duration_ms,
        mime_type=mime_type,
        is_default=False,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return VoiceProfileUploadResponse(item=serialize_voice_profile(profile))


@router.get("/{profile_id}/audio")
async def get_voice_profile_audio(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    profile = await db.get(VoiceProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")

    audio_path = Path(profile.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile audio not found.")
    return FileResponse(path=audio_path, media_type=profile.mime_type, filename=profile.source_filename)


@router.delete("/{profile_id}", response_model=MessageResponse)
async def delete_voice_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    profile = await db.get(VoiceProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")

    linked_avatar = (
        await db.execute(select(AvatarConfig).where(AvatarConfig.voice_profile_id == profile_id).limit(1))
    ).scalar_one_or_none()
    if linked_avatar is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前音色仍被数字人档案使用，无法删除。",
        )

    audio_path = Path(profile.audio_path)
    if audio_path.exists() and audio_path.is_file():
        audio_path.unlink()
    await db.delete(profile)
    await db.commit()
    return MessageResponse(message="音色资源已删除。")
