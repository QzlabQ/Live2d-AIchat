from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.admin_session import (
    AdminReplyTraceResponse,
    AdminReplyTraceSummaryResponse,
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
        reply_traces=[
            AdminReplyTraceResponse(
                reply_id=item.reply_id,
                created_at=item.created_at,
                streaming=item.streaming,
                chat_mode=item.chat_mode,
                tts_engine=item.tts_engine,
                tts_stream_profile=item.tts_stream_profile,
                prompt_cache_hit=item.prompt_cache_hit,
                prompt_cache_build_ms=item.prompt_cache_build_ms,
                torch_cuda_available=item.torch_cuda_available,
                torch_device_name=item.torch_device_name,
                requested_onnx_provider=item.requested_onnx_provider,
                tts_cosyvoice_fp16=item.tts_cosyvoice_fp16,
                tts_cosyvoice_load_jit=item.tts_cosyvoice_load_jit,
                tts_ar_backend=item.tts_ar_backend,
                tts_flow_backend=item.tts_flow_backend,
                audio_chunk_count=item.audio_chunk_count,
                segment_count=item.segment_count,
                max_chunk_gap_ms=item.max_chunk_gap_ms,
                metrics=item.metrics,
                tts_chunks=item.tts_chunks,
            )
            for item in detail.reply_traces
        ],
        reply_trace_summary=AdminReplyTraceSummaryResponse(
            trace_count=detail.reply_trace_summary.trace_count,
            latest_created_at=detail.reply_trace_summary.latest_created_at,
            avg_metrics=detail.reply_trace_summary.avg_metrics,
            max_metrics=detail.reply_trace_summary.max_metrics,
        ),
    )
