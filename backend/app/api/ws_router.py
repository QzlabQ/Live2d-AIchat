from __future__ import annotations

import asyncio
import base64
import logging
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
from app.services.rag import get_rag_service
from app.services.tts import TTSService, get_tts_service

logger = logging.getLogger(__name__)
websocket_router = APIRouter()


@dataclass(slots=True)
class ClientCapabilities:
    tts_streaming: bool = False
    audio_format: str = "audio/wav"


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


async def send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})


async def get_avatar_config(session) -> AvatarConfig:
    result = await session.execute(select(AvatarConfig).limit(1))
    avatar = result.scalar_one_or_none()
    if avatar is None:
        raise RuntimeError("Avatar configuration has not been initialized.")
    return avatar


async def save_message(
    db_session,
    session_id: str,
    role: str,
    content: str,
    emotion: str | None = None,
    latency_ms: int | None = None,
) -> None:
    db_session.add(
        Message(
            session_id=session_id,
            role=role,
            content=content,
            emotion=emotion,
            latency_ms=latency_ms,
        )
    )
    await db_session.commit()


def resolve_client_capabilities(payload: dict[str, object]) -> ClientCapabilities:
    return ClientCapabilities(
        tts_streaming=bool(payload.get("tts_streaming")),
        audio_format=str(payload.get("audio_format", "audio/wav")).strip().lower() or "audio/wav",
    )


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
) -> ReplyExecutionResult:
    send_lock = asyncio.Lock()
    segment_queue: asyncio.Queue[str | None] = asyncio.Queue()
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

    async def send_json(payload: dict[str, object]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    def elapsed_ms() -> int:
        return int((perf_counter() - started_at) * 1000)

    def mark_metric(name: str) -> None:
        at_ms = elapsed_ms()
        trace.mark(name, at_ms)
        if name not in metrics:
            metrics[name] = trace.metrics[name]

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
        mark_metric("llm_stream_start_ms")
        async for event in chat_service.stream_reply(
            content,
            persona=avatar.persona,
            query_text=query_text,
            history=history,
        ):
            if event.kind == "text_delta":
                mark_metric("llm_first_delta_ms")
                await send_json({"type": "text_delta", "content": event.content})
                continue

            if event.kind == "tts_segment":
                mark_metric("tts_first_segment_ms")
                trace.segment_count += 1
                await segment_queue.put(event.content)
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

    async def consume_tts() -> None:
        seq = 0
        while True:
            segment = await segment_queue.get()
            if segment is None:
                break

            if use_streaming_audio:
                async for tts_chunk in tts_service.stream_synthesize_segment(
                    segment,
                    seq=seq,
                    voice_id=avatar.voice_id,
                    emotion=locked_emotion,
                    reference_audio_path=avatar.tts_reference_audio_path,
                    reference_text=avatar.tts_reference_text,
                    speed=avatar.tts_speed,
                    tts_emotion_enabled=avatar.tts_emotion_enabled,
                ):
                    if tts_chunk.audio_bytes:
                        mark_metric("tts_first_audio_chunk_ms")
                        chunk_sent_at_ms = elapsed_ms()
                        if trace.audio_chunk_count == 0:
                            await send_avatar_phase("speaking", "first_audio_chunk")
                        trace.observe_audio_chunk(chunk_sent_at_ms)
                        send_started_at = perf_counter()
                        await send_json(
                            {
                                "type": "tts_audio_chunk",
                                "reply_id": reply_id,
                                "segment_id": seq,
                                "chunk_index": tts_chunk.chunk_index,
                                "sample_rate": tts_chunk.sample_rate,
                                "channels": tts_chunk.channels,
                                "encoding": tts_chunk.encoding,
                                "data": base64.b64encode(tts_chunk.audio_bytes).decode("utf-8"),
                                "is_final": tts_chunk.is_final,
                            }
                        )
                        logger.info(
                            "tts_ws_chunk seq=%s idx=%s model_chunk_ready_ms=%s ws_chunk_sent_ms=%s chunk_send_lag_ms=%s",
                            seq,
                            tts_chunk.chunk_index,
                            tts_chunk.model_chunk_ready_ms,
                            int((perf_counter() - started_at) * 1000),
                            int((perf_counter() - send_started_at) * 1000),
                        )
                    if tts_chunk.phonemes:
                        await send_json(
                            {
                                "type": "tts_viseme_chunk",
                                "reply_id": reply_id,
                                "segment_id": seq,
                                "chunk_index": tts_chunk.chunk_index,
                                "offset_ms": tts_chunk.offset_ms,
                                "frames": tts_chunk.phonemes,
                            }
                        )
            else:
                tts_chunk = await tts_service.synthesize_chunk(
                    segment,
                    seq=seq,
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
                            "seq": seq,
                        }
                    )
                if tts_chunk.phonemes:
                    await send_json({"type": "phonemes", "seq": seq, "data": tts_chunk.phonemes})
            seq += 1

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
) -> None:
    chat_service = get_chat_service()
    tts_service = get_tts_service()
    started_at = perf_counter()

    await save_message(db_session, session_id=session_id, role="user", content=content)
    avatar = await get_avatar_config(db_session)
    history = await load_recent_history(db_session, session_id=session_id, limit=6)
    query_text = content
    continued_clarification = False

    active_state = await get_active_clarification_state(db_session, session_id=session_id)
    if active_state is not None:
        resolution = await get_rag_service().clarification_resolver.resolve(
            original_question=active_state.original_question,
            assistant_followup_question=active_state.assistant_followup_question,
            user_reply=content,
        )
        if resolution.continues_clarification:
            continued_clarification = True
            query_text = resolution.resolved_question
            if history and history[-1]["role"] == "user":
                history[-1]["content"] = query_text
        else:
            await cancel_pending_clarification_state(db_session, session_id=session_id)

    locked = get_emotion_analyzer().analyze_quick(user_text=content)
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
    result = await stream_assistant_reply(
        websocket=websocket,
        session_id=session_id,
        avatar=avatar,
        content=content,
        query_text=query_text,
        history=history,
        chat_service=chat_service,
        tts_service=tts_service,
        capabilities=capabilities,
        reply_id=reply_id,
        locked_emotion=locked.label,
        emotion_payload=emotion_payload,
        started_at=started_at,
    )

    if continued_clarification:
        await resolve_pending_clarification_state(db_session, session_id=session_id)

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
    audio_buffer: bytearray,
    capabilities: ClientCapabilities,
) -> None:
    if not audio_buffer:
        await send_error(websocket, "ASR_FAILED", "未接收到可识别的音频数据。")
        return

    transcript = await get_asr_service().transcribe_pcm16(bytes(audio_buffer))
    audio_buffer.clear()
    if not transcript:
        await send_error(websocket, "ASR_FAILED", "语音识别未返回有效文本。")
        return

    await websocket.send_json({"type": "asr_result", "content": transcript})
    await process_text_message(websocket, db_session, session_id, transcript, capabilities)


