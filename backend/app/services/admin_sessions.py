from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session
from app.services.avatar_trace import _DEFAULT_LOG_PATH


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
class AdminReplyTrace:
    reply_id: str
    created_at: datetime
    streaming: bool
    chat_mode: str
    tts_engine: str
    tts_stream_profile: str | None
    prompt_cache_hit: bool | None
    prompt_cache_build_ms: float | None
    torch_cuda_available: bool | None
    torch_device_name: str | None
    requested_onnx_provider: str | None
    audio_chunk_count: int
    segment_count: int
    max_chunk_gap_ms: int
    metrics: dict[str, int]


@dataclass(slots=True)
class AdminReplyTraceSummary:
    trace_count: int
    latest_created_at: datetime | None
    avg_metrics: dict[str, float]
    max_metrics: dict[str, int]


@dataclass(slots=True)
class AdminSessionDetail:
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    items: list[AdminSessionMessage]
    reply_traces: list[AdminReplyTrace]
    reply_trace_summary: AdminReplyTraceSummary


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
    reply_traces = load_recent_reply_traces(session_id)
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
        reply_traces=reply_traces,
        reply_trace_summary=build_reply_trace_summary(reply_traces),
    )


def load_recent_reply_traces(
    session_id: str,
    *,
    limit: int = 12,
    log_path: Path | str | None = None,
) -> list[AdminReplyTrace]:
    target_path = Path(log_path or _DEFAULT_LOG_PATH)
    if limit <= 0 or not target_path.exists():
        return []

    matches: list[AdminReplyTrace] = []
    with target_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict) or str(payload.get("session_id", "")) != session_id:
                continue
            trace = _parse_reply_trace(payload)
            if trace is None:
                continue
            matches.append(trace)

    matches.sort(key=lambda item: item.created_at, reverse=True)
    return matches[:limit]


def build_reply_trace_summary(traces: list[AdminReplyTrace]) -> AdminReplyTraceSummary:
    if not traces:
        return AdminReplyTraceSummary(
            trace_count=0,
            latest_created_at=None,
            avg_metrics={},
            max_metrics={},
        )

    metric_values: dict[str, list[int]] = {}
    for trace in traces:
        for key, value in trace.metrics.items():
            metric_values.setdefault(key, []).append(int(value))

    avg_metrics = {
        key: round(sum(values) / len(values), 1)
        for key, values in metric_values.items()
        if values
    }
    max_metrics = {key: max(values) for key, values in metric_values.items() if values}

    return AdminReplyTraceSummary(
        trace_count=len(traces),
        latest_created_at=max(trace.created_at for trace in traces),
        avg_metrics=avg_metrics,
        max_metrics=max_metrics,
    )


def _parse_reply_trace(payload: dict[str, Any]) -> AdminReplyTrace | None:
    created_at_raw = payload.get("created_at")
    reply_id = str(payload.get("reply_id", "")).strip()
    if not reply_id or not isinstance(created_at_raw, str):
        return None

    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError:
        return None

    raw_metrics = payload.get("metrics")
    metrics: dict[str, int] = {}
    if isinstance(raw_metrics, dict):
        for key, value in raw_metrics.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                metrics[key] = int(value)

    return AdminReplyTrace(
        reply_id=reply_id,
        created_at=created_at,
        streaming=bool(payload.get("streaming")),
        chat_mode=str(payload.get("chat_mode", "")),
        tts_engine=str(payload.get("tts_engine", "")),
        tts_stream_profile=_as_optional_str(payload.get("tts_stream_profile")),
        prompt_cache_hit=payload.get("prompt_cache_hit") if isinstance(payload.get("prompt_cache_hit"), bool) else None,
        prompt_cache_build_ms=float(payload["prompt_cache_build_ms"])
        if isinstance(payload.get("prompt_cache_build_ms"), (int, float))
        else None,
        torch_cuda_available=payload.get("torch_cuda_available")
        if isinstance(payload.get("torch_cuda_available"), bool)
        else None,
        torch_device_name=_as_optional_str(payload.get("torch_device_name")),
        requested_onnx_provider=_as_optional_str(payload.get("requested_onnx_provider")),
        audio_chunk_count=int(payload.get("audio_chunk_count") or 0),
        segment_count=int(payload.get("segment_count") or 0),
        max_chunk_gap_ms=int(payload.get("max_chunk_gap_ms") or 0),
        metrics=metrics,
    )


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
