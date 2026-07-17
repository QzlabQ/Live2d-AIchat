from __future__ import annotations

import asyncio
import base64
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db.models import AvatarConfig, Message, Session
from app.db.session import AsyncSessionFactory
from app.services.asr import get_asr_service
from app.services.chat import ReplyStreamEvent, get_chat_service
from app.services.conversation_state import (
    cancel_pending_clarification_state,
    get_active_clarification_state,
    load_recent_history,
    resolve_pending_clarification_state,
    upsert_clarification_state,
)
from app.services.emotion import EmotionAnalysis, get_emotion_analyzer
from app.services.avatar_trace import ReplyTrace, get_avatar_trace_service
from app.services.knowledge_gaps import record_knowledge_gap, should_record_knowledge_gap
from app.services.rag import get_rag_service
from app.services.tts import TTSService, get_tts_service
from app.services.visitor_sessions import save_session_message
from app.services.vision import VisitorVisionError, get_visitor_vision_service

logger = logging.getLogger(__name__)
websocket_router = APIRouter()
DEFAULT_PHOTO_QUESTION = "请帮我看看这张图片。"


@dataclass(slots=True)
class ClientCapabilities:
    tts_streaming: bool = False
    audio_format: str = "audio/wav"


@dataclass(slots=True)
class QueuedTTSSegment:
    seq: int
    text: str


@dataclass(slots=True)
class ReplyExecutionResult:
    text: str
    sources: list[object] = field(default_factory=list)
    confidence: float = 0.0
    mode: str = "template"
    emotion: EmotionAnalysis | None = None
    metrics: dict[str, int] = field(default_factory=dict)
    reply_kind: str = "answer"
    needs_followup: bool = False
    followup_question: str = ""
    missing_slots: list[str] = field(default_factory=list)
    confidence_note: str = "confirmed"


async def send_json_payload(
    websocket: WebSocket,
    payload: dict[str, object],
    send_lock: asyncio.Lock | None = None,
) -> None:
    if send_lock is None:
        await websocket.send_json(payload)
        return

    async with send_lock:
        await websocket.send_json(payload)


async def send_error(
    websocket: WebSocket,
    code: str,
    message: str,
    send_lock: asyncio.Lock | None = None,
) -> None:
    await send_json_payload(
        websocket,
        {"type": "error", "code": code, "message": message},
        send_lock,
    )


async def get_avatar_config(session) -> AvatarConfig:
    result = await session.execute(
        select(AvatarConfig)
        .where(AvatarConfig.is_active.is_(True))
        .order_by(AvatarConfig.updated_at.desc(), AvatarConfig.id.desc())
        .limit(1)
    )
    avatar = result.scalar_one_or_none()
    if avatar is None:
        avatar = (
            await session.execute(select(AvatarConfig).order_by(AvatarConfig.id.asc()).limit(1))
        ).scalar_one_or_none()
    if avatar is None:
        raise RuntimeError("Avatar configuration has not been initialized.")
    return avatar


async def save_message(
    db_session,
    session_id: str,
    role: str,
    content: str,
    attachments: list[dict[str, object]] | None = None,
    emotion: str | None = None,
    latency_ms: int | None = None,
) -> None:
    await save_session_message(
        db_session,
        session_id=session_id,
        role=role,
        content=content,
        attachments=attachments,
        emotion=emotion,
        latency_ms=latency_ms,
    )


def resolve_client_capabilities(payload: dict[str, object]) -> ClientCapabilities:
    return ClientCapabilities(
        tts_streaming=bool(payload.get("tts_streaming")),
        audio_format=str(payload.get("audio_format", "audio/wav")).strip().lower() or "audio/wav",
    )


def normalize_message_text(content: object) -> str:
    return " ".join(str(content or "").strip().split())


