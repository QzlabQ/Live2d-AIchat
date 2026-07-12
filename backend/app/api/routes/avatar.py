from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AvatarConfig, VoiceProfile
from app.db.session import get_db
from app.schemas.admin import Live2DModelListResponse, Live2DModelOption
from app.schemas.avatar import (
    AvatarConfigResponse,
    AvatarConfigUpdate,
    AvatarProfileCreate,
    AvatarProfileListResponse,
    AvatarProfileSummary,
    MessageResponse,
)
from app.services.admin_auth import require_admin_auth

BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_ROOT.parent
LIVE2D_ROOT = REPO_ROOT / "frontend" / "public" / "live2d"

router = APIRouter(prefix="/admin/avatar", dependencies=[Depends(require_admin_auth)])


def build_avatar_select(*, profile_id: int | None = None) -> Select[tuple[AvatarConfig]]:
    if profile_id is not None:
        return select(AvatarConfig).where(AvatarConfig.id == profile_id).limit(1)
    return (
        select(AvatarConfig)
        .where(AvatarConfig.is_active.is_(True))
        .order_by(AvatarConfig.updated_at.desc(), AvatarConfig.id.desc())
        .limit(1)
    )


async def fetch_avatar_config(db: AsyncSession, profile_id: int | None = None) -> AvatarConfig:
    result = await db.execute(build_avatar_select(profile_id=profile_id))
    avatar = result.scalar_one_or_none()
    if avatar is None and profile_id is None:
        avatar = (
            await db.execute(select(AvatarConfig).order_by(AvatarConfig.id.asc()).limit(1))
        ).scalar_one_or_none()
    if avatar is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if profile_id is not None else status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Avatar profile not found." if profile_id is not None else "Avatar configuration is not initialized.",
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
            detail="TTS reference audio must be inside the backend workspace.",
        )
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS reference audio file does not exist.",
        )
    return str(resolved)


def discover_live2d_models() -> list[Live2DModelOption]:
    if not LIVE2D_ROOT.exists():
        return []

    options: list[Live2DModelOption] = []
    for model_path in sorted(LIVE2D_ROOT.rglob("*.model3.json")):
        web_path = "/" + str(model_path.relative_to(REPO_ROOT / "frontend" / "public")).replace("\\", "/")
        options.append(
            Live2DModelOption(
                path=web_path,
                label=model_path.parent.name,
            )
        )
    return options


def make_slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "avatar"


async def build_unique_slug(db: AsyncSession, name: str) -> str:
    base = make_slug(name)
    slug = base
    index = 2
    while (
        await db.execute(select(AvatarConfig.id).where(AvatarConfig.slug == slug).limit(1))
    ).scalar_one_or_none() is not None:
        slug = f"{base}-{index}"
        index += 1
    return slug


async def set_active_avatar_profile(db: AsyncSession, profile_id: int) -> AvatarConfig:
    profile = await fetch_avatar_config(db, profile_id=profile_id)
    profiles = list((await db.execute(select(AvatarConfig))).scalars())
    for item in profiles:
        item.is_active = item.id == profile.id
    await db.commit()
    await db.refresh(profile)
    return profile


