from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session


@dataclass(slots=True)
class VisitorSessionSummary:
    session_id: str
    created_at: datetime
    updated_at: datetime
    interest_tags: list[str]
    message_count: int
    last_message_preview: str


@dataclass(slots=True)
class VisitorSessionMessage:
    id: int
    role: str
    content: str
    created_at: datetime


async def list_visitor_sessions(db: AsyncSession, limit: int = 20) -> list[VisitorSessionSummary]:
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
    summaries: list[VisitorSessionSummary] = []
    for session_obj, message_count, last_message_at in rows:
        preview_stmt = (
            select(Message.content)
            .where(Message.session_id == session_obj.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        preview = (await db.execute(preview_stmt)).scalar_one_or_none() or ""
        activity_at = last_message_at or session_obj.updated_at
        summaries.append(
            VisitorSessionSummary(
                session_id=session_obj.id,
                created_at=session_obj.created_at,
                updated_at=activity_at,
                interest_tags=list(session_obj.interest_tags),
                message_count=int(message_count or 0),
                last_message_preview=preview,
            )
        )
    return summaries


async def load_session_messages(db: AsyncSession, session_id: str) -> list[VisitorSessionMessage]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    messages = list((await db.execute(stmt)).scalars())
    return [
        VisitorSessionMessage(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]


async def save_session_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    emotion: str | None = None,
    latency_ms: int | None = None,
) -> Message:
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        raise ValueError(f"Session not found: {session_id}")

    activity_at = datetime.now(timezone.utc)
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        created_at=activity_at,
        emotion=emotion,
        latency_ms=latency_ms,
    )
    db.add(message)
    session_obj.updated_at = activity_at
    await db.commit()
    await db.refresh(message)
    return message


async def update_session_interest_tags(
    db: AsyncSession,
    session_id: str,
    interest_tags: list[str],
) -> Session | None:
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        return None

    session_obj.interest_tags = list(interest_tags)
    session_obj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session_obj)
    return session_obj
