from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.admin_session import (
    AdminSessionDetailResponse,
    AdminSessionListResponse,
    AdminSessionMessageResponse,
    AdminSessionSummaryResponse,
)
from app.services.admin_auth import require_admin_auth
from app.services.admin_sessions import list_admin_sessions, load_admin_session_detail

router = APIRouter(prefix="/admin/sessions", dependencies=[Depends(require_admin_auth)])


@router.get("", response_model=AdminSessionListResponse)
async def get_admin_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionListResponse:
    items = await list_admin_sessions(db, limit=limit)
    return AdminSessionListResponse(
        items=[
            AdminSessionSummaryResponse(
                session_id=item.session_id,
                created_at=item.created_at,
                updated_at=item.updated_at,
                device_type=item.device_type,
                interest_tags=item.interest_tags,
                message_count=item.message_count,
                last_message_preview=item.last_message_preview,
            )
            for item in items
        ]
    )


@router.get("/{session_id}", response_model=AdminSessionDetailResponse)
async def get_admin_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdminSessionDetailResponse:
    detail = await load_admin_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    return AdminSessionDetailResponse(
        session_id=detail.session_id,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        device_type=detail.device_type,
        interest_tags=detail.interest_tags,
        message_count=detail.message_count,
        items=[
            AdminSessionMessageResponse(
                id=item.id,
                role=item.role,
                content=item.content,
                created_at=item.created_at,
                emotion=item.emotion,
                latency_ms=item.latency_ms,
            )
            for item in detail.items
        ],
    )
