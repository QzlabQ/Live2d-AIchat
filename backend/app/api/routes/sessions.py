from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Session
from app.db.session import get_db
from app.schemas.session import SessionCreateRequest, SessionCreateResponse

router = APIRouter(prefix="/sessions")


@router.post("", response_model=SessionCreateResponse)
async def create_session(
    payload: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionCreateResponse:
    session_obj = Session(
        interest_tags=payload.interest_tags,
        device_type=payload.device_type,
    )
    db.add(session_obj)
    await db.commit()
    await db.refresh(session_obj)
    return SessionCreateResponse(session_id=session_obj.id)