def normalize_photo_attachments(raw_attachments: object) -> list[dict[str, str]]:
    if raw_attachments is None:
        return []
    if not isinstance(raw_attachments, list):
        raise ValueError("attachments must be a list.")
    if len(raw_attachments) > 1:
        raise ValueError("Only one photo attachment is supported.")

    attachments: list[dict[str, str]] = []
    for raw in raw_attachments:
        if not isinstance(raw, dict):
            raise ValueError("attachments items must be objects.")
        kind = str(raw.get("kind", "")).strip().lower()
        if kind != "photo":
            raise ValueError("Only photo attachments are supported.")
        stored_image_path = str(raw.get("stored_image_path", "")).strip()
        filename = str(raw.get("filename", "")).strip()
        mime_type = str(raw.get("mime_type", "")).strip().lower()
        if not stored_image_path or not filename or not mime_type:
            raise ValueError("photo attachment is missing required fields.")
        attachments.append(
            {
                "kind": "photo",
                "stored_image_path": stored_image_path,
                "filename": filename,
                "mime_type": mime_type,
            }
        )
    return attachments


def enrich_photo_attachments(
    attachments: list[dict[str, str]],
    photo_context: dict[str, object],
) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for attachment in attachments:
        if attachment.get("kind") != "photo":
            enriched.append(dict(attachment))
            continue
        enriched.append(
            {
                **attachment,
                "recognized_spot": photo_context.get("recognized_spot", ""),
                "recognition_summary": photo_context.get("recognition_summary", ""),
            }
        )
    return enriched


def build_photo_query_text(user_text: str, photo_context: dict[str, str]) -> str:
    has_canonical_spot = bool(photo_context.get("recognized_spot_canonical"))
    spot_label = "图片标准景点名" if has_canonical_spot else "图片识别名称"
    parts = [
        f"{spot_label}：{str(photo_context.get('recognized_spot', '')).strip()}",
        f"图片识别摘要：{photo_context.get('recognition_summary', '').strip()}",
        f"用户问题：{user_text}",
    ]
    return "\n".join(part for part in parts if part and not part.endswith("："))


def build_source_excerpt(text: str, limit: int = 140) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def serialize_reply_meta(
    *,
    reply_id: str,
    reply_kind: str,
    needs_followup: bool,
    missing_slots: list[str],
    confidence_note: str,
) -> dict[str, object]:
    return {
        "type": "reply_meta",
        "reply_id": reply_id,
        "reply_kind": reply_kind,
        "needs_followup": needs_followup,
        "missing_slots": missing_slots,
        "confidence_note": confidence_note,
    }


def serialize_sources(sources: list[object], mode: str, reply_id: str) -> dict[str, object] | None:
    if not sources:
        return None
    return {
        "type": "sources",
        "reply_id": reply_id,
        "mode": mode,
        "items": [
            {
                "filename": item.filename,
                "title": item.title,
                "category": item.category,
                "chunk_index": item.chunk_index,
                "retrieval_score": item.retrieval_score,
                "rerank_score": item.rerank_score,
                "excerpt": build_source_excerpt(getattr(item, "text", "")),
            }
            for item in sources
        ],
    }