@websocket_router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    audio_buffer = bytearray()
    capabilities = ClientCapabilities()

    try:
        async with AsyncSessionFactory() as db_session:
            session_obj = await db_session.get(Session, session_id)
            if session_obj is None:
                await send_error(websocket, "SESSION_NOT_FOUND", "会话不存在，请先创建会话。")
                await websocket.close(code=4404)
                return

            while True:
                payload = await websocket.receive_json()
                message_type = payload.get("type")

                if message_type == "hello":
                    capabilities = resolve_client_capabilities(payload)
                    continue

                if message_type == "text":
                    content = str(payload.get("content", "")).strip()
                    if not content:
                        await send_error(websocket, "EMPTY_TEXT", "文本消息不能为空。")
                        continue
                    await process_text_message(websocket, db_session, session_id, content, capabilities)
                    continue

                if message_type == "audio_chunk":
                    encoded = payload.get("data")
                    if not isinstance(encoded, str):
                        await send_error(websocket, "INVALID_AUDIO", "音频块必须为 base64 字符串。")
                        continue

                    try:
                        audio_buffer.extend(base64.b64decode(encoded))
                    except Exception:
                        await send_error(websocket, "INVALID_AUDIO", "音频块 base64 解码失败。")
                        continue

                    if bool(payload.get("is_final")):
                        await process_audio_buffer(websocket, db_session, session_id, audio_buffer, capabilities)
                    continue

                if message_type == "audio_end":
                    await process_audio_buffer(websocket, db_session, session_id, audio_buffer, capabilities)
                    continue

                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                await send_error(websocket, "UNSUPPORTED_MESSAGE", f"不支持的消息类型: {message_type}")
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await send_error(websocket, "INTERNAL_ERROR", str(exc))
        await websocket.close(code=1011)
