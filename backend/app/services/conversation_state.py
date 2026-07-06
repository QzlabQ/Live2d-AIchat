from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationState, Message


@dataclass(slots=True)
class ConversationStateSnapshot:
    id: int
    session_id: str
    state_type: str
    status: str
    original_question: str
    assistant_followup_question: str
    missing_slots: list[str]
    provisional_answer: str
    used_source_indexes: list[int]
    created_at: datetime | None
    updated_at: datetime | None
    resolved_at: datetime | None
    expires_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_snapshot(model: ConversationState) -> ConversationStateSnapshot:
    return ConversationStateSnapshot(
        id=model.id,
        session_id=model.session_id,
        state_type=model.state_type,
        status=model.status,
        original_question=model.original_question,
        assistant_followup_question=model.assistant_followup_question,
        missing_slots=list(model.missing_slots or []),
        provisional_answer=model.provisional_answer,
        used_source_indexes=list(model.used_source_indexes or []),
        created_at=_normalize_datetime(model.created_at),
        updated_at=_normalize_datetime(model.updated_at),
        resolved_at=_normalize_datetime(model.resolved_at),
        expires_at=_normalize_datetime(model.expires_at),
    )


async def get_active_clarification_state(
    db: AsyncSession,
    *,
    session_id: str,
    now: datetime | None = None,
) -> ConversationStateSnapshot | None:
    current_time = now or _utc_now()
    result = await db.execute(
        select(ConversationState)
        .where(
            ConversationState.session_id == session_id,
            ConversationState.state_type == "rag_clarification",
            ConversationState.status == "pending",
        )
        .order_by(ConversationState.updated_at.desc(), ConversationState.id.desc())
        .limit(1)
    )
    state = result.scalar_one_or_none()
    if state is None:
        return None

    expires_at = _normalize_datetime(state.expires_at)
    if expires_at is not None and expires_at <= current_time:
        state.status = "expired"
        state.resolved_at = current_time
        await db.commit()
        return None

    return _to_snapshot(state)


async def upsert_clarification_state(
    db: AsyncSession,
    *,
    session_id: str,
    original_question: str,
    assistant_followup_question: str,
    missing_slots: list[str],
    provisional_answer: str,
    used_source_indexes: list[int],
    expires_in_minutes: int = 15,
    now: datetime | None = None,
) -> ConversationStateSnapshot:
    current_time = now or _utc_now()
    await cancel_pending_clarification_state(
        db,
        session_id=session_id,
        now=current_time,
        commit=False,
    )

    state = ConversationState(
        session_id=session_id,
        state_type="rag_clarification",
        status="pending",
        original_question=original_question,
        assistant_followup_question=assistant_followup_question,
        missing_slots=list(missing_slots),
        provisional_answer=provisional_answer,
        used_source_indexes=list(used_source_indexes),
        resolved_at=None,
        expires_at=current_time + timedelta(minutes=expires_in_minutes),
    )
    db.add(state)
    await db.commit()
    await db.refresh(state)
    return _to_snapshot(state)


async def cancel_pending_clarification_state(
    db: AsyncSession,
    *,
    session_id: str,
    now: datetime | None = None,
    commit: bool = True,
) -> None:
    current_time = now or _utc_now()
    result = await db.execute(
        select(ConversationState).where(
            ConversationState.session_id == session_id,
            ConversationState.state_type == "rag_clarification",
            ConversationState.status == "pending",
        )
    )
    changed = False
    for state in result.scalars():
        state.status = "cancelled"
        state.resolved_at = current_time
        changed = True
    if commit and changed:
        await db.commit()


async def resolve_pending_clarification_state(
    db: AsyncSession,
    *,
    session_id: str,
    now: datetime | None = None,
) -> None:
    current_time = now or _utc_now()
    result = await db.execute(
        select(ConversationState).where(
            ConversationState.session_id == session_id,
            ConversationState.state_type == "rag_clarification",
            ConversationState.status == "pending",
        )
    )
    changed = False
    for state in result.scalars():
        state.status = "resolved"
        state.resolved_at = current_time
        changed = True
    if changed:
        await db.commit()


async def load_recent_history(
    db: AsyncSession,
    *,
    session_id: str,
    limit: int = 6,
) -> list[dict[str, str]]:
    result = await db.execute(
        select(Message.role, Message.content)
        .where(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    rows = list(result.all())
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows if content]
