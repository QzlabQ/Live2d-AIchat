from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AdminSessionSummaryResponse(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    last_message_preview: str


class AdminSessionListResponse(BaseModel):
    items: list[AdminSessionSummaryResponse]


class AdminSessionMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    emotion: str | None = None
    latency_ms: int | None = None


class AdminReplyTraceResponse(BaseModel):
    reply_id: str
    created_at: datetime
    streaming: bool
    chat_mode: str
    tts_engine: str
    tts_stream_profile: str | None = None
    prompt_cache_hit: bool | None = None
    prompt_cache_build_ms: float | None = None
    torch_cuda_available: bool | None = None
    torch_device_name: str | None = None
    requested_onnx_provider: str | None = None
    audio_chunk_count: int
    segment_count: int
    max_chunk_gap_ms: int
    metrics: dict[str, int]
    tts_chunks: list[dict[str, object]]


class AdminReplyTraceSummaryResponse(BaseModel):
    trace_count: int
    latest_created_at: datetime | None = None
    avg_metrics: dict[str, float]
    max_metrics: dict[str, int]


class AdminSessionDetailResponse(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    device_type: str
    interest_tags: list[str]
    message_count: int
    items: list[AdminSessionMessageResponse]
    reply_traces: list[AdminReplyTraceResponse]
    reply_trace_summary: AdminReplyTraceSummaryResponse
