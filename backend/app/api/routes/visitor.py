from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AvatarConfig, Session
from app.db.session import get_db
from app.schemas.visitor import (
    VisitorAvatarProfileListResponse,
    VisitorAvatarProfileSummary,
    VisionRecognitionResponse,
    VisitorRecommendationRequest,
    VisitorRecommendationResponse,
)
from app.services.recommendations import (
    RecommendationRequest,
    VisitorRecommendationService,
    get_visitor_recommendation_service,
)
from app.services.vision import (
    VisitorVisionError,
    VisitorVisionPayloadTooLargeError,
    VisitorVisionService,
    get_visitor_vision_service,
)

router = APIRouter(prefix="/sessions")


def serialize_avatar_profile(profile: AvatarConfig) -> VisitorAvatarProfileSummary:
    return VisitorAvatarProfileSummary(
        id=profile.id,
        name=profile.name,
        slug=profile.slug,
        is_active=profile.is_active,
        model_path=profile.model_path,
        display_scale=profile.display_scale,
        display_offset_x=profile.display_offset_x,
        display_offset_y=profile.display_offset_y,
        stage_height=profile.stage_height,
        updated_at=profile.updated_at,
    )


async def fetch_avatar_profile(db: AsyncSession, profile_id: int) -> AvatarConfig:
    profile = await db.get(AvatarConfig, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar profile not found.")
    return profile


async def set_active_avatar_profile(db: AsyncSession, profile_id: int) -> AvatarConfig:
    profile = await fetch_avatar_profile(db, profile_id)
    profiles = list((await db.execute(select(AvatarConfig))).scalars())
    for item in profiles:
        item.is_active = item.id == profile.id
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/avatar/profiles", response_model=VisitorAvatarProfileListResponse)
async def list_public_avatar_profiles(
    db: AsyncSession = Depends(get_db),
) -> VisitorAvatarProfileListResponse:
    items = list(
        (
            await db.execute(
                select(AvatarConfig).order_by(
                    AvatarConfig.is_active.desc(),
                    AvatarConfig.updated_at.desc(),
                    AvatarConfig.id.desc(),
                )
            )
        ).scalars()
    )
    return VisitorAvatarProfileListResponse(items=[serialize_avatar_profile(item) for item in items])


@router.post("/avatar/profiles/{profile_id}/activate", response_model=VisitorAvatarProfileSummary)
async def activate_public_avatar_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
) -> VisitorAvatarProfileSummary:
    profile = await set_active_avatar_profile(db, profile_id)
    return serialize_avatar_profile(profile)


@router.post("/{session_id}/recommendations", response_model=VisitorRecommendationResponse)
async def create_session_recommendations(
    session_id: str,
    payload: VisitorRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    service: VisitorRecommendationService = Depends(get_visitor_recommendation_service),
) -> VisitorRecommendationResponse:
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    result = await service.recommend(
        RecommendationRequest(
            session_id=session_id,
            interest_tags=list(payload.interest_tags),
            visitor_profile=payload.visitor_profile,
            device_type=session_obj.device_type,
        )
    )
    return VisitorRecommendationResponse(
        route_title=result.route_title,
        intro=result.intro,
        highlights=result.highlights,
        suggested_questions=result.suggested_questions,
        applied_interest_tags=result.applied_interest_tags,
    )


@router.post("/{session_id}/vision/recognize", response_model=VisionRecognitionResponse)
async def recognize_session_vision(
    session_id: str,
    file: UploadFile = File(...),
    interest_tags: str | None = Form(default=None),
    user_prompt: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    service: VisitorVisionService = Depends(get_visitor_vision_service),
) -> VisionRecognitionResponse:
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    try:
        parsed_interest_tags = _parse_interest_tags(interest_tags, fallback=session_obj.interest_tags)
        data = await _read_upload_limited(file, max_bytes=get_settings().visitor_image_max_bytes)
        result = await service.recognize(
            session_id=session_id,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            data=data,
            interest_tags=parsed_interest_tags,
            user_prompt=user_prompt,
        )
    except VisitorVisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        await file.close()

    return VisionRecognitionResponse(
        recognized_spot=result.recognized_spot,
        recognition_summary=result.recognition_summary,
        resolved_question=result.resolved_question,
        stored_image_path=result.stored_image_path,
    )


def _parse_interest_tags(raw_value: str | None, fallback: list[str]) -> list[str]:
    if raw_value is None or not raw_value.strip():
        return list(fallback)

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="interest_tags must be a JSON array string.",
        ) from exc

    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="interest_tags must be a JSON array string.",
        )

    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="interest_tags must be a JSON array of non-empty strings.",
        )

    normalized: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="interest_tags must be a JSON array of non-empty strings.",
            )
        cleaned = " ".join(item.strip().split())
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="interest_tags must be a JSON array of non-empty strings.",
            )
        normalized.append(cleaned)
    return normalized


async def _read_upload_limited(file: UploadFile, max_bytes: int, chunk_size: int = 64 * 1024) -> bytes:
    buffer = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise VisitorVisionPayloadTooLargeError("Image file exceeds the configured size limit.")
    return bytes(buffer)