async def stream_assistant_reply(
    *,
    websocket: WebSocket,
    session_id: str,
    avatar,
    content: str,
    query_text: str,
    history: list[dict[str, str]],
    chat_service,
    tts_service: TTSService,
    capabilities: ClientCapabilities,
    reply_id: str,
    locked_emotion: str,
    emotion_payload: dict[str, object],
    started_at: float,
    initial_metrics: dict[str, int] | None = None,
    send_lock: asyncio.Lock | None = None,
    photo_context: dict[str, str] | None = None,
) -> ReplyExecutionResult:
    segment_queue: asyncio.Queue[QueuedTTSSegment | None] = asyncio.Queue()
    result = ReplyExecutionResult(text="")
    use_streaming_audio = (
        capabilities.tts_streaming
        and capabilities.audio_format == "pcm16le"
        and getattr(getattr(tts_service, "settings", None), "tts_engine", "cosyvoice") == "cosyvoice"
    )
    metrics: dict[str, int] = {}
    trace = ReplyTrace(
        reply_id=reply_id,
        session_id=session_id,
        streaming=use_streaming_audio,
        chat_mode=str(getattr(getattr(chat_service, "settings", None), "chat_mode", "unknown")),
        tts_engine=str(getattr(getattr(tts_service, "settings", None), "tts_engine", "unknown")),
    )
    runtime_snapshot_getter = getattr(tts_service, "get_runtime_trace_snapshot", None)
    if callable(runtime_snapshot_getter):
        trace.set_runtime_snapshot(runtime_snapshot_getter())
    if initial_metrics:
        for name, at_ms in initial_metrics.items():
            trace.mark(name, at_ms)
            metrics[name] = trace.metrics[name]

    async def send_json(payload: dict[str, object]) -> None:
        await send_json_payload(websocket, payload, send_lock)

    def elapsed_ms() -> int:
        return int((perf_counter() - started_at) * 1000)

    def mark_metric(name: str) -> None:
        at_ms = elapsed_ms()
        trace.mark(name, at_ms)
        if name not in metrics:
            metrics[name] = trace.metrics[name]

    def set_stage_metric(name: str, value_ms: int) -> None:
        trace.set_metric(name, value_ms)
        metrics[name] = int(value_ms)

    async def send_avatar_phase(phase: str, reason: str) -> None:
        at_ms = elapsed_ms()
        trace.mark(f"avatar_phase_{phase}_ms", at_ms)
        metrics[f"avatar_phase_{phase}_ms"] = trace.metrics[f"avatar_phase_{phase}_ms"]
        await send_json(
            {
                "type": "avatar_phase",
                "reply_id": reply_id,
                "phase": phase,
                "at_ms": at_ms,
                "reason": reason,
            }
        )

    async def produce_text() -> None:
        next_segment_seq = 0
        mark_metric("llm_stream_start_ms")
        stream_kwargs = {
            "query_text": query_text,
            "history": history,
        }
        if photo_context is not None:
            stream_kwargs["photo_context"] = photo_context
        async for event in chat_service.stream_reply(
            content,
            persona=avatar.persona,
            response_language=avatar.response_language,
            **stream_kwargs,
        ):
            if event.kind == "text_delta":
                mark_metric("llm_first_delta_ms")
                await send_json({"type": "text_delta", "content": event.content})
                continue

            if event.kind == "tts_segment":
                mark_metric("tts_first_segment_ms")
                trace.segment_count += 1
                await segment_queue.put(QueuedTTSSegment(seq=next_segment_seq, text=event.content))
                next_segment_seq += 1
                continue

            if event.kind == "metrics":
                for metric_name, metric_value in event.metrics.items():
                    set_stage_metric(metric_name, metric_value)
                continue

            if event.kind == "final":
                result.text = event.text
                result.sources = event.sources
                result.confidence = event.confidence
                result.mode = event.mode
                result.reply_kind = event.reply_kind
                result.needs_followup = event.needs_followup
                result.followup_question = event.followup_question
                result.missing_slots = list(event.missing_slots)
                result.confidence_note = event.confidence_note

        await segment_queue.put(None)
        if result.text:
            try:
                result.emotion = await chat_service.analyze_emotion(content, result.text)
            except Exception:
                result.emotion = EmotionAnalysis(
                    label=locked_emotion,
                    confidence=float(emotion_payload.get("confidence", 0.45)),
                    keywords=list(emotion_payload.get("keywords", [])),
                    reason=str(emotion_payload.get("reason", "")),
                    source=str(emotion_payload.get("source", "heuristic")),
                )
            await send_json(
                {
                    "type": "emotion",
                    "stage": "final",
                    "value": result.emotion.label,
                    "confidence": result.emotion.confidence,
                    "keywords": result.emotion.keywords,
                    "reason": result.emotion.reason,
                    "source": result.emotion.source,
                }
            )
        mark_metric("text_done_ms")
        await send_json(
            serialize_reply_meta(
                reply_id=reply_id,
                reply_kind=result.reply_kind,
                needs_followup=result.needs_followup,
                missing_slots=result.missing_slots,
                confidence_note=result.confidence_note,
            )
        )
        sources_payload = serialize_sources(result.sources, result.mode, reply_id)
        if sources_payload is not None:
            await send_json(sources_payload)
        if use_streaming_audio:
            await send_json({"type": "text_done", "reply_id": reply_id})

    async def emit_streaming_tts_chunk(tts_chunk) -> None:
        if trace.prompt_cache_hit is None or trace.prompt_cache_build_ms is None:
            trace.set_prompt_cache_snapshot(
                hit=getattr(tts_chunk, "prompt_cache_hit", None),
                build_ms=getattr(tts_chunk, "prompt_cache_build_ms", None),
            )
        if tts_chunk.audio_bytes:
            mark_metric("tts_first_audio_chunk_ms")
            chunk_sent_at_ms = elapsed_ms()
            if trace.audio_chunk_count == 0:
                await send_avatar_phase("speaking", "first_audio_chunk")
            send_started_at = perf_counter()
            await send_json(
                {
                    "type": "tts_audio_chunk",
                    "reply_id": reply_id,
                    "segment_id": tts_chunk.seq,
                    "chunk_index": tts_chunk.chunk_index,
                    "sample_rate": tts_chunk.sample_rate,
                    "channels": tts_chunk.channels,
                    "encoding": tts_chunk.encoding,
                    "data": base64.b64encode(tts_chunk.audio_bytes).decode("utf-8"),
                    "is_final": tts_chunk.is_final,
                }
            )
            send_lag_ms = int((perf_counter() - send_started_at) * 1000)
            audio_duration_ms = int(
                len(tts_chunk.audio_bytes)
                / max(int(tts_chunk.sample_rate) * int(tts_chunk.channels) * 2, 1)
                * 1000
            )
            trace.observe_tts_chunk(
                seq=tts_chunk.seq,
                chunk_index=tts_chunk.chunk_index,
                sent_at_ms=chunk_sent_at_ms,
                audio_duration_ms=audio_duration_ms,
                model_ready_ms=tts_chunk.model_chunk_ready_ms,
                send_lag_ms=send_lag_ms,
                token_wait_ms=getattr(tts_chunk, "token_wait_ms", 0),
                token2wav_ms=getattr(tts_chunk, "token2wav_ms", 0),
                hop_len=getattr(tts_chunk, "hop_len", 0),
                token_offset=getattr(tts_chunk, "token_offset", 0),
                is_final=getattr(tts_chunk, "is_final", False),
                llm_done_ms=getattr(tts_chunk, "tts_llm_done_ms", None),
                final_decode_enter_ms=getattr(tts_chunk, "tts_final_decode_enter_ms", None),
                prefetch_enabled=getattr(tts_chunk, "tts_prefetch_enabled", None),
                prefetch_started_count_delta=getattr(
                    tts_chunk, "tts_prefetch_started_count_delta", 0
                ),
                prefetch_hit_count_delta=getattr(tts_chunk, "tts_prefetch_hit_count_delta", 0),
            )
            logger.info(
                "tts_ws_chunk seq=%s idx=%s model_chunk_ready_ms=%s ws_chunk_sent_ms=%s chunk_send_lag_ms=%s",
                tts_chunk.seq,
                tts_chunk.chunk_index,
                tts_chunk.model_chunk_ready_ms,
                int((perf_counter() - started_at) * 1000),
                send_lag_ms,
            )
        if tts_chunk.phonemes:
            await send_json(
                {
                    "type": "tts_viseme_chunk",
                    "reply_id": reply_id,
                    "segment_id": tts_chunk.seq,
                    "chunk_index": tts_chunk.chunk_index,
                    "offset_ms": tts_chunk.offset_ms,
                    "frames": tts_chunk.phonemes,
                }
            )

    async def iter_segment_inputs():
        while True:
            segment = await segment_queue.get()
            if segment is None:
                break
            yield segment.seq, segment.text

    async def consume_tts() -> None:
        if use_streaming_audio and getattr(tts_service, "supports_reply_streaming", False):
            async for tts_chunk in tts_service.stream_synthesize_reply(
                iter_segment_inputs(),
                voice_id=avatar.voice_id,
                emotion=locked_emotion,
                reference_audio_path=avatar.tts_reference_audio_path,
                reference_text=avatar.tts_reference_text,
                speed=avatar.tts_speed,
                tts_emotion_enabled=avatar.tts_emotion_enabled,
            ):
                await emit_streaming_tts_chunk(tts_chunk)
        else:
            while True:
                segment = await segment_queue.get()
                if segment is None:
                    break

                if use_streaming_audio:
                    async for tts_chunk in tts_service.stream_synthesize_segment(
                        segment.text,
                        seq=segment.seq,
                        voice_id=avatar.voice_id,
                        emotion=locked_emotion,
                        reference_audio_path=avatar.tts_reference_audio_path,
                        reference_text=avatar.tts_reference_text,
                        speed=avatar.tts_speed,
                        tts_emotion_enabled=avatar.tts_emotion_enabled,
                    ):
                        await emit_streaming_tts_chunk(tts_chunk)
                else:
                    tts_chunk = await tts_service.synthesize_chunk(
                        segment.text,
                        seq=segment.seq,
                        voice_id=avatar.voice_id,
                        emotion=locked_emotion,
                        reference_audio_path=avatar.tts_reference_audio_path,
                        reference_text=avatar.tts_reference_text,
                        speed=avatar.tts_speed,
                        tts_emotion_enabled=avatar.tts_emotion_enabled,
                    )
                    if tts_chunk.audio_bytes:
                        mark_metric("tts_first_audio_chunk_ms")
                        chunk_sent_at_ms = elapsed_ms()
                        if trace.audio_chunk_count == 0:
                            await send_avatar_phase("speaking", "first_audio_chunk")
                        trace.observe_audio_chunk(chunk_sent_at_ms)
                        await send_json(
                            {
                                "type": "audio",
                                "data": base64.b64encode(tts_chunk.audio_bytes).decode("utf-8"),
                                "mime_type": tts_chunk.mime_type,
                                "seq": segment.seq,
                            }
                        )
                    if tts_chunk.phonemes:
                        await send_json({"type": "phonemes", "seq": segment.seq, "data": tts_chunk.phonemes})

        mark_metric("audio_done_ms")
        await send_avatar_phase("cooldown", "audio_done")
        if use_streaming_audio:
            await send_json({"type": "audio_done", "reply_id": reply_id})

    producer_task: asyncio.Task[None] | None = None
    consumer_task: asyncio.Task[None] | None = None

    try:
        await send_avatar_phase("thinking", "reply_started")
        await send_json(emotion_payload)
        producer_task = asyncio.create_task(produce_text())
        consumer_task = asyncio.create_task(consume_tts())
        await producer_task
        await consumer_task
        await send_avatar_phase("idle", "reply_done")
        result.metrics = metrics
        await send_json({"type": "done", "session_id": session_id})
        return result
    except asyncio.CancelledError:
        for task in (producer_task, consumer_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (producer_task, consumer_task) if task is not None),
            return_exceptions=True,
        )
        raise
    except Exception:
        for task in (producer_task, consumer_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (producer_task, consumer_task) if task is not None),
            return_exceptions=True,
        )
        raise
    finally:
        result.metrics = metrics
        get_avatar_trace_service().enqueue_trace(trace)


