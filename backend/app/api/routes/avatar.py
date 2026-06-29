from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AvatarConfig
from app.db.session import get_db
from app.schemas.avatar import AvatarConfigResponse, AvatarConfigUpdate, MessageResponse

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

    await db.commit()
    await db.refresh(avatar)
    return MessageResponse(message="配置已更新")
