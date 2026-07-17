from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session
from app.db.session import get_db
from app.schemas.session import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionInterestTagsUpdate,
    VisitorSessionListResponse,
    VisitorSessionMessageListResponse,
    VisitorSessionMessageResponse,
    VisitorSessionSummaryResponse,
)
from app.services.visitor_sessions import (
    list_visitor_sessions,
    load_session_messages,
    update_session_interest_tags as update_session_interest_tags_service,
)

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


@router.get("", response_model=VisitorSessionListResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> VisitorSessionListResponse:
    items = await list_visitor_sessions(db, limit=limit)
    return VisitorSessionListResponse(
        items=[
            VisitorSessionSummaryResponse(
                session_id=item.session_id,
                created_at=item.created_at,
                updated_at=item.updated_at,
                interest_tags=item.interest_tags,
                message_count=item.message_count,
                last_message_preview=item.last_message_preview,
            )
            for item in items
        ]
    )


@router.get("/{session_id}/messages", response_model=VisitorSessionMessageListResponse)
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> VisitorSessionMessageListResponse:
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    items = await load_session_messages(db, session_id)
    return VisitorSessionMessageListResponse(
        items=[
            VisitorSessionMessageResponse(
                id=item.id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
                attachments=item.attachments,
            )
            for item in items
        ]
    )


@router.patch("/{session_id}", response_model=VisitorSessionSummaryResponse)
async def update_session_interest_tags(
    session_id: str,
    payload: SessionInterestTagsUpdate,
    db: AsyncSession = Depends(get_db),
) -> VisitorSessionSummaryResponse:
    session_obj = await update_session_interest_tags_service(db, session_id, payload.interest_tags)
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    messages = list(
        (
            await db.execute(
                select(Message)
                .where(Message.session_id == session_obj.id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        ).scalars()
    )
    message_count = len(messages)
    last_message_preview = messages[-1].content if messages else ""
    return VisitorSessionSummaryResponse(
        session_id=session_obj.id,
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at,
        interest_tags=list(session_obj.interest_tags),
        message_count=message_count,
        last_message_preview=last_message_preview,
    )
