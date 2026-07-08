from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Session
from app.db.session import get_db
from app.schemas.visitor import (
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
