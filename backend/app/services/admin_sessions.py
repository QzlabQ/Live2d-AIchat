from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session


@dataclass(slots=True)
class AdminSessionSummary:
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    last_message_preview: str


@dataclass(slots=True)
class AdminSessionMessage:
    id: int
    role: str
    content: str
    created_at: datetime
    emotion: str | None
    latency_ms: int | None


@dataclass(slots=True)
class AdminSessionDetail:
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    items: list[AdminSessionMessage]


async def list_admin_sessions(db: AsyncSession, limit: int = 50) -> list[AdminSessionSummary]:
    stmt = (
        select(
            Session,
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .outerjoin(Message, Message.session_id == Session.id)
        .group_by(Session.id)
        .order_by(
            desc(func.coalesce(func.max(Message.created_at), Session.updated_at)),
            Session.updated_at.desc(),
            Session.id.desc(),
        )
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    items: list[AdminSessionSummary] = []
    for session_obj, message_count, last_message_at in rows:
        preview_stmt = (
            select(Message.content)
            .where(Message.session_id == session_obj.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        preview = (await db.execute(preview_stmt)).scalar_one_or_none() or ""
        activity_at = last_message_at or session_obj.updated_at
        items.append(
            AdminSessionSummary(
                session_id=session_obj.id,
                created_at=session_obj.created_at,
                updated_at=activity_at,
                device_type=session_obj.device_type,
                interest_tags=list(session_obj.interest_tags),
                message_count=int(message_count or 0),
                last_message_preview=preview,
            )
        )
    return items


async def load_admin_session_detail(db: AsyncSession, session_id: str) -> AdminSessionDetail | None:
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        return None

    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    messages = list((await db.execute(stmt)).scalars())
    updated_at = messages[-1].created_at if messages else session_obj.updated_at
    return AdminSessionDetail(
        session_id=session_obj.id,
        created_at=session_obj.created_at,
        updated_at=updated_at,
        device_type=session_obj.device_type,
        interest_tags=list(session_obj.interest_tags),
        message_count=len(messages),
        items=[
            AdminSessionMessage(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                emotion=message.emotion,
                latency_ms=message.latency_ms,
            )
            for message in messages
        ],
    )