async def process_text_message(
    websocket: WebSocket,
    db_session,
    session_id: str,
    content: str,
    capabilities: ClientCapabilities,
    *,
    attachments: list[dict[str, str]] | None = None,
    started_at: float | None = None,
    initial_metrics: dict[str, int] | None = None,
    send_lock: asyncio.Lock | None = None,
) -> None:
    chat_service = get_chat_service()
    tts_service = get_tts_service()
    started_at = started_at or perf_counter()
    reply_context_started_at = perf_counter()
    initial_metrics_payload = dict(initial_metrics or {})
    normalized_attachments = normalize_photo_attachments(attachments)
    visible_content = normalize_message_text(content)
    if normalized_attachments and not visible_content:
        visible_content = DEFAULT_PHOTO_QUESTION

    avatar = await get_avatar_config(db_session)
    history = await load_recent_history(db_session, session_id=session_id, limit=6)
    query_text = visible_content
    continued_clarification = False
    cancel_existing_clarification = False
    clarification_resolve_ms = 0
    photo_recognition_ms = 0

    active_state = await get_active_clarification_state(db_session, session_id=session_id)
    if active_state is not None:
        clarification_started_at = perf_counter()
        resolution = await get_rag_service().clarification_resolver.resolve(
            original_question=active_state.original_question,
            assistant_followup_question=active_state.assistant_followup_question,
            user_reply=visible_content,
        )
        clarification_resolve_ms = int((perf_counter() - clarification_started_at) * 1000)
        if resolution.continues_clarification:
            continued_clarification = True
            query_text = resolution.resolved_question
            if history and history[-1]["role"] == "user":
                history[-1]["content"] = query_text
        else:
            cancel_existing_clarification = True

    photo_context: dict[str, str] | None = None
    stored_attachments: list[dict[str, str]] = list(normalized_attachments)
    if stored_attachments:
        session_obj = None
        get_session = getattr(db_session, "get", None)
        if callable(get_session):
            session_obj = await get_session(Session, session_id)
        interest_tags = list(getattr(session_obj, "interest_tags", []))
        photo_recognition_started_at = perf_counter()
        recognition = await get_visitor_vision_service().recognize_stored_photo(
            session_id=session_id,
            stored_image_path=stored_attachments[0]["stored_image_path"],
            interest_tags=interest_tags,
            user_prompt=visible_content,
        )
        photo_recognition_ms = int((perf_counter() - photo_recognition_started_at) * 1000)
        photo_context = {
            "recognized_spot": recognition.recognized_spot,
            "recognition_summary": recognition.recognition_summary,
            "stored_image_path": recognition.stored_image_path,
            "recognized_spot_canonical": recognition.is_canonical_spot,
        }
        stored_attachments = enrich_photo_attachments(stored_attachments, photo_context)
        query_text = build_photo_query_text(query_text, photo_context)

    locked = get_emotion_analyzer().analyze_quick(user_text=visible_content)
    reply_id = f"{session_id}-{int(started_at * 1000)}"
    emotion_payload = {
        "type": "emotion",
        "stage": "preview",
        "value": locked.label,
        "confidence": locked.confidence,
        "keywords": locked.keywords,
        "reason": locked.reason,
        "source": locked.source,
    }
    initial_metrics_payload["clarification_resolve_ms"] = clarification_resolve_ms
    initial_metrics_payload["photo_recognition_ms"] = photo_recognition_ms
    initial_metrics_payload["reply_context_prepare_ms"] = int(
        (perf_counter() - reply_context_started_at) * 1000
    )
    result = await stream_assistant_reply(
        websocket=websocket,
        session_id=session_id,
        avatar=avatar,
        content=visible_content,
        query_text=query_text,
        photo_context=photo_context,
        history=history,
        chat_service=chat_service,
        tts_service=tts_service,
        capabilities=capabilities,
        reply_id=reply_id,
        locked_emotion=locked.label,
        emotion_payload=emotion_payload,
        initial_metrics=initial_metrics_payload,
        started_at=started_at,
        send_lock=send_lock,
    )

    if cancel_existing_clarification:
        await cancel_pending_clarification_state(db_session, session_id=session_id)
    elif continued_clarification:
        await resolve_pending_clarification_state(db_session, session_id=session_id)

    await save_message(
        db_session,
        session_id=session_id,
        role="user",
        content=visible_content,
        attachments=stored_attachments,
    )
    if result.needs_followup and result.followup_question:
        await upsert_clarification_state(
            db_session,
            session_id=session_id,
            original_question=query_text,
            assistant_followup_question=result.followup_question,
            missing_slots=result.missing_slots,
            provisional_answer=result.text,
            used_source_indexes=list(range(1, len(result.sources) + 1)),
        )

    latency_ms = int((perf_counter() - started_at) * 1000)
    await save_message(
        db_session,
        session_id=session_id,
        role="assistant",
        content=result.text,
        emotion=result.emotion.label if result.emotion else locked.label,
        latency_ms=latency_ms,
    )
    if should_record_knowledge_gap(
        mode=result.mode,
        query_text=query_text,
        reply_kind=result.reply_kind,
        confidence_note=result.confidence_note,
        confidence=result.confidence,
        source_count=len(result.sources),
        needs_followup=result.needs_followup,
    ):
        try:
            await record_knowledge_gap(
                db_session,
                session_id=session_id,
                user_question=visible_content,
                query_text=query_text,
                assistant_reply=result.text,
                reply_kind=result.reply_kind,
                confidence_note=result.confidence_note,
                confidence=result.confidence,
                sources=result.sources,
            )
        except Exception:
            logger.exception("Failed to record knowledge gap for session=%s query=%s", session_id, query_text)
    logger.info(
        "reply_metrics session=%s streaming=%s %s",
        session_id,
        capabilities.tts_streaming,
        result.metrics,
    )


