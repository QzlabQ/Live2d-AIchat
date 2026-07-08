from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session
from app.db.session import get_db
from app.schemas.visitor import VisitorRecommendationRequest, VisitorRecommendationResponse
from app.services.recommendations import (
    RecommendationRequest,
    VisitorRecommendationService,
    get_visitor_recommendation_service,
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