async def apply_avatar_payload(
    db: AsyncSession,
    avatar: AvatarConfig,
    payload: AvatarConfigUpdate | AvatarProfileCreate,
) -> None:
    provided = set(payload.model_fields_set)

    if getattr(payload, "name", None) is not None:
        avatar.name = str(payload.name).strip() or avatar.name

    if payload.model_path is not None:
        avatar.model_path = payload.model_path

    if "voice_profile_id" in provided:
        if payload.voice_profile_id:
            profile = await db.get(VoiceProfile, payload.voice_profile_id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found.")
            avatar.voice_profile_id = profile.id
            avatar.voice_id = profile.name
            avatar.tts_reference_audio_path = validate_reference_audio_path(profile.audio_path)
            avatar.tts_reference_text = profile.reference_text
        else:
            avatar.voice_profile_id = None

    manual_voice_override = False
    if payload.voice_id is not None:
        avatar.voice_id = payload.voice_id
        manual_voice_override = True
    if payload.response_language is not None:
        avatar.response_language = payload.response_language
    if payload.persona is not None:
        avatar.persona = payload.persona
    if payload.tts_reference_audio_path is not None:
        avatar.tts_reference_audio_path = validate_reference_audio_path(payload.tts_reference_audio_path)
        manual_voice_override = True
    if payload.tts_reference_text is not None:
        avatar.tts_reference_text = payload.tts_reference_text
        manual_voice_override = True
    if payload.tts_speed is not None:
        avatar.tts_speed = payload.tts_speed
    if payload.tts_emotion_enabled is not None:
        avatar.tts_emotion_enabled = payload.tts_emotion_enabled

    if manual_voice_override and "voice_profile_id" not in provided:
        avatar.voice_profile_id = None


def serialize_avatar_profile(profile: AvatarConfig) -> AvatarProfileSummary:
    return AvatarProfileSummary(
        id=profile.id,
        name=profile.name,
        slug=profile.slug,
        is_active=profile.is_active,
        model_path=profile.model_path,
        voice_id=profile.voice_id,
        response_language=profile.response_language,
        updated_at=profile.updated_at,
    )


@router.get("/models", response_model=Live2DModelListResponse)
async def list_avatar_models() -> Live2DModelListResponse:
    return Live2DModelListResponse(items=discover_live2d_models())


@router.get("/profiles", response_model=AvatarProfileListResponse)
async def list_avatar_profiles(db: AsyncSession = Depends(get_db)) -> AvatarProfileListResponse:
    items = list(
        (
            await db.execute(
                select(AvatarConfig).order_by(AvatarConfig.is_active.desc(), AvatarConfig.updated_at.desc(), AvatarConfig.id.desc())
            )
        ).scalars()
    )
    return AvatarProfileListResponse(items=[serialize_avatar_profile(item) for item in items])


@router.post("/profiles", response_model=AvatarConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_avatar_profile(
    payload: AvatarProfileCreate,
    db: AsyncSession = Depends(get_db),
) -> AvatarConfig:
    profile = AvatarConfig(
        name=payload.name.strip(),
        slug=await build_unique_slug(db, payload.name),
        is_active=False,
        model_path=payload.model_path,
        voice_id=payload.voice_id,
        voice_profile_id=None,
        response_language=payload.response_language,
        persona=payload.persona,
        tts_reference_audio_path=payload.tts_reference_audio_path,
        tts_reference_text=payload.tts_reference_text,
        tts_speed=payload.tts_speed,
        tts_emotion_enabled=payload.tts_emotion_enabled,
    )
    db.add(profile)
    await db.flush()
    await apply_avatar_payload(db, profile, payload)
    await db.commit()
    if payload.activate:
        profile = await set_active_avatar_profile(db, profile.id)
    else:
        await db.refresh(profile)
    return profile


@router.post("/profiles/{profile_id}/activate", response_model=AvatarConfigResponse)
async def activate_avatar_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
) -> AvatarConfig:
    return await set_active_avatar_profile(db, profile_id)


@router.delete("/profiles/{profile_id}", response_model=MessageResponse)
async def delete_avatar_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    profile = await fetch_avatar_config(db, profile_id=profile_id)
    profiles = list((await db.execute(select(AvatarConfig).order_by(AvatarConfig.id.asc()))).scalars())
    if len(profiles) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="At least one avatar profile must be kept.")

    was_active = profile.is_active
    await db.delete(profile)
    await db.commit()

    if was_active:
        next_profile = next((item for item in profiles if item.id != profile.id), None)
        if next_profile is not None:
            await set_active_avatar_profile(db, next_profile.id)
    return MessageResponse(message="数字人档案已删除。")


@router.get("/config", response_model=AvatarConfigResponse)
async def get_avatar_config(
    db: AsyncSession = Depends(get_db),
    profile_id: int | None = None,
) -> AvatarConfig:
    return await fetch_avatar_config(db, profile_id=profile_id)


@router.put("/config", response_model=MessageResponse)
async def update_avatar_config(
    payload: AvatarConfigUpdate,
    profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    avatar = await fetch_avatar_config(db, profile_id=profile_id)
    await apply_avatar_payload(db, avatar, payload)
    await db.commit()
    await db.refresh(avatar)
    return MessageResponse(message="数字人配置已更新。")