async def process_audio_buffer(
    websocket: WebSocket,
    db_session,
    session_id: str,
    audio_data: bytes,
    capabilities: ClientCapabilities,
    *,
    send_lock: asyncio.Lock | None = None,
) -> None:
    if not audio_data:
        await send_error(websocket, "ASR_FAILED", "未接收到可识别的音频数据。", send_lock)
        return

    started_at = perf_counter()
    asr_result = await get_asr_service().transcribe_with_metrics(audio_data)
    transcript = asr_result.text
    if not transcript:
        await send_error(websocket, "ASR_FAILED", "语音识别未返回有效文本。", send_lock)
        return

    await send_json_payload(websocket, {"type": "asr_result", "content": transcript}, send_lock)
    await process_text_message(
        websocket,
        db_session,
        session_id,
        transcript,
        capabilities,
        started_at=started_at,
        initial_metrics={
            "asr_model_load_ms": asr_result.model_load_ms,
            "asr_transcribe_ms": asr_result.asr_transcribe_ms,
            "asr_total_ms": asr_result.asr_total_ms,
        },
        send_lock=send_lock,
    )


@websocket_router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    audio_buffer = bytearray()
    capabilities = ClientCapabilities()
    send_lock = asyncio.Lock()
    active_reply_task: asyncio.Task[None] | None = None

    try:
        async with AsyncSessionFactory() as db_session:
            session_obj = await db_session.get(Session, session_id)
            if session_obj is None:
                await send_error(
                    websocket,
                    "SESSION_NOT_FOUND",
                    "会话不存在，请先创建会话。",
                    send_lock,
                )
                await websocket.close(code=4404)
                return

            def has_active_reply() -> bool:
                return active_reply_task is not None and not active_reply_task.done()

            def clear_active_reply(task: asyncio.Task[None]) -> None:
                nonlocal active_reply_task
                if active_reply_task is task:
                    active_reply_task = None

            async def start_reply_task(task_coro) -> None:
                nonlocal active_reply_task

                async def runner() -> None:
                    try:
                        await task_coro
                    except asyncio.CancelledError:
                        raise
                    except VisitorVisionError as exc:
                        await send_error(websocket, "PHOTO_RECOGNITION_FAILED", str(exc), send_lock)
                    except Exception as exc:
                        logger.exception("Reply task failed for session=%s", session_id)
                        await send_error(websocket, "INTERNAL_ERROR", str(exc), send_lock)

                active_reply_task = asyncio.create_task(runner())
                active_reply_task.add_done_callback(clear_active_reply)

            async def cancel_active_reply(reason: str = "client_cancelled") -> None:
                nonlocal active_reply_task
                had_active_reply = has_active_reply()
                audio_buffer.clear()
                if had_active_reply and active_reply_task is not None:
                    active_reply_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await active_reply_task
                active_reply_task = None
                await send_json_payload(
                    websocket,
                    {
                        "type": "reply_cancelled",
                        "session_id": session_id,
                        "had_active_reply": had_active_reply,
                        "reason": reason,
                    },
                    send_lock,
                )

            while True:
                payload = await websocket.receive_json()
                message_type = payload.get("type")

                if message_type == "hello":
                    capabilities = resolve_client_capabilities(payload)
                    continue

                if message_type == "text":
                    if has_active_reply():
                        await send_error(
                            websocket,
                            "REPLY_IN_PROGRESS",
                            "当前回复仍在生成，请先停止当前回答或等待完成。",
                            send_lock,
                        )
                        continue
                    try:
                        attachments = normalize_photo_attachments(payload.get("attachments"))
                    except ValueError as exc:
                        await send_error(websocket, "INVALID_ATTACHMENTS", str(exc), send_lock)
                        continue
                    content = normalize_message_text(payload.get("content", ""))
                    if not content and not attachments:
                        await send_error(websocket, "EMPTY_TEXT", "文本消息不能为空。", send_lock)
                        continue
                    await start_reply_task(
                        process_text_message(
                            websocket,
                            db_session,
                            session_id,
                            content,
                            capabilities,
                            attachments=attachments,
                            send_lock=send_lock,
                        )
                    )
                    continue

                if message_type == "audio_chunk":
                    if has_active_reply():
                        await send_error(
                            websocket,
                            "REPLY_IN_PROGRESS",
                            "当前回复仍在生成，请先停止当前回答或等待完成。",
                            send_lock,
                        )
                        continue
                    encoded = payload.get("data")
                    if not isinstance(encoded, str):
                        await send_error(
                            websocket,
                            "INVALID_AUDIO",
                            "音频块必须为 base64 字符串。",
                            send_lock,
                        )
                        continue

                    try:
                        audio_buffer.extend(base64.b64decode(encoded))
                    except Exception:
                        await send_error(
                            websocket,
                            "INVALID_AUDIO",
                            "音频块 base64 解码失败。",
                            send_lock,
                        )
                        continue

                    if bool(payload.get("is_final")):
                        audio_data = bytes(audio_buffer)
                        audio_buffer.clear()
                        await start_reply_task(
                            process_audio_buffer(
                                websocket,
                                db_session,
                                session_id,
                                audio_data,
                                capabilities,
                                send_lock=send_lock,
                            )
                        )
                    continue

                if message_type == "audio_end":
                    if has_active_reply():
                        await send_error(
                            websocket,
                            "REPLY_IN_PROGRESS",
                            "当前回复仍在生成，请先停止当前回答或等待完成。",
                            send_lock,
                        )
                        continue
                    audio_data = bytes(audio_buffer)
                    audio_buffer.clear()
                    await start_reply_task(
                        process_audio_buffer(
                            websocket,
                            db_session,
                            session_id,
                            audio_data,
                            capabilities,
                            send_lock=send_lock,
                        )
                    )
                    continue

                if message_type == "ping":
                    await send_json_payload(websocket, {"type": "pong"}, send_lock)
                    continue

                if message_type == "cancel_reply":
                    await cancel_active_reply()
                    continue

                await send_error(
                    websocket,
                    "UNSUPPORTED_MESSAGE",
                    f"不支持的消息类型: {message_type}",
                    send_lock,
                )
    except WebSocketDisconnect:
        if active_reply_task is not None and not active_reply_task.done():
            active_reply_task.cancel()
            await asyncio.gather(active_reply_task, return_exceptions=True)
        return
    except Exception as exc:
        if active_reply_task is not None and not active_reply_task.done():
            active_reply_task.cancel()
            await asyncio.gather(active_reply_task, return_exceptions=True)
        await send_error(websocket, "INTERNAL_ERROR", str(exc), send_lock)
        await websocket.close(code=1011)
